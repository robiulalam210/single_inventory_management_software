# products/admin.py
from django.contrib import admin
from django import forms
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Category, Unit, Brand, Product, Source, Group, ProductSaleMode, PriceTier, SaleMode
from decimal import Decimal


# ==============================
# INLINE ADMIN FOR PRODUCT SALE MODES
# ==============================
class PriceTierInline(admin.TabularInline):
    model = PriceTier
    extra = 1
    max_num = 10
    
    fields = ['min_quantity', 'max_quantity', 'price', 'get_price_per_unit']
    readonly_fields = ['get_price_per_unit']
    
    def get_price_per_unit(self, obj):
        if obj.min_quantity and obj.price and obj.min_quantity > 0:
            price_per_unit = obj.price / Decimal(str(obj.min_quantity))
            return f"৳{price_per_unit:.2f}/unit"
        return "-"
    get_price_per_unit.short_description = "Price per Unit"


class ProductSaleModeInline(admin.TabularInline):
    model = ProductSaleMode
    extra = 0
    max_num = 10
    can_delete = True
    show_change_link = True
    
    fields = ['sale_mode', 'unit_price', 'flat_price', 'discount_type', 'discount_value', 'is_active', 'get_final_price']
    readonly_fields = ['get_final_price']
    
    def get_final_price(self, obj):
        if obj.pk:
            try:
                price = obj.get_final_price(quantity=1)
                return f"৳{float(price):.2f}"
            except:
                return "Error"
        return "-"
    get_final_price.short_description = "Price"


# ==============================
# SALE MODE ADMIN
# ==============================
@admin.register(SaleMode)
class SaleModeAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'get_base_unit', 'conversion_factor', 'price_type', 'is_active', 'show_in_shop', 'show_in_webapp']
    list_filter = ['price_type', 'is_active', 'show_in_shop', 'show_in_webapp']
    search_fields = ['name', 'code', 'base_unit__name']
    list_editable = ['is_active', 'show_in_shop', 'show_in_webapp']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'code', 'base_unit', 'conversion_factor')
        }),
        ('Pricing Configuration', {
            'fields': ('price_type',)
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Where to show', {
            'fields': ('show_in_shop', 'show_in_webapp')
        }),
    )
    
    def get_base_unit(self, obj):
        return obj.base_unit.name if obj.base_unit else "-"
    get_base_unit.short_description = "Base Unit"
    get_base_unit.admin_order_field = 'base_unit__name'


