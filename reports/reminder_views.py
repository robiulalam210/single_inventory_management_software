# reports/reminder_views.py
"""
GET /api/reports/customer-due-reminders/

কার কাছে কত বাকি — আর তাকে পাঠানোর জন্য তৈরি WhatsApp / SMS লিংক।

বাকির হিসাব Customers পেজের (customers/serializers.py এর total_due) সাথে হুবহু এক:
    net due = (সব sale এর grand_total − সব sale এ পাওয়া paid_amount) − advance_balance, ০ এর নিচে নয়।
তাই Customers পেজে যার "Owes you" ও যত টাকা দেখায়, এখানেও তাই আসে — দুই জায়গায় দুই সংখ্যা হয় না।

Filter (সবই ঐচ্ছিক):
    q           নাম বা ফোন দিয়ে খোঁজা
    min_amount  এর বেশি বাকি (ডিফল্ট ০)
    min_days    সবচেয়ে পুরনো বাকি বিক্রির বয়স অন্তত এত দিন (ডিফল্ট ০)
    template    বার্তার ছাঁচ — {name} {amount} {shop} {phone} {invoices} {days}

দ্রষ্টব্য: এটা SMS/WhatsApp নিজে পাঠায় না — প্রতিটা customer এর জন্য "wa.me" ও "sms:" লিংক বানায়, যেটা চাপলে
দোকানির ফোন/WhatsApp এ বার্তা তৈরি হয়ে খোলে; পাঠানোর বোতাম দোকানি নিজে চাপেন।
স্বয়ংক্রিয় bulk SMS এর জন্য SMS gateway (পেইড সার্ভিস) লাগে — সেটা পরে এখানে জোড়া যাবে।
"""
from decimal import Decimal
from urllib.parse import quote

from django.db.models import Count, Max, Min, Q, Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.utils import custom_response

from .perms import user_has_perm
from .reminder_utils import DEFAULT_TEMPLATE, MAX_INVOICES_IN_MESSAGE, MAX_ROWS, money, normalize_phone, render_message

def _local_date(dt):
    if dt is None:
        return None
    if timezone.is_aware(dt):
        dt = timezone.localtime(dt)
    return dt.date()


class CustomerDueReminderView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not user_has_perm(request.user, 'customers', 'view'):
            return custom_response(False, 'You do not have permission to view customers.', None, 403)

        from core.models import BusinessProfile
        from customers.models import Customer
        from sales.models import Sale

        try:
            min_amount = Decimal(request.GET.get('min_amount') or '0')
        except Exception:  # noqa: BLE001
            min_amount = Decimal('0')
        try:
            min_days = max(0, int(request.GET.get('min_days') or 0))
        except ValueError:
            min_days = 0
        q = (request.GET.get('q') or '').strip().lower()
        template = (request.GET.get('template') or '').strip() or DEFAULT_TEMPLATE

        biz = BusinessProfile.get()
        shop_name = biz.name or 'আমাদের দোকান'
        shop_phone = biz.whatsapp or biz.phone or ''

        # প্রতি customer এর হিসাব (একটাই query): মোট বিক্রি, মোট পাওয়া, আর বাকি-থাকা invoice এর তারিখ/সংখ্যা
        due_sale = Q(due_amount__gt=0)
        grouped = {
            g['customer']: g
            for g in (
                Sale.objects.filter(customer__isnull=False, customer__is_active=True)
                .values('customer')
                .annotate(grand=Sum('grand_total'), paid=Sum('paid_amount'),
                          oldest=Min('sale_date', filter=due_sale), latest=Max('sale_date', filter=due_sale),
                          invoice_count=Count('id', filter=due_sale))
            )
            if (g['grand'] or 0) - (g['paid'] or 0) > 0
        }
        customers = {c.id: c for c in Customer.objects.filter(id__in=list(grouped.keys()))}

        # বার্তায় বসানোর invoice গুলো (একটাই query)
        by_customer = {}
        for s in (Sale.objects.filter(customer_id__in=list(grouped.keys()), due_amount__gt=0)
                  .order_by('sale_date', 'id').values('customer_id', 'invoice_no', 'sale_date', 'due_amount')):
            by_customer.setdefault(s['customer_id'], []).append(s)

        today = timezone.localdate()
        rows = []
        for cid, g in grouped.items():
            c = customers.get(cid)
            if c is None:
                continue
            basic_due = (g['grand'] or Decimal('0')) - (g['paid'] or Decimal('0'))
            advance = c.advance_balance or Decimal('0')
            net_due = max(Decimal('0'), basic_due - advance)
            if net_due <= 0 or net_due <= min_amount:
                continue
            oldest = _local_date(g['oldest'])
            days = (today - oldest).days if oldest else 0
            if days < min_days:
                continue
            if q and q not in (c.name or '').lower() and q not in (c.phone or '').lower():
                continue

            inv = by_customer.get(cid, [])
            inv_text = ', '.join(f"{(i['invoice_no'] or '#')} (৳{money(i['due_amount'])})" for i in inv[:MAX_INVOICES_IN_MESSAGE])
            if len(inv) > MAX_INVOICES_IN_MESSAGE:
                inv_text += f' ও আরও {len(inv) - MAX_INVOICES_IN_MESSAGE}টি'

            message = render_message(template, name=c.name or '', amount=net_due, shop=shop_name,
                                     phone=shop_phone, invoices=inv_text, days=days)
            intl = normalize_phone(c.phone)
            rows.append({
                'customer_id': c.id,
                'client_no': c.client_no,
                'name': c.name,
                'phone': c.phone or '',
                'phone_intl': intl,
                'basic_due': float(basic_due),
                'advance_balance': float(advance),
                'net_due': float(net_due),
                'invoice_count': g['invoice_count'],
                'oldest_due_date': oldest.isoformat() if oldest else None,
                'last_sale_date': _local_date(g['latest']).isoformat() if g['latest'] else None,
                'days_overdue': days,
                'invoices': [{'invoice_no': i['invoice_no'], 'date': _local_date(i['sale_date']).isoformat(),
                              'due': float(i['due_amount'])} for i in inv],
                'message': message,
                'whatsapp_url': f'https://wa.me/{intl}?text={quote(message)}' if intl else None,
                'sms_url': f'sms:+{intl}?&body={quote(message)}' if intl else None,
            })

        rows.sort(key=lambda r: (-r['net_due'], r['name'] or ''))
        total = len(rows)
        rows = rows[:MAX_ROWS]
        summary = {
            'total_customers': total,
            'total_due': round(sum(r['net_due'] for r in rows), 2),
            'with_phone': sum(1 for r in rows if r['phone_intl']),
            'without_phone': sum(1 for r in rows if not r['phone_intl']),
            'oldest_days': max([r['days_overdue'] for r in rows], default=0),
            'truncated': total > MAX_ROWS,
        }
        shop = {'name': shop_name, 'phone': shop_phone}
        return custom_response(True, 'Customer due reminders fetched successfully',
                               {'customers': rows, 'summary': summary, 'shop': shop, 'default_template': DEFAULT_TEMPLATE})
