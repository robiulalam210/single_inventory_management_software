from rest_framework import serializers
from .models import Transaction
from accounts.models import Account
from django.db.models import Sum, Q
from django.utils import timezone
from datetime import datetime, timedelta

from rest_framework import serializers
from .models import Transaction
from accounts.models import Account

class TransactionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            'transaction_type', 'amount', 'account', 'payment_method',
            'cheque_no', 'reference_no', 'transaction_date', 'description',
            'status', 'money_receipt', 'sale', 'expense', 'purchase'
        ]
    
    def validate(self, data):
        # Add any validation logic here
        return data

class TransactionSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    # date_updated = serializers.DateTimeField(read_only=True, required=False)

    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'transaction_no', 'transaction_type', 'amount', 'account', 'account_name',
            'payment_method', 'cheque_no', 'reference_no', 'transaction_date',
            'status', 'description', 'created_by', 'created_by_name',
            'money_receipt', 'sale', 'expense', 'purchase', 'created_at', 'updated_at',
            'is_opening_balance'
        ]
        read_only_fields = ['transaction_no', 'created_at', 'updated_at']

class AccountBalanceSerializer(serializers.ModelSerializer):
    current_balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    total_credits = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    total_debits = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    transaction_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Account
        fields = [
            'id', 'name', 'ac_type', 'ac_no', 'current_balance', 
            'total_credits', 'total_debits', 'transaction_count'
        ]

class TransactionSummarySerializer(serializers.Serializer):
    total_transactions = serializers.IntegerField()
    total_credits = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_debits = serializers.DecimalField(max_digits=14, decimal_places=2)
    net_flow = serializers.DecimalField(max_digits=14, decimal_places=2)