from django.urls import path

from . import views

urlpatterns = [
    path('adjustments/', views.AdjustmentListCreate.as_view(), name='stock-adjustments'),
    path('counts/', views.CountListCreate.as_view(), name='stock-counts'),
    path('counts/<int:pk>/', views.CountDetail.as_view(), name='stock-count-detail'),
    path('counts/<int:pk>/count/', views.CountSave.as_view(), name='stock-count-save'),
    path('counts/<int:pk>/apply/', views.CountApply.as_view(), name='stock-count-apply'),
    path('counts/<int:pk>/cancel/', views.CountCancel.as_view(), name='stock-count-cancel'),
]
