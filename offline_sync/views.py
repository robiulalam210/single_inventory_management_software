import datetime
import json
import logging
import uuid
from collections import OrderedDict

from django.db import transaction
from django.db.models import Count, Max, Q
from django.urls import Resolver404, resolve
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from . import context
from .models import ChangeLog, Device, ProcessedOperation, SyncIssue
from .registry import OFFLINE_WRITE_ENDPOINTS, REMAP_KEYS, SYNC_ENTITIES, SYNC_ORDER
from .utils import entity_queryset, serialize_entities, touch

logger = logging.getLogger(__name__)

# Transaction commit এর দেরির কারণে কোনো change যেন বাদ না পড়ে, তাই খুব নতুন row
# পরের pull এ দেওয়া হয় (একই data দুইবার এলে ক্ষতি নেই — desktop upsert করে)।
PULL_SAFETY_LAG = datetime.timedelta(seconds=15)
MAX_PUSH_OPS = 100


def ok(data=None, message="", code=200):
    return Response({"status": True, "message": message, "data": data}, status=code)


def fail(message, code=400, data=None):
    return Response({"status": False, "message": message, "data": data}, status=code)


def _device_for(request, device_id=None):
    if not device_id:
        device_id = request.META.get("HTTP_X_DEVICE_ID")
    if not device_id and isinstance(getattr(request, "data", None), dict):
        device_id = request.data.get("device_id")
    if not device_id:
        return None
    try:
        return Device.objects.filter(device_id=uuid.UUID(str(device_id)), is_active=True).first()
    except ValueError:
        return None


def _safe_cursor():
    cutoff = timezone.now() - PULL_SAFETY_LAG
    return ChangeLog.objects.filter(created_at__lt=cutoff).aggregate(m=Max("id"))["m"] or 0


# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------
class DeviceRegisterView(APIView):
    """
    Desktop প্রথমবার (এবং প্রতিবার online login এর পর) এটা ডাকে।
    ফলাফল: device code (D1, D2...) — offline invoice number এর prefix।
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            device_uuid = uuid.UUID(str(request.data.get("device_id")))
        except (TypeError, ValueError):
            return fail("Valid device_id (UUID) is required")

        device = Device.objects.filter(device_id=device_uuid).first()

        with transaction.atomic():
            if not device:
                used = set(Device.objects.select_for_update().values_list("code", flat=True))
                n = 1
                while f"D{n}" in used:
                    n += 1
                device = Device.objects.create(device_id=device_uuid, code=f"D{n}")
            device.name = str(request.data.get("name", device.name))[:120]
            device.platform = str(request.data.get("platform", device.platform))[:30]
            device.app_version = str(request.data.get("app_version", device.app_version))[:30]
            device.last_seen_at = timezone.now()
            device.is_active = True
            device.save()
            device.allowed_users.add(request.user)

        return ok({
            "device_code": device.code,
            "device_id": str(device.device_id),
            "server_time": timezone.now().isoformat(),
        }, "Device registered")


# ---------------------------------------------------------------------------
# Initial setup: manifest + bootstrap
# ---------------------------------------------------------------------------
class ManifestView(APIView):
    """প্রথম setup এর শুরুতে: কোন কোন data কত রেকর্ড, আর কোন cursor থেকে পরে pull করতে হবে।"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cursor = _safe_cursor()  # snapshot এর আগে cursor নেওয়া হয় → মাঝের change বাদ যায় না
        entities = [{"entity": e, "count": entity_queryset(e).count()} for e in SYNC_ORDER]
        return ok({"cursor": cursor, "entities": entities, "server_time": timezone.now().isoformat()})


