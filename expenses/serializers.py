# expenses/serializers.py
from rest_framework import serializers
from .models import Expense, ExpenseHead, ExpenseSubHead
from django.core.exceptions import ValidationError

class ExpenseHeadSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    
    class Meta:
        model = ExpenseHead
        fields = ['id', 'name', 'created_by', 'date_created', 'is_active', 'status']

class ExpenseSubHeadSerializer(serializers.ModelSerializer):
    head_name = serializers.CharField(source='head.name', read_only=True)
    status = serializers.CharField(read_only=True)
    
    class Meta:
        model = ExpenseSubHead
        fields = ['id', 'name', 'head', 'head_name', 'created_by', 'date_created', 'is_active', 'status']

class ExpenseSerializer(serializers.ModelSerializer):
    head_name = serializers.CharField(source='head.name', read_only=True)
    subhead_name = serializers.CharField(source='subhead.name', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    description = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    expense_summary = serializers.SerializerMethodField()
    
    def get_created_by_name(self, obj):
        # নাম না থাকলে username — আগে ফাঁকা দেখাত
        u = obj.created_by
        return ((u.get_full_name() or '').strip() or u.username) if u else ''

    class Meta:
        model = Expense
        fields = [
            'id', 'invoice_number', 'head', 'head_name', 'subhead', 'subhead_name',
            'amount', 'payment_method', 'account', 'account_name', 'expense_date',
            'note', 'description', 'status', 'created_by', 'created_by_name',
            'date_created', 'expense_summary'
        ]
        read_only_fields = ['invoice_number', 'date_created', 'created_by']
    
    def get_expense_summary(self, obj):
        return obj.get_expense_summary()

class ExpenseCreateSerializer(serializers.ModelSerializer):
    """Serializer specifically for creating expenses"""
    
    class Meta:
        model = Expense
        fields = [
            'head', 'subhead', 'amount', 'payment_method', 'account',
            'expense_date', 'note'
        ]
    
    def validate_payment_method(self, value):
        """Convert payment method to lowercase to match choices"""
        if value:
            value = value.lower().strip()
            valid_choices = ['cash', 'bank', 'mobile', 'card', 'other']
            if value not in valid_choices:
                # Try to map common variations
                payment_mapping = {
                    'cash': 'cash',
                    'Cash': 'cash',
                    'CASH': 'cash',
                    'bank': 'bank',
                    'Bank': 'bank',
                    'BANK': 'bank',
                    'mobile': 'mobile',
                    'Mobile': 'mobile',
                    'MOBILE': 'mobile',
                    'card': 'card',
                    'Card': 'card',
                    'CARD': 'card',
                    'other': 'other',
                    'Other': 'other',
                    'OTHER': 'other'
                }
                if value in payment_mapping:
                    return payment_mapping[value]
                else:
                    raise serializers.ValidationError(
                        f"'{value}' is not a valid choice. Must be one of: {', '.join(valid_choices)}"
                    )
        return value
    
    def validate(self, data):
        # Validate that account has sufficient balance
        account = data.get('account')
        amount = data.get('amount')
        
        if account and amount and amount > account.balance:
            raise serializers.ValidationError({
                'amount': f'Insufficient balance in account. Available: {account.balance}'
            })
        
        return data
    
    def create(self, validated_data):
        # Set created_by from request context
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user
        return super().create(validated_data)


class ExpenseUpdateSerializer(serializers.ModelSerializer):
    """Serializer specifically for updating expenses"""
    
    class Meta:
        model = Expense
        fields = [
            'head', 'subhead', 'amount', 'payment_method', 'account',
            'expense_date', 'note'
        ]
    
    def to_internal_value(self, data):
        """Convert incoming data to internal values"""
        # Make a mutable copy
        data = data.copy()
        
        # Handle 'null' strings
        if 'subhead' in data and data['subhead'] == 'null':
            data['subhead'] = None
        if 'account' in data and data['account'] == 'null':
            data['account'] = None
            
        return super().to_internal_value(data)
    
    def validate(self, data):
        """Validate expense data for updates"""
        instance = getattr(self, 'instance', None)
        request = self.context.get('request')
        
        if not instance:
            return data
        
        # Check if account balance validation is needed
        account = data.get('account')
        new_amount = data.get('amount')
        
        # If both account and amount are being updated
        if account is not None and new_amount is not None:
            # For account updates, we need to validate against the NEW account
            if account != instance.account:
                # Check if new account has enough balance for the full new amount
                if new_amount > account.balance:
                    raise serializers.ValidationError({
                        'amount': f'Insufficient balance in selected account. Available: {account.balance}'
                    })
            else:
                # Same account, check if amount increased
                if new_amount > instance.amount:
                    increase = new_amount - instance.amount
                    if increase > account.balance:
                        raise serializers.ValidationError({
                            'amount': f'Insufficient balance for amount increase. Available: {account.balance}, Increase needed: {increase}'
                        })
        
        # If only amount is being updated (account unchanged)
        elif new_amount is not None and instance.account:
            if new_amount > instance.amount:
                increase = new_amount - instance.amount
                if increase > instance.account.balance:
                    raise serializers.ValidationError({
                        'amount': f'Insufficient balance for amount increase. Available: {instance.account.balance}, Increase needed: {increase}'
                    })
        
        return data
    
