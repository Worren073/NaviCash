"""services — Lógica de facturación del CRM."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.currency import round_money
from apps.core.exceptions import BusinessRuleError
from apps.crm.models import (
    Invoice,
    InvoiceItem,
    InvoicePayment,
    Order,
    OrderItem,
    OrderPayment,
    Product,
    StockAdjustment,
)
from apps.notifications.models import Notification
from apps.transactions.services import register_transaction

# Estados de factura en los que la mercancía ya salió de inventario.
GOODS_OUT_STATUSES = {"enviada", "parcial", "pagada", "vencida"}

# Unidades cuyas cantidades deben ser enteras (sin decimales) en todo el
# flujo: existencias, ajustes y líneas de factura.
INTEGER_UNITS = frozenset({"unidad"})


def requires_integer_amounts(unit: str) -> bool:
    """True si la unidad de medida exige cantidades enteras."""
    return unit in INTEGER_UNITS


def _pick_unit_price(product: Product, contact) -> Decimal:
    """Precio de venta a usar para un cliente al armar la factura.

    Los clientes mayoristas usan ``wholesale_price`` cuando el producto lo
    tiene; el resto usa ``unit_price``.
    """
    if contact.customer_type == "mayorista" and product.wholesale_price is not None:
        return product.wholesale_price
    return product.unit_price


def _next_invoice_number(business) -> str:
    """Genera el siguiente número de factura dentro de un negocio.

    Formato: ``F-00001``, ``F-00002``, etc. En el improbable caso de una
    colisión (concurrent writes) la restricción única de BD lo detecta y el
    llamador puede reintentar.
    """
    count = Invoice.objects.filter(business=business).count()
    return f"F-{count + 1:05d}"


def _compute_item_total(quantity: Decimal, unit_price: Decimal, discount: Decimal) -> Decimal:
    return round_money(quantity * unit_price - discount)


def _item_cost_price(row: dict, *, fallback_unit_price: bool = False) -> "Decimal | None":
    """Costo de compra congelado de una línea de factura o pedido.

    - Producto del catálogo: se toma ``Product.cost_price`` (si lo tiene).
    - Producto nuevo (pedidos): se toma el ``cost_price`` declarado o, en su
      defecto, el ``unit_price`` de la línea (mismo criterio que el alta del
      producto en ``_resolve_new_product``).
    - Línea sin producto (solo facturas) y sin ``fallback_unit_price``: sin
      costo congelado (``None``).
    """
    product = row.get("product")
    if product is not None:
        return getattr(product, "cost_price", None)
    new_product = row.get("new_product") or {}
    raw_cost = new_product.get("cost_price")
    if raw_cost:
        try:
            return Decimal(str(raw_cost))
        except (ValueError, TypeError, ArithmeticError):
            return None
    return row.get("unit_price") if fallback_unit_price else None


def _derive_status(amount_paid: Decimal, total: Decimal) -> str:
    if amount_paid <= 0:
        return "enviada"
    if amount_paid >= total:
        return "pagada"
    return "parcial"


def _withdraw_stock(invoice: Invoice) -> None:
    """Descuenta existencias de los productos de una factura.

    Bloquea las filas con ``select_for_update`` para evitar carreras y rechaza
    la operación si alguna línea supera el stock disponible. Registra cada
    movimiento en ``StockAdjustment``.
    """
    lines = list(invoice.items.filter(product__isnull=False).select_related("product"))
    if not lines:
        return
    product_ids = [line.product_id for line in lines]
    products = {
        p.id: p
        for p in Product.objects.select_for_update().filter(id__in=product_ids)
    }
    for line in lines:
        product = products[line.product_id]
        if line.quantity > product.stock_quantity:
            raise BusinessRuleError(
                f"Stock insuficiente de «{product.name}»: quedan {product.stock_quantity}."
            )
    for line in lines:
        product = products[line.product_id]
        product.stock_quantity = round_money(product.stock_quantity - line.quantity)
        product.save(update_fields=["stock_quantity", "updated_at"])
        StockAdjustment.objects.create(
            user=invoice.user,
            product=product,
            delta=-line.quantity,
            reason=f"Factura {invoice.number}",
        )


def _restore_stock(invoice: Invoice) -> None:
    """Republica existencias de una factura que ya no está en curso."""
    for line in invoice.items.filter(product__isnull=False).select_related("product"):
        product = line.product
        product.stock_quantity = round_money(product.stock_quantity + line.quantity)
        product.save(update_fields=["stock_quantity", "updated_at"])
        StockAdjustment.objects.create(
            user=invoice.user,
            product=product,
            delta=line.quantity,
            reason=f"Anulación {invoice.number}",
        )


@transaction.atomic
def create_invoice(
    user,
    business,
    contact,
    items_data: list[dict],
    *,
    issue_date: date | None = None,
    due_date: date | None = None,
    tax_amount: Decimal | None = None,
    paid_amount: Decimal | None = None,
    notes: str = "",
) -> Invoice:
    """Crea una factura con sus líneas y registra el pago inicial si aplica.

    Args:
        user: dueño de la factura.
        business: negocio al que pertenece.
        contact: cliente/proveedor (BusinessContact) del negocio.
        items_data: lista de dicts con ``description``, ``quantity``,
            ``unit_price`` y opcional ``discount``.
        issue_date: fecha de emisión (por defecto hoy).
        due_date: fecha de vencimiento (por defecto hoy + días de crédito del contacto).
        tax_amount: impuesto manual (por defecto 0).
        paid_amount: monto pagado al crear la factura (0 = crédito, >= total = contado).
        notes: notas libres.

    Returns:
        La factura creada.

    Raises:
        BusinessRuleError: si no hay líneas, montos inválidos o el pago inicial
            excede el total.
    """
    if not items_data:
        raise BusinessRuleError("La factura debe tener al menos una línea.")

    issue_date = issue_date or timezone.localdate()
    if due_date is None:
        days = contact.payment_terms_days or 0
        due_date = issue_date + timedelta(days=days)

    tax_amount = round_money(tax_amount or Decimal("0"))
    paid_amount = round_money(paid_amount or Decimal("0"))

    subtotal = Decimal("0")
    prepared_items = []
    for row in items_data:
        quantity = Decimal(str(row.get("quantity", 1)))
        unit_price = Decimal(str(row.get("unit_price", 0)))
        discount = Decimal(str(row.get("discount", 0)))
        if quantity <= 0 or unit_price < 0:
            raise BusinessRuleError("Cantidad y precio unitario deben ser positivos.")
        total = _compute_item_total(quantity, unit_price, discount)
        if total < 0:
            raise BusinessRuleError("El total de una línea no puede ser negativo.")
        subtotal += total
        prepared_items.append(
            {
                "product": row.get("product"),
                "description": row.get("description", ""),
                "quantity": quantity,
                "unit_price": unit_price,
                "cost_price": _item_cost_price(row),
                "discount": discount,
                "total": total,
            }
        )

    subtotal = round_money(subtotal)
    total = round_money(subtotal + tax_amount)

    if paid_amount < 0 or paid_amount > total:
        raise BusinessRuleError("El monto pagado inicial no puede ser negativo ni mayor al total.")

    status = _derive_status(paid_amount, total)

    invoice = Invoice.objects.create(
        user=user,
        business=business,
        contact=contact,
        number=_next_invoice_number(business),
        issue_date=issue_date,
        due_date=due_date,
        status=status,
        subtotal=subtotal,
        tax_amount=tax_amount,
        total=total,
        amount_paid=paid_amount,
        balance_due=round_money(total - paid_amount),
        currency=business.currency,
        notes=notes,
    )

    for row in prepared_items:
        InvoiceItem.objects.create(
            user=user,
            invoice=invoice,
            product=row.get("product"),
            description=row["description"],
            quantity=row["quantity"],
            unit_price=row["unit_price"],
            cost_price=row["cost_price"],
            discount=row["discount"],
            total=row["total"],
        )

    _withdraw_stock(invoice)

    if paid_amount > 0:
        tx = register_transaction(
            user,
            tipo="cobro",
            monto=paid_amount,
            moneda=invoice.currency,
            concepto=f"Pago factura {invoice.number}",
            wallet=business.wallet,
            estado="pagado",
            fecha=issue_date,
            origen="crm_invoice",
        )
        InvoicePayment.objects.create(
            user=user,
            invoice=invoice,
            transaction=tx,
            amount=paid_amount,
            note="Pago al emitir",
        )

    return invoice


@transaction.atomic
def record_invoice_payment(
    invoice: Invoice,
    amount: Decimal,
    *,
    note: str = "",
    paid_at=None,
) -> InvoicePayment:
    """Registra un pago contra una factura, crea el cobro y actualiza saldos.

    Args:
        invoice: factura a pagar.
        amount: monto del pago (en la moneda de la factura).
        note: nota opcional.
        paid_at: instante del pago (por defecto ahora).

    Returns:
        El registro de pago creado.

    Raises:
        BusinessRuleError: si la factura está anulada/pagada o el pago excede
            el saldo pendiente.
    """
    amount = round_money(amount)
    if amount <= 0:
        raise BusinessRuleError("El monto del pago debe ser mayor a cero.")
    if invoice.status == "anulada":
        raise BusinessRuleError("No se puede pagar una factura anulada.")
    if invoice.status == "pagada":
        raise BusinessRuleError("La factura ya está pagada.")
    if amount > invoice.balance_due:
        raise BusinessRuleError("El pago no puede superar el saldo pendiente.")

    tx = register_transaction(
        invoice.user,
        tipo="cobro",
        monto=amount,
        moneda=invoice.currency,
        concepto=f"Pago factura {invoice.number}",
        wallet=invoice.business.wallet,
        estado="pagado",
        fecha=paid_at.date() if paid_at else timezone.localdate(),
        origen="crm_invoice",
    )

    payment = InvoicePayment.objects.create(
        user=invoice.user,
        invoice=invoice,
        transaction=tx,
        amount=amount,
        note=note,
    )

    invoice.amount_paid = round_money(invoice.amount_paid + amount)
    invoice.balance_due = round_money(invoice.total - invoice.amount_paid)
    invoice.status = _derive_status(invoice.amount_paid, invoice.total)
    invoice.save(update_fields=["amount_paid", "balance_due", "status", "updated_at"])

    # Aviso al usuario (kind invoice_paid) con extra único por pago, deduplicado
    # por la restricción (user, scope, kind, extra) de Notification.
    if invoice.status == "pagada":
        title = f"¡Factura {invoice.number} pagada!"
        message = f"{invoice.contact.name} saldó los {invoice.total} {invoice.currency}."
    else:
        title = f"Pago recibido de factura {invoice.number}"
        message = (
            f"{invoice.contact.name} pagó {payment.amount} {invoice.currency}; "
            f"restan {invoice.balance_due}."
        )
    Notification.objects.create(
        user=invoice.user,
        kind="invoice_paid",
        scope="business",
        title=title,
        message=message,
        extra={
            "invoice_id": str(invoice.id),
            "payment_id": str(payment.id),
        },
    )

    return payment


@transaction.atomic
def send_invoice(invoice: Invoice) -> Invoice:
    """Cambia una factura de borrador a enviada y descuenta stock."""
    if invoice.status != "borrador":
        raise BusinessRuleError("Solo las facturas en borrador pueden enviarse.")
    invoice.status = "enviada"
    invoice.save(update_fields=["status", "updated_at"])
    _withdraw_stock(invoice)
    return invoice


@transaction.atomic
def cancel_invoice(invoice: Invoice) -> Invoice:
    """Anula una factura.

    No revierte pagos ya registrados; simplemente congela el documento y
    repone las existencias si la mercancía ya había salido.
    """
    if invoice.status == "anulada":
        raise BusinessRuleError("La factura ya está anulada.")
    was_out = invoice.status in GOODS_OUT_STATUSES
    invoice.status = "anulada"
    invoice.save(update_fields=["status", "updated_at"])
    if was_out:
        _restore_stock(invoice)
    return invoice


@transaction.atomic
def refresh_invoice_overdue_status(invoice: Invoice, today: date | None = None) -> Invoice:
    """Marca una factura como vencida si corresponde.

    Se invoca desde el generador de notificaciones; no genera notificaciones
    por sí sola.
    """
    today = today or timezone.localdate()
    if invoice.status in ("enviada", "parcial") and invoice.due_date < today:
        invoice.status = "vencida"
        invoice.save(update_fields=["status", "updated_at"])
    return invoice


def _next_order_number(business) -> str:
    """Genera el siguiente número de pedido dentro de un negocio.

    Formato: ``PO-00001``, ``PO-00002``, etc. Las colisiones concurrentes las
    detecta la restricción única de BD y el llamador puede reintentar.
    """
    count = Order.objects.filter(business=business).count()
    return f"PO-{count + 1:05d}"


def _order_status_for_paid(amount_paid: Decimal) -> str:
    """Fase inicial de un pedido según el pago realizado al crearlo.

    El pago es ortogonal a la fase: cualquier pago inicial saca el pedido de
    borrador a «en camino»; sin pago queda en borrador (la píldora de pago es
    independiente, ver ``OrderReadSerializer.payment_state``).
    """
    return "en_camino" if amount_paid > 0 else "borrador"


def _parse_new_product(data: dict) -> dict:
    """Valida y normaliza el payload de un producto nuevo del pedido.

    Los montos viajan como strings dentro del ``JSONField`` para evitar la
    conversión imprecisa de la serialización JSON.
    """
    name = str(data.get("name", "")).strip()
    if not name:
        raise BusinessRuleError("El producto nuevo debe tener nombre.")
    unit = str(data.get("unit", "unidad") or "unidad")
    if unit not in ("unidad", "kg"):
        raise BusinessRuleError("Unidad de medida inválida para el producto nuevo.")
    normalized = {
        "name": name,
        "sku": str(data.get("sku", "")).strip(),
        "description": str(data.get("description", "")).strip(),
        "unit": unit,
        "is_active": bool(data.get("is_active", True)),
    }
    for field in ("unit_price", "wholesale_price", "cost_price", "low_stock_threshold"):
        raw = data.get(field)
        if raw is None or raw == "":
            normalized[field] = None
            continue
        try:
            value = Decimal(str(raw))
        except (ValueError, TypeError, ArithmeticError):
            raise BusinessRuleError(f"El campo «{field}» del producto nuevo no es válido.")
        if value < 0:
            raise BusinessRuleError(
                f"El campo «{field}» del producto nuevo no puede ser negativo."
            )
        normalized[field] = str(value)
    if normalized["unit_price"] is None:
        raise BusinessRuleError("El producto nuevo debe indicar un precio de venta.")
    category = data.get("category")
    normalized["category"] = str(category) if category else None
    return normalized


def _find_existing_product(business, name: str, sku: str) -> Product | None:
    """Busca por SKU o por nombre (sin importar mayúsculas) dentro del negocio."""
    if sku:
        product = Product.objects.filter(business=business, sku=sku).first()
        if product is not None:
            return product
    return Product.objects.filter(business=business, name__iexact=name).first()


def _resolve_new_product(order: Order, line: OrderItem) -> Product:
    """Enlaza la línea al producto ya existente o crea el producto nuevo.

    Si el producto ya existe (mismo SKU o nombre) solo se enlaza la línea y el
    stock se acumula; nunca se duplica ni se modifican sus datos.
    """
    data = _parse_new_product(line.new_product or {})
    existing = _find_existing_product(order.business, data["name"], data["sku"])
    if existing is not None:
        if line.product_id is None:
            line.product = existing
            line.save(update_fields=["product", "updated_at"])
        return existing
    try:
        product = Product.objects.create(
            user=order.user,
            business=order.business,
            name=data["name"],
            sku=data["sku"],
            description=data["description"],
            unit=data["unit"],
            unit_price=Decimal(data["unit_price"]),
            wholesale_price=(
                Decimal(data["wholesale_price"]) if data.get("wholesale_price") else None
            ),
            cost_price=(
                Decimal(data["cost_price"]) if data.get("cost_price") else line.unit_price
            ),
            category_id=data.get("category"),
            supplier=order.contact,
            low_stock_threshold=(
                Decimal(data["low_stock_threshold"])
                if data.get("low_stock_threshold")
                else None
            ),
            is_active=data["is_active"],
            stock_quantity=Decimal("0"),
        )
    except IntegrityError:
        existing = _find_existing_product(order.business, data["name"], data["sku"])
        if existing is None:
            raise BusinessRuleError(
                "No se pudo crear el producto nuevo: el nombre o código ya está en uso."
            )
        product = existing
    if line.product_id is None:
        line.product = product
        line.save(update_fields=["product", "updated_at"])
    return product


def _restock(order: Order) -> None:
    """Integra la mercancía de un pedido al inventario (recibo único).

    Los productos existentes suman existencias (sin tocar sus datos); los
    productos nuevos se crean y se enlazan. Cada movimiento queda auditado en
    ``StockAdjustment``.
    """
    lines = list(order.items.select_related("product"))
    if not lines:
        return
    product_ids = [line.product_id for line in lines if line.product_id]
    locked = {
        p.id: p
        for p in Product.objects.select_for_update().filter(id__in=product_ids)
    }
    for line in lines:
        if line.product_id:
            product = locked[line.product_id]
        else:
            product = _resolve_new_product(order, line)
        product.stock_quantity = round_money(product.stock_quantity + line.quantity)
        product.save(update_fields=["stock_quantity", "updated_at"])
        StockAdjustment.objects.create(
            user=order.user,
            product=product,
            delta=line.quantity,
            reason=f"Pedido {order.number}",
        )


@transaction.atomic
def create_order(
    user,
    business,
    contact,
    items_data: list[dict],
    *,
    order_date: date | None = None,
    due_date: date | None = None,
    shipping_amount: Decimal | None = None,
    paid_amount: Decimal | None = None,
    notes: str = "",
) -> Order:
    """Crea un pedido con sus líneas y registra el pago inicial si aplica.

    Args:
        user: dueño del pedido.
        business: negocio al que pertenece.
        contact: proveedor (BusinessContact) del negocio.
        items_data: lista de dicts con ``description``, ``quantity``,
            ``unit_price``, opcional ``discount`` y, en excluyente mutuo, un
            ``product`` existente o un ``new_product`` con los datos del alta.
        order_date: fecha del pedido (por defecto hoy).
        due_date: fecha prevista de pago (por defecto hoy + días de crédito
            del proveedor).
        shipping_amount: costo de envío que se suma al subtotal (por defecto 0).
        paid_amount: monto pagado al crear el pedido (0 = solo borrador).
        notes: notas libres.

    Returns:
        El pedido creado.

    Raises:
        BusinessRuleError: si no hay líneas, montos inválidos o el pago inicial
            excede el total.
    """
    if not items_data:
        raise BusinessRuleError("El pedido debe tener al menos una línea.")

    order_date = order_date or timezone.localdate()
    if due_date is None:
        days = contact.payment_terms_days or 0
        due_date = order_date + timedelta(days=days)
    shipping_amount = round_money(shipping_amount or Decimal("0"))
    paid_amount = round_money(paid_amount or Decimal("0"))

    subtotal = Decimal("0")
    prepared_items = []
    for row in items_data:
        quantity = Decimal(str(row.get("quantity", 1)))
        unit_price = Decimal(str(row.get("unit_price", 0)))
        discount = Decimal(str(row.get("discount", 0)))
        if quantity <= 0 or unit_price < 0:
            raise BusinessRuleError("Cantidad y precio unitario deben ser positivos.")
        total = _compute_item_total(quantity, unit_price, discount)
        if total < 0:
            raise BusinessRuleError("El total de una línea no puede ser negativo.")
        subtotal += total
        new_product = row.get("new_product") or {}
        if new_product and row.get("product") is not None:
            raise BusinessRuleError(
                "Indica un producto del inventario o un producto nuevo, no ambos."
            )
        prepared_items.append(
            {
                "product": row.get("product"),
                "new_product": _parse_new_product(new_product) if new_product else {},
                "description": row.get("description", ""),
                "quantity": quantity,
                "unit_price": unit_price,
                "cost_price": _item_cost_price(row, fallback_unit_price=True),
                "discount": discount,
                "total": total,
            }
        )

    subtotal = round_money(subtotal)
    total = round_money(subtotal + shipping_amount)

    if paid_amount < 0 or paid_amount > total:
        raise BusinessRuleError("El monto pagado inicial no puede ser negativo ni mayor al total.")

    order = Order.objects.create(
        user=user,
        business=business,
        contact=contact,
        number=_next_order_number(business),
        order_date=order_date,
        due_date=due_date,
        status=_order_status_for_paid(paid_amount),
        subtotal=subtotal,
        shipping_amount=shipping_amount,
        total=total,
        amount_paid=paid_amount,
        balance_due=round_money(total - paid_amount),
        currency=business.currency,
        notes=notes,
    )

    for row in prepared_items:
        OrderItem.objects.create(
            user=user,
            order=order,
            product=row["product"],
            new_product=row["new_product"],
            description=row["description"],
            quantity=row["quantity"],
            unit_price=row["unit_price"],
            cost_price=row["cost_price"],
            discount=row["discount"],
            total=row["total"],
        )

    if paid_amount > 0:
        tx = register_transaction(
            user,
            tipo="pago",
            monto=paid_amount,
            moneda=order.currency,
            concepto=f"Pago pedido {order.number}",
            wallet=business.wallet,
            estado="pagado",
            fecha=order_date,
            origen="crm_order",
        )
        OrderPayment.objects.create(
            user=user,
            order=order,
            transaction=tx,
            amount=paid_amount,
            note="Pago al crear",
        )

    return order


@transaction.atomic
def record_order_payment(
    order: Order,
    amount: Decimal,
    *,
    note: str = "",
    paid_at=None,
) -> OrderPayment:
    """Registra un pago contra un pedido, crea la salida y actualiza saldos.

    Args:
        order: pedido a pagar.
        amount: monto del pago (en la moneda del pedido).
        note: nota opcional.
        paid_at: instante del pago (por defecto ahora).

    Returns:
        El registro de pago creado.

    Raises:
        BusinessRuleError: si el pedido está anulado/pagado o el pago excede el
            saldo pendiente.
    """
    amount = round_money(amount)
    if amount <= 0:
        raise BusinessRuleError("El monto del pago debe ser mayor a cero.")
    if order.status == "anulado":
        raise BusinessRuleError("No se puede pagar un pedido anulado.")
    if order.balance_due <= 0:
        raise BusinessRuleError("El pedido ya está pagado.")
    if amount > order.balance_due:
        raise BusinessRuleError("El pago no puede superar el saldo pendiente.")

    tx = register_transaction(
        order.user,
        tipo="pago",
        monto=amount,
        moneda=order.currency,
        concepto=f"Pago pedido {order.number}",
        wallet=order.business.wallet,
        estado="pagado",
        fecha=paid_at.date() if paid_at else timezone.localdate(),
        origen="crm_order",
    )

    payment = OrderPayment.objects.create(
        user=order.user,
        order=order,
        transaction=tx,
        amount=amount,
        note=note,
    )

    order.amount_paid = round_money(order.amount_paid + amount)
    order.balance_due = round_money(order.total - order.amount_paid)
    order.save(update_fields=["amount_paid", "balance_due", "updated_at"])

    is_paid = order.balance_due <= 0
    if is_paid:
        title = f"¡Pedido {order.number} pagado!"
        message = f"Saldo pagado a {order.contact.name}: {order.total} {order.currency}."
    else:
        title = f"Pago registrado de pedido {order.number}"
        message = (
            f"Pagaste {payment.amount} {order.currency} a {order.contact.name}; "
            f"restan {order.balance_due}."
        )
    Notification.objects.create(
        user=order.user,
        kind="order_paid",
        scope="business",
        title=title,
        message=message,
        extra={
            "order_id": str(order.id),
            "payment_id": str(payment.id),
        },
    )

    return payment


@transaction.atomic
def send_order(order: Order) -> Order:
    """Cambia un pedido de borrador a en camino."""
    if order.status != "borrador":
        raise BusinessRuleError("Solo los pedidos en borrador pueden enviarse.")
    order.status = "en_camino"
    order.save(update_fields=["status", "updated_at"])
    return order


@transaction.atomic
def receive_order(order: Order) -> Order:
    """Marca el pedido como recibido e integra la mercancía al inventario.

    La integración ocurre una sola vez: tras recibir el pedido queda congelado
    y no puede volver a recibirse.
    """
    if order.status in ("recibido", "anulado"):
        raise BusinessRuleError("Este pedido ya fue recibido o anulado.")
    _restock(order)
    order.status = "recibido"
    order.received_at = timezone.now()
    order.save(update_fields=["status", "received_at", "updated_at"])
    return order


@transaction.atomic
def cancel_order(order: Order) -> Order:
    """Anula un pedido no recibido.

    No revierte pagos ya registrados; simplemente congela el documento. Al no
    haberse recibido, no hubo integración de stock que reponer.
    """
    if order.status in ("recibido", "anulado"):
        raise BusinessRuleError("Solo los pedidos no recibidos pueden anularse.")
    order.status = "anulado"
    order.save(update_fields=["status", "updated_at"])
    return order
