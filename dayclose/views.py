"""
Day close API  (/api/day-close/ এর নিচে)

  GET  summary/?date=YYYY-MM-DD   — ওই দিনের সারাংশ + account ভিত্তিক expected + বন্ধ হয়ে থাকলে তার রেকর্ড
  GET  /                           — বন্ধ করা দিনের তালিকা (?page_size=)
  POST /   {date, counts:{account_id: amount}, note}   — দিন বন্ধ
  DELETE <id>/                     — আবার খোলা (শুধু Super Admin / Admin)

অনুমতি: দেখতে reports.view; বন্ধ করতে accounts.edit (Super Admin সবসময়)।
"""
from datetime import date as date_cls
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.utils import custom_response
from .models import DayClose
from . import services


def _can(user, module, action):
    return bool(user.is_superuser or user.has_permission(module, action))


def _deny():
    return custom_response(False, "You don't have permission for this.", None, 403)


def _row(c):
    return {
        'id': c.id, 'date': c.date.isoformat(), 'summary': c.summary, 'lines': c.lines,
        'total_expected': float(c.total_expected), 'total_counted': float(c.total_counted),
        'difference': float(c.difference), 'note': c.note,
        'closed_by': (c.closed_by.get_full_name() or c.closed_by.username) if c.closed_by_id else '',
        'closed_at': timezone.localtime(c.closed_at).isoformat(),
    }


def _parse_day(raw):
    if not raw:
        return timezone.localdate()
    try:
        return date_cls.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


class Summary(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _can(request.user, 'reports', 'view'):
            return _deny()
        day = _parse_day(request.query_params.get('date'))
        if day is None:
            return custom_response(False, 'Date must be YYYY-MM-DD.', None, 400)
        closed = DayClose.objects.filter(date=day).first()
        return custom_response(True, 'OK', {
            'summary': services.build_summary(day),
            'closed': _row(closed) if closed else None,
            'can_close': _can(request.user, 'accounts', 'edit'),
            'can_reopen': bool(request.user.is_superuser or getattr(request.user, 'role', '') in ('SUPER_ADMIN', 'ADMIN')),
        })


class CloseList(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _can(request.user, 'reports', 'view'):
            return _deny()
        try:
            size = max(1, min(int(request.query_params.get('page_size', 30)), 200))
        except ValueError:
            size = 30
        rows = [_row(c) for c in DayClose.objects.select_related('closed_by')[:size]]
        return custom_response(True, 'OK', {'results': rows})

    def post(self, request):
        if not _can(request.user, 'accounts', 'edit'):
            return _deny()
        day = _parse_day(request.data.get('date'))
        if day is None:
            return custom_response(False, 'Date must be YYYY-MM-DD.', None, 400)
        if day > timezone.localdate():
            return custom_response(False, "You can't close a day that hasn't happened yet.", None, 400)
        if DayClose.objects.filter(date=day).exists():
            return custom_response(False, 'This day is already closed.', None, 400)
        counts = request.data.get('counts') or {}
        if not isinstance(counts, dict):
            return custom_response(False, 'counts must be an object of account id → amount.', None, 400)
        for v in counts.values():
            if v in (None, ''):
                continue
            try:
                Decimal(str(v))
            except InvalidOperation:
                return custom_response(False, 'Counted amounts must be numbers.', None, 400)
        c = services.close_day(day, counts, (request.data.get('note') or '')[:500], request.user)
        return custom_response(True, 'Day closed.', _row(c), 201)


class CloseDetail(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        if not (request.user.is_superuser or getattr(request.user, 'role', '') in ('SUPER_ADMIN', 'ADMIN')):
            return _deny()
        deleted, _ = DayClose.objects.filter(pk=pk).delete()
        if not deleted:
            return custom_response(False, 'Not found.', None, 404)
        return custom_response(True, 'Day reopened.', None)
