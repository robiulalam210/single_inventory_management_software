"""Online Shop — স্টাফ অ্যাপের (Flutter mobile + desktop) JSON API।

/api/shop/orders/                 GET   তালিকা (?status=pending|confirmed|delivered|cancelled|all &q= &page=)
/api/shop/orders/<id>/            GET   একটা অর্ডার
/api/shop/orders/<id>/status/     POST  {action: confirm|deliver|cancel, cash_received: bool}
/api/shop/settings/               GET / PATCH   শপ সেটিংস

Response ধরন সব API র মতোই: {status: bool, message: str, data: ...}
Permission ওয়েবের মতোই: দেখা = sales.view, বদলানো = sales.edit
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.urls import reverse
from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.perms import user_has_perm

from .forms import ShopSettingsForm
from .models import ShopOrder, ShopSettings

STATUS_FILTERS = ['pending', 'confirmed', 'delivered', 'cancelled', 'all']
PAGE_SIZE = 20

ACTIONS = {
    'confirm': ShopOrder.CONFIRMED,
    'deliver': ShopOrder.DELIVERED,
    'cancel': ShopOrder.CANCELLED,
}


def _ok(data, message='OK', code=http.HTTP_200_OK):
    return Response({'status': True, 'message': message, 'data': data}, status=code)


def _fail(message, code=http.HTTP_400_BAD_REQUEST, data=None):
    return Response({'status': False, 'message': message, 'data': data}, status=code)


def _shop_url(request):
    return request.build_absolute_uri(reverse('shop:store'))


def _money(v):
    return f'{Decimal(v or 0):.2f}'


def serialize_order(o, can_edit, with_items=True):
    sale = o.sale if o.sale_id else None
    data = {
        'id': o.id,
        'order_no': o.order_no,
        'customer_name': o.customer_name,
        'phone': o.phone,
        'address': o.address,
        'note': o.note,
        'status': o.status,
        'delivery_charge': _money(o.delivery_charge),
        'total': _money(o.total),
        'item_count': sum(i.qty for i in o.items.all()),
        'stock_deducted': o.stock_deducted,
        'can_edit': can_edit,
        'sale_id': o.sale_id,
        'invoice_no': sale.invoice_no if sale else None,
        'paid_amount': _money(sale.paid_amount) if sale else None,
        'due_amount': _money(sale.due_amount) if sale else None,
        'created_at': o.created_at.isoformat() if o.created_at else None,
    }
    if with_items:
        data['items'] = [
            {
                'id': i.id,
                'product_id': i.product_id,
                'product_name': i.product_name,
                'unit_price': _money(i.unit_price),
                'qty': i.qty,
                'line_total': _money(i.line_total),
            }
            for i in o.items.all()
        ]
    return data


class ShopOrderListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not user_has_perm(request.user, 'sales', 'view'):
            return _fail('You do not have permission to view online orders.', http.HTTP_403_FORBIDDEN)

        st = request.query_params.get('status', 'pending')
        if st not in STATUS_FILTERS:
            st = 'pending'
        q = (request.query_params.get('q') or '').strip()
        try:
            page = max(int(request.query_params.get('page', 1)), 1)
        except (TypeError, ValueError):
            page = 1

        base = ShopOrder.objects.all()
        counts = {r['status']: r['n'] for r in base.values('status').annotate(n=Count('id'))}
        counts = {s: counts.get(s, 0) for s in STATUS_FILTERS if s != 'all'} | {'all': sum(counts.values())}

        qs = base.select_related('sale').prefetch_related('items')
        if st != 'all':
            qs = qs.filter(status=st)
        if q:
            qs = qs.filter(Q(order_no__icontains=q) | Q(customer_name__icontains=q) | Q(phone__icontains=q))

        total = qs.count()
        pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
        page = min(page, pages)
        rows = qs[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]

        can_edit = user_has_perm(request.user, 'sales', 'edit')
        ss = ShopSettings.load()
        return _ok({
            'count': total,
            'total_pages': pages,
            'current_page': page,
            'page_size': PAGE_SIZE,
            'results': [serialize_order(o, can_edit) for o in rows],
            'counts': counts,
            'shop_is_open': ss.is_open,
            'can_edit': can_edit,
            'shop_url': _shop_url(request),
        })


class ShopOrderDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not user_has_perm(request.user, 'sales', 'view'):
            return _fail('You do not have permission to view online orders.', http.HTTP_403_FORBIDDEN)
        order = (ShopOrder.objects.select_related('sale').prefetch_related('items')
                 .filter(pk=pk).first())
        if order is None:
            return _fail('Order not found.', http.HTTP_404_NOT_FOUND)
        return _ok(serialize_order(order, user_has_perm(request.user, 'sales', 'edit')))


class ShopOrderStatusAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not user_has_perm(request.user, 'sales', 'edit'):
            return _fail('You do not have permission to change online orders.', http.HTTP_403_FORBIDDEN)
        order = ShopOrder.objects.filter(pk=pk).first()
        if order is None:
            return _fail('Order not found.', http.HTTP_404_NOT_FOUND)

        target = ACTIONS.get(request.data.get('action'))
        if target is None:
            return _fail('action must be confirm, deliver or cancel.')

        cash = request.data.get('cash_received')
        cash = cash is True or str(cash).lower() in ('1', 'true', 'yes', 'on')
        try:
            done = order.change_status(target, user=request.user, cash_received=cash)
        except ValueError as e:
            return _fail(str(e))
        except ValidationError as e:
            return _fail(' '.join(getattr(e, 'messages', None) or [str(e)]))

        done = (ShopOrder.objects.select_related('sale').prefetch_related('items').get(pk=done.pk))
        msg = f'{done.order_no} is now {target}.'
        if done.sale_id:
            msg += f' Invoice {done.sale.invoice_no} created.'
        return _ok(serialize_order(done, True), msg)


SETTINGS_FIELDS = [
    'is_open', 'shop_name', 'tagline', 'brand_color', 'default_theme', 'announcement',
    'hero_title', 'hero_subtitle', 'hero_button_text',
    'about_title', 'about_text',
    'phone', 'whatsapp', 'email', 'address', 'opening_hours', 'facebook_url',
    'delivery_charge', 'free_delivery_min', 'delivery_note', 'payment_note',
]


def serialize_settings(ss, request):
    d = {k: getattr(ss, k) for k in SETTINGS_FIELDS}
    d['delivery_charge'] = _money(ss.delivery_charge)
    d['free_delivery_min'] = _money(ss.free_delivery_min)
    d['hero_image'] = request.build_absolute_uri(ss.hero_image.url) if ss.hero_image else None
    d['shop_url'] = _shop_url(request)
    d['updated_at'] = ss.updated_at.isoformat() if ss.updated_at else None
    return d


class ShopSettingsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not user_has_perm(request.user, 'sales', 'view'):
            return _fail('You do not have permission to view shop settings.', http.HTTP_403_FORBIDDEN)
        return _ok(serialize_settings(ShopSettings.load(), request))

    def patch(self, request):
        # ওয়েবে Shop Settings এর মতোই: sales.edit লাগে
        if not user_has_perm(request.user, 'sales', 'edit'):
            return _fail('You do not have permission to change shop settings.', http.HTTP_403_FORBIDDEN)

        ss = ShopSettings.load()
        # শুধু পাঠানো ফিল্ডই বদলাবে; বাকি আগের মান থাকবে (ModelForm সব ফিল্ড চায়, তাই মার্জ করা হলো)
        merged = {k: getattr(ss, k) for k in SETTINGS_FIELDS}
        for k in SETTINGS_FIELDS:
            if k in request.data:
                merged[k] = request.data.get(k)
        if request.data.get('remove_hero_image') in (True, 'true', '1', 1):
            merged['remove_hero_image'] = True

        form = ShopSettingsForm(merged, instance=ss)
        if not form.is_valid():
            first = next(iter(form.errors.items()), None)
            msg = f'{first[0]}: {first[1][0]}' if first else 'Invalid data.'
            return _fail(msg, data={k: list(v) for k, v in form.errors.items()})
        form.save()
        return _ok(serialize_settings(ShopSettings.load(), request), 'Shop settings saved.')
