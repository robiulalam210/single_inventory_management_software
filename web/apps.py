from django.apps import AppConfig


class WebConfig(AppConfig):
    """
    Web software — desktop app এর মতো একই কাজ, browser থেকে।
    Django admin panel নয়: নিজস্ব login, sidebar, module।
    Data ও নিয়ম (permission, হিসাব) একই backend / API থেকে আসে, তাই
    app ও web এর হিসাব কখনো আলাদা হয় না।
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'web'
    verbose_name = 'Web software'
