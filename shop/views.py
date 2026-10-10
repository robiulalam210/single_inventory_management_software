"""কাস্টমারের পাবলিক শপ — login লাগে না।
/ (হোম) ও /shop/ দুই জায়গাতেই একই শপ পেজ।"""
import json
import re
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_POST

from core.models import BusinessProfile
from products.models import Product

from .forms import HEX
from .models import ShopOrder, ShopOrderItem, ShopSettings

MAX_ITEMS = 50
MAX_ORDERS_PER_WINDOW = 5      # একই IP থেকে
WINDOW_SECONDS = 10 * 60
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


def _product_dict(p, new_after):
    sell, final = p.selling_price, p.final_price
    on_sale = final < sell and sell > 0
    return {
        'id': p.id,
        'name': p.name,
        'price': float(final),
        'old': float(sell) if on_sale else None,
        'off': int(round((1 - final / sell) * 100)) if on_sale else 0,
        'stock': p.stock_qty,
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
    qs = (Product.objects.filter(is_active=True, stock_qty__gt=0)
          .select_related('category', 'unit', 'brand').order_by('-created_at')[:500])
    products = [_product_dict(p, now - timedelta(days=NEW_DAYS)) for p in qs]
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

    # ঝুড়ি: product id → qty (দাম কখনো client থেকে নেওয়া হয় না)
    wanted = {}
    for row in (data.get('items') or [])[:MAX_ITEMS]:
        try:
            pid, qty = int(row.get('id')), int(row.get('qty'))
        except (TypeError, ValueError, AttributeError):
            continue
        if qty > 0:
            wanted[pid] = wanted.get(pid, 0) + qty
    if not wanted:
        return JsonResponse({'ok': False, 'error': 'Your cart is empty.'}, status=400)

    # স্টক reserve: অর্ডার দেওয়ার মুহূর্তেই stock কমে (POS এর সাথে overselling ঠেকাতে)।
    # Cancel করলে ফেরত আসে। row lock এর কারণে POS ও অনলাইন একসাথে একই stock কিনতে পারে না।
    try:
        with transaction.atomic():
            products = {p.id: p for p in Product.objects.select_for_update()
                        .filter(is_active=True, id__in=wanted.keys())}
            lines, subtotal = [], Decimal('0.00')
            for pid, qty in wanted.items():
                p = products.get(pid)
                if p is None:
                    raise ValueError('A product in your cart is no longer available. Please refresh.')
                if p.stock_qty < qty:
                    raise ValueError(f"Only {p.stock_qty} of '{p.name}' in stock.")
                unit_price = p.final_price
                line = (unit_price * qty).quantize(Decimal('0.01'))
                lines.append((p, qty, unit_price, line))
                subtotal += line
            delivery = ss.delivery_for(subtotal)
            total = subtotal + delivery

            order = ShopOrder.objects.create(customer_name=name, phone=phone,
                                             address=address, note=note, delivery_charge=delivery,
                                             total=total, stock_deducted=True)
            ShopOrderItem.objects.bulk_create([
                ShopOrderItem(order=order, product=p, product_name=p.name, unit_price=up, qty=qty, line_total=line)
                for p, qty, up, line in lines
            ])
            for p, qty, _, _ in lines:
                p.stock_qty -= qty
                p.save(update_fields=['stock_qty'])
    except ValueError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=409)
    cache.set(key, (cache.get(key) or 0) + 1, WINDOW_SECONDS)
    return JsonResponse({'ok': True, 'order_no': order.order_no, 'total': float(total), 'delivery': float(delivery)})
