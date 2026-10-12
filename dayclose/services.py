"""Day close এর হিসাব — একটা তারিখের সারাংশ + account ভিত্তিক ব্যালান্স।"""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from accounts.models import Account
from expenses.models import Expense
from income.models import Income
from money_receipts.models import MoneyReceipt
from purchases.models import Purchase
from returns.models import SalesReturn
from sales.models import Sale
from transactions.models import Transaction

ZERO = Decimal('0.00')


def _f(v):
    return float(v or ZERO)


def day_bounds(day):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    return start, start + timedelta(days=1)


def _balance_before(account, moment):
    """account এর ব্যালান্স একটা মুহূর্তের আগ পর্যন্ত (completed লেনদেন, opening সহ)।"""
    t = Transaction.objects.filter(account=account, status='completed', transaction_date__lt=moment)
    cr = t.filter(transaction_type='credit').aggregate(s=Sum('amount'))['s'] or ZERO
    dr = t.filter(transaction_type='debit').aggregate(s=Sum('amount'))['s'] or ZERO
    return cr - dr


def build_summary(day):
    start, end = day_bounds(day)

    sales = Sale.objects.filter(sale_date__gte=start, sale_date__lt=end)
    s = sales.aggregate(n=Count('id'), total=Sum('grand_total'), paid=Sum('paid_amount'), due=Sum('due_amount'))
    returns = SalesReturn.objects.filter(return_date=day).exclude(status='cancelled').aggregate(
        n=Count('id'), total=Sum('return_amount'))
    purchases = Purchase.objects.filter(purchase_date=day).aggregate(
        n=Count('id'), total=Sum('grand_total'), paid=Sum('paid_amount'), due=Sum('due_amount'))
    expenses = Expense.objects.filter(expense_date=day).aggregate(n=Count('id'), total=Sum('amount'))
    income = Income.objects.filter(income_date=day).aggregate(n=Count('id'), total=Sum('amount'))
    receipts = MoneyReceipt.objects.filter(payment_date__gte=start, payment_date__lt=end,
                                           payment_status='completed').aggregate(n=Count('id'), total=Sum('amount'))

    accounts = []
    for a in Account.objects.filter(is_active=True).order_by('name'):
        tx = Transaction.objects.filter(account=a, status='completed', is_opening_balance=False,
                                        transaction_date__gte=start, transaction_date__lt=end)
        money_in = tx.filter(transaction_type='credit').aggregate(s=Sum('amount'))['s'] or ZERO
        money_out = tx.filter(transaction_type='debit').aggregate(s=Sum('amount'))['s'] or ZERO
        opening = _balance_before(a, start)
        accounts.append({
            'account_id': a.id, 'name': a.name, 'type': a.ac_type,
            'opening': _f(opening), 'money_in': _f(money_in), 'money_out': _f(money_out),
            'expected': _f(opening + money_in - money_out),
        })

    net_sales = (s['total'] or ZERO) - (returns['total'] or ZERO)
    return {
        'date': day.isoformat(),
        'sales': {'count': s['n'] or 0, 'total': _f(s['total']), 'paid': _f(s['paid']), 'due': _f(s['due'])},
        'returns': {'count': returns['n'] or 0, 'total': _f(returns['total'])},
        'net_sales': _f(net_sales),
        'purchases': {'count': purchases['n'] or 0, 'total': _f(purchases['total']),
                      'paid': _f(purchases['paid']), 'due': _f(purchases['due'])},
        'expenses': {'count': expenses['n'] or 0, 'total': _f(expenses['total'])},
        'income': {'count': income['n'] or 0, 'total': _f(income['total'])},
        'receipts': {'count': receipts['n'] or 0, 'total': _f(receipts['total'])},
        'accounts': accounts,
        'total_expected': round(sum(x['expected'] for x in accounts), 2),
    }


def close_day(day, counts, note, user):
    """counts = {account_id: counted_amount}; যে account এর সংখ্যা নেই তার counted = expected ধরা হয় না — বাদ।"""
    from .models import DayClose
    summary = build_summary(day)
    lines, exp_total, cnt_total = [], Decimal('0'), Decimal('0')
    for a in summary['accounts']:
        raw = counts.get(str(a['account_id']), counts.get(a['account_id']))
        if raw in (None, ''):
            continue
        counted = Decimal(str(raw))
        expected = Decimal(str(a['expected']))
        lines.append({**a, 'counted': float(counted), 'difference': float(counted - expected)})
        exp_total += expected
        cnt_total += counted
    return DayClose.objects.create(
        date=day, summary=summary, lines=lines, total_expected=exp_total, total_counted=cnt_total,
        difference=cnt_total - exp_total, note=note or '', closed_by=user)