# ==============================
# PRODUCT SALE MODE ADMIN
# ==============================
@admin.register(ProductSaleMode)
class ProductSaleModeAdmin(admin.ModelAdmin):
    list_display = [
        'product_link', 
        'sale_mode_link', 
        'price_type_display', 
        'unit_price', 
        'flat_price', 
        'discount_display',
        'is_active'
    ]
    list_filter = ['is_active', 'sale_mode__price_type']
    search_fields = ['product__name', 'sale_mode__name', 'product__sku']
    inlines = [PriceTierInline]
    list_editable = ['is_active']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('product', 'sale_mode')
        }),
        ('Pricing Configuration', {
            'fields': ('unit_price', 'flat_price')
        }),
        ('Discount Settings', {
            'fields': ('discount_type', 'discount_value')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
    )
    
    def product_link(self, obj):
        url = reverse('admin:products_product_change', args=[obj.product.id])
        return format_html('<a href="{}">{}</a>', url, obj.product.name)
    product_link.short_description = "Product"
    product_link.admin_order_field = 'product__name'
    
    def sale_mode_link(self, obj):
        url = reverse('admin:products_salemode_change', args=[obj.sale_mode.id])
        return format_html('<a href="{}">{}</a>', url, obj.sale_mode.name)
    sale_mode_link.short_description = "Sale Mode"
    sale_mode_link.admin_order_field = 'sale_mode__name'
    
    def price_type_display(self, obj):
        return obj.sale_mode.get_price_type_display() if obj.sale_mode else "-"
    price_type_display.short_description = "Price Type"
    
    def discount_display(self, obj):
        if obj.discount_type and obj.discount_value:
            if obj.discount_type == 'percentage':
                return f"{obj.discount_value}%"
            else:
                return f"৳{obj.discount_value}"
        return "-"
    discount_display.short_description = "Discount"


# ==============================
# PRICE TIER ADMIN
# ==============================
@admin.register(PriceTier)
class PriceTierAdmin(admin.ModelAdmin):
    list_display = [
        'product_sale_mode_link',
        'min_quantity',
        'max_quantity',
        'price',
        'price_per_unit',
        'range_display'
    ]
    list_filter = ['product_sale_mode__product', 'product_sale_mode__sale_mode']
    search_fields = ['product_sale_mode__product__name', 'product_sale_mode__sale_mode__name']
    
    def product_sale_mode_link(self, obj):
        url = reverse('admin:products_productsalemode_change', args=[obj.product_sale_mode.id])
        product_name = obj.product_sale_mode.product.name
        sale_mode = obj.product_sale_mode.sale_mode.name
        return format_html('<a href="{}">{} - {}</a>', url, product_name, sale_mode)
    product_sale_mode_link.short_description = "Product & Mode"
    
    def price_per_unit(self, obj):
        if obj.min_quantity and obj.min_quantity > 0:
            try:
                price_per_unit = Decimal(str(obj.price)) / Decimal(str(obj.min_quantity))
                return f"৳{price_per_unit:.2f}"
            except:
                return "-"
        return "-"
    price_per_unit.short_description = "Unit Price"
    
    def range_display(self, obj):
        if obj.max_quantity:
            return f"{obj.min_quantity} - {obj.max_quantity}"
        return f"{obj.min_quantity}+"
    range_display.short_description = "Quantity Range"


# ==============================
# PRODUCT ADMIN WITH SALE MODES
# ==============================
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'name', 
        'sku', 
        'category', 
        'brand', 
        'stock_qty', 
        'selling_price', 
        'final_price_display',
        'is_active',
        'sale_modes_count'
    ]
    list_filter = ('category', 'brand', 'unit', 'is_active', 'created_at')
    search_fields = ('name', 'sku', 'category__name', 'brand__name', 'description')
    ordering = ('name',)
    inlines = [ProductSaleModeInline]
    readonly_fields = ['stock_qty', 'created_at', 'updated_at', 'sku', 'final_price_display', 'stock_status_display']
    
    # Define fieldsets
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'sku', 'description', 'image', 'is_active')
        }),
        ('Classification', {
            'fields': ('category', 'unit', 'brand', 'group', 'source')
        }),
        ('Pricing & Stock', {
            'fields': ('purchase_price', 'selling_price', 'discount_type', 'discount_value', 'discount_applied_on', 'final_price_display')
        }),
        ('Stock Information', {
            'fields': ('opening_stock', 'stock_qty', 'alert_quantity', 'stock_status_display')
        }),
        ('Sale Modes', {
            'fields': ('get_sale_modes_link',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_readonly_fields(self, request, obj=None):
        """Dynamically set readonly fields"""
        readonly_fields = ['stock_qty', 'created_at', 'updated_at', 'final_price_display', 'stock_status_display']
        if obj and obj.pk:  # Editing an existing object
            readonly_fields.append('sku')
            readonly_fields.append('get_sale_modes_link')
        else:  # New object
            readonly_fields = ['stock_qty', 'created_at', 'updated_at', 'final_price_display', 'stock_status_display']
        return readonly_fields
    
    def final_price_display(self, obj):
        if obj.pk:
            return f"৳{float(obj.final_price):.2f}"
        return "-"
    final_price_display.short_description = "Final Price"
    
    def stock_status_display(self, obj):
        if obj.pk:
            status = obj.stock_status
            color = {
                'out_of_stock': 'red',
                'low_stock': 'orange',
                'in_stock': 'green'
            }.get(status, 'black')
            return format_html('<span style="color: {};">{}</span>', color, status.title())
        return "-"
    stock_status_display.short_description = "Stock Status"
    
    def sale_modes_count(self, obj):
        if obj.pk:
            count = obj.sale_modes.filter(is_active=True).count()
            url = reverse('admin:products_productsalemode_changelist') + f'?product__id__exact={obj.id}'
            return format_html('<a href="{}">{} modes</a>', url, count)
        return 0
    sale_modes_count.short_description = "Sale Modes"
    
    def get_sale_modes_link(self, obj):
        if obj.pk:
            url = reverse('admin:products_productsalemode_changelist') + f'?product__id__exact={obj.id}'
            count = obj.sale_modes.count()
            return format_html('<a href="{}" class="button">Manage {} Sale Modes</a>', url, count)
        return "Save product first to add sale modes"
    get_sale_modes_link.short_description = "Sale Modes Management"
    
    def save_model(self, request, obj, form, change):
        """Handle saving the model with sale mode support"""
        if not change:  # This is a new instance
            # Set created_by if not set
            if not obj.created_by:
                obj.created_by = request.user
        
        # Save the product
        super().save_model(request, obj, form, change)
        
        # Auto-create default sale mode if none exists
        if obj.unit and not obj.sale_modes.exists():
            try:
                default_sale_mode = SaleMode.objects.filter(
                    base_unit=obj.unit,
                    conversion_factor=Decimal('1.00'),
                    price_type='unit'
                ).first()
                
                if default_sale_mode:
                    ProductSaleMode.objects.create(
                        product=obj,
                        sale_mode=default_sale_mode,
                        unit_price=obj.selling_price,
                        is_active=True
                    )
                    self.message_user(request, f"Default sale mode '{default_sale_mode.name}' created for product.")
            except Exception as e:
                self.message_user(request, f"Error creating default sale mode: {e}", level='error')


# ==============================
# CATEGORY ADMIN (ENHANCED)
# ==============================
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'products_count']
    list_filter = ['is_active']
    search_fields = ['name', 'description']
    list_editable = ['is_active']
    
    def products_count(self, obj):
        count = obj.products.count()
        url = reverse('admin:products_product_changelist') + f'?category__id__exact={obj.id}'
        return format_html('<a href="{}">{}</a>', url, count)
    products_count.short_description = "Products"


# ==============================
# UNIT ADMIN (ENHANCED)
# ==============================
@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active', 'products_count', 'sale_modes_count']
    list_filter = ['is_active']
    search_fields = ['name', 'code']
    list_editable = ['is_active']
    
    def products_count(self, obj):
        count = obj.product_set.count()
        url = reverse('admin:products_product_changelist') + f'?unit__id__exact={obj.id}'
        return format_html('<a href="{}">{}</a>', url, count)
    products_count.short_description = "Products"
    
    def sale_modes_count(self, obj):
        count = obj.sale_modes.count()
        url = reverse('admin:products_salemode_changelist') + f'?base_unit__id__exact={obj.id}'
        return format_html('<a href="{}">{}</a>', url, count)
    sale_modes_count.short_description = "Sale Modes"


# ==============================
# BRAND ADMIN (ENHANCED)
# ==============================
@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'products_count']
    list_filter = ['is_active']
    search_fields = ['name']
    list_editable = ['is_active']
    
    def products_count(self, obj):
        count = obj.products.count()
        url = reverse('admin:products_product_changelist') + f'?brand__id__exact={obj.id}'
        return format_html('<a href="{}">{}</a>', url, count)
    products_count.short_description = "Products"


# ==============================
# SOURCE ADMIN
# ==============================
@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'products_count']
    list_filter = ['is_active']
    search_fields = ['name']
    
    def products_count(self, obj):
        return obj.products.count()
    products_count.short_description = "Products"


