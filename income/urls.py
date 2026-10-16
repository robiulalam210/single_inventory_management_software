from django.urls import path
from .views import (
    IncomeListView,
    IncomeHeadListCreateView,
    IncomeHeadDetailView,
    IncomeDetailView,
    IncomeSummaryView,
)

urlpatterns = [
    path('incomes/', IncomeListView.as_view(), name='incomes'),
    path('incomes/summary/', IncomeSummaryView.as_view(), name='incomes-summary'),
    path('incomes/<int:pk>/', IncomeDetailView.as_view(), name='income-detail'),
    path('income-heads/', IncomeHeadListCreateView.as_view(), name='income-heads-list-create'),
    path('income-heads/<int:pk>/', IncomeHeadDetailView.as_view(), name='income-heads-detail'),
]