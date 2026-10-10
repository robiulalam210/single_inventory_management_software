from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),

    # Core API
    path('api/', include('core.urls')),  # core handles all apps
    path('products/barcode-search/', views.search_product_by_barcode, name='barcode-search'),



]
