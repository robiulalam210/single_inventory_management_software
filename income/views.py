"""
Income (অন্যান্য আয়) — বিক্রি ছাড়া যে টাকা আসে: ভাড়া, কমিশন, ভর্তুকি ইত্যাদি।
অনুমতি: Accounts module (menu তেও Income, Accounts এর অনুমতিতে দেখায়)।

  GET/POST          /api/income-heads/
  PATCH/DELETE      /api/income-heads/<id>/           আয় থাকলে মোছে না, বন্ধ করে
  GET/POST          /api/incomes/?search=&start_date=&end_date=&head_id=&account_id=
  GET/PATCH/DELETE  /api/incomes/<id>/                টাকা/account বদলালে বা মুছলে account এর হিসাব উল্টে যায়
  GET               /api/incomes/summary/?start_date=&end_date=
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q, Sum
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.utils import custom_response
from .models import Income, IncomeHead
from .serializers import IncomeSerializer, IncomeHeadSerializer, IncomeCreateSerializer


def _deny(request, action):
    u = request.user
    if getattr(u, 'role', '') == 'SUPER_ADMIN' or u.is_superuser or u.has_permission('accounts', action):
        return None
    verb = {'view': 'see', 'create': 'add', 'edit': 'change', 'delete': 'delete'}[action]
    return custom_response(False, f"You don't have permission to {verb} income.", None, status.HTTP_403_FORBIDDEN)


def _msg(e):
    if isinstance(e, DjangoValidationError):
        return ' '.join(e.messages)
    return str(e)


def _check_refs(data):
    """head আর account নিজের কোম্পানির কিনা — আগে অন্য কোম্পানির head বসানো যেত"""
    from accounts.models import Account
    head = data.get('head')
    if head not in (None, '', 'null') and not IncomeHead.objects.filter(id=head).exists():
        return {'head': ['Pick one of your income heads.']}
    acc = data.get('account')
    if acc not in (None, '', 'null') and not Account.objects.filter(id=acc).exists():
        return {'account': ['Pick one of your accounts.']}
    return None


class IncomeHeadListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        heads = IncomeHead.objects.filter().annotate(
            income_count=Count('income', distinct=True), income_total=Sum('income__amount')
        ).order_by('name')
        data = IncomeHeadSerializer(heads, many=True).data
        for row, h in zip(data, heads):
            row['income_count'] = h.income_count
            row['income_total'] = str(h.income_total or 0)
        return custom_response(True, "Income heads fetched successfully.", data, status.HTTP_200_OK)

    def post(self, request):
        denied = _deny(request, 'create')
        if denied:
            return denied
        name = (request.data.get('name') or '').strip()
        if not name:
            return custom_response(False, "Validation Error.", {'name': ['Give the income head a name.']}, status.HTTP_400_BAD_REQUEST)
        if IncomeHead.objects.filter(name__iexact=name).exists():
            return custom_response(False, "Validation Error.", {'name': ['This income head already exists.']}, status.HTTP_400_BAD_REQUEST)
        data = request.data.copy()
        data['name'] = name
        serializer = IncomeHeadSerializer(data=data)
        if serializer.is_valid():
            serializer.save(created_by=request.user)
            return custom_response(True, "Income head created successfully.", serializer.data, status.HTTP_201_CREATED)
        return custom_response(False, "Validation Error.", serializer.errors, status.HTTP_400_BAD_REQUEST)


class IncomeHeadDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request, pk):
        return IncomeHead.objects.filter(id=pk).first()

    def get(self, request, pk):
        head = self._get(request, pk)
        if not head:
            return custom_response(False, "Income head not found.", None, status.HTTP_404_NOT_FOUND)
        return custom_response(True, "Income head fetched successfully.", IncomeHeadSerializer(head).data, status.HTTP_200_OK)

    def patch(self, request, pk):
        denied = _deny(request, 'edit')
        if denied:
            return denied
        head = self._get(request, pk)
        if not head:
            return custom_response(False, "Income head not found.", None, status.HTTP_404_NOT_FOUND)
        data = {k: v for k, v in request.data.items() if k in ('name', 'is_active')}
        if 'name' in data:
            data['name'] = (data['name'] or '').strip()
            if not data['name']:
                return custom_response(False, "Validation Error.", {'name': ['Give the income head a name.']}, status.HTTP_400_BAD_REQUEST)
            if IncomeHead.objects.filter(name__iexact=data['name']).exclude(pk=head.pk).exists():
                return custom_response(False, "Validation Error.", {'name': ['This income head already exists.']}, status.HTTP_400_BAD_REQUEST)
        serializer = IncomeHeadSerializer(head, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return custom_response(True, "Income head updated successfully.", serializer.data, status.HTTP_200_OK)
        return custom_response(False, "Validation error.", serializer.errors, status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        denied = _deny(request, 'delete')
        if denied:
            return denied
        head = self._get(request, pk)
        if not head:
            return custom_response(False, "Income head not found.", None, status.HTTP_404_NOT_FOUND)
        # আয় থাকলে মুছলে সেই আয়গুলোর head হারিয়ে যেত (SET_NULL) — তাই বন্ধ করি
        if Income.objects.filter(head=head).exists():
            head.is_active = False
            head.save(update_fields=['is_active'])
            return custom_response(True, f"{head.name} has income recorded, so it was turned off instead of deleted.", None, status.HTTP_200_OK)
        head.delete()
        return custom_response(True, "Income head deleted successfully.", None, status.HTTP_204_NO_CONTENT)


def _filtered(request):
    qs = Income.objects.filter().select_related('head', 'account', 'created_by')
    p = request.query_params
    search = (p.get('search') or '').strip()
    if search:
        q = Q(note__icontains=search) | Q(invoice_number__icontains=search) | Q(head__name__icontains=search)
        try:
            q |= Q(amount=float(search.replace(',', '')))
        except ValueError:
            pass
        qs = qs.filter(q)
    if p.get('start_date'):
        qs = qs.filter(income_date__gte=p['start_date'])
    if p.get('end_date'):
        qs = qs.filter(income_date__lte=p['end_date'])
    if p.get('head_id'):
        qs = qs.filter(head_id=p['head_id'])
    if p.get('account_id'):
        qs = qs.filter(account_id=p['account_id'])
    return qs


class IncomeListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        denied = _deny(request, 'view')
        if denied:
            return denied
        incomes = _filtered(request).order_by('-income_date', '-id')
        return custom_response(True, "Income fetched successfully.", IncomeSerializer(incomes, many=True).data, status.HTTP_200_OK)

    def post(self, request):
        denied = _deny(request, 'create')
        if denied:
            return denied
        bad = _check_refs(request.data)
        if bad:
            return custom_response(False, "Validation Error.", bad, status.HTTP_400_BAD_REQUEST)
        data = request.data.copy()
        serializer = IncomeCreateSerializer(data=data, context={'request': request})
        if serializer.is_valid():
            try:
                income = serializer.save(created_by=request.user)
            except Exception as e:
                return custom_response(False, _msg(e), None, status.HTTP_400_BAD_REQUEST)
            return custom_response(True, "Income created successfully.", IncomeSerializer(income).data, status.HTTP_201_CREATED)
        return custom_response(False, "Validation Error.", serializer.errors, status.HTTP_400_BAD_REQUEST)


class IncomeDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request, pk):
        return Income.objects.filter(pk=pk).select_related('head', 'account').first()

    def get(self, request, pk):
        denied = _deny(request, 'view')
        if denied:
            return denied
        inc = self._get(request, pk)
        if not inc:
            return custom_response(False, "Income not found.", None, status.HTTP_404_NOT_FOUND)
        data = IncomeSerializer(inc).data
        data['transactions'] = [
            {'id': t.id, 'transaction_no': t.transaction_no, 'type': t.transaction_type, 'amount': str(t.amount),
             'status': t.status, 'account': t.account.name if t.account else '', 'date': t.transaction_date.isoformat() if t.transaction_date else None,
             'description': t.description}
            for t in inc.transactions.select_related('account').order_by('id')
        ]
        return custom_response(True, "Income fetched successfully.", data, status.HTTP_200_OK)

    def patch(self, request, pk):
        denied = _deny(request, 'edit')
        if denied:
            return denied
        inc = self._get(request, pk)
        if not inc:
            return custom_response(False, "Income not found.", None, status.HTTP_404_NOT_FOUND)
        bad = _check_refs(request.data)
        if bad:
            return custom_response(False, "Validation Error.", bad, status.HTTP_400_BAD_REQUEST)
        data = {k: v for k, v in request.data.items() if k in ('head', 'amount', 'account', 'income_date', 'note', 'payment_method')}
        serializer = IncomeCreateSerializer(inc, data=data, partial=True, context={'request': request})
        if not serializer.is_valid():
            return custom_response(False, "Validation Error.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        try:
            inc = serializer.save()
        except Exception as e:
            # যেমন: আয়ের টাকা ইতিমধ্যে খরচ হয়ে গেছে, তাই কমানো যাচ্ছে না
            return custom_response(False, _msg(e), None, status.HTTP_400_BAD_REQUEST)
        return custom_response(True, "Income updated.", IncomeSerializer(inc).data, status.HTTP_200_OK)

    def delete(self, request, pk):
        denied = _deny(request, 'delete')
        if denied:
            return denied
        inc = self._get(request, pk)
        if not inc:
            return custom_response(False, "Income not found.", None, status.HTTP_404_NOT_FOUND)
        label = inc.invoice_number
        try:
            inc.delete()
        except Exception as e:
            return custom_response(False, _msg(e), None, status.HTTP_400_BAD_REQUEST)
        return custom_response(True, f"{label} deleted. The money was taken back out of the account.", None, status.HTTP_200_OK)


class IncomeSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        denied = _deny(request, 'view')
        if denied:
            return denied
        qs = _filtered(request)
        tot = qs.aggregate(total=Sum('amount'), count=Count('id'))
        by_head = list(qs.values('head_id', 'head__name').annotate(total=Sum('amount'), count=Count('id')).order_by('-total'))
        by_account = list(qs.values('account_id', 'account__name').annotate(total=Sum('amount')).order_by('-total'))
        return custom_response(True, "Income summary", {
            'total': str(tot['total'] or 0), 'count': tot['count'],
            'by_head': [{'id': r['head_id'], 'name': r['head__name'] or 'No head', 'total': str(r['total']), 'count': r['count']} for r in by_head],
            'by_account': [{'id': r['account_id'], 'name': r['account__name'] or 'No account', 'total': str(r['total'])} for r in by_account],
        }, status.HTTP_200_OK)
