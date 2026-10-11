from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CustomLoginView, UserViewSet, StaffRoleViewSet, StaffViewSet, CustomTokenObtainPairView,
    BusinessProfileView, BusinessLogoUpdateAPIView, UserProfileImageUpdateAPIView,
    admin_signup, admin_login, dashboard, user_list, create_user, home, user_management
)
from rest_framework_simplejwt.views import TokenRefreshView
from money_receipts.views import MoneyReceiptCreateAPIView, MoneyReceiptDetailAPIView, MoneyReceiptSummaryAPIView
from supplier_payment.view import SupplierPaymentListCreateAPIView, SupplierPaymentDetailAPIView, SupplierPaymentCancelAPIView, SupplierPaymentSummaryAPIView
# from purchases.views import PurchaseViewSet, PurchaseItemViewSet,PurchaseAllListViewSet
from purchases.views import PurchaseViewSet, PurchaseItemViewSet, PurchaseAllListViewSet
from purchases.views import get_due_purchases
from suppliers.views import SupplierViewSet,SupplierNonPaginationViewSet
from sales.views import SaleViewSet, SaleItemViewSet,SaleAllListViewSet,get_due_sales  # Import get_due_sales here
from sales.views import SaleViewSet, SaleItemViewSet    
from customers.views import CustomerViewSet,CustomerNonPaginationViewSet
from products.views import ProductViewSet, CategoryViewSet, UnitViewSet, BrandViewSet, GroupViewSet, SourceViewSet, SaleModeViewSet, ProductSaleModeViewSet ,PriceTierViewSet
from returns.views import SalesReturnViewSet, PurchaseReturnViewSet, BadStockViewSet
from accounts.views import AccountViewSet
from account_transfer.views import AccountTransferViewSet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, HttpResponsePermanentRedirect
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from core.views import ProfileAPIView, UserPermissionsAPIView, user_dashboard_stats, ChangePasswordAPIView, PermissionCheckView, UserPermissionManagementView   ,ResetPermissionsAPIView, UserPermissionListView
from django.conf import settings
from django.conf.urls.static import static

# Remove this import since we're importing functions directly above
# from . import views
from transactions.views import TransactionViewSet


router = DefaultRouter()

router.register(r'users', UserViewSet, basename='user')
router.register(r'staff-roles', StaffRoleViewSet, basename='staffrole')
router.register(r'staffs', StaffViewSet, basename='staff')

router.register(r'products', ProductViewSet, basename='product')
# router.register(r'product-active',ProductNonPaginationViewSet,basename="products")

router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'units', UnitViewSet, basename='unit')
router.register(r'brands', BrandViewSet, basename='brand')
router.register(r'groups', GroupViewSet, basename='group')
router.register(r'sources', SourceViewSet, basename='source')
router.register(r'sale-modes', SaleModeViewSet)
router.register(r'price-tiers', PriceTierViewSet, basename='price-tier')   
router.register(r'product-sale-modes', ProductSaleModeViewSet)
router.register(r'sales', SaleViewSet, basename='sale')
router.register(r'sale-invoice', SaleAllListViewSet, basename='sale-invoice')

router.register(r'sale-items', SaleItemViewSet, basename='sale-item')
router.register(r'customers', CustomerViewSet, basename='customer')
router.register(r'customers-active', CustomerNonPaginationViewSet, basename='customer-active')

router.register(r'suppliers', SupplierViewSet, basename='supplier')
router.register(r'suppliers-active', SupplierNonPaginationViewSet, basename='s')

router.register(r'purchases', PurchaseViewSet, basename='purchase')
router.register(r'purchases-invocie', PurchaseAllListViewSet, basename='purchase-invoice')

router.register(r'purchase-items', PurchaseItemViewSet, basename='purchase-item')
router.register(r'sales-returns', SalesReturnViewSet, basename='sales-return')
router.register(r'purchase-returns', PurchaseReturnViewSet, basename='purchase-return')
router.register(r'bad-stocks', BadStockViewSet, basename='bad-stock')
router.register(r'accounts', AccountViewSet, basename='account')
router.register(r'transfers', AccountTransferViewSet, basename='account-transfer')

router.register(r'transactions', TransactionViewSet, basename='transaction')
# router.register(r'profile', UserProfileViewSet, basename='profile')



