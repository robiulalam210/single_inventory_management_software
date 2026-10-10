"""
Payroll API  (/api/payroll/…)  — শুধু Admin / Super Admin।

  GET  slips/?month=YYYY-MM&staff=&status=&page=   বেতন স্লিপ + summary
  POST slips/generate/ {month}                      এ মাসে যাদের স্লিপ নেই সবার জন্য বানায়
  GET/PATCH/DELETE slips/<id>/                      দেখা / (unpaid হলে) বদলানো / (unpaid হলে) মোছা
  POST slips/<id>/pay/ {account_id, payment_method, date}
  POST slips/<id>/unpay/                            বেতন দেওয়া বাতিল (টাকা account এ ফেরত)
  GET  advances/?staff=&open=1  ·  POST advances/   অগ্রিম
  DELETE advances/<id>/                             (কিছু কাটা না হলে) অগ্রিম বাতিল
  GET  report/?start=YYYY-MM&end=YYYY-MM            মাস/স্টাফ অনুযায়ী মোট
"""
import calendar
import math
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from accounts.models import Account
from core.models import Staff
from core.utils import custom_response
from expenses.models import Expense, ExpenseHead
from .models import SalaryAdvance, SalarySlip, ZERO

PAGE = 50
METHODS = {'cash', 'bank', 'mobile', 'card', 'other'}
SLIP_MONEY = ('basic', 'commission', 'bonus', 'other_addition', 'advance_deduction', 'other_deduction')


def _guard(request):
    u = request.user
    role = (getattr(u, 'role', '') or '').upper()
    allowed = u.is_superuser or role in ('SUPER_ADMIN', 'ADMIN')
    if not allowed:  # পরে permission list এ 'payroll' module যোগ করলে অন্য role কেও দেওয়া যাবে
        try:
            allowed = bool(u.has_permission('payroll', 'view'))
        except Exception:
            allowed = False
    if allowed:
        return None
    return custom_response(False, "You don't have permission to manage payroll.", None, http.HTTP_403_FORBIDDEN)


def _money(v, field, allow_zero=True):
    try:
        d = Decimal(str(v if v not in (None, '') else '0')).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        raise ValueError(f'{field}: enter a valid amount.')
    if d < 0 or (d == 0 and not allow_zero):
        raise ValueError(f'{field}: must be {"greater than" if not allow_zero else "at least"} 0.')
    return d


def _month(s):
    """'2026-10' (या '2026-10-15') → date(2026,10,1)"""
    try:
        y, m = str(s)[:7].split('-')
        return date(int(y), int(m), 1)
    except Exception:
        return None


def _month_end(d):
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def _name(staff):
    u = getattr(staff, 'user', None)
    return (getattr(u, 'full_name', '') or getattr(u, 'username', '') or f'Staff #{staff.id}') if u else f'Staff #{staff.id}'


def _head(name):
    head, _ = ExpenseHead.objects.get_or_create(name=name)
    return head


def _open_advance(staff_id):
    agg = SalaryAdvance.objects.filter(staff_id=staff_id).aggregate(a=Sum('amount'), d=Sum('deducted'))
    return (agg['a'] or ZERO) - (agg['d'] or ZERO)


def _slip(s, open_adv=None):
    return {
        'id': s.id, 'month': s.month.isoformat(), 'status': s.status,
        'staff_id': s.staff_id, 'staff_name': _name(s.staff),
        'designation': getattr(s.staff, 'designation', '') or '', 'employee_id': getattr(s.staff, 'employee_id', '') or '',
        'basic': str(s.basic), 'commission': str(s.commission), 'bonus': str(s.bonus), 'other_addition': str(s.other_addition),
        'advance_deduction': str(s.advance_deduction), 'other_deduction': str(s.other_deduction), 'net': str(s.net),
        'paid_date': s.paid_date.isoformat() if s.paid_date else None,
        'account_id': s.account_id, 'account_name': s.account.name if s.account else '',
        'payment_method': s.payment_method, 'note': s.note,
        'open_advance': str(open_adv) if open_adv is not None else None,
    }


def _adv(a):
    return {
        'id': a.id, 'staff_id': a.staff_id, 'staff_name': _name(a.staff), 'amount': str(a.amount), 'deducted': str(a.deducted),
        'remaining': str(a.remaining), 'date': a.date.isoformat(), 'account_name': a.account.name if a.account else '',
        'payment_method': a.payment_method, 'note': a.note,
    }


def _account(request, pk):
    try:
        return Account.objects.get(pk=pk, is_active=True)
    except (Account.DoesNotExist, ValueError, TypeError):
        return None


