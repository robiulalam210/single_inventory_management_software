"""
প্রতিটা audited model save/delete হলে ChangeLog এ একটা row লেখা হয়।

- pre_save: DB থেকে পুরনো মান পড়ে রাখা হয়
- post_save: নতুন মানের সাথে তুলনা করে শুধু যেসব field বদলেছে সেগুলো লেখা হয় (old → new)
- post_delete: delete হওয়া record এর শেষ অবস্থা লেখা হয়

Audit লেখায় কোনো সমস্যা হলে মূল কাজ (sale/purchase) কখনো আটকাবে না — exception গিলে log করা হয়।
"""
import datetime
import decimal
import logging
import uuid

from django.apps import apps
from django.db.models.signals import post_delete, post_save, pre_save
from django.utils import timezone

from . import context
from .registry import AUDIT_IGNORED_FIELDS, AUDITED_MODELS, SYNC_ENTITIES

logger = logging.getLogger(__name__)

_MODEL_TO_ENTITY = {cfg["model"]: name for name, cfg in SYNC_ENTITIES.items()}
_connected = False


def _json_safe(value):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, datetime.datetime):
        if timezone.is_aware(value):
            value = value.astimezone(datetime.timezone.utc)
        return value.isoformat()
    if isinstance(value, (datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    from django.db.models.fields.files import FieldFile
    if isinstance(value, FieldFile):
        return value.name or None
    return str(value)


def _normalize_decimal(field, value):
    """
    DecimalField এর মান একই আকারে আনা — না হলে DB থেকে আসা Decimal('4510.00') আর
    memory তে থাকা 4510 কে আলাদা ধরে audit এ ভুয়া "update" লেখা হতো।
    """
    if value is None:
        return None
    try:
        places = field.decimal_places or 0
        return decimal.Decimal(str(value)).quantize(decimal.Decimal(1).scaleb(-places))
    except (decimal.InvalidOperation, TypeError, ValueError):
        return value


def _snapshot(instance):
    from django.db.models import DecimalField
    data = {}
    for f in instance._meta.concrete_fields:
        if f.name in AUDIT_IGNORED_FIELDS:
            continue
        value = getattr(instance, f.attname, None)
        if isinstance(f, DecimalField):
            value = _normalize_decimal(f, value)
        data[f.attname] = _json_safe(value)
    return data


def _resolve_device(device_id):
    if not device_id:
        return None
    from .models import Device
    try:
        return Device.objects.filter(device_id=device_id).only("id").first()
    except Exception:
        return None


def _write(instance, action, changes):
    from .models import ChangeLog
    ctx = context.current()
    user = ctx["user"]
    ChangeLog.objects.create(
        user=user,
        user_display=(user.get_full_name() or user.username)[:150] if user else "System",
        device=_resolve_device(ctx["device_id"]),
        source=ctx["source"],
        model_label=instance._meta.label,
        entity=_MODEL_TO_ENTITY.get(instance._meta.label, ""),
        object_id=str(instance.pk),
        object_repr=str(instance)[:200],
        action=action,
        changes=changes,
        ip_address=ctx["ip"],
        client_time=ctx["client_time"],
    )


def on_pre_save(sender, instance, raw=False, **kwargs):
    if raw:
        return
    instance._audit_old = None
    if instance.pk:
        try:
            old = sender._default_manager.filter(pk=instance.pk).first()
            instance._audit_old = _snapshot(old) if old else None
        except Exception:
            instance._audit_old = None


def on_post_save(sender, instance, created, raw=False, update_fields=None, **kwargs):
    if raw:
        return
    try:
        new = _snapshot(instance)
        old = getattr(instance, "_audit_old", None)
        if created or old is None:
            changes = {k: [None, v] for k, v in new.items() if v not in (None, "", [], {})}
            _write(instance, "create", changes)
        else:
            changes = {k: [old.get(k), v] for k, v in new.items() if old.get(k) != v}
            if changes:  # কিছুই না বদলালে log লেখা হয় না
                _write(instance, "update", changes)
        instance._audit_old = new
    except Exception:
        logger.exception("Audit log write failed for %s", sender)


def on_post_delete(sender, instance, **kwargs):
    try:
        _write(instance, "delete", {k: [v, None] for k, v in _snapshot(instance).items() if v not in (None, "")})
    except Exception:
        logger.exception("Audit log write failed (delete) for %s", sender)


def connect_all():
    global _connected
    if _connected:
        return
    for label in AUDITED_MODELS:
        try:
            model = apps.get_model(label)
        except LookupError:
            logger.warning("offline_sync: model %s not found, skipping audit", label)
            continue
        uid = f"offline_sync_{label}"
        pre_save.connect(on_pre_save, sender=model, dispatch_uid=uid + "_pre")
        post_save.connect(on_post_save, sender=model, dispatch_uid=uid + "_post")
        post_delete.connect(on_post_delete, sender=model, dispatch_uid=uid + "_del")
    _connected = True