urlpatterns = [
    # API routes
    path('', include(router.urls)),
    
    
    
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/login/', CustomLoginView.as_view(), name='custom_login'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # FIX: আগে 'api/auth/change-password/' ছিল → আসল URL হয়ে যেত /api/api/auth/change-password/
    path('auth/change-password/', ChangePasswordAPIView.as_view(), name='change-password'),
    path('profile/', ProfileAPIView.as_view(), name='profile'),

    path('profile/permissions/', UserPermissionsAPIView.as_view(), name='user-permissions'),
    path('dashboard/stats/', user_dashboard_stats, name='user-dashboard-stats'),

  path('user-permissions/', UserPermissionsAPIView.as_view(), name='user_permissions'),
    path('user-permissions/check/', PermissionCheckView.as_view(), name='permission_check'),
    path('user-permissions/update/', UserPermissionManagementView.as_view(), name='update_permissions'),
   path('user-permissions/reset/', ResetPermissionsAPIView.as_view(), name='reset_permissions'), 
    # নির্দিষ্ট একজন user এর permission (admin panel এর permission editor এর জন্য)
    path('user-permissions/user/<int:user_id>/', UserPermissionListView.as_view(), name='user_permission_detail'),
    path('money-receipts/', MoneyReceiptCreateAPIView.as_view(), name='money_receipt_create'),
    # একমাত্র ব্যবসা — নাম/লোগো/ফোন/ঠিকানা (ক্লায়েন্ট যে নাম দেবে সেটাই সব জায়গায় দেখাবে)
    path('business/', BusinessProfileView.as_view(), name='business-profile'),
    path('business/logo/', BusinessLogoUpdateAPIView.as_view(), name='business-logo-update'),
    path('money-receipts/summary/', MoneyReceiptSummaryAPIView.as_view(), name='money_receipt_summary'),
    path('money-receipts/<int:receipt_id>/', MoneyReceiptDetailAPIView.as_view(), name='money_receipt_detail'),
    path('supplier-payments/', SupplierPaymentListCreateAPIView.as_view(), name='supplier-payment-list-create'),
    path('supplier-payments/summary/', SupplierPaymentSummaryAPIView.as_view(), name='supplier-payment-summary'),
    path('supplier-payments/<int:pk>/', SupplierPaymentDetailAPIView.as_view(), name='supplier-payment-detail'),
    path('supplier-payments/<int:pk>/cancel/', SupplierPaymentCancelAPIView.as_view(), name='supplier-payment-cancel'),

    path('reports/', include('reports.urls')),
    path('sync/', include('offline_sync.urls')),  # offline sync + audit

    path('shop/', include('shop.api_urls')),  # Online Shop API (Flutter অ্যাপ): /api/shop/orders/, /api/shop/settings/
    path('payroll/', include('payroll.urls')),
    path('expenses/', include('expenses.urls')),
    path('income/', include('income.urls')),
    
    # FIXED: Use the imported function directly, not via views.
    path('due/', get_due_sales, name='due-sales'),  # This creates /api/due/
    path('purchase-due/', get_due_purchases, name='get_due_purchases'),
     path('purchases-invoice/supplier/<int:supplier_id>/', 
         PurchaseAllListViewSet.as_view({'get': 'supplier_invoices'}), 
         name='supplier-invoices'),
    # Custom API endpoints for stock filtering
    path('api/products/search/', ProductViewSet.as_view({'get': 'search'}), name='product-search'),
    path('api/products/stock-info/', ProductViewSet.as_view({'get': 'stock_info'}), name='product-stock-info'),
    path('api/products/low-stock/', ProductViewSet.as_view({'get': 'low_stock'}), name='product-low-stock'),
    path('api/products/advanced-search/', ProductViewSet.as_view({'get': 'advanced_search'}), name='product-advanced-search'),
    path('api/products/filters/', ProductViewSet.as_view({'get': 'filters'}), name='product-filters'),
    

    # Admin UI
    path('admin/signup/', admin_signup, name='admin_signup'),
    path('admin/login/', admin_login, name='admin_login'),
    path('admin/dashboard/', dashboard, name='admin_dashboard'),
    path('admin/users/', user_list, name='user_list'),
    path('admin/users/create/', create_user, name='create_user'),

    path('user/profile-picture/', UserProfileImageUpdateAPIView.as_view(), name='user-profile-picture-self'),
    path('user/<int:pk>/profile-picture/', UserProfileImageUpdateAPIView.as_view(), name='user-profile-picture'),
]



if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)