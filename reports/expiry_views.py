# reports/expiry_views.py — মেয়াদ শেষ হওয়ার সতর্কতা (ব্যাচ/মেয়াদ ট্র্যাকিং)
from rest_framework.response import Response

from core.base_viewsets import BaseReportView
from core.utils import custom_response
from purchases.batches import expiry_report, write_off_batch
from purchases.models import ProductBatch


def _int(request, key, default, lo, hi):
    try:
        v = int(request.GET.get(key, default))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


class ExpiryAlertsView(BaseReportView):
    """
    GET /api/reports/expiry-alerts/?days=30&status=alerts&limit=6
      days   — "শিগগিরই শেষ" ধরার সীমা, ১–৩৬৫ (ডিফল্ট ৩০)
      status — alerts (ডিফল্ট: পেরোনো + শিগগিরই) | all | expired | expiring | ok
      limit  — সর্বোচ্চ কয়টা ব্যাচ পাঠাবে (ডিফল্ট সব)
    """

    def get(self, request):
        try:
            days = _int(request, 'days', 30, 1, 365)
            status = request.GET.get('status', 'alerts')
            if status not in ('alerts', 'all', 'expired', 'expiring', 'ok'):
                status = 'alerts'
            limit = _int(request, 'limit', 0, 0, 1000) or None
            return custom_response(True, "Expiry alerts fetched successfully",
                                   expiry_report(days=days, status=status, limit=limit))
        except Exception as e:
            return self.handle_exception(e)


class ExpiryWriteOffView(BaseReportView):
    """POST /api/reports/expiry-alerts/<batch_id>/write-off/  {"reason": "..."}"""

    def post(self, request, batch_id):
        user = request.user
        if not (user.is_superuser or user.has_permission('products', 'edit')):
            return custom_response(False, "You don't have permission to write off stock.", None, 403)
        try:
            result = write_off_batch(batch_id, reason=str(request.data.get('reason') or ''), user=user)
            return custom_response(True, f"{result['written_off']} of {result['product']} written off", result)
        except ProductBatch.DoesNotExist:
            return custom_response(False, "Batch not found.", None, 404)
        except ValueError as e:
            return custom_response(False, str(e), None, 400)
        except Exception as e:
            return self.handle_exception(e)