class BootstrapView(APIView):
    """একটা entity এর সব data page আকারে (প্রথম setup / দৈনিক full refresh)।"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        entity = request.query_params.get("entity")
        if entity not in SYNC_ENTITIES:
            return fail("Unknown entity")
        try:
            page = max(int(request.query_params.get("page", 1)), 1)
            page_size = min(max(int(request.query_params.get("page_size", 300)), 1), 1000)
        except ValueError:
            return fail("Invalid page")
        qs = entity_queryset(entity)
        total = qs.count()
        start = (page - 1) * page_size
        objects = list(qs[start:start + page_size])
        return ok({
            "entity": entity,
            "page": page,
            "total": total,
            "has_more": start + page_size < total,
            "items": serialize_entities(entity, objects, request),
        })


# ---------------------------------------------------------------------------
# Pull: server → desktop
# ---------------------------------------------------------------------------
class PullView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            cursor = int(request.query_params.get("cursor", 0))
            limit = min(max(int(request.query_params.get("limit", 500)), 1), 2000)
        except ValueError:
            return fail("Invalid cursor")

        cutoff = timezone.now() - PULL_SAFETY_LAG
        rows = list(
            ChangeLog.objects.filter(id__gt=cursor, created_at__lt=cutoff)
            .order_by("id").values("id", "entity", "object_id")[:limit]
        )
        next_cursor = rows[-1]["id"] if rows else cursor

        touched = OrderedDict()
        for r in rows:
            if r["entity"] in SYNC_ENTITIES:
                touched.setdefault(r["entity"], set()).add(r["object_id"])

        changes = []
        for entity, ids in touched.items():
            int_ids = [int(i) for i in ids if str(i).lstrip("-").isdigit()]
            objects = list(entity_queryset(entity).filter(pk__in=int_ids))
            found = {o.pk for o in objects}
            for item in serialize_entities(entity, objects, request):
                changes.append({"entity": entity, "op": "upsert", "id": item.get("id"), "data": item})
            for missing in set(int_ids) - found:
                changes.append({"entity": entity, "op": "delete", "id": missing})

        device = _device_for(request)
        if device:
            Device.objects.filter(pk=device.pk).update(last_seen_at=timezone.now(), last_pull_cursor=next_cursor)

        return ok({"changes": changes, "next_cursor": next_cursor, "has_more": len(rows) == limit})


# ---------------------------------------------------------------------------
# Push: desktop offline queue → server
# ---------------------------------------------------------------------------
class _Rollback(Exception):
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body


class _Blocked(Exception):
    pass


def _remap(value, device, key=None):
    """Payload এর ভিতরের negative (offline) id → server id।"""
    if isinstance(value, dict):
        return {k: _remap(v, device, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_remap(v, device, key) for v in value]
    if key in REMAP_KEYS and value not in (None, ""):
        try:
            num = int(value)
        except (TypeError, ValueError):
            return value
        if num < 0:
            server_id = (
                ProcessedOperation.objects.filter(
                    device=device, entity=REMAP_KEYS[key], local_id=num, status=ProcessedOperation.STATUS_APPLIED
                ).values_list("server_id", flat=True).first()
            )
            if not server_id:
                raise _Blocked(f"{REMAP_KEYS[key]} {num} এখনো server এ ওঠেনি")
            return server_id if isinstance(value, int) else str(server_id)
    return value


def _extract_id(body):
    node = body
    for _ in range(3):
        if not isinstance(node, dict):
            return None
        if isinstance(node.get("id"), int):
            return node["id"]
        node = node.get("data")
    return None


def _is_stock_error(body):
    text = json.dumps(body, ensure_ascii=False).lower() if body is not None else ""
    return "stock" in text and ("insufficient" in text or "not enough" in text or "available" in text)


def _message_from(body):
    if isinstance(body, dict):
        msg = body.get("message") or body.get("detail") or body.get("error")
        data = body.get("data")
        if isinstance(data, dict) and data:
            first_key = next(iter(data))
            val = data[first_key]
            detail = val[0] if isinstance(val, list) and val else val
            if isinstance(detail, dict):
                detail = json.dumps(detail, ensure_ascii=False)
            return f"{msg or 'Validation error'}: {first_key} — {detail}"[:500]
        if msg:
            return str(msg)[:500]
    return str(body)[:500]


def _dispatch(user, device, method, path, payload):
    factory = APIRequestFactory()
    req = factory.generic(
        method, path, data=json.dumps(payload), content_type="application/json",
        HTTP_X_DEVICE_ID=str(device.device_id), HTTP_X_CLIENT_SOURCE="desktop_offline",
    )
    force_authenticate(req, user=user)
    match = resolve(path)
    response = match.func(req, *match.args, **match.kwargs)
    if hasattr(response, "render"):
        response.render()
    try:
        body = json.loads(response.content.decode("utf-8")) if response.content else {}
    except Exception:
        body = {"raw": response.content.decode("utf-8", "ignore")[:2000]}
    return response.status_code, body


class PushView(APIView):
    """
    Desktop এর offline queue ক্রমানুসারে এখানে আসে। প্রতিটা operation:
    1. আগে apply হয়েছে কিনা (op_id) দেখা হয় → হলে আগের ফলাফল (duplicate হয় না)
    2. offline (negative) id গুলো আসল id দিয়ে বদলানো হয়
    3. App এর নিজের API view দিয়েই চালানো হয় → online এর মতো হুবহু একই validation/হিসাব
    4. ব্যর্থ হলে পুরো operation rollback, আর SyncIssue তৈরি হয় (চুপচাপ হারায় না)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        device = _device_for(request, request.data.get("device_id"))
        if not device:
            return fail("Device not registered. Please run setup again.", 403)
        ops = request.data.get("ops") or []
        if not isinstance(ops, list) or len(ops) > MAX_PUSH_OPS:
            return fail(f"ops must be a list of at most {MAX_PUSH_OPS}")

        allowed_users = {u.id: u for u in device.allowed_users.filter(is_active=True)}
        results = [self._apply(op, request, device, allowed_users) for op in ops]

        Device.objects.filter(pk=device.pk).update(last_push_at=timezone.now(), last_seen_at=timezone.now())
        return ok({"results": results, "server_time": timezone.now().isoformat()})

    # ------------------------------------------------------------------
    def _apply(self, op, request, device, allowed_users):
        result = {"op_id": op.get("op_id"), "local_id": op.get("local_id"), "status": "error", "server_id": None, "message": ""}
        try:
            op_id = uuid.UUID(str(op.get("op_id")))
        except (TypeError, ValueError):
            result.update(status="rejected", message="Invalid op_id")
            return result

        path = op.get("path") or ""
        method = (op.get("method") or "POST").upper()
        cfg = OFFLINE_WRITE_ENDPOINTS.get(path)
        if method != "POST" or not cfg:
            result.update(status="rejected", message="এই কাজটি offline এ করা যায় না")
            return result
        entity = cfg["entity"]

        # 1) Idempotency
        prev = ProcessedOperation.objects.filter(op_id=op_id).first()
        if prev and prev.status == ProcessedOperation.STATUS_APPLIED:
            result.update(status="duplicate", server_id=prev.server_id, message="Already synced", response=prev.response_body)
            return result

        user = allowed_users.get(op.get("user_id")) or (
            request.user if request.user.id in allowed_users else None
        )
        if user is None:
            result.update(status="rejected", message="এই user এই device এ অনুমোদিত নয়")
            return result

        client_time = parse_datetime(str(op.get("client_created_at") or "")) or None
        if client_time and timezone.is_naive(client_time):
            client_time = timezone.make_aware(client_time)
        payload = dict(op.get("payload") or {})

        try:
            payload = _remap(payload, device)
        except _Blocked as exc:
            result.update(status="blocked", message=str(exc))
            return result

        offline_invoice_no = payload.pop("offline_invoice_no", None)
        local_id = op.get("local_id")

        # Sale: offline এ যে তারিখ/সময়ে বিক্রি হয়েছিল সেটাই থাকবে
        if entity == "sale" and client_time:
            sd = payload.get("sale_date")
            if not sd or (parse_date(str(sd)) and parse_date(str(sd)) == timezone.localtime(client_time).date()):
                payload["sale_date"] = client_time.isoformat()

        # Customer: একই phone এর customer আগেই থাকলে নতুন বানানো হয় না → duplicate customer হয় না
        if entity == "customer" and payload.get("phone"):
            from customers.models import Customer
            existing = Customer.objects.filter(phone=payload["phone"]).first()
            if existing:
                body = {"status": True, "message": "Existing customer matched by phone", "data": {"id": existing.id}}
                self._record(op_id, device, user, entity, method, path, local_id, existing.id,
                             ProcessedOperation.STATUS_APPLIED, 200, body, client_time)
                result.update(status="applied", server_id=existing.id, message="Matched existing customer", response=body)
                return result

        try:
            with context.audit_override(user=user, client_time=client_time, source="desktop_offline",
                                        device_id=str(device.device_id)):
                with transaction.atomic():
                    code, body = _dispatch(user, device, method, path, payload)
                    if not (200 <= code < 300):
                        raise _Rollback(code, body)
                    server_id = _extract_id(body)
                    if entity == "sale" and offline_invoice_no and server_id:
                        from sales.models import Sale
                        if not Sale.objects.filter(invoice_no=offline_invoice_no).exclude(pk=server_id).exists():
                            Sale.objects.filter(pk=server_id).update(invoice_no=offline_invoice_no)
                            touch(Sale, server_id, ["invoice_no"])
                            if isinstance(body, dict) and isinstance(body.get("data"), dict):
                                body["data"]["invoice_no"] = offline_invoice_no
                    self._record(op_id, device, user, entity, method, path, local_id, server_id,
                                 ProcessedOperation.STATUS_APPLIED, code, body, client_time)
            SyncIssue.objects.filter(op_id=op_id, is_resolved=False).update(
                is_resolved=True, resolution="retried", resolved_at=timezone.now())
            result.update(status="applied", server_id=server_id, message="Synced", response=body)
            return result

        except _Rollback as rb:
            is_stock = _is_stock_error(rb.body)
            st = ProcessedOperation.STATUS_CONFLICT if is_stock else ProcessedOperation.STATUS_REJECTED
            if rb.status_code >= 500:
                result.update(status="error", message=_message_from(rb.body))
                return result
            message = _message_from(rb.body)
            self._record(op_id, device, user, entity, method, path, local_id, None, st, rb.status_code, rb.body, client_time)
            self._issue(op_id, device, user, entity, st, message, rb.body, op.get("payload") or {}, client_time)
            result.update(status=st, message=message, response=rb.body)
            return result
        except Resolver404:
            result.update(status="rejected", message="Unknown endpoint")
            return result
        except Exception as exc:  # server error → পরে আবার চেষ্টা হবে
            logger.exception("Push op failed: %s", op_id)
            result.update(status="error", message=str(exc)[:300])
            return result

    @staticmethod
    def _record(op_id, device, user, entity, method, path, local_id, server_id, st, code, body, client_time):
        ProcessedOperation.objects.update_or_create(
            op_id=op_id,
            defaults=dict(device=device, user=user, entity=entity, method=method, path=path,
                          local_id=local_id, server_id=server_id, status=st, response_status=code,
                          response_body=body, client_time=client_time),
        )

    @staticmethod
    def _issue(op_id, device, user, entity, issue_type, message, details, payload, client_time):
        if SyncIssue.objects.filter(op_id=op_id, is_resolved=False).exists():
            SyncIssue.objects.filter(op_id=op_id, is_resolved=False).update(message=message, details=details or {})
            return
        SyncIssue.objects.create(device=device, user=user, op_id=op_id, entity=entity,
                                 issue_type=issue_type, message=message, details=details or {},
                                 payload=payload, client_time=client_time)


