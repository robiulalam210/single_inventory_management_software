import uuid

from django.conf import settings
from django.db import models


class Device(models.Model):
    """
    প্রতিটা Desktop installation একটা Device।
    - device_id: app প্রথমবার চালু হলে নিজে UUID বানায় (install অনুযায়ী স্থায়ী)
    - code: D1, D2 ... — offline invoice number এ prefix হিসেবে বসে, তাই দুই PC
      offline এ invoice বানালেও কখনো একই নম্বর হবে না।
    """
    device_id = models.UUIDField(unique=True)
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=120, blank=True, default="")
    platform = models.CharField(max_length=30, blank=True, default="")
    app_version = models.CharField(max_length=30, blank=True, default="")
    # এই device এ যারা online login করেছে শুধু তাদের নামেই offline কাজ sync হবে
    allowed_users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="sync_devices")
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_push_at = models.DateTimeField(null=True, blank=True)
    last_pull_cursor = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("code",)]

    def __str__(self):
        return f"{self.code} - {self.name or self.device_id}"


class ChangeLog(models.Model):
    """
    একটাই table দুই কাজ করে:
    1) Audit — কে, কখন, কোন device থেকে, কোন record এ কী পরিবর্তন করেছে (field-wise old → new)
    2) Sync change-feed — id (auto increment) টাই desktop এর pull cursor।
       Client এর ঘড়ির উপর নির্ভর করা হয় না, তাই ঘড়ি ভুল থাকলেও কোনো change বাদ পড়ে না।
    """
    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"
    ACTION_CHOICES = [(ACTION_CREATE, "Create"), (ACTION_UPDATE, "Update"), (ACTION_DELETE, "Delete")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    user_display = models.CharField(max_length=150, blank=True, default="")
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True)
    source = models.CharField(max_length=20, default="api")  # mobile / desktop / desktop_offline / admin / system
    model_label = models.CharField(max_length=80, db_index=True)  # e.g. sales.Sale
    entity = models.CharField(max_length=40, blank=True, default="", db_index=True)  # sync entity name, if any
    object_id = models.CharField(max_length=64, db_index=True)
    object_repr = models.CharField(max_length=200, blank=True, default="")
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    changes = models.JSONField(default=dict, blank=True)  # {field: [old, new]}
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    client_time = models.DateTimeField(null=True, blank=True)  # offline এ আসলে কখন কাজটা হয়েছিল
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["model_label", "object_id"])]

    def __str__(self):
        return f"#{self.id} {self.action} {self.model_label}:{self.object_id} by {self.user_display}"


class ProcessedOperation(models.Model):
    """
    Idempotency ledger। প্রতিটা write request / offline operation এর একটা UUID (op_id) থাকে।
    একই op_id দ্বিতীয়বার এলে আবার save না করে আগের ফলাফল ফেরত দেওয়া হয় —
    তাই network কেটে গিয়ে retry হলেও কখনো duplicate sale/payment হয় না।
    """
    STATUS_APPLIED = "applied"
    STATUS_CONFLICT = "stock_conflict"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [(STATUS_APPLIED, "Applied"), (STATUS_CONFLICT, "Stock conflict"), (STATUS_REJECTED, "Rejected")]

    op_id = models.UUIDField(unique=True)
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    entity = models.CharField(max_length=40, blank=True, default="")
    method = models.CharField(max_length=8, default="POST")
    path = models.CharField(max_length=255)
    local_id = models.BigIntegerField(null=True, blank=True)   # desktop এর temporary (negative) id
    server_id = models.BigIntegerField(null=True, blank=True)  # server এ তৈরি হওয়া আসল id
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_APPLIED)
    response_status = models.PositiveSmallIntegerField(default=200)
    response_body = models.JSONField(null=True, blank=True)
    client_time = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["device", "entity", "local_id"])]


class SyncIssue(models.Model):
    """
    যেসব offline কাজ server এ বসানো যায়নি (যেমন stock শেষ, validation error)।
    এগুলো চুপচাপ হারিয়ে যায় না — Desktop এর "Sync Center" এ দেখায়, admin সমাধান করে।
    """
    TYPE_STOCK = "stock_conflict"
    TYPE_REJECTED = "rejected"
    TYPE_CHOICES = [(TYPE_STOCK, "Stock conflict"), (TYPE_REJECTED, "Rejected")]

    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    op_id = models.UUIDField(db_index=True)
    entity = models.CharField(max_length=40, blank=True, default="")
    issue_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    message = models.TextField(blank=True, default="")
    details = models.JSONField(default=dict, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    client_time = models.DateTimeField(null=True, blank=True)
    is_resolved = models.BooleanField(default=False)
    resolution = models.CharField(max_length=20, blank=True, default="")  # retried / dismissed
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


def new_uuid():
    return uuid.uuid4()
