"""কাস্টমারের পাবলিক শপ — login লাগে না।
/ (হোম) ও /shop/ দুই জায়গাতেই একই শপ পেজ।"""
import json
import re
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction
from django.db.models import Prefetch, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_POST

from core.models import BusinessProfile
from products.models import Product, ProductSaleMode

from .forms import HEX
from .models import ShopOrder, ShopOrderItem, ShopSettings

MAX_ITEMS = 50
MAX_ORDERS_PER_WINDOW = 5      # একই IP থেকে
WINDOW_SECONDS = 10 * 60
MAX_TRACKS_PER_WINDOW = 20     # অর্ডার ট্র্যাক করার চেষ্টা, একই IP থেকে
PHONE_RE = re.compile(r'^\+?\d{10,15}$')
SECTION_SIZE = 8
NEW_DAYS = 14


def _ip(request):
    fwd = request.META.get('HTTP_X_FORWARDED_FOR')
    return (fwd.split(',')[0].strip() if fwd else request.META.get('REMOTE_ADDR')) or 'unknown'


@ensure_csrf_cookie
@never_cache
def home_store_view(request):
    """সাইটের হোম পেজ (/) — ই-কমার্স শপ + Login বাটন"""
    return _render_store(request)


@ensure_csrf_cookie
@never_cache
def store_view(request):
    return _render_store(request)


def _on_brand(hex_color):
    """ব্র্যান্ড কালারের উপর লেখা সাদা হবে না গাঢ় — উজ্জ্বলতা দেখে ঠিক হয়"""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return '#111418' if (0.299 * r + 0.587 * g + 0.114 * b) > 165 else '#ffffff'


def _unit_name(p):
    u = getattr(p, 'unit', None)
    return (getattr(u, 'name', '') or '') if u else ''


def _mode_info(psm):
    """একটা ProductSaleMode এর অনলাইন-বিক্রির তথ্য। বেস ইউনিটে পূর্ণসংখ্যা না হলে None (স্টক পূর্ণসংখ্যা বলে)।
    step: এক ক্লিকে কত বাড়বে — কাস্টম ওজন (unit-type, ফ্যাক্টর ≤ ১, যেমন গ্রাম) হলে ৫০, নইলে ১।"""
    sm = psm.sale_mode
    factor = Decimal(sm.conversion_factor)
    custom = sm.price_type != 'flat' and factor <= 1
    step = 50 if custom else 1
    base = factor * step
    if base <= 0 or base != base.to_integral_value():
        return None
    return {'sm': sm, 'custom': custom, 'step': step, 'base': int(base), 'factor': factor}


def _modes_for(p, final_default):
    """পণ্যের সক্রিয় সেল মোড → শপের প্যাক/ওজন বাটন। কোনো মোড না থাকলে একটাই ডিফল্ট (পুরনো আচরণ)।"""
    out = []
    for psm in p.product_sale_modes.all():
        info = _mode_info(psm)
        if info is None:
            continue
        price = psm.get_final_price(info['step']).quantize(Decimal('0.01'))
        if price <= 0 or p.stock_qty < info['base']:
            continue
        if psm.sale_mode.price_type == 'flat':
            raw = (psm.flat_price or Decimal('0')) * info['step']
        else:
            raw = (psm.unit_price or Decimal('0')) * info['base']
        on_sale = raw > price
        out.append({
            'id': psm.sale_mode_id, 'name': psm.sale_mode.name, 'custom': info['custom'],
            'step': info['step'], 'base': info['base'],
            'price': float(price), 'old': float(raw) if on_sale else None,
            'off': int(round((1 - price / raw) * 100)) if on_sale else 0,
            '_order': (info['custom'], -info['base']),
        })
    out.sort(key=lambda m: m['_order'])
    for m in out:
        del m['_order']
    if out:
        return out
    sell = p.selling_price
    on_sale = final_default < sell and sell > 0
    return [{'id': 0, 'name': _unit_name(p) or 'Each', 'custom': False, 'step': 1, 'base': 1,
             'price': float(final_default), 'old': float(sell) if on_sale else None,
             'off': int(round((1 - final_default / sell) * 100)) if on_sale else 0}]


def _product_dict(p, new_after):
    sell, final = p.selling_price, p.final_price
    modes = _modes_for(p, final)
    first = modes[0]
    return {
        'id': p.id,
        'name': p.name,
        'modes': modes,
        'price': first['price'],
        'old': first['old'],
        'off': first['off'],
        'stock': p.stock_qty,   # বেস ইউনিটে (গ্রাম/পিস); মোড অনুযায়ী কতটা বিক্রি যাবে তা modes[].base দিয়ে ক্লায়েন্ট হিসাব করে
        'image': p.image.url if p.image else '',
        'cat': p.category_id or 0,
        'catName': p.category.name if p.category_id else '',
        'brand': p.brand.name if p.brand_id else '',
        'unit': _unit_name(p),
        'desc': (p.description or '')[:600],
        'isNew': p.created_at >= new_after,
        'created': p.created_at.timestamp(),
    }


