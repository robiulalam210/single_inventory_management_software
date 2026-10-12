"""
Stock adjustment & stocktake API  (সব /api/stock/ এর নিচে)

  GET  adjustments/          ?q=&product=&reason=&start=&end=&page=&page_size=   — ইতিহাস + মোট
  POST adjustments/          {product_id, new_qty | change, reason, note}        — এক পণ্যের স্টক ঠিক করা
  GET  counts/               ?status=                                            — গণনার তালিকা
  POST counts/               {title?, category_id?, note?}                       — নতুন গণনা শুরু (snapshot)
  GET  counts/<id>/                                                              — লাইনসহ বিস্তারিত
  POST counts/<id>/count/    {rows: [{line_id|product_id, counted_qty|null}]}    — গণনা সেভ
  POST counts/<id>/apply/                                                        — পার্থক্য স্টকে বসানো
  POST counts/<id>/cancel/                                                       — বাতিল (স্টক বদলায় না)

অনুমতি: দেখতে products.view; বদলাতে products.edit (Super Admin সবসময়)।
"""
from datetime import datetime

from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.utils import custom_response
from .models import StockAdjustment, Stocktake
from . import services


def _can(user, action):
    return bool(user.is_superuser or user.has_permission('products', action))


def _deny(msg="You don't have permission for this."):
    return custom_response(False, msg, None, 403)


def _local(dt):
    return timezone.localtime(dt).isoformat() if dt else None


def _adj(a):
    return {
        'id': a.id, 'number': a.number, 'product_id': a.product_id, 'product_name': a.product_name, 'sku': a.sku,
        'qty_before': a.qty_before, 'qty_after': a.qty_after, 'change': a.change,
        'unit_cost': float(a.unit_cost), 'value_change': float(a.value_change),
        'reason': a.reason, 'reason_label': a.get_reason_display(), 'note': a.note,
        'stocktake_id': a.stocktake_id, 'stocktake_number': a.stocktake.number if a.stocktake_id else '',
        'created_by': (a.created_by.get_full_name() or a.created_by.username) if a.created_by_id else '',
        'created_at': _local(a.created_at),
    }


def _st_head(st, with_summary=True):
    d = {
        'id': st.id, 'number': st.number, 'title': st.title, 'note': st.note, 'status': st.status,
        'status_label': st.get_status_display(), 'category_id': st.category_id, 'category_name': st.category_name,
        'created_by': (st.created_by.get_full_name() or st.created_by.username) if st.created_by_id else '',
        'created_at': _local(st.created_at),
        'applied_by': (st.applied_by.get_full_name() or st.applied_by.username) if st.applied_by_id else '',
        'applied_at': _local(st.applied_at),
    }
    if with_summary:
        d['summary'] = services.summary(st)
    return d


