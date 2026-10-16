from django.contrib import admin
from .models import ExpenseHead, ExpenseSubHead, Expense

# Inline for subheads under heads
class ExpenseSubHeadInline(admin.TabularInline):
    model = ExpenseSubHead
    extra = 1  # How many empty forms to display

@admin.register(ExpenseHead)
class ExpenseHeadAdmin(admin.ModelAdmin):
    list_display = ('name',)
    inlines = [ExpenseSubHeadInline]

@admin.register(ExpenseSubHead)
class ExpenseSubHeadAdmin(admin.ModelAdmin):
    list_display = ('name', 'head')
    list_filter = ('head',)
    search_fields = ('name',)

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'head', 'subhead', 'amount', 'account', 'expense_date')
    list_filter = ('head', 'subhead', 'account', 'expense_date', 'payment_method')
    search_fields = ('invoice_number',)
    date_hierarchy = 'expense_date'

