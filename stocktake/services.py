"""Stock adjustment / stocktake এর সব হিসাব ও স্টক বদল — view গুলো শুধু এগুলো ডাকে।"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from products.models import Product
from .models import StockAdjustment, Stocktake, StocktakeLine

REASON_KEYS = {k for k, _ in StockAdjustment.REASONS}


def _int(value, field):
    """পুরো সংখ্যা (স্টক পুরো সংখ্যায় রাখা হয়) — নইলে ValueError"""
    if isinstance(value, bool) or value is None or str(value).strip() == '':
        raise ValueError(f'{field} is required.')
    try:
        d = Decimal(str(value).replace(',', '').strip())
    except Exception:
        raise ValueError(f'{field} must be a number.')
    if d != d.to_integral_value():
        raise ValueError(f'{field} must be a whole number.')
    return int(d)


@transaction.atomic
def adjust_stock(product_id, user, new_qty=None, change=None, reason='other', note='', stocktake=None):
    """
    এক পণ্যের স্টক বদলায় আর StockAdjustment লেখে। new_qty (গুনে পাওয়া মোট) অথবা change (+/−) — একটাই দিতে হবে।
    """
    if (new_qty is None) == (change is None):
        raise ValueError('Give either the new quantity or the change, not both.')
    if reason not in REASON_KEYS:
        raise ValueError('Choose a valid reason.')
    try:
        product = Product.objects.select_for_update().get(pk=product_id)
    except Product.DoesNotExist:
        raise ValueError('Product not found.')

    before = product.stock_qty
    after = _int(new_qty, 'New quantity') if new_qty is not None else before + _int(change, 'Change')
    if after < 0:
        raise ValueError(f"'{product.name}' has only {before} in stock, so it can't go down by {before - after}.")
    diff = after - before
    if diff == 0 and stocktake is None:
        raise ValueError('That is the same as the current stock — nothing to change.')

    product.stock_qty = after
    product.save(update_fields=['stock_qty', 'updated_at'])
    cost = product.purchase_price or Decimal('0.00')
    adj = StockAdjustment.objects.create(
        product=product, product_name=product.name, sku=product.sku or '',
        qty_before=before, qty_after=after, change=diff, unit_cost=cost,
        value_change=(cost * diff).quantize(Decimal('0.01')),
        reason=reason, note=(note or '').strip()[:300], stocktake=stocktake, created_by=user)
    adj.number = f"ADJ-{adj.pk:06d}"
    adj.save(update_fields=['number'])
    return adj


@transaction.atomic
def start_stocktake(user, title='', category_id=None, note=''):
    """গণনা শুরু — scope এর সব active পণ্যের এখনকার স্টক snapshot করে লাইন বানায়।"""
    from products.models import Category

    category = None
    if category_id:
        category = Category.objects.filter(pk=category_id).first()
        if category is None:
            raise ValueError('Category not found.')
    products = Product.objects.filter(is_active=True).select_related('category')
    if category:
        products = products.filter(category=category)
    products = list(products.order_by('category__name', 'name'))
    if not products:
        raise ValueError('There are no active products to count' + (' in this category.' if category else '.'))

    st = Stocktake.objects.create(
        title=(title or '').strip()[:150], note=(note or '').strip(), category=category,
        category_name=category.name if category else '', created_by=user)
    st.number = f"ST-{st.pk:06d}"
    if not st.title:
        st.title = f"Count of {timezone.localdate():%d %b %Y}" + (f" — {category.name}" if category else '')
    st.save(update_fields=['number', 'title'])
    StocktakeLine.objects.bulk_create([
        StocktakeLine(
            stocktake=st, product=p, product_name=p.name, sku=p.sku or '',
            category_name=p.category.name if p.category_id else '',
            system_qty=p.stock_qty, unit_cost=p.purchase_price or Decimal('0.00'))
        for p in products])
    return st


@transaction.atomic
def save_counts(stocktake_id, rows):
    """rows = [{'line_id': 5, 'counted_qty': 12}, {'product_id': 9, 'counted_qty': None}, ...] — None মানে গণনা মুছে ফেলা।"""
    st = Stocktake.objects.select_for_update().get(pk=stocktake_id)
    if st.status != Stocktake.DRAFT:
        raise ValueError(f'This count is already {st.get_status_display().lower()}.')
    by_id = {l.id: l for l in st.lines.all()}
    by_product = {l.product_id: l for l in by_id.values() if l.product_id}
    now = timezone.now()
    changed = []
    for i, r in enumerate(rows or [], 1):
        line = by_id.get(r.get('line_id')) if r.get('line_id') else by_product.get(r.get('product_id'))
        if line is None:
            raise ValueError(f'Row {i}: that product is not in this count.')
        raw = r.get('counted_qty')
        if raw is None or str(raw).strip() == '':
            line.counted_qty, line.counted_at = None, None
        else:
            q = _int(raw, f'Row {i}: counted quantity')
            if q < 0:
                raise ValueError(f'Row {i}: counted quantity cannot be negative.')
            line.counted_qty, line.counted_at = q, now
        changed.append(line)
    StocktakeLine.objects.bulk_update(changed, ['counted_qty', 'counted_at'])
    return summary(st)


def summary(st):
    """গণনার অগ্রগতি + পার্থক্যের মোট (পরিমাণ ও কেনা-দামে টাকা)"""
    lines = list(st.lines.all())
    counted = [l for l in lines if l.counted_qty is not None]
    short_q = over_q = 0
    short_v = over_v = Decimal('0')
    differing = 0
    for l in counted:
        v = l.counted_qty - l.system_qty
        if v < 0:
            short_q += -v
            short_v += -v * l.unit_cost
            differing += 1
        elif v > 0:
            over_q += v
            over_v += v * l.unit_cost
            differing += 1
    return {
        'total': len(lines), 'counted': len(counted), 'uncounted': len(lines) - len(counted),
        'differing': differing,
        'short_qty': short_q, 'over_qty': over_q,
        'short_value': float(short_v.quantize(Decimal('0.01'))),
        'over_value': float(over_v.quantize(Decimal('0.01'))),
        'net_value': float((over_v - short_v).quantize(Decimal('0.01'))),
    }


@transaction.atomic
def apply_stocktake(stocktake_id, user):
    """
    গণনা করা লাইনের পার্থক্য (গণনা − snapshot) এখনকার স্টকে বসায়। গণনা না করা লাইন ছোঁয়া হয় না।
    কোনো একটা লাইনে স্টক ঋণাত্মক হয়ে যাওয়ার কথা হলে কিছুই বদলায় না — আগে কারণ জানায়।
    """
    st = Stocktake.objects.select_for_update().get(pk=stocktake_id)
    if st.status != Stocktake.DRAFT:
        raise ValueError(f'This count is already {st.get_status_display().lower()}.')
    lines = list(st.lines.select_related('product'))
    if not any(l.counted_qty is not None for l in lines):
        raise ValueError('Count at least one product before applying.')

    products = {p.id: p for p in Product.objects.select_for_update().filter(
        id__in=[l.product_id for l in lines if l.product_id])}
    problems = []
    todo = []
    for l in lines:
        if l.counted_qty is None or l.product_id not in products:
            continue
        v = l.counted_qty - l.system_qty
        if v == 0:
            continue
        now_qty = products[l.product_id].stock_qty
        if now_qty + v < 0:
            problems.append(f"{l.product_name}: counted {l.counted_qty}, but {now_qty} is in stock now "
                            f"(it was {l.system_qty} when counting started) — recount it.")
        todo.append((l, v))
    if problems:
        raise ValueError('Cannot apply yet. ' + ' '.join(problems[:5]) + (' …' if len(problems) > 5 else ''))

    for l, v in todo:
        adj = adjust_stock(l.product_id, user, change=v, reason='count',
                           note=f"{st.number}: counted {l.counted_qty}, system {l.system_qty}", stocktake=st)
        l.applied_change = adj.change
    StocktakeLine.objects.bulk_update([l for l, _ in todo], ['applied_change'])

    out = summary(st)
    st.status = Stocktake.APPLIED
    st.applied_by = user
    st.applied_at = timezone.now()
    st.save(update_fields=['status', 'applied_by', 'applied_at', 'updated_at'])
    out['adjusted'] = len(todo)
    return out


@transaction.atomic
def cancel_stocktake(stocktake_id):
    st = Stocktake.objects.select_for_update().get(pk=stocktake_id)
    if st.status != Stocktake.DRAFT:
        raise ValueError(f'This count is already {st.get_status_display().lower()}.')
    st.status = Stocktake.CANCELLED
    st.save(update_fields=['status', 'updated_at'])
    return st
