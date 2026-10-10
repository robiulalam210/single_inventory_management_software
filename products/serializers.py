# products/serializers.py
from rest_framework import serializers
from django.conf import settings
from django.db import transaction, IntegrityError
import time
import random
from decimal import Decimal, InvalidOperation
import re
import json
from .models import Category, Unit, Brand, Group, Source, Product, ProductSaleMode, SaleMode, PriceTier


# SKU ক্রমিক নম্বর (ProductSequence না থাকলে fallback)
class ProductSequence:
    """Fallback ProductSequence class for SKU generation"""
    @classmethod
    def get_next_sequence(cls):
        """Get next sequence number"""
        try:
            from .models import ProductSequence as RealSequence
            return RealSequence.get_next_sequence()
        except (ImportError, AttributeError):
            import time
            timestamp = int(time.time())
            return timestamp % 1000000 + 1000


class CleanedChoiceField(serializers.ChoiceField):
    """Custom ChoiceField that cleans quoted strings BEFORE any validation"""
    
    def __init__(self, **kwargs):
        kwargs.setdefault('allow_blank', True)
        super().__init__(**kwargs)
    
    def to_internal_value(self, data):
        """Clean the data before validation"""
        if data is not None:
            if not isinstance(data, str):
                data = str(data)
            
            data = re.sub(r'["\']', '', data).strip().lower()
            
            value_mapping = {
                'percent': 'percentage',
                'pct': 'percentage',
                'perc': 'percentage',
                'fixed_amount': 'fixed',
                'flat': 'fixed',
                'percentage': 'percentage',
                'fixed': 'fixed',
            }
            
            if data in value_mapping:
                data = value_mapping[data]
            
            if data == '':
                data = None
        
        return super().to_internal_value(data)


def _product_count(obj, field):
    """list এ annotate করা থাকে; create/update এর উত্তরে না থাকলে গুনে নিই"""
    v = getattr(obj, 'product_count', None)
    if v is not None:
        return v
    if not obj.pk:
        return 0
    from .models import Product
    return Product.objects.filter(**{field: obj}).count()

class CategorySerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    product_count = serializers.SerializerMethodField()

    def get_product_count(self, obj):
        return _product_count(obj, 'category')
    
    class Meta:
        model = Category
        fields = '__all__'





class BrandSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    product_count = serializers.SerializerMethodField()

    def get_product_count(self, obj):
        return _product_count(obj, 'brand')
    
    class Meta:
        model = Brand
        fields = '__all__'


class GroupSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    product_count = serializers.SerializerMethodField()

    def get_product_count(self, obj):
        return _product_count(obj, 'group')
    
    class Meta:
        model = Group
        fields = '__all__'


class SourceSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    product_count = serializers.SerializerMethodField()

    def get_product_count(self, obj):
        return _product_count(obj, 'source')
    
    class Meta:
        model = Source
        fields = '__all__'

        
class UnitSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    product_count = serializers.SerializerMethodField()
    sale_mode_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Unit
        fields = '__all__'

    # list এ annotate করা থাকে; create/update এর উত্তরে না থাকলে গুনে নিই
    def get_product_count(self, obj):
        v = getattr(obj, 'product_count', None)
        return v if v is not None else (obj.products.count() if obj.pk else 0)

    def get_sale_mode_count(self, obj):
        v = getattr(obj, 'sale_mode_count', None)
        return v if v is not None else (obj.sale_modes.count() if obj.pk else 0)
