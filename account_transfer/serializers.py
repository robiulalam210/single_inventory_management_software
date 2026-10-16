from rest_framework import serializers
from accounts.models import Account
from .models import  AccountTransfer
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

class TransferAccountSerializer(serializers.ModelSerializer):
    """Serializer for account details in transfers"""
    class Meta:
        model = Account
        fields = ['id', 'name', 'ac_type', 'ac_no', 'balance', 'is_active']
        read_only_fields = ['name', 'ac_type', 'ac_no', 'balance', 'is_active']

class AccountTransferCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating account transfers"""
    from_account_id = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.all(),
        source='from_account',
        write_only=True
    )
    to_account_id = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.all(),
        source='to_account',
        write_only=True
    )
    from_account = TransferAccountSerializer(read_only=True)
    to_account = TransferAccountSerializer(read_only=True)
    
    class Meta:
        model = AccountTransfer
        fields = [
            'id', 'transfer_no', 'from_account_id', 'to_account_id',
            'from_account', 'to_account', 'amount', 'description',
            'transfer_type', 'reference_no', 'remarks', 'status',
            'transfer_date', 'created_at'
        ]
        read_only_fields = [
            'id', 'transfer_no', 'status', 'created_at', 'from_account', 'to_account'
        ]

    def validate(self, data):
        request = self.context.get('request')
        user = request.user if request else None
        
        from_account = data.get('from_account')
        to_account = data.get('to_account')
        amount = data.get('amount')
        
        # Validate accounts are active
        if not from_account.is_active:
            raise serializers.ValidationError("Source account is not active")
        if not to_account.is_active:
            raise serializers.ValidationError("Destination account is not active")
        
        # Validate not same account
        if from_account == to_account:
            raise serializers.ValidationError("Cannot transfer to the same account")
        
        # Validate amount
        if amount <= Decimal('0.00'):
            raise serializers.ValidationError("Amount must be greater than 0")
        
        # Check sufficient balance
        if from_account.balance < amount:
            raise serializers.ValidationError(
                f"Insufficient balance in source account. "
                f"Available: {from_account.balance}, Required: {amount}"
            )
        
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user if request else None
        
        # Create transfer with user
        transfer = AccountTransfer.objects.create(
            created_by=user,
            **validated_data
        )
        
        logger.info(f"Transfer created: {transfer.transfer_no}")
        return transfer

class AccountTransferSerializer(serializers.ModelSerializer):
    """Serializer for viewing account transfers"""
    from_account = TransferAccountSerializer()
    to_account = TransferAccountSerializer()
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.username', read_only=True)
    
    class Meta:
        model = AccountTransfer
        fields = [
            'id', 'transfer_no', 'from_account', 'to_account', 'amount',
            'description', 'transfer_type', 'status', 'transfer_date',
            'created_at', 'created_by', 'created_by_name', 'approved_by',
            'approved_by_name', 'reference_no', 'remarks', 'is_reversal',
            'debit_transaction', 'credit_transaction'
        ]
        read_only_fields = fields

class ExecuteTransferSerializer(serializers.Serializer):
    """Serializer for executing transfers"""
    user_id = serializers.IntegerField(required=False)
    
    def validate(self, data):
        return data

class ReverseTransferSerializer(serializers.Serializer):
    """Serializer for reversing transfers"""
    reason = serializers.CharField(required=False, allow_blank=True)
    user_id = serializers.IntegerField(required=False)
    
    def validate(self, data):
        return data

class CancelTransferSerializer(serializers.Serializer):
    """Serializer for cancelling transfers"""
    reason = serializers.CharField(required=False, allow_blank=True)
    user_id = serializers.IntegerField(required=False)
    
    def validate(self, data):
        return data