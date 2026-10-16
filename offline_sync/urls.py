from django.urls import path

from . import views

urlpatterns = [
    path("devices/register/", views.DeviceRegisterView.as_view(), name="sync-device-register"),
    path("manifest/", views.ManifestView.as_view(), name="sync-manifest"),
    path("bootstrap/", views.BootstrapView.as_view(), name="sync-bootstrap"),
    path("pull/", views.PullView.as_view(), name="sync-pull"),
    path("push/", views.PushView.as_view(), name="sync-push"),
    path("status/", views.SyncStatusView.as_view(), name="sync-status"),
    path("issues/", views.SyncIssueListView.as_view(), name="sync-issues"),
    path("issues/<int:pk>/resolve/", views.SyncIssueResolveView.as_view(), name="sync-issue-resolve"),
    path("audit/", views.AuditLogView.as_view(), name="audit-log"),
    path("audit/meta/", views.AuditMetaView.as_view(), name="audit-meta"),
]