def _render_store(request):
    ss = ShopSettings.load()
    business = BusinessProfile.get()
    now = timezone.now()
    modes_qs = ProductSaleMode.objects.filter(is_active=True, sale_mode__is_active=True, sale_mode__show_in_shop=True).select_related('sale_mode')
    qs = (Product.objects.filter(is_active=True, stock_qty__gt=0)
          .select_related('category', 'unit', 'brand')
          .prefetch_related(Prefetch('product_sale_modes', queryset=modes_qs))
          .order_by('-created_at')[:500])
    products = [_product_dict(p, now - timedelta(days=NEW_DAYS)) for p in qs]
    products = [p for p in products if p['modes']]
    by_id = {p['id']: p for p in products}

    cats = {}
    for p in products:
        if p['cat']:
            c = cats.setdefault(p['cat'], {'id': p['cat'], 'name': p['catName'], 'count': 0})
            c['count'] += 1
    cats = sorted(cats.values(), key=lambda c: (-c['count'], c['name']))

    deals = [p['id'] for p in products if p['old']]
    deals.sort(key=lambda i: -by_id[i]['off'])
    popular_rows = (ShopOrderItem.objects
                    .filter(product_id__in=by_id.keys())
                    .exclude(order__status=ShopOrder.CANCELLED)
                    .values('product_id').annotate(n=Sum('qty')).order_by('-n')[:SECTION_SIZE])
    data = {
        'products': products,
        'cats': cats,
        'sections': {
            'deals': deals[:SECTION_SIZE],
            'new': [p['id'] for p in products][:SECTION_SIZE],  # created_at desc
            'popular': [r['product_id'] for r in popular_rows],
        },
        'delivery': {'charge': float(ss.delivery_charge), 'freeMin': float(ss.free_delivery_min)},
        'isOpen': ss.is_open,
        'orderUrl': reverse('shop:place_order'),
        'trackUrl': reverse('shop:track_order'),
    }

    user = request.user
    staff = bool(user.is_authenticated)
    can_orders = False
    if staff and hasattr(user, 'get_permissions'):
        can_orders = bool((user.get_permissions().get('sales') or {}).get('view'))
    pending = ShopOrder.objects.filter(status='pending').count() if can_orders else 0

    brand = ss.brand_color if HEX.match(ss.brand_color or '') else '#0f766e'
    logo = getattr(business, 'logo', None)
    return render(request, 'shop/store.html', {
        'ss': ss,
        'shop_name': ss.shop_name or business.name,
        'brand': brand,
        'on_brand': _on_brand(brand),
        'company_logo': logo.url if logo else '',
        'hero_image': ss.hero_image.url if ss.hero_image else '',
        'data': data,
        'is_staff_user': staff,
        'can_orders': can_orders,
        'pending_orders': pending,
        'year': now.year,
    })