def _run(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except ValueError as e:
        return custom_response(False, str(e), None, 400)


class AdjustmentListCreate(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _can(request.user, 'view'):
            return _deny()
        g = request.GET
        qs = StockAdjustment.objects.select_related('created_by', 'stocktake')
        if g.get('product'):
            qs = qs.filter(product_id=g['product'])
        if g.get('reason'):
            qs = qs.filter(reason=g['reason'])
        if g.get('q'):
            qs = qs.filter(Q(product_name__icontains=g['q']) | Q(sku__icontains=g['q']) | Q(number__icontains=g['q'])
                           | Q(note__icontains=g['q']))
        for key, op in (('start', 'gte'), ('end', 'lte')):
            if g.get(key):
                try:
                    d = datetime.strptime(g[key], '%Y-%m-%d').date()
                except ValueError:
                    continue
                qs = qs.filter(**{f'created_at__date__{op}': d})
        agg = qs.aggregate(total=Sum('value_change'))
        loss = qs.filter(change__lt=0).aggregate(v=Sum('value_change'))['v'] or 0
        gain = qs.filter(change__gt=0).aggregate(v=Sum('value_change'))['v'] or 0
        try:
            page = max(1, int(g.get('page', 1)))
            size = max(1, min(100, int(g.get('page_size', 30))))
        except ValueError:
            page, size = 1, 30
        count = qs.count()
        rows = [_adj(a) for a in qs[(page - 1) * size: page * size]]
        return custom_response(True, 'Stock adjustments fetched', {
            'count': count, 'page': page, 'total_pages': max(1, -(-count // size)), 'results': rows,
            'totals': {'net_value': float(agg['total'] or 0), 'loss_value': float(-loss), 'gain_value': float(gain)},
            'reasons': [{'key': k, 'label': v} for k, v in StockAdjustment.REASONS if k != 'count'] +
                       [{'key': 'count', 'label': 'Stock count'}],
        })

    def post(self, request):
        if not _can(request.user, 'edit'):
            return _deny("You don't have permission to change stock.")
        d = request.data
        reason = d.get('reason') or 'other'
        if reason == 'count':
            return custom_response(False, "'Stock count' is only used by a Stocktake.", None, 400)
        res = _run(services.adjust_stock, d.get('product_id'), request.user,
                   new_qty=d.get('new_qty'), change=d.get('change'), reason=reason, note=d.get('note') or '')
        if not isinstance(res, StockAdjustment):
            return res
        sign = '+' if res.change > 0 else ''
        return custom_response(True, f"{res.product_name}: {res.qty_before} → {res.qty_after} ({sign}{res.change})",
                               _adj(res), 201)


class CountListCreate(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _can(request.user, 'view'):
            return _deny()
        qs = Stocktake.objects.select_related('created_by', 'applied_by')
        if request.GET.get('status') in ('draft', 'applied', 'cancelled'):
            qs = qs.filter(status=request.GET['status'])
        return custom_response(True, 'Stock counts fetched', [_st_head(s) for s in qs[:200]])

    def post(self, request):
        if not _can(request.user, 'edit'):
            return _deny("You don't have permission to start a count.")
        d = request.data
        res = _run(services.start_stocktake, request.user, d.get('title') or '', d.get('category_id') or None,
                   d.get('note') or '')
        if not isinstance(res, Stocktake):
            return res
        return custom_response(True, f"{res.number} started with {res.lines.count()} products", _st_head(res), 201)


def _get(pk):
    return Stocktake.objects.select_related('created_by', 'applied_by').filter(pk=pk).first()


class CountDetail(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not _can(request.user, 'view'):
            return _deny()
        st = _get(pk)
        if st is None:
            return custom_response(False, 'Count not found.', None, 404)
        from products.models import Product
        lines = list(st.lines.all())
        now = dict(Product.objects.filter(id__in=[l.product_id for l in lines if l.product_id])
                   .values_list('id', 'stock_qty')) if st.status == Stocktake.DRAFT else {}
        out = []
        for l in lines:
            cur = now.get(l.product_id)
            out.append({
                'id': l.id, 'product_id': l.product_id, 'name': l.product_name, 'sku': l.sku,
                'category': l.category_name, 'system_qty': l.system_qty, 'counted_qty': l.counted_qty,
                'variance': l.variance, 'unit_cost': float(l.unit_cost),
                'system_now': cur, 'moved': cur is not None and cur != l.system_qty,
                'applied_change': l.applied_change,
            })
        d = _st_head(st)
        d['lines'] = out
        return custom_response(True, 'Count fetched', d)


class CountSave(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not _can(request.user, 'edit'):
            return _deny("You don't have permission to count stock.")
        if not Stocktake.objects.filter(pk=pk).exists():
            return custom_response(False, 'Count not found.', None, 404)
        rows = request.data.get('rows')
        if not isinstance(rows, list) or not rows:
            return custom_response(False, 'Send the counted rows.', None, 400)
        res = _run(services.save_counts, pk, rows)
        return res if not isinstance(res, dict) else custom_response(True, 'Saved', res)


class CountApply(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not _can(request.user, 'edit'):
            return _deny("You don't have permission to apply a count.")
        if not Stocktake.objects.filter(pk=pk).exists():
            return custom_response(False, 'Count not found.', None, 404)
        res = _run(services.apply_stocktake, pk, request.user)
        if not isinstance(res, dict):
            return res
        return custom_response(True, f"Stock matched — {res['adjusted']} product{'s' if res['adjusted'] != 1 else ''} adjusted", res)


class CountCancel(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not _can(request.user, 'edit'):
            return _deny()
        if not Stocktake.objects.filter(pk=pk).exists():
            return custom_response(False, 'Count not found.', None, 404)
        res = _run(services.cancel_stocktake, pk)
        return res if not isinstance(res, Stocktake) else custom_response(True, 'Count cancelled. Stock was not changed.', _st_head(res))
