# sales/serializers.py
from rest_framework import serializers
from .models import Sale, SaleItem
from products.models import Product, SaleMode, ProductSaleMode
from accounts.models import Account
from customers.models import Customer
from django.db import transaction
from django.contrib.auth import get_user_model
from decimal import Decimal
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


class FlexibleDateTimeField(serializers.DateTimeField):
    """'2026-01-16' (শুধু তারিখ) অথবা পুরো datetime — দুটোই নেয়।
    শুধু তারিখ এলে সেই দিনের বর্তমান সময় বসে (আজকের হলে) নয়তো দুপুর ১২টা।"""

    def to_internal_value(self, value):
        from datetime import datetime, time as dtime
        from django.utils import timezone as tz
        from django.utils.dateparse import parse_date
        if isinstance(value, str) and len(value.strip()) == 10:
            d = parse_date(value.strip())
            if d is None:
                for fmt in ("%d-%m-%Y", "%d/%m/%Y"):
                    try:
                        d = datetime.strptime(value.strip(), fmt).date()
                        break
                    except ValueError:
                        pass
            if d is not None:
                now = tz.localtime()
                t = now.time() if d == now.date() else dtime(12, 0)
                return tz.make_aware(datetime.combine(d, t))
        return super().to_internal_value(value)



class SaleItemSerializer(serializers.ModelSerializer):
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source='product',
        write_only=True
    )
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    
    # Sale mode fields
    sale_mode_id = serializers.PrimaryKeyRelatedField(
        queryset=SaleMode.objects.all(),
        source='sale_mode',
        required=False,
        allow_null=True
    )
    sale_mode_name = serializers.CharField(source='sale_mode.name', read_only=True)
    
    # Quantity fields
    quantity = serializers.DecimalField(
        max_digits=12, 
        decimal_places=3,
        required=False,
        min_value=Decimal('0.001'),
        write_only=True
    )
    sale_quantity = serializers.DecimalField(
        max_digits=12, 
        decimal_places=3,
        required=False,
        min_value=Decimal('0.001'),
        write_only=True
    )
    
    base_quantity = serializers.DecimalField(
        max_digits=12, 
        decimal_places=3,
        read_only=True
    )
    
    # Price fields
    price_type = serializers.CharField(read_only=True)
    flat_price = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2,
        required=False,
        allow_null=True
    )
    
    subtotal = serializers.SerializerMethodField()
    discount_type = serializers.CharField(required=False, default='fixed')

    class Meta:
        model = SaleItem
        fields = [
            'id', 'product_id', 'product_name', 'product_sku',
            'sale_mode_id', 'sale_mode_name',
            'quantity', 'sale_quantity', 'base_quantity',
            'unit_price', 'price_type', 'flat_price',
            'discount', 'discount_type', 'subtotal'
        ]
        read_only_fields = [
            'id', 'product_name', 'product_sku', 'sale_mode_name',
            'base_quantity', 'price_type', 'subtotal'
        ]

    def validate_discount_type(self, value):
        """Normalize discount_type values"""
        if value is None or value == '':
            return 'fixed'
        if not isinstance(value, str):
            raise serializers.ValidationError('Invalid discount_type.')

        v = value.strip().lower()
        if v == 'percentage':
            return 'percent'
        if v in ('percent', 'fixed'):
            return v

        raise serializers.ValidationError('Invalid discount_type. Allowed: fixed, percent, percentage')

    def validate(self, data):
        """Validate sale item"""
        product = data.get('product')
        sale_mode = data.get('sale_mode')
        
        # Handle quantity/sale_quantity
        quantity = data.get('quantity')
        sale_quantity = data.get('sale_quantity')
        
        if sale_quantity is not None:
            final_quantity = sale_quantity
            data.pop('sale_quantity', None)
        elif quantity is not None:
            final_quantity = quantity
        else:
            final_quantity = Decimal('1.00')
        
        data['quantity'] = final_quantity
        
        # If no sale mode specified, try to find default
        if not sale_mode and product and product.unit:
            try:
                sale_mode = SaleMode.objects.filter(
                    base_unit=product.unit,
                    conversion_factor=Decimal('1.00'),
                    price_type='unit'
                ).first()
                if sale_mode:
                    data['sale_mode'] = sale_mode
            except Exception:
                pass
        
        # Validate stock
        if sale_mode and product:
            try:
                base_quantity = sale_mode.convert_to_base(final_quantity)
            except:
                base_quantity = final_quantity
        else:
            base_quantity = final_quantity
        
        # Check stock
        if product and base_quantity > Decimal(str(product.stock_qty)):
            raise serializers.ValidationError({
                'quantity': f"Insufficient stock. Available: {product.stock_qty} {product.unit.name if product.unit else 'units'}, "
                          f"Requested: {final_quantity} {sale_mode.name if sale_mode else product.unit.name if product.unit else 'units'}"
            })
        
        # Get unit price if not provided
        if 'unit_price' not in data or not data['unit_price']:
            if sale_mode:
                try:
                    product_sale_mode = ProductSaleMode.objects.get(
                        product=product,
                        sale_mode=sale_mode,
                        is_active=True
                    )
                    
                    if sale_mode.price_type == 'flat' and product_sale_mode.flat_price:
                        data['flat_price'] = product_sale_mode.flat_price
                        data['unit_price'] = product_sale_mode.flat_price / final_quantity if final_quantity else Decimal('0.00')
                    elif sale_mode.price_type == 'tier':
                        data['unit_price'] = product_sale_mode.get_tier_price(base_quantity)
                    else:
                        data['unit_price'] = product_sale_mode.get_unit_price()
                        
                except ProductSaleMode.DoesNotExist:
                    data['unit_price'] = product.selling_price
            else:
                data['unit_price'] = product.selling_price
        
        return data

    def get_subtotal(self, obj):
        return float(obj.subtotal()) if obj.subtotal() else 0.0
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['sale_quantity'] = representation.get('quantity', 0)
        return representation


