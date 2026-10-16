from django.apps import AppConfig


class OfflineSyncConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "offline_sync"
    verbose_name = "Offline Sync & Audit"

    def ready(self):
        # Signal handler গুলো connect করা হচ্ছে — এর মাধ্যমেই প্রতিটা create/update/delete
        # Audit log ও sync change-feed এ জমা হয়।
        from . import signals  # noqa: F401
        signals.connect_all()
