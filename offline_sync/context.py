"""
Request-level context (কে, কোন device থেকে, কোন সময়ে কাজটা করছে)।

Signal handler এর কাছে request থাকে না, তাই contextvars দিয়ে current request
ও অতিরিক্ত তথ্য রাখা হয়। DRF JWT authentication view এর ভিতরে হয়, কিন্তু DRF
authenticated user কে মূল HttpRequest.user এও বসিয়ে দেয় — তাই signal চলার সময়
request.user পড়লে সঠিক user পাওয়া যায়।
"""
import contextvars
from contextlib import contextmanager

_request = contextvars.ContextVar("offline_sync_request", default=None)
_override = contextvars.ContextVar("offline_sync_override", default=None)


def set_request(request):
    return _request.set(request)


def reset_request(token):
    _request.reset(token)


@contextmanager
def audit_override(**values):
    """Sync push এর সময় আসল (offline) user, device ও সময় বসানোর জন্য।"""
    token = _override.set(values)
    try:
        yield
    finally:
        _override.reset(token)


def current():
    """Return dict: user, device_id, source, client_time, ip."""
    data = {"user": None, "device_id": None, "source": "system", "client_time": None, "ip": None}
    req = _request.get()
    if req is not None:
        user = getattr(req, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            data["user"] = user
        meta = getattr(req, "META", {})
        data["device_id"] = meta.get("HTTP_X_DEVICE_ID") or None
        data["source"] = (meta.get("HTTP_X_CLIENT_SOURCE") or ("admin" if req.path.startswith("/admin/") else "api"))[:20]
        fwd = meta.get("HTTP_X_FORWARDED_FOR")
        data["ip"] = (fwd.split(",")[0].strip() if fwd else meta.get("REMOTE_ADDR")) or None
    ov = _override.get()
    if ov:
        data.update({k: v for k, v in ov.items() if v is not None})
    return data
