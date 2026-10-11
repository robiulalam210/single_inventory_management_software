from django.urls import path

from . import api_views as v

# core/urls.py থেকে `path('shop/', include('shop.api_urls'))` → /api/shop/…
urlpatterns = [
    path('orders/', v.ShopOrderListAPIView.as_view(), name='api-shop-orders'),
    path('orders/<int:pk>/', v.ShopOrderDetailAPIView.as_view(), name='api-shop-order-detail'),
    path('orders/<int:pk>/status/', v.ShopOrderStatusAPIView.as_view(), name='api-shop-order-status'),
    path('settings/', v.ShopSettingsAPIView.as_view(), name='api-shop-settings'),
]
