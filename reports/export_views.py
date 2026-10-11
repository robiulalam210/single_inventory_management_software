# reports/export_views.py
"""
GET /api/reports/export/<key>/?fmt=xlsx|pdf&<report এর নিজের filter গুলো>

যে report এর যে filter (start, end, customer, status …) — ঠিক সেগুলোই দিলে সেই report এর পুরো ফলাফল
(পাতা ভাগ না করে) Excel বা PDF ফাইল হয়ে নামে। হিসাব বের করে report এর নিজের view — এখানে নতুন হিসাব নেই,
তাই screen ও ফাইলের সংখ্যা সবসময় এক।

দ্রষ্টব্য: `format` নামটা DRF নিজে content-negotiation এ ব্যবহার করে, তাই এখানে `fmt`।
"""
import logging

from django.http import Http404, HttpResponse, JsonResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from . import exports
from .perms import user_has_perm

logger = logging.getLogger(__name__)

CONTENT_TYPES = {
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'pdf': 'application/pdf',
}


def _business_name():
    try:
        from core.models import BusinessProfile
        return BusinessProfile.get().name or 'My Business'
    except Exception:  # business profile না থাকলেও export আটকাবে না
        return 'My Business'


def _rows_of(report):
    """view এর `report` — list, নয়তো {results: [...]}।"""
    if isinstance(report, dict):
        return list(report.get('results') or [])
    return list(report or [])


class ReportExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, key):
        cfg = exports.REPORT_EXPORTS.get(key)
        if not cfg:
            raise Http404('Unknown report')

        fmt = (request.GET.get('fmt') or 'xlsx').lower()
        if fmt not in CONTENT_TYPES:
            return JsonResponse({'status': False, 'message': "fmt must be 'xlsx' or 'pdf'", 'data': None}, status=400)

        if not user_has_perm(request.user, 'reports', 'view'):
            return JsonResponse({'status': False, 'message': 'You do not have permission to view reports.', 'data': None}, status=403)

        from . import views as report_views
        view_cls = getattr(report_views, cfg['view'])
        view = view_cls()
        view.pagination_class = None          # ফাইলে সব সারি যাবে, শুধু প্রথম পাতা নয়
        view.request, view.args, view.kwargs, view.format_kwarg = request, (), {}, None

        resp = view.get(request)
        body = getattr(resp, 'data', None) or {}
        if resp.status_code != 200 or not body.get('status', True):
            msg = body.get('message') or 'Could not build this report.'
            return JsonResponse({'status': False, 'message': msg, 'data': None}, status=resp.status_code if resp.status_code >= 400 else 400)
        data = body.get('data') or {}

        business = _business_name()
        try:
            if cfg.get('kind') == 'statement':
                dr = data.get('date_range') or {}
                period = exports.period_text(dr.get('start'), dr.get('end'))
                statement = exports.statement_from_data(data)
                args = (business, cfg['title'], period, [], [], None, statement)
            else:
                summary = data.get('summary') or {}
                dr = summary.get('date_range') or {}
                period = exports.period_text(dr.get('start'), dr.get('end'), cfg.get('dates', True))
                rows = _rows_of(data.get('report'))
                cards = [(label, summary.get(k), f) for label, k, f in cfg['cards'] if k in summary]
                args = (business, cfg['title'], period, cfg['cols'], rows, cards, None)

            content = exports.build_xlsx(*args) if fmt == 'xlsx' else exports.build_pdf(*args)
        except Exception as e:  # noqa: BLE001
            logger.exception('Report export failed: %s', key)
            return JsonResponse({'status': False, 'message': f'Export failed: {e}', 'data': None}, status=500)

        out = HttpResponse(content, content_type=CONTENT_TYPES[fmt])
        out['Content-Disposition'] = f'attachment; filename="{exports.safe_filename(key)}.{fmt}"'
        out['Cache-Control'] = 'no-store'
        return out
