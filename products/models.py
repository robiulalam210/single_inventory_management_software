# products/models.py
from django.db import models, transaction, IntegrityError
from django.conf import settings
from decimal import Decimal
import time
import random
from django.db.models import Prefetch

# ========== ADD THIS CLASS AT THE TOP ==========
class ProductQuerySet(models.QuerySet):
    """Custom QuerySet for Product with optimized queries"""
    
    def with_details(self):
        """Fetch products with all related details"""
        # Prefetch active sale modes
        sale_modes_prefetch = Prefetch(
            'product_sale_modes',
            queryset=ProductSaleMode.objects.filter(is_active=True)
            .select_related('sale_mode')
            .prefetch_related('tiers')
        )
        
        queryset = self.select_related(
            'category', 'unit', 'brand', 'group', 'source', 'created_by'
        ).prefetch_related(sale_modes_prefetch)
        
        return queryset
# ========== END OF ADDED CODE ==========

class Category(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name'], name='unique_category_name')
        ]
        verbose_name_plural = "Categories"
    
    def __str__(self):
        return self.name


class Brand(models.Model):
    name = models.CharField(max_length=120)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name'], name='unique_brand_name')
        ]
    
    def __str__(self):
        return self.name


class Group(models.Model):
    name = models.CharField(max_length=120)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name'], name='unique_group_name')
        ]

    def __str__(self):
        return self.name


class Source(models.Model):
    name = models.CharField(max_length=120)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name'], name='unique_source_name')
        ]

    def __str__(self):
        return self.name


class Unit(models.Model):
    name = models.CharField(max_length=60)
    code = models.CharField(max_length=20, blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name'], name='unique_unit_name')
        ]

    def __str__(self):
        return self.name


class ProductSequence(models.Model):
    """
    প্রোডাক্টের ক্রমিক SKU নম্বর তৈরির জন্য (একটাই সারি, pk=1)
    """
    last_number = models.PositiveIntegerField(default=10000)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Product Sequence"
        verbose_name_plural = "Product Sequences"

    @classmethod
    def get_next_sequence(cls):
        """
        পরের ক্রমিক নম্বর (concurrent-safe)
        """
        with transaction.atomic():
            sequence, created = cls.objects.select_for_update().get_or_create(
                pk=1,
                defaults={'last_number': 10000}
            )
            sequence.last_number += 1
            sequence.save()
            return sequence.last_number

    def __str__(self):
        return f"Product sequence - {self.last_number:05d}"


class SaleMode(models.Model):
    """Sale Mode configuration (KG, GRAM, PACKET, BOSTA, DOZEN, etc.)"""
    
    PRICE_TYPE_CHOICES = [
        ('unit', 'Unit Price'),
        ('flat', 'Flat Price'),
        ('tier', 'Tier Price'),
    ]
    
    name = models.CharField(max_length=50, help_text="KG, GRAM, PACKET, BOSTA, DOZEN, etc.")
    code = models.CharField(max_length=20, help_text="Short code (unique)")
    base_unit = models.ForeignKey('Unit', on_delete=models.CASCADE, related_name='sale_modes')
    conversion_factor = models.DecimalField(
        max_digits=12, 
        decimal_places=3,
        default=Decimal('1.00'),
        help_text="Multiplier to convert to base unit (e.g., 0.001 for GRAM to KG)"
    )
    price_type = models.CharField(max_length=10, choices=PRICE_TYPE_CHOICES, default='unit')
    is_active = models.BooleanField(default=True)
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='created_sale_modes'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['code'],
                name='unique_sale_mode_code'
            )
        ]
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.get_price_type_display()})"
    
    def convert_to_base(self, quantity):
        """Convert sale quantity to base unit quantity"""
        return Decimal(str(quantity)) * self.conversion_factor


