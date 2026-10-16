from rest_framework import serializers
from .model import SupplierPayment
from purchases.models import Purchase
from suppliers.models import Supplier
from accounts.models import Account

from django.contrib.auth import get_user_model

User = get_user_model()

class SupplierPaymentSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    supplier_phone = serializers.CharField(source='supplier.phone', read_only=True)
    prepared_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    purchase_invoice_no = serializers.CharField(source='purchase.invoice_no', read_only=True, allow_null=True)
    payment_summary = serializers.SerializerMethodField()
    account_name = serializers.CharField(source='account.name', read_only=True, allow_null=True)
    allocation_detail = serializers.SerializerMethodField()
    
    # Input fields
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all(), required=True)
    account = serializers.PrimaryKeyRelatedField(queryset=Account.objects.all(), required=True)
    purchase = serializers.PrimaryKeyRelatedField(queryset=Purchase.objects.all(), required=False, allow_null=True)
    created_by = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False)

    class Meta:
        model = SupplierPayment
        fields = [
            'id', 'sp_no', 'supplier', 'supplier_name', 'supplier_phone',
            'payment_type', 'use_advance', 'advance_amount_used', 'purchase', 'purchase_invoice_no',
            'amount', 'payment_method', 'payment_date', 'description', 
            'account', 'created_by', 'prepared_by_name', 'reference_no', 'status',
            'created_at', 'updated_at', 'payment_summary', 'account_name', 'allocation_detail'
        ]
        read_only_fields = [
            'id', 'sp_no', 'supplier_name', 'supplier_phone', 'purchase_invoice_no',
            'prepared_by_name', 'created_at', 'updated_at', 'status',
            'payment_summary'
        ]

    def validate(self, attrs):
        request = self.context.get('request')
        
        # Ensure supplier is provided
        if 'supplier' not in attrs:
            raise serializers.ValidationError({
                "supplier": "Supplier is required."
            })
            
        # Ensure account is provided
        if 'account' not in attrs:
            raise serializers.ValidationError({
                "account": "Account is required."
            })
        
        purchase = attrs.get('purchase')
        if purchase and attrs.get('supplier') and purchase.supplier_id != attrs['supplier'].id:
            raise serializers.ValidationError({"purchase": "This invoice belongs to another supplier."})

        # Validate payment amount
        amount = attrs.get('amount')
        if amount and amount <= 0:
            raise serializers.ValidationError({
                "amount": "Payment amount must be greater than 0."
            })
        
        # Validate payment date
        payment_date = attrs.get('payment_date')
        if not payment_date:
            raise serializers.ValidationError({
                "payment_date": "Payment date is required."
            })
        
        return attrs

    def get_payment_summary(self, obj):
        return obj.get_payment_summary()

    def get_allocation_detail(self, obj):
        """কোন invoice এ কত বসেছে, কত advance ব্যবহার/জমা — voucher এ দেখানোর জন্য (পুরনো payment এ null)"""
        alloc = obj.allocation or {}
        if not alloc:
            return None
        pmap = alloc.get('purchases') or {}
        ids = [int(k) for k in pmap if str(k).isdigit()]
        names = dict(Purchase.objects.filter(pk__in=ids).values_list('pk', 'invoice_no')) if ids else {}
        return {
            'invoices': [{'purchase_id': int(k), 'invoice_no': names.get(int(k), f'#{k}'), 'amount': float(v)}
                         for k, v in pmap.items() if str(k).isdigit()],
            'advance_used': float(alloc.get('advance_used') or 0),
            'advance_added': float(alloc.get('advance_added') or 0),
        }

    def create(self, validated_data):
        request = self.context.get('request')
        
        # Set created_by from request user if not provided
        if 'created_by' not in validated_data and request and request.user:
            validated_data['created_by'] = request.user
        
        return super().create(validated_data)