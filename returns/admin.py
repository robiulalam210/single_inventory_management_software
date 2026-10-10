# returns/admin.py
from django.contrib import admin
from .models import SalesReturn, SalesReturnItem, PurchaseReturn, PurchaseReturnItem, BadStock

class SalesReturnItemInline(admin.TabularInline):
    model = SalesReturnItem
    extra = 0
    readonly_fields = ['total']

@admin.register(SalesReturn)
class SalesReturnAdmin(admin.ModelAdmin):
    list_display = ['receipt_no', 'customer_name', 'return_date', 'return_amount', 'status']
    list_filter = ['status', 'return_date']
    search_fields = ['receipt_no', 'customer_name']
    inlines = [SalesReturnItemInline]
    readonly_fields = ['return_amount', 'created_at']

class PurchaseReturnItemInline(admin.TabularInline):
    model = PurchaseReturnItem
    extra = 0
    readonly_fields = ['total']

@admin.register(PurchaseReturn)
class PurchaseReturnAdmin(admin.ModelAdmin):
    list_display = ['invoice_no', 'supplier', 'return_date', 'return_amount', 'status']
    list_filter = ['status', 'return_date']
    search_fields = ['invoice_no', 'supplier']
    inlines = [PurchaseReturnItemInline]
    readonly_fields = ['return_amount', 'created_at']

@admin.register(BadStock)
class BadStockAdmin(admin.ModelAdmin):
    list_display = ['product', 'quantity', 'reference_type', 'date']
    list_filter = ['reference_type', 'date']
    search_fields = ['product__name', 'reason']
    readonly_fields = ['date']