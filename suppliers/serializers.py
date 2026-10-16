# suppliers/serializers.py
import logging
from rest_framework import serializers
from .models import Supplier

logger = logging.getLogger(__name__)

class SupplierSerializer(serializers.ModelSerializer):
    amount_type = serializers.SerializerMethodField()
    
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Supplier
        fields = [
            'id', 'name', 'email', 'phone', 'address', 'is_active', 'supplier_no',
            'shop_name', 'product_name',  # ADDED: New fields
            'total_due', 'total_paid', 'total_purchases', 'purchase_count',
            'advance_balance',
            'amount_type', 'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'created_by', 'supplier_no', 'created_at', 'updated_at',
            'total_due', 'total_paid', 'total_purchases', 'purchase_count',
            'advance_balance'
        ]

    def get_amount_type(self, obj):
        """Determine if supplier has due or is paid - ENHANCED VERSION"""
        if obj.total_due > 0:
            return "Due"
        elif obj.advance_balance > 0:
            return "Advance"
        else:
            return "Paid"

class SupplierListSerializer(serializers.ModelSerializer):
    """Optimized serializer for list view"""
    amount_type = serializers.SerializerMethodField()
    
    class Meta:
        model = Supplier
        fields = [
            'id', 'supplier_no', 'name', 'phone', 'address', 'is_active',
            'shop_name', 'product_name',  # ADDED: New fields
            'total_purchases', 'total_paid', 'total_due', 'purchase_count', 
            'advance_balance',
            'amount_type'
        ]

    def get_amount_type(self, obj):
        """Enhanced amount type that considers advance balance"""
        if obj.total_due > 0:
            return "Due"
        elif obj.advance_balance > 0:
            return "Advance"
        else:
            return "Paid"

class SupplierCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating suppliers"""
    class Meta:
        model = Supplier
        fields = ['name', 'email', 'phone', 'address', 'shop_name', 'product_name', 'is_active']  # UPDATED
        
    def validate_phone(self, value):
        """Validate phone number format"""
        if value and len(value) < 10:
            raise serializers.ValidationError("Phone number must be at least 10 digits")
        return value

    def validate(self, data):
        """Ensure at least one contact method is provided"""
        if not data.get('email') and not data.get('phone'):
            raise serializers.ValidationError("Either email or phone must be provided")
        
        # Optional: Validate shop_name if provided
        if data.get('shop_name') and len(data['shop_name']) > 255:
            raise serializers.ValidationError("Shop name cannot exceed 255 characters")
            
        return data