class SaleSerializer(serializers.ModelSerializer):
    # Foreign key fields
    customer_id = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(),
        source='customer',
        required=False,
        allow_null=True
    )
    customer_name = serializers.CharField(read_only=True)
    account_id = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.all(),
        source='account',
        required=False,
        allow_null=True
    )
    account_name = serializers.CharField(source='account.name', read_only=True)
    sale_by = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False,
        allow_null=True,
        write_only=True
    )
    sale_by_name = serializers.CharField(source='sale_by.username', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    # Sale items
    items = SaleItemSerializer(many=True, write_only=True)
    
    # CRITICAL FIX: Add fields to accept charge values from frontend
    vat = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        required=False, 
        default=Decimal('0.00'),
        write_only=True,
        min_value=Decimal('0.00')
    )
    
    service_charge = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        required=False, 
        default=Decimal('0.00'),
        write_only=True,
        min_value=Decimal('0.00')
    )
    
    delivery_charge = serializers.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        required=False, 
        default=Decimal('0.00'),
        write_only=True,
        min_value=Decimal('0.00')
    )
    
    # Read-only calculated fields
    gross_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    net_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    grand_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    payable_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal('0.00'))
    due_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    change_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    payment_status = serializers.CharField(read_only=True)
    invoice_no = serializers.CharField(read_only=True)
    # FIX: আগে read_only ছিল, তাই app থেকে পাঠানো তারিখ বাদ পড়ত
    sale_date = FlexibleDateTimeField(required=False)

    class Meta:
        model = Sale
        fields = [
            'id', 'invoice_no', 'customer_id', 'customer_name', 'customer_type',
            'sale_type', 'sale_date', 'sale_by', 'sale_by_name', 'created_by_name',
            'gross_total', 'net_total', 'grand_total', 'payable_amount',
            'paid_amount', 'due_amount', 'change_amount', 'tendered_amount',
            'overall_discount', 'overall_discount_type',
            'overall_delivery_charge', 'overall_delivery_type',
            'overall_service_charge', 'overall_service_type',
            'overall_vat_amount', 'overall_vat_type',
            'payment_method', 'account_id', 'account_name',
            'with_money_receipt', 'remark', 'items', 'payment_status',
            # Add the write-only fields that frontend sends
            'vat', 'service_charge', 'delivery_charge'
        ]
        read_only_fields = [
            'id', 'invoice_no', 'payment_status',
            'gross_total', 'net_total', 'grand_total', 'payable_amount',
            'due_amount', 'change_amount', 'tendered_amount', 'created_by_name', 'sale_by_name'
        ]

    def validate(self, attrs):
        """Validate sale-level data"""
        items = attrs.get('items', [])
        
        if not items:
            raise serializers.ValidationError({'items': 'At least one item is required.'})

        # Validate each item
        for i, item in enumerate(items):
            if 'product' not in item:
                raise serializers.ValidationError({
                    'items': f'Item {i+1}: Product is required'
                })
            
            quantity = item.get('quantity')
            sale_quantity = item.get('sale_quantity')
            
            if quantity is None and sale_quantity is None:
                raise serializers.ValidationError({
                    'items': f'Item {i+1}: Either quantity or sale_quantity is required'
                })
            
            final_quantity = sale_quantity if sale_quantity is not None else quantity
            if final_quantity <= 0:
                raise serializers.ValidationError({
                    'items': f'Item {i+1}: Quantity must be greater than 0'
                })
        
        return attrs

    def create(self, validated_data):
        """
        Create sale with proper charge mapping
        """
        # CRITICAL: Extract charge values from frontend data
        vat_amount = validated_data.pop('vat', Decimal('0.00'))
        service_charge_amount = validated_data.pop('service_charge', Decimal('0.00'))
        delivery_charge_amount = validated_data.pop('delivery_charge', Decimal('0.00'))
        
        # CRITICAL: Map to model fields
        # FIX: 'vat' না পাঠিয়ে সরাসরি 'overall_vat_amount' পাঠালে (একই কথা service/delivery) আগে সেটা
        # 0 দিয়ে মুছে যেত, কারণ 'vat' এর default 0। এখন শুধু পাঠানো হলে তবেই alias বসে।
        sent = getattr(self, 'initial_data', {}) or {}
        if 'vat' in sent or 'overall_vat_amount' not in sent:
            validated_data['overall_vat_amount'] = vat_amount
        if 'service_charge' in sent or 'overall_service_charge' not in sent:
            validated_data['overall_service_charge'] = service_charge_amount
        if 'delivery_charge' in sent or 'overall_delivery_charge' not in sent:
            validated_data['overall_delivery_charge'] = delivery_charge_amount
        
        logger.info(f"Sale creation - Charges mapped: "
                   f"VAT={vat_amount} -> overall_vat_amount={validated_data['overall_vat_amount']}, "
                   f"Service={service_charge_amount} -> overall_service_charge={validated_data['overall_service_charge']}, "
                   f"Delivery={delivery_charge_amount} -> overall_delivery_charge={validated_data['overall_delivery_charge']}")
        
        # Extract items
        items_data = validated_data.pop('items', [])

        # FIX: paid_amount = customer যত টাকা দিয়েছে। Sale প্রথমে paid=0 দিয়ে তৈরি হয়,
        # items ও total হিসাবের পরে receive_payment() সঠিক পরিমাণ জমা করে।
        received_amount = Decimal(str(validated_data.pop('paid_amount', None) or '0'))
        if received_amount < 0:
            raise serializers.ValidationError({'paid_amount': 'Paid amount cannot be negative.'})
        validated_data['paid_amount'] = Decimal('0.00')
        validated_data['tendered_amount'] = received_amount
        payment_method = validated_data.get('payment_method')
        payment_account = validated_data.get('account')
        if received_amount > 0 and not payment_method:
            raise serializers.ValidationError({'payment_method': 'Payment method is required when making a payment.'})
        # Attach metadata from request user
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user and request.user.is_authenticated:
            validated_data['created_by'] = request.user
            if 'sale_by' not in validated_data or not validated_data['sale_by']:
                validated_data['sale_by'] = request.user

        # Handle walk-in defaults
        if validated_data.get('customer_type') == 'walk_in':
            validated_data['customer'] = None
            validated_data.setdefault('customer_name', 'Walk-in Customer')

        try:
            with transaction.atomic():
                # Create the sale
                sale = Sale.objects.create(**validated_data)

                # Create items
                for item_data in items_data:
                    # Handle sale_quantity to quantity conversion
                    if 'sale_quantity' in item_data and 'quantity' not in item_data:
                        item_data['quantity'] = item_data.pop('sale_quantity')
                    
                    SaleItem.objects.create(sale=sale, **item_data)

                # Recalculate totals
                sale.calculate_totals()

                # FIX: walk-in customer এর কাছে বাকি রাখা যায় না (পরে কার কাছ থেকে আদায় হবে?)
                if sale.customer_type == 'walk_in' and received_amount < sale.grand_total:
                    raise serializers.ValidationError({
                        'paid_amount': f'Walk-in customer: full payment required. Total {sale.grand_total}, paid {received_amount}.'
                    })

                # FIX: টাকা জমা একবারই — MoneyReceipt + Transaction দিয়ে।
                # Customer বেশি দিলে (৫০০ দিল, বিল ৪৩০) paid = 430, change = 70।
                if received_amount > 0:
                    sale.receive_payment(
                        received_amount,
                        payment_method=payment_method or 'Cash',
                        account=payment_account,
                        received_by=validated_data.get('created_by'),
                        allow_change=True,
                        payment_date=sale.sale_date,
                    )
                sale.refresh_from_db()
                
                logger.info(f"Sale created successfully: {sale.invoice_no}")
                return sale

        except serializers.ValidationError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error while creating sale")
            raise serializers.ValidationError({'non_field_errors': [str(exc)]})

    def to_representation(self, instance):
        """Return sale representation including item details"""
        rep = super().to_representation(instance)
        
        # Add item details
        rep['items'] = SaleItemSerializer(instance.items.all(), many=True).data
        rep['customer_name'] = instance.get_customer_display()

        # Convert Decimal fields to float
        decimal_fields = [
            'gross_total', 'net_total', 'grand_total', 'payable_amount',
            'paid_amount', 'due_amount', 'change_amount', 'tendered_amount',
            'overall_discount', 'overall_delivery_charge',
            'overall_service_charge', 'overall_vat_amount'
        ]
        for field in decimal_fields:
            if field in rep and rep[field] is not None:
                rep[field] = float(rep[field])
                
        return rep