@require_POST
@csrf_protect
def place_order_view(request):
    ss = ShopSettings.load()
    if not ss.is_open:
        return JsonResponse({'ok': False, 'error': 'We are not taking orders right now. Please check back soon.'}, status=403)

    key = f"shop-order:{_ip(request)}"
    if (cache.get(key) or 0) >= MAX_ORDERS_PER_WINDOW:
        return JsonResponse({'ok': False, 'error': 'Too many orders from this device. Please try again later.'}, status=429)

    try:
        data = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'Invalid request.'}, status=400)

    name = (data.get('name') or '').strip()[:100]
    phone = re.sub(r'[\s-]', '', (data.get('phone') or ''))
    address = (data.get('address') or '').strip()[:500]
    note = (data.get('note') or '').strip()[:500]
    if not name or not address:
        return JsonResponse({'ok': False, 'error': 'Please enter your name and delivery address.'}, status=400)
    if not PHONE_RE.match(phone):
        return JsonResponse({'ok': False, 'error': 'Please enter a valid phone number.'}, status=400)

    # ঝুড়ি: (product id, sale mode id) → qty (দাম কখনো client থেকে নেওয়া হয় না)
    wanted = {}
    for row in (data.get('items') or [])[:MAX_ITEMS]:
        try:
            pid, mid, qty = int(row.get('id')), int(row.get('mode') or 0), int(row.get('qty'))
        except (TypeError, ValueError, AttributeError):
            continue
        if qty > 0:
            wanted[(pid, mid)] = wanted.get((pid, mid), 0) + qty
    if not wanted:
        return JsonResponse({'ok': False, 'error': 'Your cart is empty.'}, status=400)

    # স্টক reserve: অর্ডার দেওয়ার মুহূর্তেই stock কমে (POS এর সাথে overselling ঠেকাতে)।
    # Cancel করলে ফেরত আসে। row lock এর কারণে POS ও অনলাইন একসাথে একই stock কিনতে পারে না।
    try:
        with transaction.atomic():
            pids = {pid for pid, _ in wanted}
            products = {p.id: p for p in Product.objects.select_for_update()
                        .filter(is_active=True, id__in=pids)}
            psms = {(x.product_id, x.sale_mode_id): x for x in ProductSaleMode.objects
                    .filter(product_id__in=pids, is_active=True, sale_mode__is_active=True, sale_mode__show_in_shop=True).select_related('sale_mode')}
            has_modes = {pid for pid, _ in psms}
            lines, subtotal, need = [], Decimal('0.00'), {}
            for (pid, mid), qty in wanted.items():
                p = products.get(pid)
                if p is None:
                    raise ValueError('A product in your cart is no longer available. Please refresh.')
                if mid == 0:
                    if pid in has_modes:
                        raise ValueError(f"Please choose a pack size for '{p.name}'. Refresh the page and try again.")
                    sm, mode_name, base, line = None, '', qty, (p.final_price * qty).quantize(Decimal('0.01'))
                else:
                    psm = psms.get((pid, mid))
                    info = _mode_info(psm) if psm else None
                    if info is None or qty % info['step']:
                        raise ValueError(f"'{p.name}' is not available in that size anymore. Please refresh.")
                    sm, mode_name = psm.sale_mode, psm.sale_mode.name
                    base = int(info['factor'] * qty)
                    line = psm.get_final_price(qty).quantize(Decimal('0.01'))
                if line <= 0:
                    raise ValueError(f"'{p.name}' has no price set. Please refresh.")
                need[pid] = need.get(pid, 0) + base
                lines.append((p, sm, mode_name, qty, base, (line / qty).quantize(Decimal('0.01')), line))
                subtotal += line
            for pid, n in need.items():
                if products[pid].stock_qty < n:
                    raise ValueError(f"Not enough '{products[pid].name}' in stock. Please reduce the quantity.")
            delivery = ss.delivery_for(subtotal)
            total = subtotal + delivery

            order = ShopOrder.objects.create(customer_name=name, phone=phone,
                                             address=address, note=note, delivery_charge=delivery,
                                             total=total, stock_deducted=True)
            ShopOrderItem.objects.bulk_create([
                ShopOrderItem(order=order, product=p, product_name=p.name, unit_price=up, qty=qty, line_total=line,
                              sale_mode=sm, mode_name=mn, base_qty=base if sm else 0)
                for p, sm, mn, qty, base, up, line in lines
            ])
            for pid, n in need.items():
                products[pid].stock_qty -= n
                products[pid].save(update_fields=['stock_qty'])
    except ValueError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=409)
    cache.set(key, (cache.get(key) or 0) + 1, WINDOW_SECONDS)
    return JsonResponse({'ok': True, 'order_no': order.order_no, 'total': float(total), 'delivery': float(delivery)})


def _digits(s):
    return re.sub(r'\D', '', s or '')


def _same_phone(a, b):
    """+88 / 0 দিয়ে লিখলেও মিলবে — শেষের ১০ ডিজিট তুলনা করা হয়"""
    a, b = _digits(a), _digits(b)
    return len(a) >= 10 and len(b) >= 10 and a[-10:] == b[-10:]


@require_POST
@csrf_protect
def track_order_view(request):
    """কাস্টমার অর্ডার নম্বর + ফোন দিয়ে নিজের অর্ডারের অবস্থা দেখে (login লাগে না)।
    অর্ডার নম্বর ক্রমিক (WEB-00001...) তাই ফোন না মিললে কিছুই জানানো হয় না — অন্যের অর্ডার দেখা যাবে না।"""
    key = f"shop-track:{_ip(request)}"
    if (cache.get(key) or 0) >= MAX_TRACKS_PER_WINDOW:
        return JsonResponse({'ok': False, 'error': 'Too many attempts. Please try again in a few minutes.'}, status=429)
    cache.set(key, (cache.get(key) or 0) + 1, WINDOW_SECONDS)

    try:
        data = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'Invalid request.'}, status=400)

    order_no = (data.get('order_no') or '').strip().upper()
    phone = data.get('phone') or ''
    if order_no.isdigit():                       # "12" বা "00012" লিখলেও চলবে
        order_no = f"WEB-{int(order_no):05d}"
    not_found = JsonResponse({'ok': False, 'error': 'No order found. Please check the order number and phone number.'}, status=404)
    if not order_no or not _digits(phone):
        return JsonResponse({'ok': False, 'error': 'Enter your order number and the phone number you used.'}, status=400)

    order = ShopOrder.objects.filter(order_no=order_no).prefetch_related('items').first()
    if order is None or not _same_phone(order.phone, phone):
        return not_found

    subtotal = sum((i.line_total for i in order.items.all()), Decimal('0.00'))
    return JsonResponse({
        'ok': True,
        'order_no': order.order_no,
        'status': order.status,
        'placed': timezone.localtime(order.created_at).strftime('%d %b %Y, %I:%M %p'),
        'updated': timezone.localtime(order.updated_at).strftime('%d %b %Y, %I:%M %p'),
        'name': order.customer_name,
        'address': order.address,
        'items': [{'name': i.product_name + (' · ' + i.mode_name if i.mode_name else ''), 'qty': i.qty,
                   'price': float(i.unit_price), 'total': float(i.line_total)}
                  for i in order.items.all()],
        'subtotal': float(subtotal),
        'delivery': float(order.delivery_charge),
        'total': float(order.total),
    })
