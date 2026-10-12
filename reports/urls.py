# reports/urls.py
from django.urls import path
from . import views
from .export_views import ReportExportView
from .expiry_views import ExpiryAlertsView, ExpiryWriteOffView
from .reminder_views import CustomerDueReminderView

urlpatterns = [
    path('sales/', views.SalesReportView.as_view(), name='sales-report'),
    path('purchases/', views.PurchaseReportView.as_view(), name='purchase-report'),
    path('profit-loss/', views.ProfitLossReportView.as_view(), name='profit-loss-report'),
    path('expenses/', views.ExpenseReportView.as_view(), name='expense-report'),
    path('purchase-returns/', views.PurchaseReturnReportView.as_view(), name='purchase-return-report'),
    path('sales-returns/', views.SalesReturnReportView.as_view(), name='sales-return-report'),
    path('top-products/', views.TopSoldProductsReportView.as_view(), name='top-products-report'),
    path('low-stock/', views.LowStockReportView.as_view(), name='low-stock-report'),
    path('low-stock-alert/', views.LowStockAlertView.as_view(), name='low-stock-alert'),
    path('bad-stock/', views.BadStockReportView.as_view(), name='bad-stock-report'),
    path('stock/', views.StockReportView.as_view(), name='stock-report'),
    path('dashboard/', views.DashboardSummaryView.as_view(), name='dashboard-summary'),
    path('dashboard-trends/', views.DashboardTrendsView.as_view(), name='dashboard-trends'),
    path('expiry-alerts/', ExpiryAlertsView.as_view(), name='expiry-alerts'),
    path('expiry-alerts/<int:batch_id>/write-off/', ExpiryWriteOffView.as_view(), name='expiry-write-off'),
    path('dashboard-charts/', views.DashboardChartsView.as_view(), name='dashboard-charts'),

    path('supplier-due-advance/', views.SupplierDueAdvanceReportView.as_view(), name='supplier-due-advance-report'),
    path('supplier-ledger/', views.SupplierLedgerReportView.as_view(), name='supplier-ledger-report'),
    path('customer-due-advance/', views.CustomerDueAdvanceReportView.as_view(), name='customer-due-advance-report'),
    path('customer-ledger/', views.CustomerLedgerReportView.as_view(), name='customer-ledger-report'),

    # Excel / PDF download — /api/reports/export/<key>/?fmt=xlsx|pdf
    path('export/<str:key>/', ReportExportView.as_view(), name='report-export'),
    # বাকি টাকার রিমাইন্ডার তালিকা (WhatsApp / SMS লিংক সহ)
    path('customer-due-reminders/', CustomerDueReminderView.as_view(), name='customer-due-reminders'),
]