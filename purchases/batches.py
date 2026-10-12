"""
ব্যাচ / মেয়াদ ট্র্যাকিং — বিক্রির সময় FEFO কমানো, আর মেয়াদ-শেষ সতর্কতার হিসাব।

নিয়ম
• বিক্রিতে আগে কমে সেই ব্যাচ, যার মেয়াদ সবচেয়ে আগে শেষ হবে (FEFO) — কিন্তু মেয়াদ-পেরোনো ব্যাচ সবার শেষে:
  পেরোনো মাল বিক্রি না করে বাতিল (write-off) করাই উচিত।
  ক্রম: ① মেয়াদ আছে ও পেরোয়নি (আগে শেষ যেটা) → ② মেয়াদ দেওয়া নেই → ③ মেয়াদ পেরিয়েছে।
• ব্যাচ ছাড়া স্টক (আগে কেনা বা মেয়াদ না দেওয়া মাল) থাকলে ব্যাচ ফুরোলে বাকিটা সেখান থেকে যায়।
• Product.stock_qty ই আসল স্টক। Sales return / Purchase return / Bad stock ব্যাচ ছোঁয় না, তাই রিপোর্টে
  ব্যাচের যোগফল stock_qty র বেশি হলে বাড়তিটা সবচেয়ে দেরির মেয়াদের ব্যাচ থেকে ছাঁটা হয় — যাতে জরুরি
  সতর্কতা কখনো লুকিয়ে না যায়।
"""
from datetime import date
from decimal import Decimal, ROUND_CEILING

from django.db import transaction
from django.utils import timezone

from .models import ProductBatch

ZERO = Decimal('0')


def _order_key(batch, today):
    if batch.expiry_date is None:
        group, when = 1, date.max
    elif batch.expiry_date < today:
        group, when = 2, batch.expiry_date
    else:
        group, when = 0, batch.expiry_date
    return (group, when, batch.id)


@transaction.atomic
def allocate_for_sale_item(sale_item):
    """নতুন SaleItem এর base_quantity ব্যাচ থেকে FEFO তে কমায়, আর কোথা থেকে কত গেল তা লিখে রাখে।"""
    from sales.models import SaleItemBatch

    need = Decimal(str(sale_item.base_quantity or 0))
    if need <= 0:
        return []
    today = timezone.localdate()
    batches = list(ProductBatch.objects.select_for_update().filter(
        product_id=sale_item.product_id, is_active=True, qty_remaining__gt=0))
    batches.sort(key=lambda b: _order_key(b, today))

    used = []
    for b in batches:
        if need <= 0:
            break
        take = min(b.qty_remaining, need)
        b.qty_remaining -= take
        b.save(update_fields=['qty_remaining', 'updated_at'])
        SaleItemBatch.objects.create(sale_item=sale_item, batch=b, qty=take)
        used.append((b, take))
        need -= take
    return used


@transaction.atomic
def restore_for_sale_item(sale_item):
    """SaleItem মুছলে যে ব্যাচ থেকে কমেছিল সেখানেই ফেরত দেয়।"""
    for alloc in sale_item.batch_allocations.select_related('batch'):
        b = alloc.batch
        if b is None:
            continue
        b.qty_remaining = min(b.qty_received, b.qty_remaining + alloc.qty)
        b.is_active = True
        b.save(update_fields=['qty_remaining', 'is_active', 'updated_at'])


def effective_quantities(product_ids):
    """
    {batch_id: ব্যাচে সত্যিকারের কতটা আছে} — ব্যাচের যোগফল stock_qty র বেশি হলে বাড়তি ছাঁটা (উপরের নিয়মে)।
    """
    from products.models import Product

    stock = dict(Product.objects.filter(id__in=product_ids).values_list('id', 'stock_qty'))
    per_product = {}
    for b in ProductBatch.objects.filter(product_id__in=product_ids, is_active=True, qty_remaining__gt=0):
        per_product.setdefault(b.product_id, []).append(b)

    result = {}
    for pid, batches in per_product.items():
        for b in batches:
            result[b.id] = b.qty_remaining
        excess = sum(b.qty_remaining for b in batches) - Decimal(str(stock.get(pid, 0)))
        if excess <= 0:
            continue
        # সবচেয়ে দেরির মেয়াদ (আর মেয়াদহীন) আগে ছাঁটি
        for b in sorted(batches, key=lambda x: (x.expiry_date or date.max, x.id), reverse=True):
            if excess <= 0:
                break
            cut = min(result[b.id], excess)
            result[b.id] -= cut
            excess -= cut
    return result


