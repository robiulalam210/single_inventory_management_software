from django.db.models.signals import post_save
from django.dispatch import receiver
from products.models import Product
from returns.models import SalesReturn, PurchaseReturn, BadStock, SalesReturnItem



@receiver(post_save, sender=SalesReturn)
def create_badstock_from_sales_return(sender, instance, created, **kwargs):
    """
    When a SalesReturn is created, automatically add each returned product
    to bad stock and optionally restore it to available stock.
    """
    if not created:
        return

    # Loop through all returned items
    for item in instance.items.all():
        if item.quantity > 0:
            product = Product.objects.filter(id=item.product_id).first()
            if not product:
                continue

            # SUCCESS: Create a BadStock record
            BadStock.objects.create(
                product=product,
                quantity=item.quantity,
                reason=f"Sales Return (Invoice {instance.invoice_no})"
            )

            # SUCCESS: Optional: restore returned stock to available inventory
            product.stock += item.quantity
            product.save()


@receiver(post_save, sender=PurchaseReturn)

@receiver(post_save, sender=PurchaseReturn)
def create_badstock_from_purchase_return(sender, instance, created, **kwargs):
    """
    When a PurchaseReturn is created, add each returned product to BadStock
    and decrease product stock_qty.
    """
    if not created:
        return

    for item in instance.items.all():
        product = item.product_ref
        if item.qty > 0:
            # Create BadStock record
            BadStock.objects.create(
                product=product,
                qty=item.qty,
                reason=f"Purchase Return",
                date=instance.date.date()
            )

            # Decrease product stock
            product.stock_qty -= item.qty
            product.save()