"""services — Lógica de facturación del CRM."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.currency import round_money
from apps.core.exceptions import BusinessRuleError
from apps.crm.models import (
    Invoice,
    InvoiceItem,
    InvoicePayment,
    Product,
    StockAdjustment,
)
from apps.notifications.models import Notification
from apps.transactions.services import register_transaction

# Estados de factura en los que la mercancía ya salió de inventario.
GOODS_OUT_STATUSES = {"enviada", "parcial", "pagada", "vencida"}


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
