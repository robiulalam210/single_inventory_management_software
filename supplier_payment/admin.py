# # supplier_payment/admin.py
# from django.contrib import admin
# from .model import SupplierPayment  # Only import models from this app

# @admin.register(SupplierPayment)
# class SupplierPaymentAdmin(admin.ModelAdmin):
#     list_display = [
#         'sp_no', 'supplier', 'payment_type', 'amount', 'payment_method',
#         'payment_date', 'cheque_status', 'prepared_by', 'created_at'
#     ]
#     list_filter = [
#         'payment_type', 'payment_method', 'cheque_status', 
#         'payment_date', 'created_at'
#     ]
#     search_fields = [
#         'sp_no', 'supplier__name', 'purchase__invoice_no',
#         'cheque_no', 'bank_name'
#     ]
#     readonly_fields = ['sp_no', 'created_at', 'updated_at']
#     list_per_page = 20
#     date_hierarchy = 'payment_date'
    
#     fieldsets = (
#         ('Payment Information', {
#             'fields': (
#                 'sp_no', 'company', 'supplier', 'purchase', 
#                 'payment_type', 'specific_bill', 'amount'
#             )
#         }),
#         ('Payment Details', {
#             'fields': (
#                 'payment_method', 'payment_date', 'account',
#                 'cheque_status', 'cheque_no', 'cheque_date', 'bank_name'
#             )
#         }),
#         ('Additional Information', {
#             'fields': ('remark', 'prepared_by')
#         }),
#         ('Metadata', {
#             'fields': ('created_at', 'updated_at'),
#             'classes': ('collapse',)
#         })
#     )
    
#     def get_queryset(self, request):
#         qs = super().get_queryset(request)
#         if request.user.is_superuser:
#             return qs
#         return qs.filter(company=request.user.company)