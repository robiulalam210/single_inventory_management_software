"""ব্যাচ / মেয়াদ হিসাব (FEFO)।

ক্রয়  -> PurchaseItem save/delete হলে ProductBatch তৈরি/আপডেট/মোছা
বিক্রি -> SaleItem তৈরি হলে allocate_for_sale_item (FEFO), মুছলে restore_for_sale_item
সব ফাংশন সেফ: ব্যাচ না থাকলেও (যেমন ওপেনিং স্টক) মূল স্টকের কাজ আটকায় না।
"""
import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)
ZERO = Decimal('0')


def _dec(v):
    return Decimal(str(v or 0))


def sync_for_purchase_item(item):
    """PurchaseItem save হওয়ার পর ব্যাচ তৈরি বা আপডেট করে।"""
    from .models import ProductBatch
    qty = _dec(item.qty)
    batch = ProductBatch.objects.filter(purchase_item=item).first()
    if batch is None:
        return ProductBatch.objects.create(
            product_id=item.product_id, purchase_item=item,
            batch_no=item.batch_no, expiry_date=item.expiry_date,
            qty_received=qty, qty_remaining=qty,
            received_at=getattr(item, 'date_created', None) or timezone.now(),
        )
    # qty বদলালে বাকি স্টকও সেই পরিমাণ বাড়ে/কমে (০ এর নিচে নয়)
    delta = qty - _dec(batch.qty_received)
    batch.qty_received = qty
    batch.qty_remaining = max(ZERO, _dec(batch.qty_remaining) + delta)
    batch.batch_no = item.batch_no
    batch.expiry_date = item.expiry_date
    batch.save()
    return batch


def remove_for_purchase_item(item):
    """PurchaseItem মোছার আগে তার ব্যাচ মুছে দেয়।"""
    from .models import ProductBatch
    ProductBatch.objects.filter(purchase_item=item).delete()


def void_for_purchase(purchase):
    """Purchase বাতিল হলে তার সব ব্যাচের বাকি স্টক ০।"""
    from .models import ProductBatch
    ProductBatch.objects.filter(purchase_item__purchase=purchase).update(qty_remaining=ZERO)


@transaction.atomic
def allocate_for_sale_item(sale_item):
    """বিক্রিত পরিমাণ FEFO নিয়মে ব্যাচ থেকে কমায় এবং কোথা থেকে কতটা গেল লিখে রাখে।"""
    from .models import ProductBatch
    from sales.models import SaleItemBatch

    need = _dec(sale_item.base_quantity)
    if need <= 0:
        return
    batches = (ProductBatch.objects.select_for_update()
               .filter(product_id=sale_item.product_id, qty_remaining__gt=0))
    # মেয়াদ আছে এমন আগে (কাছের মেয়াদ প্রথমে), মেয়াদহীন সবার শেষে
    batches = sorted(batches, key=lambda b: (b.expiry_date is None, b.expiry_date or timezone.now().date(),
                                             b.received_at, b.pk))
    for b in batches:
        if need <= 0:
            break
        take = min(need, _dec(b.qty_remaining))
        b.qty_remaining = _dec(b.qty_remaining) - take
        b.save(update_fields=['qty_remaining'])
        SaleItemBatch.objects.create(sale_item=sale_item, batch=b, qty=take)
        need -= take


@transaction.atomic
def restore_for_sale_item(sale_item):
    """SaleItem মুছলে যেখান থেকে কমেছিল ঠিক সেই ব্যাচে ফেরত দেয়।"""
    from sales.models import SaleItemBatch

    for alloc in SaleItemBatch.objects.select_for_update().filter(sale_item=sale_item):
        if alloc.batch_id:
            b = alloc.batch
            b.qty_remaining = _dec(b.qty_remaining) + _dec(alloc.qty)
            b.save(update_fields=['qty_remaining'])
        alloc.delete()