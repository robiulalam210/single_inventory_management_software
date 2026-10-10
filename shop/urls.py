from django.urls import path

from . import views

app_name = 'shop'

urlpatterns = [
    path('', views.store_view, name='store'),
    path('order/', views.place_order_view, name='place_order'),
]
