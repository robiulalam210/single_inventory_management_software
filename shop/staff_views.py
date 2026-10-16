"""স্টাফের দিকের Online Orders — /app/online-orders/ (web software এর ভেতরে, login ও permission সহ)"""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from web.views import forbidden, has_perm, web_login_required

from .forms import ShopSettingsForm
from .models import ShopOrder, ShopSettings

STATUS_FILTERS = ['pending', 'confirmed', 'delivered', 'cancelled', 'all']


@web_login_required
@never_cache
@csrf_protect
def orders_view(request):
    user = request.user
    if not has_perm(user, 'sales', 'view'):
        return forbidden(request, 'Online Orders')

    if request.method == 'POST':
        if not has_perm(user, 'sales', 'edit'):
            return forbidden(request, 'Online Orders')
        order = ShopOrder.objects.filter(pk=request.POST.get('order_id')).first()
        target = {'confirm': ShopOrder.CONFIRMED, 'deliver': ShopOrder.DELIVERED,
                  'cancel': ShopOrder.CANCELLED}.get(request.POST.get('action'))
        if order is None or target is None:
            messages.error(request, 'Order not found.')
        else:
            try:
                done = order.change_status(target, user=user, cash_received=bool(request.POST.get('cash_received')))
                extra = f' Invoice {done.sale.invoice_no} created.' if done.sale_id else ''
                messages.success(request, f'{order.order_no} is now {target}.{extra}')
            except ValueError as e:
                messages.error(request, str(e))
            except ValidationError as e:
                messages.error(request, ' '.join(getattr(e, 'messages', None) or [str(e)]))
        nxt = request.POST.get('back') or reverse('web:shop_orders')
        return redirect(nxt if nxt.startswith('/app/') else reverse('web:shop_orders'))

    status = request.GET.get('status', 'pending')
    if status not in STATUS_FILTERS:
        status = 'pending'
    q = (request.GET.get('q') or '').strip()

    base = ShopOrder.objects.all()
    counts = {r['status']: r['n'] for r in base.values('status').annotate(n=Count('id'))}
    qs = base.select_related('sale').prefetch_related('items')
    if status != 'all':
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(Q(order_no__icontains=q) | Q(customer_name__icontains=q) | Q(phone__icontains=q))

    return render(request, 'web/shop/orders.html', {
        'page_title': 'Online Orders',
        'orders': qs[:100],
        'status': status,
        'q': q,
        'tabs': [(s, s.title(), counts.get(s, 0) if s != 'all' else sum(counts.values())) for s in STATUS_FILTERS],
        'can_edit': has_perm(user, 'sales', 'edit'),
        'shop_url': ShopSettings.load().public_url(request),
    })


@web_login_required
@never_cache
@csrf_protect
def settings_view(request):
    """অ্যাডমিন: শপ পেজের তথ্য, ব্যানার, যোগাযোগ, ডেলিভারি — এক জায়গা থেকে"""
    user = request.user
    if not has_perm(user, 'sales', 'edit'):
        return forbidden(request, 'Shop Settings')

    ss = ShopSettings.load()
    if request.method == 'POST':
        form = ShopSettingsForm(request.POST, request.FILES, instance=ss)
        if form.is_valid():
            form.save()
            messages.success(request, 'Shop settings saved.')
            return redirect('web:shop_settings')
        messages.error(request, 'Please fix the highlighted fields.')
    else:
        form = ShopSettingsForm(instance=ss)

    groups = [
        ('Store', 'Basic info shown at the top of your shop.',
         ['is_open', 'shop_name', 'tagline', 'brand_color', 'default_theme', 'announcement']),
        ('Banner', 'The big section at the top of the home page.',
         ['hero_title', 'hero_subtitle', 'hero_button_text', 'hero_image', 'remove_hero_image']),
        ('About', 'A short story about your shop. Leave empty to hide the section.',
         ['about_title', 'about_text']),
        ('Contact', 'Shown in the contact section and footer.',
         ['phone', 'whatsapp', 'email', 'address', 'opening_hours', 'facebook_url']),
        ('Delivery and payment', 'Delivery charge is added to every online order.',
         ['delivery_charge', 'free_delivery_min', 'delivery_note', 'payment_note']),
    ]
    return render(request, 'web/shop/settings.html', {
        'page_title': 'Shop Settings',
        'form': form,
        'groups': [(t, d, [form[f] for f in fs]) for t, d, fs in groups],
        'shop_url': ss.public_url(request),
        'current_hero': ss.hero_image.url if ss.hero_image else '',
    })
