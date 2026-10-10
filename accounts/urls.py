from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    # Core API
    path('api/', include('core.urls')),  # core handles all apps
]
