# reports/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('sales/', views.SalesReportView.as_view(), name='sales-report'),
    path('purchases/', views.PurchaseReportView.as_view(), name='purchase-report'),
    path('profit-loss/', views.ProfitLossReportView.as_view(), name='profit-loss-report'),
    path('expenses/', views.ExpenseReportView.as_view(), name='expense-report'),
    path('purchase-returns/', views.PurchaseReturnReportView.as_view(), name='purchase-return-report'),
    path('sales-returns/', views.SalesReturnReportView.as_view(), name='sales-return-report'),
    path('top-products/', views.TopSoldProductsReportView.as_view(), name='top-products-report'),
    path('low-stock/', views.LowStockReportView.as_view(), name='low-stock-report'),
    path('bad-stock/', views.BadStockReportView.as_view(), name='bad-stock-report'),
    path('stock/', views.StockReportView.as_view(), name='stock-report'),
    path('dashboard/', views.DashboardSummaryView.as_view(), name='dashboard-summary'),

    path('supplier-due-advance/', views.SupplierDueAdvanceReportView.as_view(), name='supplier-due-advance-report'),
    path('supplier-ledger/', views.SupplierLedgerReportView.as_view(), name='supplier-ledger-report'),
    path('customer-due-advance/', views.CustomerDueAdvanceReportView.as_view(), name='customer-due-advance-report'),
    path('customer-ledger/', views.CustomerLedgerReportView.as_view(), name='customer-ledger-report'),
]