import logging
from importlib import import_module

from django.apps import apps
from django.urls import resolve

from .registry import SYNC_ENTITIES

logger = logging.getLogger(__name__)


def touch(model, pk, fields=None):
    """
    `Model.objects.filter(...).update(...)` Django signal চালায় না, তাই audit/sync এ
    ধরা পড়ে না। এ ধরনের bulk update এর পরে এই function ডাকলে পরিবর্তনটা
    ChangeLog এ উঠে যায় (desktop ও নতুন stock/balance পাবে)।
    """
    from .signals import _snapshot, _write
    try:
        obj = model._default_manager.filter(pk=pk).first()
        if obj is None:
            return
        snap = _snapshot(obj)
        keys = fields or list(snap.keys())
        _write(obj, "update", {k: ["(bulk)", snap.get(k)] for k in keys if k in snap})
    except Exception:
        logger.exception("offline_sync.touch failed")


def _import(path):
    module, name = path.rsplit(".", 1)
    return getattr(import_module(module), name)


def entity_model(entity):
    return apps.get_model(SYNC_ENTITIES[entity]["model"])


def entity_queryset(entity, company=None):
    model = entity_model(entity)
    return model._default_manager.all().order_by("pk")


def entity_serializer_class(entity, request):
    """
    App এর list API যে serializer ব্যবহার করে, ঠিক সেটাই নেওয়া হয় — ফলে desktop এ
    জমা থাকা JSON আর online API এর JSON হুবহু এক রকম হয়, UI কোনো পার্থক্য বোঝে না।
    """
    cfg = SYNC_ENTITIES[entity]
    if cfg.get("serializer"):
        return _import(cfg["serializer"])
    match = resolve(cfg["path"])
    view_cls = getattr(match.func, "cls", None) or getattr(match.func, "view_class", None)
    view = view_cls()
    view.request = request
    view.format_kwarg = None
    view.action = "list"
    view.kwargs = {}
    if hasattr(view, "get_serializer_class"):
        return view.get_serializer_class()
    return view.serializer_class


def serialize_entities(entity, objects, request):
    serializer_cls = entity_serializer_class(entity, request)
    return serializer_cls(objects, many=True, context={"request": request}).data
