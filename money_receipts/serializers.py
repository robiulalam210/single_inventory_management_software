from rest_framework import serializers
from decimal import Decimal, InvalidOperation
from .models import MoneyReceipt
from sales.models import Sale
from customers.models import Customer
from accounts.models import Account
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

class MoneyReceiptSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    customer_phone = serializers.CharField(source='customer.phone', read_only=True, allow_null=True)
    seller_name = serializers.CharField(source='seller.username', read_only=True, allow_null=True)
    sale_invoice_no = serializers.SerializerMethodField(read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True, allow_null=True)
    payment_summary = serializers.SerializerMethodField()
    allocation_detail = serializers.SerializerMethodField()
    
    # FIXED: Use DecimalField instead of CharField for amount
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=True,
        coerce_to_string=True  # This will handle string input properly
    )
    
    # Writeable fields
    customer_id = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(), 
        source='customer',
        write_only=True,
        required=False,
        allow_null=True
    )
    account_id = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.all(),
        source='account', 
        write_only=True,
        required=False,
        allow_null=True
    )
    sale_id = serializers.PrimaryKeyRelatedField(
        queryset=Sale.objects.all(),
        source='sale',
        write_only=True,
        required=False,
        allow_null=True
    )
    seller_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source='seller',
        write_only=True,
        required=False,
        allow_null=True
    )

    class Meta:
        model = MoneyReceipt
        fields = [
            'id', 'mr_no',
            'customer', 'customer_id', 'customer_name', 'customer_phone',
            'payment_type', 'specific_invoice', 'is_advance_payment', 
            'sale', 'sale_id', 'sale_invoice_no',
            'amount', 'payment_method', 'payment_date', 'remark', 
            'account', 'account_id', 'account_name', 
            'seller', 'seller_id', 'seller_name',
            'cheque_status', 'cheque_id', 'payment_status', 
            'created_at', 'updated_at', 'payment_summary', 'allocation_detail'
        ]
        read_only_fields = [
            'id', 'mr_no', 'customer_name', 'customer_phone', 'sale_invoice_no', 
            'seller_name', 'account_name', 
            'created_at', 'updated_at', 'payment_summary',
            'payment_type', 'specific_invoice'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['account_id'].queryset = Account.objects.filter(is_active=True)
        except Exception as e:
            logger.warning(f"Error filtering accounts: {e}")

    def validate_amount(self, value):
        """Validate amount field specifically"""
        try:
            # Convert to Decimal if it's a string
            if isinstance(value, str):
                # Remove commas if present
                value = value.replace(',', '')
                decimal_value = Decimal(value)
            elif isinstance(value, (int, float)):
                decimal_value = Decimal(str(value))
            else:
                decimal_value = value
            
            # Validate it's greater than 0
            if decimal_value <= Decimal('0'):
                raise serializers.ValidationError("Payment amount must be greater than 0.")
            
            return decimal_value
        except (InvalidOperation, ValueError, TypeError) as e:
            raise serializers.ValidationError(f"Invalid amount format: {str(e)}")

    def validate(self, attrs):
        """Enhanced validation"""
        request = self.context.get('request')
        
        # Amount is already validated in validate_amount and is now a Decimal
        # No need to validate amount here again
        
        customer = attrs.get('customer')
        sale = attrs.get('sale')
        account = attrs.get('account')
        is_advance_payment = attrs.get('is_advance_payment', False)
        payment_type = attrs.get('payment_type', 'overall')

        # Validate customer requirements
        if self.instance is None and is_advance_payment and not customer:
            raise serializers.ValidationError({
                "customer": "Customer is required for advance payments."
            })

        if self.instance is None and payment_type == 'specific' and not sale:
            raise serializers.ValidationError({
                "sale": "Sale is required for specific invoice payments."
            })

        if self.instance is None and payment_type == 'overall' and not customer and not sale:
            raise serializers.ValidationError({
                "customer": "Customer is required for overall payments."
            })

        if self.instance is None:
            # FIX: account ছাড়া receipt হলে টাকা কোনো account এ ঢুকত না
            if not account:
                raise serializers.ValidationError({"account": "Account is required to receive payment."})
            # Walk-in invoice এ due এর বেশি নেওয়া যায় না (advance রাখার মতো customer নেই)
            if sale and not sale.customer_id and not customer:
                sale.calculate_totals()
                if attrs.get('amount') and attrs['amount'] > sale.due_amount:
                    raise serializers.ValidationError({
                        "amount": f"Amount is more than invoice due ({sale.due_amount})."
                    })
        else:
            # FIX: টাকার পরিমাণ/কার কাছ থেকে/কোন invoice/কোন account — এগুলো edit করলে আগের হিসাব
            # উল্টানো হত না। তাই এগুলো বদলাতে হলে receipt বাতিল করে নতুন receipt করতে হবে।
            locked = {'amount': 'amount', 'customer': 'customer', 'sale': 'sale', 'account': 'account',
                      'is_advance_payment': 'is_advance_payment'}
            for key, field in locked.items():
                if key in attrs:
                    old_val = getattr(self.instance, field)
                    new_val = attrs[key]
                    if key == 'amount':
                        changed = Decimal(str(new_val)) != Decimal(str(old_val))
                    else:
                        changed = (getattr(new_val, 'pk', new_val)) != (getattr(old_val, 'pk', old_val))
                    if changed:
                        raise serializers.ValidationError({
                            key: "এই তথ্য বদলানো যায় না। Receipt বাতিল (delete) করে নতুন receipt করুন।"
                        })

        return attrs

    def create(self, validated_data):
        """Create money receipt with proper context - FIXED"""
        request = self.context.get('request')
        
        if not request:
            raise serializers.ValidationError("Request context is required.")
        
        # Set seller and created_by from request user if not provided
        if 'seller' not in validated_data or not validated_data['seller']:
            validated_data['seller'] = request.user
        if 'created_by' not in validated_data or not validated_data['created_by']:
            validated_data['created_by'] = request.user
        
        # Set default payment method if not provided
        if 'payment_method' not in validated_data or not validated_data['payment_method']:
            validated_data['payment_method'] = 'cash'
        
        # Ensure payment status
        if 'payment_status' not in validated_data:
            validated_data['payment_status'] = 'completed'
        
        try:
            # Create the money receipt
            receipt = MoneyReceipt.objects.create(**validated_data)
            return receipt
        except Exception as e:
            logger.error(f"Error creating money receipt: {e}")
            raise serializers.ValidationError(f"Error creating money receipt: {str(e)}")

    def get_sale_invoice_no(self, obj):
        """Get sale invoice number safely"""
        if obj.sale:
            return obj.sale.invoice_no
        elif obj.sale_invoice_no:
            return obj.sale_invoice_no
        return None

    def get_allocation_detail(self, obj):
        """
        রসিদের টাকা ঠিক কোন invoice এ কত বসেছিল আর কত advance — save এর সময়ের রেকর্ড (allocation) থেকে।
        রসিদে "SL-2038 ৳144, SL-2011 ৳856" দেখানোর জন্য। পুরনো রসিদে রেকর্ড না থাকলে null।
        """
        alloc = obj.allocation or {}
        if not alloc:
            return None
        sales_map = alloc.get('sales') or {}
        ids = [int(k) for k in sales_map.keys() if str(k).isdigit()]
        names = dict(Sale.objects.filter(pk__in=ids).values_list('pk', 'invoice_no')) if ids else {}
        invoices = [
            {'sale_id': int(k), 'invoice_no': names.get(int(k), f'#{k}'), 'amount': float(Decimal(str(v)))}
            for k, v in sales_map.items() if str(k).isdigit()
        ]
        return {'invoices': invoices, 'advance': float(Decimal(str(alloc.get('advance') or '0')))}

    def get_payment_summary(self, obj):
        """Get payment summary from model method - SAFELY"""
        try:
            return obj.get_payment_summary()
        except Exception as e:
            logger.error(f"Error getting payment summary for {obj.mr_no}: {e}")
            return {
                'mr_no': obj.mr_no,
                'amount': float(obj.amount),
                'payment_type': obj.payment_type,
                'error': 'Could not generate full summary'
            }