# serializers.py
class PriceTierSerializer(serializers.ModelSerializer):
    product_sale_mode = serializers.IntegerField(write_only=True)
    
    # New fields for user input in sale mode units
    min_quantity_sale_mode = serializers.DecimalField(
        max_digits=12, 
        decimal_places=3,
        write_only=True,
        required=False,
        help_text="Minimum quantity in sale mode units (e.g., Dojon)"
    )
    max_quantity_sale_mode = serializers.DecimalField(
        max_digits=12, 
        decimal_places=3,
        write_only=True,
        required=False,
        help_text="Maximum quantity in sale mode units (e.g., Dojon)"
    )
    
    # Display fields
    min_quantity_display = serializers.SerializerMethodField()
    max_quantity_display = serializers.SerializerMethodField()
    unit_info = serializers.SerializerMethodField()
    
    class Meta:
        model = PriceTier
        fields = [
            'id', 'product_sale_mode', 
            'min_quantity', 'max_quantity', 'price',
            'min_quantity_sale_mode', 'max_quantity_sale_mode',  # For input
            'min_quantity_display', 'max_quantity_display',  # For display
            'unit_info',  # For display
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_min_quantity_display(self, obj):
        """Show min quantity in sale mode units"""
        product_sale_mode = obj.product_sale_mode
        if product_sale_mode and product_sale_mode.sale_mode:
            conversion = product_sale_mode.sale_mode.conversion_factor
            if conversion and conversion > 0:
                min_in_sale_mode = obj.min_quantity / conversion
                return f"{min_in_sale_mode:.2f} {product_sale_mode.sale_mode.name}"
        return f"{obj.min_quantity}"
    
    def get_max_quantity_display(self, obj):
        """Show max quantity in sale mode units"""
        if not obj.max_quantity:
            return "∞"
        
        product_sale_mode = obj.product_sale_mode
        if product_sale_mode and product_sale_mode.sale_mode:
            conversion = product_sale_mode.sale_mode.conversion_factor
            if conversion and conversion > 0:
                max_in_sale_mode = obj.max_quantity / conversion
                return f"{max_in_sale_mode:.2f} {product_sale_mode.sale_mode.name}"
        return f"{obj.max_quantity}"
    
    def get_unit_info(self, obj):
        """Get unit information"""
        product_sale_mode = obj.product_sale_mode
        if product_sale_mode and product_sale_mode.sale_mode:
            return {
                'sale_mode_name': product_sale_mode.sale_mode.name,
                'base_unit_name': product_sale_mode.sale_mode.base_unit.name,
                'conversion_factor': float(product_sale_mode.sale_mode.conversion_factor),
                'formula': f"1 {product_sale_mode.sale_mode.name} = {product_sale_mode.sale_mode.conversion_factor} {product_sale_mode.sale_mode.base_unit.name}"
            }
        return None
    
    def validate(self, data):
        """Validate tier data"""
        # Check if user provided sale mode units or base units
        min_sale_mode = data.get('min_quantity_sale_mode')
        max_sale_mode = data.get('max_quantity_sale_mode')
        min_base = data.get('min_quantity')
        max_base = data.get('max_quantity')
        
        # Get product sale mode for conversion
        product_sale_mode_id = data.get('product_sale_mode')
        if product_sale_mode_id:
            try:
                product_sale_mode = ProductSaleMode.objects.get(id=product_sale_mode_id)
                conversion = product_sale_mode.sale_mode.conversion_factor
                
                # If user provided sale mode units, convert to base units
                if min_sale_mode is not None:
                    data['min_quantity'] = min_sale_mode * conversion
                
                if max_sale_mode is not None:
                    if max_sale_mode:
                        data['max_quantity'] = max_sale_mode * conversion
                    else:
                        data['max_quantity'] = None
                
            except ProductSaleMode.DoesNotExist:
                pass
        
        # Validate min < max if both provided
        if data.get('max_quantity') and data.get('min_quantity'):
            if data['max_quantity'] <= data['min_quantity']:
                raise serializers.ValidationError({
                    'max_quantity': 'Maximum quantity must be greater than minimum quantity'
                })
        
        return data
    
    def create(self, validated_data):
        """Create PriceTier with proper conversion"""
        # Remove sale mode unit fields
        validated_data.pop('min_quantity_sale_mode', None)
        validated_data.pop('max_quantity_sale_mode', None)
        
        # Get the ProductSaleMode instance from ID
        product_sale_mode_id = validated_data.pop('product_sale_mode')
        try:
            product_sale_mode = ProductSaleMode.objects.get(id=product_sale_mode_id)
        except ProductSaleMode.DoesNotExist:
            raise serializers.ValidationError({
                'product_sale_mode': f'ProductSaleMode with id {product_sale_mode_id} does not exist'
            })
        
        # Create the PriceTier
        return PriceTier.objects.create(
            product_sale_mode=product_sale_mode,
            **validated_data
        )

class ProductSaleModeSerializer(serializers.ModelSerializer):
    """Serializer for ProductSaleMode with tiers"""
    tiers = PriceTierSerializer(many=True, read_only=True)  # Make sure this is read_only=True
    
    sale_mode_name = serializers.CharField(source='sale_mode.name', read_only=True)
    sale_mode_code = serializers.CharField(source='sale_mode.code', read_only=True)
    price_type = serializers.CharField(source='sale_mode.price_type', read_only=True)
    conversion_factor = serializers.DecimalField(
        source='sale_mode.conversion_factor', 
        max_digits=12, 
        decimal_places=6,
        read_only=True
    )
    base_unit_name = serializers.CharField(source='sale_mode.base_unit.name', read_only=True)
    
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    
    class Meta:
        model = ProductSaleMode
        fields = [
            'id', 'product', 'product_name', 'product_sku',
            'sale_mode', 'sale_mode_name', 'sale_mode_code',
            'unit_price', 'flat_price', 'price_type', 'conversion_factor',
            'base_unit_name', 'discount_type', 'discount_value', 'is_active',
            'tiers',  # Include tiers here
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'product_name', 'product_sku', 'sale_mode_name', 'sale_mode_code',
            'price_type', 'conversion_factor', 'base_unit_name', 'created_at', 'updated_at'
        ]
        
class ProductSaleModeNestedSerializer(serializers.ModelSerializer):
    """Serializer for ProductSaleMode when nested inside Product"""
    sale_mode_id = serializers.IntegerField(source='sale_mode.id', read_only=True)
    sale_mode_name = serializers.CharField(source='sale_mode.name', read_only=True)
    sale_mode_code = serializers.CharField(source='sale_mode.code', read_only=True)
    price_type = serializers.CharField(source='sale_mode.price_type', read_only=True)
    conversion_factor = serializers.DecimalField(
        source='sale_mode.conversion_factor', 
        max_digits=12, 
        decimal_places=6,
        read_only=True
    )
    base_unit_name = serializers.CharField(source='sale_mode.base_unit.name', read_only=True)
    
    # Include tiers
    tiers = PriceTierSerializer(many=True, read_only=True)
    
    # 🔥 FIXED: Change to DecimalField with proper source
    effective_unit_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
        source='get_effective_unit_price_for_api'  # New property method
    )
    
    effective_flat_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
        source='get_effective_flat_price_for_api'  # New property method
    )
    
    class Meta:
        model = ProductSaleMode
        fields = [
            'id', 'sale_mode_id', 'sale_mode_name', 'sale_mode_code',
            'price_type', 'unit_price', 'flat_price', 'conversion_factor',
            'base_unit_name', 'discount_type', 'discount_value', 'is_active',
            'tiers', 
            'effective_unit_price', 'effective_flat_price',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SaleModeSerializer(serializers.ModelSerializer):
    base_unit_name = serializers.CharField(source='base_unit.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True, allow_null=True)
    
    class Meta:
        model = SaleMode
        fields = [
            'id', 'name', 'code', 'base_unit', 'base_unit_name',
            'conversion_factor', 'price_type', 'is_active', 
            'created_by', 'created_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']

    def to_representation(self, instance):
        # কতগুলো product এ এই মাপের দাম বসানো, আর কতবার বিক্রি হয়েছে (list এ annotate করা থাকে)
        data = super().to_representation(instance)
        pc = getattr(instance, 'product_count', None)
        sc = getattr(instance, 'sale_count', None)
        data['product_count'] = pc if pc is not None else (instance.product_sale_modes.count() if instance.pk else 0)
        data['sale_count'] = sc if sc is not None else (instance.saleitem_set.count() if instance.pk else 0)
        return data
    
    def validate_base_unit(self, value):
        """Validate base_unit exists"""
        if not value:
            raise serializers.ValidationError("Base unit is required")
        
        return value
    
    def validate_conversion_factor(self, value):
        """Validate conversion factor"""
        if value <= 0:
            raise serializers.ValidationError(
                "Conversion factor must be greater than 0"
            )
        return value
    
    def create(self, validated_data):
        """Override create to set created_by"""
        request = self.context.get('request')
        
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        
        return super().create(validated_data)


class ProductSaleModeSimpleSerializer(serializers.ModelSerializer):
    """Simple serializer for nested product sale modes with tiers"""
    sale_mode_id = serializers.IntegerField(source='sale_mode.id', read_only=True)
    sale_mode_name = serializers.CharField(source='sale_mode.name', read_only=True)
    sale_mode_code = serializers.CharField(source='sale_mode.code', read_only=True)
    price_type = serializers.CharField(source='sale_mode.price_type', read_only=True)
    
    # Include tiers
    tiers = PriceTierSerializer(many=True, read_only=True)
    
    class Meta:
        model = ProductSaleMode
        fields = [
            'id', 'sale_mode_id', 'sale_mode_name', 'sale_mode_code',
            'price_type', 'unit_price', 'flat_price', 'discount_type',
            'discount_value', 'is_active', 'tiers'  # Add tiers
        ]
        
class ProductDetailSerializer(serializers.ModelSerializer):
    """Extended product serializer with sale modes"""
    # ========== FIXED: Use the new nested serializer ==========
    sale_modes = ProductSaleModeNestedSerializer(
        source='active_sale_modes',
        many=True, 
        read_only=True
    )
    # ========== END FIX ==========
    
    available_sale_modes = serializers.SerializerMethodField()
    base_unit_name = serializers.CharField(source='unit.name', read_only=True)
    base_unit_code = serializers.CharField(source='unit.code', read_only=True)
    
    # Foreign key info fields
    category_info = serializers.SerializerMethodField(read_only=True)
    unit_info = serializers.SerializerMethodField(read_only=True)
    brand_info = serializers.SerializerMethodField(read_only=True)
    group_info = serializers.SerializerMethodField(read_only=True)
    source_info = serializers.SerializerMethodField(read_only=True)
    created_by_info = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'sku', 'created_by',
            'category', 'unit', 'brand', 'group', 'source',
            'purchase_price', 'selling_price', 'opening_stock',
            'stock_qty', 'alert_quantity', 'description', 'image',
            'is_active', 'discount_type', 'discount_value',
            'discount_applied_on', 'created_at', 'updated_at',
            'stock_status', 'final_price', 'stock_status_code',
            # Sale mode fields WITH tiers
            'sale_modes', 'available_sale_modes', 'base_unit_name', 'base_unit_code',
            # Foreign key info
            'category_info', 'unit_info', 'brand_info', 'group_info', 
            'source_info', 'created_by_info'
        ]
        read_only_fields = [
            'id', 'created_by', 'sku', 'stock_status',
            'final_price', 'stock_status_code', 'created_at', 'updated_at'
        ]
    
    def get_available_sale_modes(self, obj):
        """Get all available sale modes for this product type"""
        from .models import SaleMode
        
        sale_modes = SaleMode.objects.filter(
            base_unit=obj.unit,
            is_active=True
        ).values('id', 'name', 'code', 'price_type', 'conversion_factor')
        
        for mode in sale_modes:
            try:
                product_sale_mode = ProductSaleMode.objects.get(
                    product=obj,
                    sale_mode_id=mode['id']
                )
                mode['configured'] = True
                mode['is_active'] = product_sale_mode.is_active
                mode['unit_price'] = float(product_sale_mode.unit_price) if product_sale_mode.unit_price else None
                mode['flat_price'] = float(product_sale_mode.flat_price) if product_sale_mode.flat_price else None
                mode['discount_type'] = product_sale_mode.discount_type
                mode['discount_value'] = float(product_sale_mode.discount_value) if product_sale_mode.discount_value else None
            except ProductSaleMode.DoesNotExist:
                mode['configured'] = False
                mode['is_active'] = False
                mode['unit_price'] = None
                mode['flat_price'] = None
                mode['discount_type'] = None
                mode['discount_value'] = None
        
        return list(sale_modes)
    
    def get_category_info(self, obj):
        if obj.category:
            return {'id': obj.category.id, 'name': obj.category.name}
        return None

    def get_unit_info(self, obj):
        if obj.unit:
            return {'id': obj.unit.id, 'name': obj.unit.name, 'code': obj.unit.code}
        return None

    def get_brand_info(self, obj):
        if obj.brand:
            return {'id': obj.brand.id, 'name': obj.brand.name}
        return None

    def get_group_info(self, obj):
        if obj.group:
            return {'id': obj.group.id, 'name': obj.group.name}
        return None

    def get_source_info(self, obj):
        if obj.source:
            return {'id': obj.source.id, 'name': obj.source.name}
        return None

    def get_created_by_info(self, obj):
        if obj.created_by:
            return {
                'id': obj.created_by.id, 
                'username': obj.created_by.username,
                'email': obj.created_by.email
            }
        return None
    

class ProductCreateSerializer(serializers.ModelSerializer):
    discount_type = CleanedChoiceField(
        choices=Product.DISCOUNT_TYPE_CHOICES,
        required=False,
        allow_null=True
    )
    discount_value = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
        min_value=Decimal('0.00')
    )
    discount_applied_on = serializers.BooleanField(
        required=False,
        default=False
    )
    
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
       required=False,         # Change required=True to required=False
    allow_null=True         # Add allow_null=True
    )

    unit = serializers.PrimaryKeyRelatedField(
        queryset=Unit.objects.all(),
        required=True
    )
    brand = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.all(),
        required=False,
        allow_null=True
    )
    group = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(),
        required=False,
        allow_null=True
    )
    source = serializers.PrimaryKeyRelatedField(
        queryset=Source.objects.all(),
        required=False,
        allow_null=True
    )

    class Meta:
        model = Product
        fields = [
            'name', 'category', 'unit', 'brand', 'group', 'source',
            'purchase_price', 'selling_price', 'opening_stock', 
            'alert_quantity', 'description', 'image', 'is_active',
            'discount_type', 'discount_value', 'discount_applied_on'
        ]
        extra_kwargs = {
            'purchase_price': {'default': Decimal('0.00')},
            'selling_price': {'default': Decimal('0.00')},
            'opening_stock': {'default': 0},
            'alert_quantity': {'default': 5},
            'is_active': {'default': True},
        }

    def to_internal_value(self, data):
        if isinstance(data, dict):
            data = data.copy()
            
            if 'groups' in data and 'group' not in data:
                data['group'] = data.pop('groups')
            
            if 'discount_applied_on' in data:
                value = data['discount_applied_on']
                if isinstance(value, str):
                    value = value.strip().lower()
                    data['discount_applied_on'] = value in ['true', '1', 'yes', 'on']
        
        return super().to_internal_value(data)

    def validate_name(self, value):
        if Product.objects.filter(name=value).exists():
            raise serializers.ValidationError(
                "A product with this name already exists."
            )
        return value

    def validate(self, data):
        purchase_price = data.get('purchase_price', Decimal('0.00'))
        selling_price = data.get('selling_price', Decimal('0.00'))
        
        if selling_price < purchase_price:
            raise serializers.ValidationError({
                "selling_price": "Selling price cannot be less than purchase price"
            })
        
        opening_stock = data.get('opening_stock', 0)
        if opening_stock < 0:
            raise serializers.ValidationError({
                "opening_stock": "Opening stock cannot be negative"
            })
        
        alert_quantity = data.get('alert_quantity', 5)
        if alert_quantity < 0:
            raise serializers.ValidationError({
                "alert_quantity": "Alert quantity cannot be negative"
            })
        
        discount_type = data.get('discount_type')
        discount_value = data.get('discount_value')
        discount_applied_on = data.get('discount_applied_on', False)
        
        if discount_applied_on:
            if not discount_type:
                raise serializers.ValidationError({
                    "discount_type": "Discount type is required when discount is applied"
                })
            if not discount_value:
                raise serializers.ValidationError({
                    "discount_value": "Discount value is required when discount is applied"
                })
            if discount_value and discount_value < Decimal('0.00'):
                raise serializers.ValidationError({
                    "discount_value": "Discount value cannot be negative"
                })
        else:
            if discount_type or discount_value:
                data['discount_type'] = None
                data['discount_value'] = None
        
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required")

        validated_data['created_by'] = request.user

        opening_stock = validated_data.get('opening_stock', 0)
        validated_data['stock_qty'] = opening_stock

        if not validated_data.get('sku'):
            try:
                next_num = ProductSequence.get_next_sequence()
                validated_data['sku'] = f"PDT-{next_num}"
            except Exception as e:
                timestamp = int(time.time())
                random_suffix = random.randint(100, 999)
                validated_data['sku'] = f"PDT-FB{timestamp}{random_suffix}"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                with transaction.atomic():
                    product = Product.objects.create(**validated_data)
                return product
            except IntegrityError as e:
                if 'sku' in str(e).lower() and attempt < max_retries - 1:
                    timestamp = int(time.time())
                    random_suffix = random.randint(100, 999)
                    validated_data['sku'] = f"PDT-{timestamp}{random_suffix}"
                    continue
                else:
                    if 'unique_product_name' in str(e) or 'name' in str(e).lower() and 'unique' in str(e).lower() and 'sku' not in str(e).lower():
                        raise serializers.ValidationError({
                            'name': 'A product with this name already exists.'
                        })
                    elif 'sku' in str(e).lower():
                        raise serializers.ValidationError({
                            'sku': f'Could not generate unique SKU after {max_retries} attempts. Please try again.'
                        })
                    else:
                        raise