class ProductSaleMode(models.Model):
    """Link between Product and SaleMode with specific pricing"""
    
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='product_sale_modes')
    sale_mode = models.ForeignKey('SaleMode', on_delete=models.CASCADE, related_name='product_sale_modes')
    
    # Unit Price (for price_type='unit')
    unit_price = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    
    # Flat Price (for price_type='flat')
    flat_price = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    
    # Additional fields for discounts
    discount_type = models.CharField(
        max_length=10, 
        choices=[('fixed', 'Fixed'), ('percentage', 'Percentage')],
        null=True, 
        blank=True
    )
    discount_value = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'sale_mode'],
                name='unique_product_sale_mode'
            )
        ]
        ordering = ['sale_mode__name']
    
    def __str__(self):
        return f"{self.product.name} - {self.sale_mode.name}"
    
    def get_final_price(self, quantity=1):
        """Calculate final price based on price type and quantity"""
        if not self.is_active:
            return Decimal('0.00')
        
        base_quantity = self.sale_mode.convert_to_base(quantity)
        
        # Get base price based on price type
        if self.sale_mode.price_type == 'flat':
            price = self.flat_price or Decimal('0.00')
            total = price * Decimal(str(quantity))
        else:  # unit or tier
            unit_price = self.get_unit_price(base_quantity)
            total = base_quantity * unit_price
        
        # Apply discount if any
        if self.discount_type == 'fixed' and self.discount_value:
            total -= self.discount_value
        elif self.discount_type == 'percentage' and self.discount_value:
            total -= (total * self.discount_value / Decimal('100.00'))
        
        return max(Decimal('0.00'), total)
    
    def get_unit_price(self, base_quantity=None):
        """Get unit price for the sale mode"""
        if self.sale_mode.price_type == 'tier':
            # Get tier price for the quantity
            return self.get_tier_price(base_quantity)
        else:
            return self.unit_price or Decimal('0.00')
    
    def get_tier_price(self, base_quantity):
        """Get tier price for given quantity"""
        if not hasattr(self, 'tiers'):
            return self.unit_price or Decimal('0.00')
        
        # Find appropriate tier
        tiers = self.tiers.all().order_by('min_quantity')
        for tier in tiers:
            if base_quantity >= tier.min_quantity:
                if tier.max_quantity is None or base_quantity <= tier.max_quantity:
                    return tier.price
        
        # Return default price if no tier matches
        return self.unit_price or Decimal('0.00')



class PriceTier(models.Model):
    """Tier pricing for products"""
    
    product_sale_mode = models.ForeignKey(
        'ProductSaleMode', 
        on_delete=models.CASCADE, 
        related_name='tiers'
    )
    min_quantity = models.DecimalField(
        max_digits=12, 
        decimal_places=3,
        help_text="Minimum quantity (in base unit) for this tier"
    )
    max_quantity = models.DecimalField(
        max_digits=12, 
        decimal_places=3,
        null=True, 
        blank=True,
        help_text="Maximum quantity (in base unit) for this tier (null for unlimited)"
    )
    price = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Add these if not present
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['min_quantity']
        constraints = [
            models.UniqueConstraint(
                fields=['product_sale_mode', 'min_quantity'],
                name='unique_tier_start'
            )
        ]
    
    def __str__(self):
        max_qty = f" - {self.max_quantity}" if self.max_quantity else "+"
        return f"{self.min_quantity}{max_qty}: {self.price}"




