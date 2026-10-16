from rest_framework import serializers
from .models import Account
from decimal import Decimal


class AccountSerializer(serializers.ModelSerializer):
    ac_number = serializers.CharField(source='number', required=False, allow_blank=True, allow_null=True)
    status = serializers.SerializerMethodField()
    
    class Meta:
        model = Account
        fields = [
            'id', 'name', 'ac_type', 'ac_number', 'balance', 
            'bank_name', 'branch', 'opening_balance', 
            'status', 'ac_no', 'is_active', 'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'balance': {'read_only': True},
            'ac_no': {'read_only': True},
            'created_at': {'read_only': True},
            'updated_at': {'read_only': True},
        }
    
    def get_status(self, obj):
        return "Active" if obj.is_active else "Inactive"
    
    def validate_opening_balance(self, value):
        """Ensure opening_balance is a valid decimal"""
        if isinstance(value, str):
            try:
                if value.strip() == '' or value == '00':
                    return Decimal('0.00')
                return Decimal(value)
            except (ValueError, TypeError):
                raise serializers.ValidationError("Enter a valid decimal number.")
        return value
    
    def validate(self, data):
        """Validate the entire data set"""
        # Get the actual number value from the source mapping
        if 'number' in data:
            if data['number'] == '' or data['number'] is None:
                data['number'] = None
        
        # Get account type
        ac_type = data.get('ac_type', self.instance.ac_type if self.instance else None)
        number = data.get('number', self.instance.number if self.instance else None)
        
        # Bank and Mobile banking must have numbers
        if ac_type in [Account.TYPE_BANK, Account.TYPE_MOBILE]:
            if not number:
                raise serializers.ValidationError({
                    'ac_number': f"{ac_type} accounts must have an account number."
                })
            
            # Check for duplicates
            if number:
                queryset = Account.objects.filter(
                    ac_type=ac_type,
                    number=number
                )
                if self.instance:
                    queryset = queryset.exclude(pk=self.instance.pk)
                
                if queryset.exists():
                    raise serializers.ValidationError({
                        'ac_number': f"A {ac_type} account with this number already exists."
                    })
        
        # Ensure opening_balance is included and valid
        opening_balance = data.get('opening_balance', Decimal('0.00'))
        if opening_balance is None:
            data['opening_balance'] = Decimal('0.00')
        
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user if request else None
        # Extract data
        ac_type = validated_data.get('ac_type')
        name = validated_data.get('name')
        number = validated_data.get('number')
        opening_balance = validated_data.get('opening_balance', Decimal('0.00'))

        # For Bank/Mobile banking, ensure number exists
        if ac_type in [Account.TYPE_BANK, Account.TYPE_MOBILE] and not number:
            raise serializers.ValidationError({
                'ac_number': f"{ac_type} accounts must have an account number."
            })

        # Check for duplicates for Bank/Mobile banking
        if ac_type in [Account.TYPE_BANK, Account.TYPE_MOBILE] and number:
            if Account.objects.filter(ac_type=ac_type, number=number).exists():
                raise serializers.ValidationError({
                    'ac_number': "An account with this type and number already exists."
                })

        # Create the account
        account = Account(
            name=name,
            ac_type=ac_type,
            number=number,
            bank_name=validated_data.get('bank_name'),
            branch=validated_data.get('branch'),
            opening_balance=opening_balance,
            balance=opening_balance,
            is_active=True,
            created_by=user
        )

        # Validate and save
        account.full_clean()
        account.save(creating_user=user)
        return account

    def update(self, instance, validated_data):
        """
        FIX: আগে opening balance বদলালে শুধু ওই ঘরটা বদলাত, আসল balance একই থাকত — দুটো আর মিলত না।
        এখন যতটুকু বদলাল, balance ও ঠিক ততটুকু বদলায়, আর opening balance এর রেকর্ড (transaction) ও।
        """
        from django.db import transaction as db_transaction
        new_opening = validated_data.get('opening_balance', instance.opening_balance)
        if new_opening is None:
            new_opening = Decimal('0.00')
        delta = Decimal(str(new_opening)) - (instance.opening_balance or Decimal('0.00'))
        with db_transaction.atomic():
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            if delta:
                instance.balance = (instance.balance or Decimal('0.00')) + delta
            instance.save()
            if delta:
                from transactions.models import Transaction
                ob = Transaction.objects.filter(account=instance, is_opening_balance=True).order_by('id').first()
                if ob:
                    Transaction.objects.filter(pk=ob.pk).update(amount=new_opening)
                elif new_opening > 0:
                    request = self.context.get('request')
                    instance.create_opening_balance_transaction(getattr(request, 'user', None))
        return instance