class ProductUpdateSerializer(serializers.ModelSerializer):
    discount_type = CleanedChoiceField(
        choices=Product.DISCOUNT_TYPE_CHOICES,
        required=False,
        allow_null=True
    )
    discount_value = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
        min_value=Decimal('0.00')
    )
    discount_applied_on = serializers.BooleanField(required=False)
    
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        required=False
    )
    unit = serializers.PrimaryKeyRelatedField(
        queryset=Unit.objects.all(),
        required=False
    )
    brand = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.all(),
        required=False,
        allow_null=True
    )
    group = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(),
        required=False,
        allow_null=True
    )
    source = serializers.PrimaryKeyRelatedField(
        queryset=Source.objects.all(),
        required=False,
        allow_null=True
    )

    class Meta:
        model = Product
        fields = [
            'name', 'category', 'unit', 'brand', 'group', 'source',
            'purchase_price', 'selling_price', 'alert_quantity', 
            'description', 'image', 'is_active',
            'discount_type', 'discount_value', 'discount_applied_on'
        ]

    def to_internal_value(self, data):
        if isinstance(data, dict):
            data = data.copy()
            
            if 'groups' in data and 'group' not in data:
                data['group'] = data.pop('groups')
            
            if 'discount_applied_on' in data:
                value = data['discount_applied_on']
                if isinstance(value, str):
                    value = value.strip().lower()
                    data['discount_applied_on'] = value in ['true', '1', 'yes', 'on']
        
        return super().to_internal_value(data)

    def validate_name(self, value):
        instance = self.instance
        
        if Product.objects.filter(name=value).exclude(id=instance.id).exists():
            raise serializers.ValidationError(
                "A product with this name already exists."
            )
        return value

    def validate(self, data):
        errors = {}

        instance = self.instance
        purchase_price = data.get('purchase_price', instance.purchase_price if instance else Decimal('0.00'))
        selling_price = data.get('selling_price', instance.selling_price if instance else Decimal('0.00'))
        
        if selling_price < purchase_price:
            errors['selling_price'] = "Selling price cannot be less than purchase price"
        
        discount_type = data.get('discount_type')
        discount_value = data.get('discount_value')
        discount_applied_on = data.get('discount_applied_on', 
                                     instance.discount_applied_on if instance else False)
        
        if discount_applied_on:
            if not discount_type:
                discount_type = instance.discount_type if instance else None
            if not discount_value:
                discount_value = instance.discount_value if instance else None
                
            if not discount_type:
                errors['discount_type'] = "Discount type is required when discount is applied"
            if not discount_value:
                errors['discount_value'] = "Discount value is required when discount is applied"
            elif discount_value and discount_value < Decimal('0.00'):
                errors['discount_value'] = "Discount value cannot be negative"
        else:
            data['discount_type'] = None
            data['discount_value'] = None
            data['discount_applied_on'] = False

        if errors:
            raise serializers.ValidationError(errors)

        return data
    
    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        return instance


class ProductSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    
    # ========== FIXED: Use the new nested serializer ==========
    sale_modes = ProductSaleModeNestedSerializer(
        source='active_sale_modes',
        many=True, 
        read_only=True
    )
    # ========== END FIX ==========
    
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        required=False
    )
    unit = serializers.PrimaryKeyRelatedField(
        queryset=Unit.objects.all(),
        required=False
    )
    brand = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.all(),
        required=False,
        allow_null=True
    )
    group = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(),
        required=False,
        allow_null=True
    )
    source = serializers.PrimaryKeyRelatedField(
        queryset=Source.objects.all(),
        required=False,
        allow_null=True
    )
    
    # Info fields
    category_info = serializers.SerializerMethodField(read_only=True)
    unit_info = serializers.SerializerMethodField(read_only=True)
    brand_info = serializers.SerializerMethodField(read_only=True)
    group_info = serializers.SerializerMethodField(read_only=True)
    source_info = serializers.SerializerMethodField(read_only=True)
    created_by_info = serializers.SerializerMethodField(read_only=True)
    
    # Stock fields
    stock_status = serializers.ReadOnlyField()
    stock_status_display = serializers.SerializerMethodField(read_only=True)
    stock_status_code = serializers.ReadOnlyField()
    
    # Discount fields
    discount_type = CleanedChoiceField(
        choices=Product.DISCOUNT_TYPE_CHOICES,
        required=False,
        allow_null=True
    )
    discount_value = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
        min_value=Decimal('0.00')
    )
    discount_applied_on = serializers.BooleanField(required=False, default=False)
    
    discount_applied = serializers.BooleanField(source='discount_applied_on', read_only=True)
    final_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )
    
    class Meta:
        model = Product
        fields = [
            'id', 'created_by', 'name', 'sku', 
            'category', 'unit', 'brand', 'group', 'source',
            'purchase_price', 'selling_price', 'opening_stock', 
            'stock_qty', 'alert_quantity', 'description', 'image',
            'is_active', 'created_at', 'updated_at',
            # Info fields
            'category_info', 'unit_info', 'brand_info', 'group_info', 
            'source_info', 'created_by_info',
            # Stock fields
            'stock_status', 'stock_status_display', 'stock_status_code',
            # Discount fields
            'discount_type', 'discount_value', 'discount_applied_on',
            'discount_applied', 'final_price',
            # Sale modes WITH tiers
            'sale_modes'
        ]
        read_only_fields = [
            'id', 'created_by', 'created_at', 'updated_at', 
            'sku', 'stock_status', 'stock_status_code', 'stock_qty', 'final_price'
        ]

    def get_category_info(self, obj):
        if obj.category:
            return {'id': obj.category.id, 'name': obj.category.name}
        return None

    def get_unit_info(self, obj):
        if obj.unit:
            return {'id': obj.unit.id, 'name': obj.unit.name, 'code': obj.unit.code}
        return None

    def get_brand_info(self, obj):
        if obj.brand:
            return {'id': obj.brand.id, 'name': obj.brand.name}
        return None

    def get_group_info(self, obj):
        if obj.group:
            return {'id': obj.group.id, 'name': obj.group.name}
        return None

    def get_source_info(self, obj):
        if obj.source:
            return {'id': obj.source.id, 'name': obj.source.name}
        return None

    def get_created_by_info(self, obj):
        if obj.created_by:
            return {
                'id': obj.created_by.id, 
                'username': obj.created_by.username,
                'email': obj.created_by.email
            }
        return None

    def get_stock_status_display(self, obj):
        status_map = {
            'out_of_stock': 'Out of Stock',
            'low_stock': 'Low Stock', 
            'in_stock': 'In Stock'
        }
        return status_map.get(obj.stock_status, 'Unknown')

    def validate(self, data):
        discount_applied_on = data.get('discount_applied_on', False)
        discount_type = data.get('discount_type')
        discount_value = data.get('discount_value')
        
        if discount_applied_on:
            if not discount_type:
                raise serializers.ValidationError({
                    "discount_type": "Discount type is required when discount is applied"
                })
            if not discount_value:
                raise serializers.ValidationError({
                    "discount_value": "Discount value is required when discount is applied"
                })
        
        return data

class ProductBulkCreateSerializer(serializers.Serializer):
    """Serializer for bulk product creation"""
    products = ProductCreateSerializer(many=True)
    
    def create(self, validated_data):
        products_data = validated_data['products']
        products = []
        
        for product_data in products_data:
            serializer = ProductCreateSerializer(
                data=product_data,
                context=self.context
            )
            if serializer.is_valid():
                product = serializer.save()
                products.append(product)
            else:
                raise serializers.ValidationError({
                    'errors': serializer.errors
                })
        
        return {'products': products}


class ProductImportSerializer(serializers.Serializer):
    """Serializer for product import from CSV/Excel"""
    file = serializers.FileField()
    overwrite = serializers.BooleanField(default=False)
    
    def validate_file(self, value):
        valid_extensions = ['.csv', '.xlsx', '.xls']
        import os
        ext = os.path.splitext(value.name)[1]
        if ext.lower() not in valid_extensions:
            raise serializers.ValidationError(
                f"Unsupported file format. Supported formats: {', '.join(valid_extensions)}"
            )
        return value