def _pay_expense(request, head_name, amount, account, method, when, note):
    """খরচ লিখলে Expense.save() নিজেই account থেকে টাকা কেটে Transaction বানায়; টাকা কম হলে ValidationError।"""
    exp = Expense(created_by=request.user, head=_head(head_name), amount=amount, account=account,
                  payment_method=method, expense_date=when, note=note)
    exp.save()
    return exp


class SlipListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        denied = _guard(request)
        if denied:
            return denied
        q = SalarySlip.objects.filter().select_related('staff', 'staff__user', 'account')
        m = _month(request.query_params.get('month'))
        if m:
            q = q.filter(month=m)
        if request.query_params.get('staff'):
            q = q.filter(staff_id=request.query_params['staff'])
        if request.query_params.get('status') in ('paid', 'unpaid'):
            q = q.filter(status=request.query_params['status'])
        agg = q.aggregate(net=Sum('net'), basic=Sum('basic'), add=Sum('commission'))
        paid = q.filter(status='paid').aggregate(n=Sum('net'))['n'] or ZERO
        total = agg['net'] or ZERO
        count = q.count()
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except ValueError:
            page = 1
        rows = list(q.order_by('staff__user__first_name', 'staff_id')[(page - 1) * PAGE: page * PAGE])
        adv = {r['staff_id']: (r['a'] or ZERO) - (r['d'] or ZERO) for r in
               SalaryAdvance.objects.filter().values('staff_id').annotate(a=Sum('amount'), d=Sum('deducted'))}
        data = {
            'results': [_slip(s, adv.get(s.staff_id, ZERO)) for s in rows], 'count': count, 'total_pages': max(1, math.ceil(count / PAGE)),
            'summary': {'slips': count, 'total_net': str(total), 'paid': str(paid), 'unpaid': str(total - paid),
                        'paid_count': q.filter(status='paid').count(), 'unpaid_count': q.filter(status='unpaid').count()},
        }
        return custom_response(True, 'Salary slips fetched.', data)


class SlipGenerateView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        denied = _guard(request)
        if denied:
            return denied
        m = _month(request.data.get('month'))
        if not m:
            return custom_response(False, 'Choose a month.', None, http.HTTP_400_BAD_REQUEST)
        if m > date.today().replace(day=1):
            return custom_response(False, "You can't prepare salary for a future month.", None, http.HTTP_400_BAD_REQUEST)
        have = set(SalarySlip.objects.filter(month=m).values_list('staff_id', flat=True))
        made = skipped = 0
        for st in Staff.objects.filter().select_related('user'):
            if st.id in have:
                continue
            joined = getattr(st, 'joining_date', None)
            left = getattr(st, 'leaving_date', None)
            active = getattr(st, 'is_currently_active', True)
            if (joined and joined > _month_end(m)) or (left and left < m) or (not active and not left) or not (st.salary or 0):
                skipped += 1
                continue
            s = SalarySlip(staff=st, month=m, basic=st.salary or ZERO, commission=st.commission or ZERO,
                           bonus=st.bonus or ZERO, created_by=request.user)
            s.recalc()
            s.save()
            made += 1
        return custom_response(True, f'{made} slip(s) prepared.', {'created': made, 'skipped': skipped}, http.HTTP_201_CREATED)


class SlipDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request, pk):
        return SalarySlip.objects.select_related('staff', 'staff__user', 'account').filter(pk=pk).first()

    def get(self, request, pk):
        denied = _guard(request)
        if denied:
            return denied
        s = self._get(request, pk)
        if not s:
            return custom_response(False, 'Slip not found.', None, http.HTTP_404_NOT_FOUND)
        return custom_response(True, 'OK', _slip(s, _open_advance(s.staff_id)))

    @transaction.atomic
    def patch(self, request, pk):
        denied = _guard(request)
        if denied:
            return denied
        s = self._get(request, pk)
        if not s:
            return custom_response(False, 'Slip not found.', None, http.HTTP_404_NOT_FOUND)
        if s.status == 'paid':
            return custom_response(False, 'This slip is already paid. Cancel the payment first to change it.', None, http.HTTP_400_BAD_REQUEST)
        try:
            for f in SLIP_MONEY:
                if f in request.data:
                    setattr(s, f, _money(request.data[f], f))
        except ValueError as e:
            return custom_response(False, str(e), None, http.HTTP_400_BAD_REQUEST)
        if 'note' in request.data:
            s.note = str(request.data['note'] or '')[:255]
        if s.advance_deduction > _open_advance(s.staff_id):
            return custom_response(False, f'Advance deduction is more than the advance still owed ({_open_advance(s.staff_id)}).', None, http.HTTP_400_BAD_REQUEST)
        if s.recalc() < 0:
            return custom_response(False, 'Deductions are more than the salary.', None, http.HTTP_400_BAD_REQUEST)
        s.save()
        return custom_response(True, 'Slip updated.', _slip(s, _open_advance(s.staff_id)))

    @transaction.atomic
    def delete(self, request, pk):
        denied = _guard(request)
        if denied:
            return denied
        s = self._get(request, pk)
        if not s:
            return custom_response(False, 'Slip not found.', None, http.HTTP_404_NOT_FOUND)
        if s.status == 'paid':
            return custom_response(False, 'A paid slip can’t be deleted. Cancel the payment first.', None, http.HTTP_400_BAD_REQUEST)
        s.delete()
        return custom_response(True, 'Slip deleted.', None)


