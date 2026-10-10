# sales/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import Sale, SaleItem
from decimal import Decimal


# ==============================
# SALE ITEM INLINE FOR SALE ADMIN
# ==============================
class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    max_num = 20
    can_delete = True
    readonly_fields = ['subtotal_display', 'stock_info', 'base_quantity']
    
    fields = [
        'product', 
        'sale_mode', 
        'sale_quantity', 
        'base_quantity',
        'unit_price',
        'price_type',
        'flat_price',
        'discount',
        'discount_type',
        'subtotal_display',
        'stock_info'
    ]
    
    def subtotal_display(self, obj):
        if obj.pk:
            return f"৳{float(obj.subtotal()):.2f}"
        return "-"
    subtotal_display.short_description = "Subtotal"
    
    def stock_info(self, obj):
        if obj.pk and obj.product:
            return f"Stock: {obj.product.stock_qty} {obj.product.unit.name if obj.product.unit else 'units'}"
        return "-"
    stock_info.short_description = "Product Stock"


# ==============================
# SALE ADMIN
# ==============================
@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = [
        'invoice_no',
        'customer_display',
        'sale_date',
        'grand_total',
        'paid_amount',
        'due_amount',
        'payment_status',
        'sale_type',
        'items_count'
    ]
    
    list_filter = [
        'sale_type',
        'payment_status',
        'customer_type',
        'sale_date',
        'with_money_receipt'
    ]
    
    search_fields = [
        'invoice_no',
        'customer__name',
        'customer__phone',
        'customer_name',
        'sale_by__username'
    ]
    
    readonly_fields = [
        'invoice_no',
        'sale_date',
        'gross_total',
        'net_total',
        'payable_amount',
        'grand_total',
        'due_amount',
        'change_amount',
        'payment_status',
        'items_count_display',
        'customer_display',
        'payment_summary'
    ]
    
    fieldsets = (
        ('Sale Information', {
            'fields': ('invoice_no', 'sale_date', 'sale_type')
        }),
        ('Customer Information', {
            'fields': ('customer_type', 'customer', 'customer_name', 'customer_display')
        }),
        ('Sale Details', {
            'fields': ('sale_by', 'remark', 'with_money_receipt')
        }),
        ('Payment Information', {
            'fields': ('payment_method', 'account', 'paid_amount', 'payment_summary')
        }),
        ('Charges & Discounts', {
            'classes': ('collapse',),
            'fields': (
                'overall_discount', 'overall_discount_type',
                'overall_delivery_charge', 'overall_delivery_type',
                'overall_service_charge', 'overall_service_type',
                'overall_vat_amount', 'overall_vat_type'
            )
        }),
        ('Totals (Auto-calculated)', {
            'fields': (
                'gross_total', 'net_total', 'payable_amount',
                'grand_total', 'due_amount', 'change_amount',
                'payment_status', 'items_count_display'
            )
        }),
    )
    
    inlines = [SaleItemInline]
    
    date_hierarchy = 'sale_date'
    ordering = ['-sale_date', '-id']
    
    def customer_display(self, obj):
        if obj.customer_type == 'walk_in':
            return obj.customer_name or "Walk-in Customer"
        elif obj.customer:
            return obj.customer.name
        return "Unknown"
    customer_display.short_description = "Customer"
    customer_display.admin_order_field = 'customer__name'
    
    def items_count(self, obj):
        count = obj.items.count()
        return count
    items_count.short_description = "Items"
    
    def items_count_display(self, obj):
        count = obj.items.count()
        url = reverse('admin:sales_saleitem_changelist') + f'?sale__id__exact={obj.id}'
        return format_html('<a href="{}">{} items</a>', url, count)
    items_count_display.short_description = "Sale Items"
    
    def payment_summary(self, obj):
        return format_html(
            """
            <div style="padding: 10px; background-color: #f8f9fa; border-radius: 5px;">
                <strong>Grand Total:</strong> ৳{:.2f}<br>
                <strong>Paid:</strong> ৳{:.2f}<br>
                <strong>Due:</strong> ৳{:.2f}<br>
                <strong>Change:</strong> ৳{:.2f}<br>
                <strong>Status:</strong> {}
            </div>
            """,
            float(obj.grand_total),
            float(obj.paid_amount),
            float(obj.due_amount),
            float(obj.change_amount),
            obj.get_payment_status_display()
        )
    payment_summary.short_description = "Payment Summary"
    
    def save_model(self, request, obj, form, change):
        """Handle saving sale and recalculating totals"""
        if not change:  # New sale
            if not obj.created_by:
                obj.created_by = request.user
            if not obj.sale_by:
                obj.sale_by = request.user
        
        super().save_model(request, obj, form, change)
        
        # Recalculate totals if items exist
        if obj.items.exists():
            try:
                obj.calculate_totals()
                obj.save()
            except Exception as e:
                self.message_user(request, f"Error calculating totals: {e}", level='error')


