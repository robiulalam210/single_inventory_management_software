# purchases/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Purchase, PurchaseItem

@receiver(post_save, sender=Purchase)
def update_supplier_on_purchase_save(sender, instance, **kwargs):
    """Update supplier totals when purchase is saved"""
    try:
        if instance.supplier and hasattr(instance.supplier, 'update_purchase_totals'):
            print(f"🔄 Signal: Updating supplier '{instance.supplier.name}' after purchase save")
            instance.supplier.update_purchase_totals()
    except Exception as e:
        print(f"ERROR:Error updating supplier on purchase save: {e}")

@receiver(post_delete, sender=Purchase)
def update_supplier_on_purchase_delete(sender, instance, **kwargs):
    """Update supplier totals when purchase is deleted"""
    try:
        if instance.supplier and hasattr(instance.supplier, 'update_purchase_totals'):
            print(f"🔄 Signal: Updating supplier '{instance.supplier.name}' after purchase delete")
            instance.supplier.update_purchase_totals()
    except Exception as e:
        print(f"ERROR:Error updating supplier on purchase delete: {e}")