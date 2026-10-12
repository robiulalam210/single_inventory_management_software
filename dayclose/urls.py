from django.urls import path

from . import views

urlpatterns = [
    path('summary/', views.Summary.as_view(), name='day-close-summary'),
    path('', views.CloseList.as_view(), name='day-close-list'),
    path('<int:pk>/', views.CloseDetail.as_view(), name='day-close-detail'),
]