# ---------------------------------------------------------------------------
# Sync issues (Sync Center)
# ---------------------------------------------------------------------------
class SyncIssueListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = SyncIssue.objects.all()
        if request.query_params.get("status", "open") == "open":
            qs = qs.filter(is_resolved=False)
        device = _device_for(request, request.query_params.get("device_id"))
        if device and request.query_params.get("mine") == "true":
            qs = qs.filter(device=device)
        data = [{
            "id": i.id, "op_id": str(i.op_id), "entity": i.entity, "issue_type": i.issue_type,
            "message": i.message, "details": i.details, "payload": i.payload,
            "device": i.device.code if i.device else None,
            "user": (i.user.get_full_name() or i.user.username) if i.user else None,
            "client_time": i.client_time, "created_at": i.created_at,
            "is_resolved": i.is_resolved, "resolution": i.resolution,
        } for i in qs.select_related("device", "user")[:200]]
        return ok(data)


class SyncIssueResolveView(APIView):
    """Admin কোনো offline entry বাতিল (dismiss) করলে সেটা audit সহ রেকর্ড থাকে।"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        issue = SyncIssue.objects.filter(pk=pk).first()
        if not issue:
            return fail("Not found", 404)
        resolution = request.data.get("resolution", "dismissed")
        if resolution not in ("dismissed", "retried"):
            return fail("Invalid resolution")
        issue.is_resolved = True
        issue.resolution = resolution
        issue.resolved_by = request.user
        issue.resolved_at = timezone.now()
        issue.save()
        ChangeLog.objects.create(
            user=request.user,
            user_display=(request.user.get_full_name() or request.user.username)[:150],
            device=issue.device, source=context.current()["source"], model_label="offline_sync.SyncIssue",
            object_id=str(issue.pk), object_repr=f"Offline {issue.entity} ({issue.issue_type})",
            action="update", changes={"resolution": [None, resolution], "note": [None, request.data.get("note", "")]},
        )
        return ok({"id": issue.id, "resolution": resolution}, "Issue resolved")


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
# Audit শুধু Super Admin ও Admin দেখবে
AUDIT_ROLES = {"SUPER_ADMIN", "ADMIN"}


def _is_super(user):
    return user.is_superuser or getattr(user, "role", "") == "SUPER_ADMIN"


def _audit_base_qs(request):
    """
    কার জন্য কোন log:
    - Super Admin ও Admin: সব log
    অনুমতি না থাকলে None
    """
    user = request.user
    if not (_is_super(user) or getattr(user, "role", "") in AUDIT_ROLES):
        return None
    return ChangeLog.objects.all()


def _apply_audit_filters(qs, p, skip=()):
    """
    Query parameter অনুযায়ী filter। `skip` এ যে filter থাকে সেটা বাদ যায় —
    meta তে প্রতিটা dropdown এর বিকল্প গোনার সময় নিজের filter বাদ দিয়ে বাকিগুলো মানা হয়
    (faceted filter), তাই এমন জোড়া বাছাই করা যায় না যার কোনো ফলাফল নেই।
    """
    if "model" not in skip and p.get("model"):
        m = p["model"]
        qs = qs.filter(Q(model_label__iexact=m) | Q(entity=m) | Q(model_label__iendswith="." + m))
    if "model" not in skip and p.get("object_id"):
        qs = qs.filter(object_id=p["object_id"])
    if "user_id" not in skip and p.get("user_id"):
        # "none" = কোনো user ছাড়া (System এর স্বয়ংক্রিয় কাজ)
        qs = qs.filter(user_id__isnull=True) if p["user_id"] == "none" else qs.filter(user_id=p["user_id"])
    if "action" not in skip and p.get("action"):
        qs = qs.filter(action=p["action"])
    if "source" not in skip and p.get("source"):
        qs = qs.filter(source=p["source"])
    if p.get("device"):
        qs = qs.filter(device__code=p["device"])
    if p.get("date_from") and parse_date(p["date_from"]):
        qs = qs.filter(created_at__date__gte=parse_date(p["date_from"]))
    if p.get("date_to") and parse_date(p["date_to"]):
        qs = qs.filter(created_at__date__lte=parse_date(p["date_to"]))
    if p.get("q"):
        qs = qs.filter(Q(object_repr__icontains=p["q"]) | Q(user_display__icontains=p["q"]))
    return qs


class AuditLogView(APIView):
    """
    কে, কখন, কোন device/app থেকে, কোন record এ কী বদলেছে।
    Filter: entity/model, object_id, user_id, action, source, device,
            date_from, date_to, q
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = _audit_base_qs(request)
        if qs is None:
            return fail("Audit log দেখার অনুমতি নেই", 403)

        p = request.query_params
        qs = _apply_audit_filters(qs.select_related("device"), p)

        try:
            page = max(int(p.get("page", 1)), 1)
            page_size = min(max(int(p.get("page_size", 30)), 1), 100)
        except ValueError:
            page, page_size = 1, 30
        total = qs.count()
        rows = qs[(page - 1) * page_size: page * page_size]

        results = []
        for r in rows:
            results.append({
                "id": r.id,
                "action": r.action,
                "model": r.model_label,
                "entity": r.entity,
                "object_id": r.object_id,
                "object_repr": r.object_repr,
                "user_id": r.user_id,
                "user": r.user_display,
                "source": r.source,
                "device": r.device.code if r.device else None,
                "ip": r.ip_address,
                "changes": [{"field": k, "old": v[0], "new": v[1]} for k, v in (r.changes or {}).items()
                            if isinstance(v, (list, tuple)) and len(v) == 2],
                "client_time": r.client_time,   # offline এ আসল কাজের সময়
                "created_at": r.created_at,     # server এ পৌঁছানোর সময়
            })
        return ok({
            "count": total,
            "total_pages": (total + page_size - 1) // page_size,
            "current_page": page,
            "page_size": page_size,
            "results": results,
        })


