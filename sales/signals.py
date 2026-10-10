# sales/signals.py
"""
আগে এখানে তিনটা signal ছিল যেগুলো টাকার হিসাব নষ্ট করত:
- SaleItem save হলেই sale.save() → প্রতিটা item এ account balance এ paid_amount আবার যোগ হত
- Sale এর paid_amount বাড়লেই আরেকটা Transaction তৈরি হত (MoneyReceipt এর Transaction এর পাশাপাশি)
  → একই টাকা account এ দুইবার

এখন টাকা জমা হয় শুধু Sale.receive_payment() → MoneyReceipt → Transaction পথে।
এখানে শুধু item মুছে গেলে sale এর total আবার হিসাব হয়।
"""
import logging

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Sale, SaleItem

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=SaleItem)
def recalculate_sale_totals_on_item_delete(sender, instance, **kwargs):
    try:
        sale = Sale.objects.filter(pk=instance.sale_id).first()
        if sale:
            sale.calculate_totals()
    except Exception:
        logger.exception("Failed to recalculate totals after item delete")