# ==============================
# GROUP ADMIN
# ==============================
@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'products_count']
    list_filter = ['is_active']
    search_fields = ['name']
    
    def products_count(self, obj):
        return obj.products.count()
    products_count.short_description = "Products"


# ==============================
# ADMIN ACTIONS
# ==============================
def activate_selected(modeladmin, request, queryset):
    queryset.update(is_active=True)
activate_selected.short_description = "Activate selected items"

def deactivate_selected(modeladmin, request, queryset):
    queryset.update(is_active=False)
deactivate_selected.short_description = "Deactivate selected items"

def create_default_sale_modes(modeladmin, request, queryset):
    """Create default sale modes for selected products"""
    count = 0
    for product in queryset:
        if product.unit and not product.sale_modes.exists():
            try:
                default_sale_mode = SaleMode.objects.filter(
                    base_unit=product.unit,
                    conversion_factor=Decimal('1.00'),
                    price_type='unit'
                ).first()
                
                if default_sale_mode:
                    ProductSaleMode.objects.get_or_create(
                        product=product,
                        sale_mode=default_sale_mode,
                        defaults={
                            'unit_price': product.selling_price,
                            'is_active': True
                        }
                    )
                    count += 1
            except Exception:
                pass
    
    modeladmin.message_user(request, f"Default sale modes created for {count} products.")
create_default_sale_modes.short_description = "Create default sale modes"

# Add actions to admin models
ProductAdmin.actions = [activate_selected, deactivate_selected, create_default_sale_modes]
SaleModeAdmin.actions = [activate_selected, deactivate_selected]
ProductSaleModeAdmin.actions = [activate_selected, deactivate_selected]
CategoryAdmin.actions = [activate_selected, deactivate_selected]
UnitAdmin.actions = [activate_selected, deactivate_selected]
BrandAdmin.actions = [activate_selected, deactivate_selected]
SourceAdmin.actions = [activate_selected, deactivate_selected]
GroupAdmin.actions = [activate_selected, deactivate_selected]


# ==============================
# ADMIN SITE CUSTOMIZATION
# ==============================
admin.site.site_header = "Multi-Unit Sale System Admin"
admin.site.site_title = "Product & Sale Management"
admin.site.index_title = "Dashboard"