# ==============================
# SALE ITEM ADMIN
# ==============================
@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'sale_link',
        'product_link',
        'sale_mode_display',
        'sale_quantity',
        'base_quantity',
        'unit_price',
        'discount_display',
        'subtotal_display'
    ]
    
    list_filter = [
        'sale_mode',
        'price_type',
        'sale__sale_date',
        'product__category'
    ]
    
    search_fields = [
        'sale__invoice_no',
        'product__name',
        'product__sku',
        'sale__customer__name'
    ]
    
    readonly_fields = [
        'base_quantity',
        'subtotal_display',
        'stock_info',
        'price_info'
    ]
    
    fieldsets = (
        ('Sale Information', {
            'fields': ('sale',)
        }),
        ('Product Information', {
            'fields': ('product', 'stock_info')
        }),
        ('Sale Mode & Quantity', {
            'fields': ('sale_mode', 'sale_quantity', 'base_quantity')
        }),
        ('Pricing', {
            'fields': ('price_type', 'unit_price', 'flat_price', 'price_info')
        }),
        ('Discount', {
            'fields': ('discount', 'discount_type')
        }),
        ('Calculated Values', {
            'fields': ('subtotal_display',)
        }),
    )
    
    def sale_link(self, obj):
        url = reverse('admin:sales_sale_change', args=[obj.sale.id])
        return format_html('<a href="{}">{}</a>', url, obj.sale.invoice_no)
    sale_link.short_description = "Sale Invoice"
    sale_link.admin_order_field = 'sale__invoice_no'
    
    def product_link(self, obj):
        url = reverse('admin:products_product_change', args=[obj.product.id])
        return format_html('<a href="{}">{}</a>', url, obj.product.name)
    product_link.short_description = "Product"
    product_link.admin_order_field = 'product__name'
    
    def sale_mode_display(self, obj):
        if obj.sale_mode:
            return obj.sale_mode.name
        elif obj.product and obj.product.unit:
            return obj.product.unit.name
        return "Unit"
    sale_mode_display.short_description = "Sale Mode"
    
    def subtotal_display(self, obj):
        return f"৳{float(obj.subtotal()):.2f}"
    subtotal_display.short_description = "Subtotal"
    
    def discount_display(self, obj):
        if obj.discount and obj.discount > 0:
            if obj.discount_type == 'percent':
                return f"{obj.discount}%"
            else:
                return f"৳{obj.discount}"
        return "-"
    discount_display.short_description = "Discount"
    
    def stock_info(self, obj):
        if obj.product:
            return f"Available: {obj.product.stock_qty} {obj.product.unit.name if obj.product.unit else 'units'}"
        return "-"
    stock_info.short_description = "Current Stock"
    
    def price_info(self, obj):
        if obj.price_type == 'flat' and obj.flat_price:
            return f"Flat Price: ৳{obj.flat_price} for {obj.sale_quantity} {obj.sale_mode.name if obj.sale_mode else 'units'}"
        elif obj.sale_mode and obj.sale_mode.price_type == 'tier':
            return "Tier pricing applied"
        else:
            return f"Unit Price: ৳{obj.unit_price}/base unit"
    price_info.short_description = "Pricing Info"
    
    def save_model(self, request, obj, form, change):
        """Handle saving sale item with stock update"""
        old_base_quantity = None
        if change and obj.pk:
            try:
                old_item = SaleItem.objects.get(pk=obj.pk)
                old_base_quantity = old_item.base_quantity
            except SaleItem.DoesNotExist:
                pass
        
        # Save the item
        super().save_model(request, obj, form, change)
        
        # Handle stock return if quantity changed
        if change and old_base_quantity and old_base_quantity != obj.base_quantity:
            try:
                # Return old stock
                obj.product.stock_qty += float(old_base_quantity)
                # Deduct new stock
                obj.product.stock_qty -= float(obj.base_quantity)
                obj.product.save(update_fields=['stock_qty'])
                
                # Recalculate sale totals
                obj.sale.calculate_totals()
                
                self.message_user(
                    request, 
                    f"Stock updated: Returned {old_base_quantity}, Deducted {obj.base_quantity}",
                    level='info'
                )
            except Exception as e:
                self.message_user(request, f"Error updating stock: {e}", level='error')


# ==============================
# ADMIN SITE CONFIGURATION
# ==============================
admin.site.site_header = "Sales Management System"
admin.site.site_title = "Sales Admin"
admin.site.index_title = "Sales Dashboard"