class AuditMetaView(APIView):
    """
    Audit screen এর filter dropdown ও উপরের summary card এর জন্য।
    GET /api/sync/audit/meta/?model=&user_id=&source=&action=&date_from=&date_to=&q=
    প্রতিটা dropdown এর বিকল্প ও সংখ্যা বাকি filter গুলো মেনে গোনা হয় (faceted)।
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = _audit_base_qs(request)
        if qs is None:
            return fail("Audit log দেখার অনুমতি নেই", 403)

        today = timezone.localdate()
        today_qs = qs.filter(created_at__date=today)
        by_action = dict(today_qs.values_list("action").annotate(n=Count("id")))

        p = request.query_params
        models_qs = _apply_audit_filters(qs, p, skip=("model",))
        users_qs = _apply_audit_filters(qs, p, skip=("user_id",))
        sources_qs = _apply_audit_filters(qs, p, skip=("source",))

        models = list(models_qs.values("model_label").annotate(count=Count("id")).order_by("-count", "model_label"))
        users = list(
            users_qs.exclude(user_id=None).values("user_id", "user_display")
            .annotate(count=Count("id")).order_by("-count")[:200]
        )
        system_count = users_qs.filter(user_id__isnull=True).count()
        sources = list(sources_qs.values("source").annotate(count=Count("id")).order_by("-count"))

        data = {
            "is_super_admin": _is_super(request.user),
            "summary": {
                "total": qs.count(),
                "today": today_qs.count(),
                "today_create": by_action.get(ChangeLog.ACTION_CREATE, 0),
                "today_update": by_action.get(ChangeLog.ACTION_UPDATE, 0),
                "today_delete": by_action.get(ChangeLog.ACTION_DELETE, 0),
            },
            "models": [{"model": m["model_label"], "count": m["count"]} for m in models],
            "users": [{"id": u["user_id"], "name": u["user_display"], "count": u["count"]} for u in users]
                     + ([{"id": "none", "name": "System (automatic)", "count": system_count}] if system_count else []),
            "sources": [{"source": s["source"], "count": s["count"]} for s in sources],
        }
        return ok(data)


class SyncStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        device = _device_for(request, request.query_params.get("device_id"))
        return ok({
            "server_time": timezone.now().isoformat(),
            "open_issues": SyncIssue.objects.filter(is_resolved=False).count(),
            "device_code": device.code if device else None,
            "latest_cursor": _safe_cursor(),
        })