class SlipPayView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        denied = _guard(request)
        if denied:
            return denied
        s = SalarySlip.objects.select_for_update().select_related('staff', 'staff__user').filter(pk=pk).first()
        if not s:
            return custom_response(False, 'Slip not found.', None, http.HTTP_404_NOT_FOUND)
        if s.status == 'paid':
            return custom_response(False, 'Already paid.', None, http.HTTP_400_BAD_REQUEST)
        acc = _account(request, request.data.get('account_id'))
        if not acc:
            return custom_response(False, 'Choose the account the salary is paid from.', None, http.HTTP_400_BAD_REQUEST)
        method = (request.data.get('payment_method') or 'cash').lower()
        if method not in METHODS:
            method = 'other'
        when = parse_date(str(request.data.get('date') or '')) or timezone.localdate()
        s.recalc()
        applied, left = [], s.advance_deduction
        if left > 0:  # সবচেয়ে পুরনো অগ্রিম আগে কাটে
            for a in SalaryAdvance.objects.select_for_update().filter(staff=s.staff).order_by('date', 'id'):
                take = min(a.remaining, left)
                if take > 0:
                    applied.append({'id': a.id, 'amount': str(take)})
                    left -= take
                if left <= 0:
                    break
            if left > 0:
                return custom_response(False, 'Advance deduction is more than the advance still owed.', None, http.HTTP_400_BAD_REQUEST)
        try:
            exp = None
            if s.net > 0:
                exp = _pay_expense(request, 'Salary', s.net, acc, method, when, f'Salary {s.month:%b %Y} — {_name(s.staff)}')
        except Exception as e:  # ValidationError: balance কম ইত্যাদি
            msg = '; '.join(getattr(e, 'messages', None) or [str(e)])
            return custom_response(False, msg, None, http.HTTP_400_BAD_REQUEST)
        for r in applied:
            a = SalaryAdvance.objects.get(pk=r['id'])
            a.deducted += Decimal(r['amount'])
            a.save(update_fields=['deducted'])
        s.status, s.paid_date, s.account, s.payment_method, s.expense, s.advance_applied = 'paid', when, acc, method, exp, applied
        s.save()
        return custom_response(True, 'Salary paid.', _slip(s))


class SlipUnpayView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        denied = _guard(request)
        if denied:
            return denied
        s = SalarySlip.objects.select_for_update().select_related('staff', 'staff__user').filter(pk=pk).first()
        if not s:
            return custom_response(False, 'Slip not found.', None, http.HTTP_404_NOT_FOUND)
        if s.status != 'paid':
            return custom_response(False, 'This slip is not paid.', None, http.HTTP_400_BAD_REQUEST)
        for r in s.advance_applied or []:
            a = SalaryAdvance.objects.filter(pk=r['id']).first()
            if a:
                a.deducted = max(ZERO, a.deducted - Decimal(r['amount']))
                a.save(update_fields=['deducted'])
        exp = s.expense
        s.status, s.paid_date, s.account, s.payment_method, s.expense, s.advance_applied = 'unpaid', None, None, '', None, []
        s.save()
        if exp:
            exp.delete()  # Expense.delete() টাকা account এ ফেরত দেয়
        return custom_response(True, 'Payment cancelled; the money is back in the account.', _slip(s))


class AdvanceListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        denied = _guard(request)
        if denied:
            return denied
        q = SalaryAdvance.objects.filter().select_related('staff', 'staff__user', 'account')
        if request.query_params.get('staff'):
            q = q.filter(staff_id=request.query_params['staff'])
        if request.query_params.get('open') in ('1', 'true'):
            q = q.filter(amount__gt=F('deducted'))
        rows = list(q[:500])
        bal = {}
        for r in SalaryAdvance.objects.filter().values('staff_id').annotate(a=Sum('amount'), d=Sum('deducted')):
            bal[r['staff_id']] = str((r['a'] or ZERO) - (r['d'] or ZERO))
        return custom_response(True, 'Advances fetched.', {'results': [_adv(a) for a in rows], 'balances': bal, 'count': len(rows)})

    @transaction.atomic
    def post(self, request):
        denied = _guard(request)
        if denied:
            return denied
        st = Staff.objects.filter(pk=request.data.get('staff_id')).select_related('user').first()
        if not st:
            return custom_response(False, 'Choose a staff member.', None, http.HTTP_400_BAD_REQUEST)
        try:
            amount = _money(request.data.get('amount'), 'Amount', allow_zero=False)
        except ValueError as e:
            return custom_response(False, str(e), None, http.HTTP_400_BAD_REQUEST)
        acc = _account(request, request.data.get('account_id'))
        if not acc:
            return custom_response(False, 'Choose the account the advance is paid from.', None, http.HTTP_400_BAD_REQUEST)
        method = (request.data.get('payment_method') or 'cash').lower()
        if method not in METHODS:
            method = 'other'
        when = parse_date(str(request.data.get('date') or '')) or timezone.localdate()
        note = str(request.data.get('note') or '')[:255]
        try:
            exp = _pay_expense(request, 'Salary Advance', amount, acc, method, when, f'Advance — {_name(st)}' + (f' ({note})' if note else ''))
        except Exception as e:
            return custom_response(False, '; '.join(getattr(e, 'messages', None) or [str(e)]), None, http.HTTP_400_BAD_REQUEST)
        a = SalaryAdvance.objects.create(staff=st, amount=amount, date=when, account=acc, payment_method=method,
                                         expense=exp, note=note, created_by=request.user)
        return custom_response(True, 'Advance recorded.', _adv(a), http.HTTP_201_CREATED)


class AdvanceDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def delete(self, request, pk):
        denied = _guard(request)
        if denied:
            return denied
        a = SalaryAdvance.objects.select_for_update().filter(pk=pk).first()
        if not a:
            return custom_response(False, 'Advance not found.', None, http.HTTP_404_NOT_FOUND)
        if a.deducted > 0:
            return custom_response(False, 'Part of this advance was already cut from a salary, so it can’t be cancelled.', None, http.HTTP_400_BAD_REQUEST)
        exp = a.expense
        a.delete()
        if exp:
            exp.delete()
        return custom_response(True, 'Advance cancelled; the money is back in the account.', None)


class ReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        denied = _guard(request)
        if denied:
            return denied
        today = date.today().replace(day=1)
        end = _month(request.query_params.get('end')) or today
        start = _month(request.query_params.get('start')) or date(end.year, 1, 1)
        q = SalarySlip.objects.filter(month__gte=start, month__lte=end).select_related('staff', 'staff__user')
        by = {}
        for s in q:
            r = by.setdefault(s.staff_id, {'staff_id': s.staff_id, 'staff_name': _name(s.staff), 'designation': getattr(s.staff, 'designation', '') or '',
                                           'months': 0, 'basic': ZERO, 'additions': ZERO, 'deductions': ZERO, 'net': ZERO, 'paid': ZERO})
            r['months'] += 1
            r['basic'] += s.basic
            r['additions'] += s.commission + s.bonus + s.other_addition
            r['deductions'] += s.advance_deduction + s.other_deduction
            r['net'] += s.net
            if s.status == 'paid':
                r['paid'] += s.net
        rows = sorted(by.values(), key=lambda r: r['staff_name'].lower())
        tot = {k: sum((r[k] for r in rows), ZERO) for k in ('basic', 'additions', 'deductions', 'net', 'paid')}
        adv = SalaryAdvance.objects.filter(date__gte=start, date__lte=_month_end(end)).aggregate(a=Sum('amount'))['a'] or ZERO
        for r in rows:
            for k in ('basic', 'additions', 'deductions', 'net', 'paid'):
                r[k] = str(r[k])
            r['unpaid'] = str(Decimal(r['net']) - Decimal(r['paid']))
        summary = {k: str(v) for k, v in tot.items()}
        summary.update(unpaid=str(tot['net'] - tot['paid']), advances_given=str(adv), staff=len(rows),
                       start=start.isoformat(), end=end.isoformat())
        return custom_response(True, 'Payroll report.', {'results': rows, 'summary': summary})


class StaffOptionsView(APIView):
    """অগ্রিম দেওয়ার সময় staff বাছাই — Staff id (user id না) আর বর্তমান বেতন।"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        denied = _guard(request)
        if denied:
            return denied
        rows = [{'id': st.id, 'name': _name(st), 'designation': getattr(st, 'designation', '') or '', 'salary': str(st.salary or ZERO)}
                for st in Staff.objects.filter().select_related('user')]
        rows.sort(key=lambda r: r['name'].lower())
        return custom_response(True, 'Staff fetched.', rows)
