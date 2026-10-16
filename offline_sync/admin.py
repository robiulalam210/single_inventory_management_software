from django.contrib import admin

from .models import ChangeLog, Device, ProcessedOperation, SyncIssue


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "platform", "app_version", "last_seen_at", "last_push_at", "is_active")
    list_filter = ("is_active", "platform")
    filter_horizontal = ("allowed_users",)


@admin.register(ChangeLog)
class ChangeLogAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "user_display", "source", "device", "action", "model_label", "object_id", "object_repr")
    list_filter = ("action", "source", "model_label")
    search_fields = ("object_repr", "user_display", "object_id")
    readonly_fields = [f.name for f in ChangeLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False  # Audit log কেউ বদলাতে পারবে না

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProcessedOperation)
class ProcessedOperationAdmin(admin.ModelAdmin):
    list_display = ("op_id", "device", "entity", "status", "local_id", "server_id", "created_at")
    list_filter = ("status", "entity")
    search_fields = ("op_id",)


@admin.register(SyncIssue)
class SyncIssueAdmin(admin.ModelAdmin):
    list_display = ("id", "device", "entity", "issue_type", "message", "is_resolved", "created_at")
    list_filter = ("is_resolved", "issue_type")