def expiry_report(days=30, status='all', limit=None):
    """
    মেয়াদ রিপোর্ট। status: all | expired | expiring | ok | alerts (= expired + expiring)
    days — "শিগগিরই শেষ" ধরার সীমা (আজ থেকে কত দিন)।
    """
    today = timezone.localdate()
    qs = (ProductBatch.objects
          .filter(is_active=True, qty_remaining__gt=0, expiry_date__isnull=False, product__is_active=True)
          .select_related('product', 'product__category', 'purchase_item__purchase__supplier')
          .order_by('expiry_date', 'id'))
    rows = list(qs)
    eff = effective_quantities({b.product_id for b in rows})

    out = []
    counts = {'expired': 0, 'expiring': 0, 'ok': 0}
    value = {'expired': Decimal('0'), 'expiring': Decimal('0')}
    for b in rows:
        q = eff.get(b.id, ZERO)
        if q <= 0:
            continue
        left = (b.expiry_date - today).days
        st = 'expired' if left < 0 else ('expiring' if left <= days else 'ok')
        counts[st] += 1
        cost_value = (q * b.unit_cost).quantize(Decimal('0.01'))
        if st in value:
            value[st] += cost_value
        item = b.purchase_item
        out.append({
            'id': b.id,
            'product_id': b.product_id,
            'product_name': b.product.name,
            'sku': b.product.sku or '',
            'category': b.product.category.name if b.product.category_id else '',
            'batch_no': b.batch_no,
            'expiry_date': b.expiry_date.isoformat(),
            'days_left': left,
            'status': st,
            'qty_received': float(b.qty_received),
            'qty_remaining': float(q),
            'unit_cost': float(b.unit_cost),
            'cost_value': float(cost_value),
            'purchase_invoice': item.purchase.invoice_no if item and item.purchase_id else '',
            'supplier': (item.purchase.supplier.name if item and item.purchase_id and item.purchase.supplier_id else ''),
        })

    wanted = {'all': None, 'alerts': ('expired', 'expiring')}.get(status, (status,))
    listing = [r for r in out if wanted is None or r['status'] in wanted]
    if limit:
        listing = listing[:limit]
    return {
        'days': days,
        'today': today.isoformat(),
        'counts': {**counts, 'total': sum(counts.values())},
        'value': {k: float(v) for k, v in value.items()},
        'batches': listing,
    }


@transaction.atomic
def write_off_batch(batch_id, reason='', user=None):
    """মেয়াদ-পেরোনো (বা নষ্ট) ব্যাচের বাকিটা স্টক থেকে বাদ দিয়ে Bad Stock এ তোলে।"""
    from products.models import Product
    from returns.models import BadStock
    from offline_sync.utils import touch

    batch = ProductBatch.objects.select_for_update().select_related('product').get(pk=batch_id)
    qty = effective_quantities([batch.product_id]).get(batch.id, ZERO)
    if qty <= 0:
        raise ValueError('Nothing left in this batch to write off.')
    product = Product.objects.select_for_update().get(pk=batch.product_id)
    whole = int(qty.to_integral_value(rounding=ROUND_CEILING))
    whole = min(whole, product.stock_qty)
    if whole <= 0:
        raise ValueError(f"'{product.name}' has no stock left to write off.")

    product.stock_qty -= whole
    product.save(update_fields=['stock_qty', 'updated_at'])
    batch.qty_remaining = ZERO
    batch.save(update_fields=['qty_remaining', 'updated_at'])
    note = reason.strip() or 'Expired'
    BadStock.objects.create(
        product=product, quantity=whole, reference_type='direct', reference_id=batch.id,
        reason=f"{note} — batch {batch.batch_no or batch.id}, expiry {batch.expiry_date or 'n/a'}")
    touch(Product, product.id)
    return {'product': product.name, 'written_off': whole, 'stock_left': product.stock_qty}
