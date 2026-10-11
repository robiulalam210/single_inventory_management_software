from django.contrib import admin

from .models import StockAdjustment, Stocktake, StocktakeLine


class LineInline(admin.TabularInline):
    model = StocktakeLine
    extra = 0
    fields = ('product_name', 'system_qty', 'counted_qty', 'applied_change')
    readonly_fields = fields
    can_delete = False


@admin.register(Stocktake)
class StocktakeAdmin(admin.ModelAdmin):
    list_display = ('number', 'title', 'status', 'created_by', 'created_at', 'applied_at')
    list_filter = ('status',)
    inlines = [LineInline]


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('number', 'product_name', 'qty_before', 'qty_after', 'change', 'reason', 'created_by', 'created_at')
    list_filter = ('reason',)
    search_fields = ('product_name', 'sku', 'number')
