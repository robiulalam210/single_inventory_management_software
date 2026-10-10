import json
import logging
import uuid

from django.db import IntegrityError
from django.http import JsonResponse

from . import context

logger = logging.getLogger(__name__)

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class AuditContextMiddleware:
    """Signal handler যাতে জানতে পারে কে / কোন device থেকে request করেছে।"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = context.set_request(request)
        try:
            return self.get_response(request)
        finally:
            context.reset_request(token)


class IdempotencyMiddleware:
    """
    Duplicate প্রতিরোধ (mobile ও desktop দুটোর জন্যই)।

    App প্রতিটা write request এ `X-Idempotency-Key: <uuid>` header পাঠায়।
    - প্রথমবার: request স্বাভাবিকভাবে চলে, সফল হলে ফলাফল সংরক্ষণ হয়।
    - একই key আবার এলে (double tap, timeout এর পর retry, offline queue replay):
      নতুন করে কিছু save হয় না, আগের ফলাফলটাই ফেরত যায়।
    """

    SKIP_PREFIXES = ("/api/sync/push",)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        key = request.META.get("HTTP_X_IDEMPOTENCY_KEY")
        if request.method not in WRITE_METHODS or not key or request.path.startswith(self.SKIP_PREFIXES):
            return self.get_response(request)
        try:
            op_id = uuid.UUID(str(key))
        except ValueError:
            return self.get_response(request)

        from .models import ProcessedOperation

        existing = ProcessedOperation.objects.filter(op_id=op_id, status=ProcessedOperation.STATUS_APPLIED).first()
        if existing:
            resp = JsonResponse(existing.response_body or {}, status=existing.response_status, safe=False)
            resp["X-Idempotent-Replay"] = "true"
            return resp

        response = self.get_response(request)

        if 200 <= response.status_code < 300:
            try:
                body = json.loads(response.content.decode("utf-8")) if response.content else {}
            except Exception:
                body = None
            user = getattr(request, "user", None)
            user = user if getattr(user, "is_authenticated", False) else None
            try:
                ProcessedOperation.objects.create(
                    op_id=op_id,
                    user=user,
                    method=request.method,
                    path=request.path[:255],
                    server_id=_extract_id(body),
                    status=ProcessedOperation.STATUS_APPLIED,
                    response_status=response.status_code,
                    response_body=body,
                )
            except IntegrityError:
                pass  # একই key এর আরেকটা request প্রায় একই সময়ে শেষ হয়েছে
            except Exception:
                logger.exception("Idempotency record failed")
        return response


def _extract_id(body):
    """Response এর ভিতর থেকে তৈরি হওয়া record এর id খোঁজা (data.id / id / data.data.id)।"""
    node = body
    for _ in range(3):
        if not isinstance(node, dict):
            return None
        if isinstance(node.get("id"), int):
            return node["id"]
        node = node.get("data")
    return None
