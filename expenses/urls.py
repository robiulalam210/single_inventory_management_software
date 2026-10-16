from django.urls import path
from .views import ExpenseHeadListView, ExpenseSubHeadListView, ExpenseListView, ExpenseHeadDetailView, ExpenseSubHeadDetailView, ExpenseDetailView, ExpenseSummaryView

urlpatterns = [


     # Expense Head URLs
    path('expense-heads/', ExpenseHeadListView.as_view(), name='expense-head-list'),
    path('expense-heads/<int:pk>/', ExpenseHeadDetailView.as_view(), name='expense-head-detail'),
    
    # Expense SubHead URLs
    path('expense-subheads/', ExpenseSubHeadListView.as_view(), name='expense-subhead-list'),
    path('expense-subheads/<int:pk>/', ExpenseSubHeadDetailView.as_view(), name='expense-subhead-detail'),
    
    # Expense URLs
    path('expenses/', ExpenseListView.as_view(), name='expense-list'),
    path('expenses/summary/', ExpenseSummaryView.as_view(), name='expense-summary'),
    path('expenses/<int:pk>/',ExpenseDetailView.as_view(), name='expense-detail'),
]
