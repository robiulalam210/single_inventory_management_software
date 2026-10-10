# branch_warehouse/admin.py
from django.contrib import admin
from .models import Purchase, PurchaseItem
from django.contrib.auth import get_user_model
from django.utils.html import format_html
from decimal import Decimal


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ('invoice_no', 'supplier', 'purchase_date', 'grand_total_display', 
                    'paid_amount_display', 'due_amount_display', 'payment_status_colored', 'item_count')
    list_filter = ('payment_status', 'purchase_date', 'payment_method')
    search_fields = ('invoice_no', 'supplier__name', 'remark', 'reference_no')
    date_hierarchy = 'purchase_date'
    readonly_fields = ('created_by', 'updated_by', 'date_created', 'date_updated', 
                       'total', 'grand_total', 'due_amount', 'change_amount', 'item_count_display')
    raw_id_fields = ('supplier', 'account')
    fieldsets = (
        ('Basic Information', {
            'fields': ('supplier', 'purchase_date', 'invoice_no', 'reference_no', 'expected_delivery_date')
        }),
        ('Amounts', {
            'fields': (('total', 'grand_total'), ('paid_amount', 'due_amount', 'change_amount'))
        }),
        ('Charges & Discounts', {
            'fields': (
                ('overall_discount', 'overall_discount_type'),
                ('overall_delivery_charge', 'overall_delivery_charge_type'),
                ('overall_service_charge', 'overall_service_charge_type'),
                ('vat', 'vat_type'),
            )
        }),
        ('Payment Information', {
            'fields': ('payment_status', 'payment_method', 'account')
        }),
        ('Additional Information', {
            'fields': ('remark', 'return_amount', 'is_active')
        }),
        ('Audit Information', {
            'fields': ('created_by', 'updated_by', 'date_created', 'date_updated', 'item_count_display'),
            'classes': ('collapse',)
        }),
    )
    
    # Add actions
    actions = ['mark_as_paid', 'mark_as_cancelled']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('supplier', 'account')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name in ["created_by", "updated_by"]:
            kwargs["queryset"] = get_user_model().objects.filter(is_active=True)
        elif db_field.name == "account":
            kwargs["queryset"] = db_field.related_model.objects.filter(is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        """Set created_by/updated_by users and handle totals"""
        if not change:
            obj.created_by = request.user
            # Generate invoice number if not provided
            if not obj.invoice_no:
                obj.invoice_no = obj.generate_invoice_no()
        
        obj.updated_by = request.user
        
        # Calculate totals if items exist
        if obj.pk and obj.items.exists():
            obj.update_totals()
        
        super().save_model(request, obj, form, change)
    
    # Custom display methods
    def grand_total_display(self, obj):
        return f"${obj.grand_total:,.2f}"
    grand_total_display.short_description = 'Grand Total'
    grand_total_display.admin_order_field = 'grand_total'
    
    def paid_amount_display(self, obj):
        return f"${obj.paid_amount:,.2f}"
    paid_amount_display.short_description = 'Paid'
    paid_amount_display.admin_order_field = 'paid_amount'
    
    def due_amount_display(self, obj):
        color = 'green' if obj.due_amount == Decimal('0.00') else 'red'
        return format_html(f'<span style="color: {color}; font-weight: bold;">${obj.due_amount:,.2f}</span>')
    due_amount_display.short_description = 'Due'
    due_amount_display.admin_order_field = 'due_amount'
    
    def payment_status_colored(self, obj):
        colors = {
            'paid': 'green',
            'partial': 'orange',
            'pending': 'gray',
            'overdue': 'red',
            'cancelled': 'black'
        }
        color = colors.get(obj.payment_status, 'black')
        return format_html(f'<span style="color: {color}; font-weight: bold;">{obj.get_payment_status_display()}</span>')
    payment_status_colored.short_description = 'Status'
    
    def item_count(self, obj):
        return obj.items.count()
    item_count.short_description = 'Items'
    
    def item_count_display(self, obj):
        if obj.pk:
            return obj.items.count()
        return 'N/A'
    item_count_display.short_description = 'Number of Items'
    
    # Custom actions
    def mark_as_paid(self, request, queryset):
        """Mark selected purchases as paid"""
        updated = 0
        for purchase in queryset:
            if purchase.payment_status != 'paid' and purchase.due_amount > 0:
                purchase.paid_amount = purchase.grand_total
                purchase.due_amount = Decimal('0.00')
                purchase.payment_status = 'paid'
                purchase.save()
                updated += 1
        
        self.message_user(request, f"{updated} purchase(s) marked as paid.")
    mark_as_paid.short_description = "Mark selected purchases as paid"
    
    def mark_as_cancelled(self, request, queryset):
        """Mark selected purchases as cancelled"""
        cancelled = 0
        for purchase in queryset:
            if purchase.payment_status != 'cancelled':
                purchase.payment_status = 'cancelled'
                purchase.is_active = False
                purchase.save()
                cancelled += 1
        
        self.message_user(request, f"{cancelled} purchase(s) marked as cancelled.")
    mark_as_cancelled.short_description = "Mark selected purchases as cancelled"
    
    # Inline for purchase items
    class PurchaseItemInline(admin.TabularInline):
        model = PurchaseItem
        extra = 1
        fields = ('product', 'qty', 'price', 'discount', 'discount_type', 'batch_no', 'expiry_date', 'subtotal_display')
        readonly_fields = ('subtotal_display',)
        
        def subtotal_display(self, obj):
            if obj.pk:
                return f"${obj.subtotal():,.2f}"
            return 'N/A'
        subtotal_display.short_description = 'Subtotal'
        
        def get_queryset(self, request):
            qs = super().get_queryset(request)
            return qs.select_related('product')
    
    inlines = [PurchaseItemInline]


@admin.register(PurchaseItem)
class PurchaseItemAdmin(admin.ModelAdmin):
    list_display = ('purchase_link', 'product', 'qty', 'price_display', 'discount_display', 'subtotal_display', 'expiry_date')
    list_filter = ('purchase__purchase_date', 'expiry_date')
    search_fields = ('product__name', 'batch_no', 'purchase__invoice_no')
    raw_id_fields = ('purchase', 'product')
    readonly_fields = ('subtotal_display',)
    list_select_related = ('purchase', 'product')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('purchase', 'product')

    def purchase_link(self, obj):
        url = f"/admin/branch_warehouse/purchase/{obj.purchase.id}/change/"
        return format_html(f'<a href="{url}">{obj.purchase.invoice_no}</a>')
    purchase_link.short_description = 'Purchase'
    purchase_link.admin_order_field = 'purchase__invoice_no'
    
    def price_display(self, obj):
        return f"${obj.price:,.2f}"
    price_display.short_description = 'Price'
    price_display.admin_order_field = 'price'
    
    def discount_display(self, obj):
        if obj.discount_type == 'percentage':
            return f"{obj.discount}%"
        return f"${obj.discount:,.2f}"
    discount_display.short_description = 'Discount'
    
    def subtotal_display(self, obj):
        if obj.pk:
            return f"${obj.subtotal():,.2f}"
        return 'N/A'
    subtotal_display.short_description = 'Subtotal'