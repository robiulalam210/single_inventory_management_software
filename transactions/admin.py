# transactions/admin.py
from django.contrib import admin
from .models import Transaction

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction_no', 'transaction_type', 'amount', 'account', 'status', 'transaction_date')
    list_filter = ('transaction_type', 'status', 'payment_method', 'transaction_date')
    search_fields = ('transaction_no', 'account__name', 'description')
    readonly_fields = ('transaction_no', 'created_at', 'updated_at')
    date_hierarchy = 'transaction_date'