"""Backfill de la equivalencia congelada en pagos existentes.

Los pagos creados antes de esta versión no guardaban la moneda efectiva, el
monto recibido ni la tasa BCV congelada. Se reconstruyen a partir de la
operación (``Transaction``) enlazada: su ``moneda``/``monto``/``tasa_usd``
reflejan el movimiento real del día. Si no hay operación, se asume misma moneda
que el documento con tasa 1 (caso límite sin datos históricos).
"""

from django.db import migrations


def _method_for(currency: str) -> str:
    return "efectivo_ves" if currency == "VES" else "efectivo_usd"


def _backfill(payment, document_currency, Transaction):
    tx = None
    if payment.transaction_id:
        tx = Transaction.objects.filter(pk=payment.transaction_id).first()
    if tx is not None:
        paid_currency = tx.moneda
        paid_amount = tx.monto
        rate_usd = tx.tasa_usd
    else:
        paid_currency = document_currency
        paid_amount = payment.amount
        rate_usd = 1
    payment.paid_currency = paid_currency
    payment.paid_amount = paid_amount
    payment.rate_usd = rate_usd
    payment.payment_method = _method_for(paid_currency)
    payment.save(
        update_fields=["paid_currency", "paid_amount", "rate_usd", "payment_method"]
    )


def forwards(apps, schema_editor):
    Invoice = apps.get_model("crm", "Invoice")
    InvoicePayment = apps.get_model("crm", "InvoicePayment")
    Order = apps.get_model("crm", "Order")
    OrderPayment = apps.get_model("crm", "OrderPayment")
    Transaction = apps.get_model("transactions", "Transaction")

    invoice_currency = {i.id: i.currency for i in Invoice.objects.all()}
    for payment in InvoicePayment.objects.all():
        _backfill(payment, invoice_currency.get(payment.invoice_id, "USD"), Transaction)

    order_currency = {o.id: o.currency for o in Order.objects.all()}
    for payment in OrderPayment.objects.all():
        _backfill(payment, order_currency.get(payment.order_id, "USD"), Transaction)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0012_alter_invoicepayment_options_and_more"),
        ("transactions", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