class Product(models.Model):
    DISCOUNT_TYPE_CHOICES = [
        ('fixed', 'Fixed'),
        ('percentage', 'Percentage'),
    ]
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=120, blank=True, null=True, unique=True)

    category = models.ForeignKey('Category', on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    unit = models.ForeignKey('Unit', on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    brand = models.ForeignKey('Brand', on_delete=models.SET_NULL, null=True, blank=True)
    group = models.ForeignKey('Group', on_delete=models.SET_NULL, null=True, blank=True)
    source = models.ForeignKey('Source', on_delete=models.SET_NULL, null=True, blank=True)

    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
   
    opening_stock = models.PositiveIntegerField(default=0)
    stock_qty = models.PositiveIntegerField(default=0)
    alert_quantity = models.PositiveIntegerField(default=5)
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='inventory-products/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    discount_type = models.CharField(
        max_length=10, 
        choices=DISCOUNT_TYPE_CHOICES,
        null=True, 
        blank=True
    )
    discount_value = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True,
        default=Decimal('0.00')
    )
    discount_applied_on = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ========== ADD THIS LINE ==========
    objects = ProductQuerySet.as_manager()  # Add custom manager
    
    # ========== FIXED: KEEP ONLY THIS ONE PROPERTY ==========
    @property
    def active_sale_modes(self):
        """Get active sale modes, using prefetched data if available"""
        # Check if we have prefetched data
        if hasattr(self, '_prefetched_objects_cache') and 'product_sale_modes' in self._prefetched_objects_cache:
            # Filter prefetched data for active sale modes
            return [psm for psm in self._prefetched_objects_cache['product_sale_modes'] if psm.is_active]
        # Fallback to database query
        return self.product_sale_modes.filter(is_active=True).select_related('sale_mode')
    # ========== END FIX ==========

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['sku']),
            models.Index(fields=['name']),
            models.Index(fields=['category']),
            models.Index(fields=['brand']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['name'],
                name='unique_product_name'
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.sku})" if self.sku else self.name

    @property
    def status(self):
        return "Active" if self.is_active else "Inactive"

    @property
    def stock_status(self):
        """Returns stock status: 'out_of_stock', 'low_stock', 'in_stock'"""
        if self.stock_qty == 0:
            return "out_of_stock"
        elif self.stock_qty <= self.alert_quantity:
            return "low_stock"
        else:
            return "in_stock"

    @property
    def stock_status_code(self):
        """Returns stock status code: 0=out of stock, 1=low stock, 2=in stock"""
        if self.stock_qty == 0:
            return 0
        elif self.stock_qty <= self.alert_quantity:
            return 1
        else:
            return 2

    @property
    def final_price(self):
        """Calculate final price after discount"""
        if not self.discount_applied_on or not self.discount_value:
            return self.selling_price
        
        if self.discount_type == 'fixed':
            final_price = max(Decimal('0.00'), self.selling_price - self.discount_value)
        elif self.discount_type == 'percentage':
            discount_amount = (self.selling_price * self.discount_value) / Decimal('100.00')
            final_price = max(Decimal('0.00'), self.selling_price - discount_amount)
        else:
            final_price = self.selling_price
            
        return final_price.quantize(Decimal('0.01'))

    def get_sale_mode_price(self, sale_mode_id, quantity=1):
        """Get price for specific sale mode and quantity"""
        try:
            product_sale_mode = ProductSaleMode.objects.select_related('sale_mode').get(
                product=self,
                sale_mode_id=sale_mode_id,
                is_active=True
            )
            return product_sale_mode.get_final_price(quantity)
        except ProductSaleMode.DoesNotExist:
            return None

    def get_sale_mode_by_code(self, sale_mode_code, quantity=1):
        """Get price for sale mode by code"""
        try:
            product_sale_mode = ProductSaleMode.objects.select_related('sale_mode').get(
                product=self,
                sale_mode__code=sale_mode_code,
                is_active=True
            )
            return {
                'sale_mode_id': product_sale_mode.sale_mode.id,
                'sale_mode_name': product_sale_mode.sale_mode.name,
                'sale_mode_code': product_sale_mode.sale_mode.code,
                'price_type': product_sale_mode.sale_mode.price_type,
                'price': float(product_sale_mode.get_final_price(quantity)),
                'unit_price': float(product_sale_mode.unit_price) if product_sale_mode.unit_price else None,
                'flat_price': float(product_sale_mode.flat_price) if product_sale_mode.flat_price else None,
                'discount_type': product_sale_mode.discount_type,
                'discount_value': float(product_sale_mode.discount_value) if product_sale_mode.discount_value else None,
            }
        except ProductSaleMode.DoesNotExist:
            return None

    def _generate_sku(self):
        """Generate sequential SKU"""
        try:
            next_num = ProductSequence.get_next_sequence()
            return f"PDT-{next_num}"
        except Exception as e:
            return self._generate_fallback_sku()

    def _generate_fallback_sku(self):
        """Generate fallback SKU using timestamp"""
        timestamp = int(time.time())
        random_suffix = random.randint(100, 999)
        return f"PDT-FB{timestamp}{random_suffix}"

    def clean(self):
        """Model validation"""
        from django.core.exceptions import ValidationError
        
        if self.purchase_price < 0:
            raise ValidationError("Purchase price cannot be negative")
        
        if self.selling_price < 0:
            raise ValidationError("Selling price cannot be negative")
        
        if self.discount_value and self.discount_value < 0:
            raise ValidationError("Discount value cannot be negative")
        
        if self.discount_value and not self.discount_type:
            raise ValidationError("Discount type is required when discount value is set")
        
        if self.discount_type and not self.discount_value:
            raise ValidationError("Discount value is required when discount type is set")

    def save(self, *args, **kwargs):
        """Custom save with SKU generation and validation"""
        is_new = self.pk is None
        
        self.clean()
        
        if is_new:
            if self.stock_qty == 0 and self.opening_stock > 0:
                self.stock_qty = self.opening_stock

            if not self.sku:
                try:
                    self.sku = self._generate_sku()
                except Exception as e:
                    self.sku = self._generate_fallback_sku()

        max_retries = 3
        for attempt in range(max_retries):
            try:
                with transaction.atomic():
                    super().save(*args, **kwargs)
                break
            except IntegrityError as e:
                if 'sku' in str(e).lower() and is_new and attempt < max_retries - 1:
                    self.sku = self._generate_fallback_sku()
                    continue
                else:
                    raise

    def can_be_deleted(self):
        """Check if product can be safely deleted"""
        try:
            from purchases.models import PurchaseItem
            from sales.models import SaleItem
            
            has_purchases = PurchaseItem.objects.filter(product=self).exists()
            has_sales = SaleItem.objects.filter(product=self).exists()
            
            return not (has_purchases or has_sales)
        except (ImportError, Exception):
            return True

    def update_stock(self, quantity, transaction_type, update_product=True):
        """Update product stock quantity"""
        if transaction_type == 'in':
            self.stock_qty += quantity
        elif transaction_type == 'out':
            if self.stock_qty < quantity:
                raise ValueError(f"Insufficient stock. Available: {self.stock_qty}, Requested: {quantity}")
            self.stock_qty -= quantity
        else:
            raise ValueError("Transaction type must be 'in' or 'out'")
        
        if update_product:
            self.save(update_fields=['stock_qty', 'updated_at'])
        
        return self.stock_qty

    def get_stock_value(self, price_type='purchase'):
        """Get total stock value based on price type"""
        if price_type == 'purchase':
            price = self.purchase_price
        elif price_type == 'selling':
            price = self.selling_price
        elif price_type == 'final':
            price = self.final_price
        else:
            price = self.purchase_price
            
        return self.stock_qty * price

    @classmethod
    def get_low_stock_products(cls):
        """Get products with low stock"""
        return cls.objects.filter(
            is_active=True,
            stock_qty__lte=models.F('alert_quantity')
        ).order_by('stock_qty')

    @classmethod
    def get_out_of_stock_products(cls):
        """Get out-of-stock products"""
        return cls.objects.filter(
            is_active=True,
            stock_qty=0
        )

    def get_product_summary(self):
        """Get product summary for API responses"""
        sale_modes_summary = []
        for sale_mode in self.active_sale_modes:
            sale_modes_summary.append({
                'id': sale_mode.id,
                'sale_mode_id': sale_mode.sale_mode.id,
                'sale_mode_name': sale_mode.sale_mode.name,
                'sale_mode_code': sale_mode.sale_mode.code,
                'price_type': sale_mode.sale_mode.price_type,
                'unit_price': float(sale_mode.unit_price) if sale_mode.unit_price else None,
                'flat_price': float(sale_mode.flat_price) if sale_mode.flat_price else None,
                'discount_type': sale_mode.discount_type,
                'discount_value': float(sale_mode.discount_value) if sale_mode.discount_value else None,
                'is_active': sale_mode.is_active,
            })
        
        return {
            'id': self.id,
            'name': self.name,
            'sku': self.sku,
            'category': self.category.name if self.category else None,
            'brand': self.brand.name if self.brand else None,
            'unit': self.unit.name if self.unit else None,
            'purchase_price': float(self.purchase_price),
            'selling_price': float(self.selling_price),
            'final_price': float(self.final_price),
            'stock_qty': self.stock_qty,
            'alert_quantity': self.alert_quantity,
            'stock_status': self.stock_status,
            'stock_status_code': self.stock_status_code,
            'is_active': self.is_active,
            'sale_modes': sale_modes_summary,
            'created_at': self.created_at.isoformat(),
        }