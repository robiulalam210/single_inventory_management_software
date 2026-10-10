from django.db import models
from django.db.models import Q, Max
from decimal import Decimal
from django.conf import settings
from django.utils import timezone   
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
import random
import string


class Account(models.Model):
    TYPE_BANK = 'Bank'
    TYPE_MOBILE = 'Mobile banking'
    TYPE_CASH = 'Cash'
    TYPE_OTHER = 'Other'

    ACCOUNT_TYPE_CHOICES = [
        (TYPE_BANK, 'Bank'),
        (TYPE_MOBILE, 'Mobile banking'),
        (TYPE_CASH, 'Cash'),
        (TYPE_OTHER, 'Other'),
    ]

    ac_no = models.CharField(max_length=20, null=True, blank=True, unique=True)
    name = models.CharField(max_length=150)
    ac_type = models.CharField(max_length=30, choices=ACCOUNT_TYPE_CHOICES, default=TYPE_OTHER)
    number = models.CharField(max_length=64, blank=True, null=True)
    bank_name = models.CharField(max_length=150, blank=True, null=True)
    branch = models.CharField(max_length=150, blank=True, null=True)
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-id']
        constraints = [
            # Bank and Mobile banking must have unique numbers
            models.UniqueConstraint(
                fields=['ac_type', 'number'], 
                name='unique_ac_type_number',
                condition=Q(ac_type__in=['Bank', 'Mobile banking']) & Q(number__isnull=False)
            ),
            # Cash and Other accounts can have multiple entries, even without numbers
        ]
        verbose_name = "Account"
        verbose_name_plural = "Accounts"

    def __str__(self):
        return f"{self.name} ({self.ac_type})"

    @property
    def status(self):
        return "Active" if self.is_active else "Inactive"

    def create_opening_balance_transaction(self, user):
        """
        Create an opening balance transaction for this account
        """
        if self.opening_balance and self.opening_balance > 0:
            try:
                from transactions.models import Transaction
                
                # Opening balance transaction number
                timestamp = int(timezone.now().timestamp())
                transaction_no = f"OB-{timestamp}"
                
                # Ensure uniqueness
                counter = 1
                base_no = transaction_no
                while Transaction.objects.filter(transaction_no=transaction_no).exists():
                    transaction_no = f"{base_no}-{counter}"
                    counter += 1
                    if counter > 100:
                        # Ultimate fallback
                        transaction_no = f"OB-{timezone.now().strftime('%Y%m%d%H%M%S')}"
                        break

                # Create opening balance transaction WITH special flag
                transaction = Transaction.objects.create(
                    transaction_no=transaction_no,
                    account=self,
                    transaction_type='credit',
                    amount=self.opening_balance,
                    description=f"Opening balance for {self.name}",
                    transaction_date=timezone.now().date(),
                    status='completed',
                    created_by=user,
                    is_opening_balance=True
                )
                
                return transaction
            except Exception as e:
                return None
        return None

    def save(self, *args, **kwargs):
        # Extract user from kwargs if provided
        user = kwargs.pop('creating_user', None)
        
        is_new = self.pk is None
        creating_opening_balance = is_new and self.opening_balance and self.opening_balance > 0
        
        # Clean up fields based on account type
        if self.ac_type in [self.TYPE_CASH, self.TYPE_OTHER]:
            self.bank_name = None
            self.branch = None
            # For Cash accounts without number, generate a default name-based number
            if self.ac_type == self.TYPE_CASH and not self.number:
                self.number = f"CASH-{self.name.upper().replace(' ', '-')}"
        
        # Set initial balance to opening_balance for new accounts
        if is_new:
            self.balance = self.opening_balance
        
        # Generate AC_NO (ACC-1001, ACC-1002 ...)
        if is_new and not self.ac_no:
            numbers = []
            for no in Account.objects.filter(ac_no__startswith='ACC-').values_list('ac_no', flat=True):
                try:
                    numbers.append(int(no.rsplit('-', 1)[-1]))
                except (ValueError, IndexError):
                    pass
            new_number = max(numbers) + 1 if numbers else 1001
            while Account.objects.filter(ac_no=f"ACC-{new_number}").exists():
                new_number += 1
            self.ac_no = f"ACC-{new_number}"
        
        # Save the account first
        super().save(*args, **kwargs)
        
        # Create opening balance transaction after saving (for record keeping only)
        if creating_opening_balance and user:
            self.create_opening_balance_transaction(user)
            
    def clean(self):
        """Validate account data"""
        from django.core.exceptions import ValidationError
        
        # Bank and Mobile banking must have numbers
        if self.ac_type in [self.TYPE_BANK, self.TYPE_MOBILE]:
            if not self.number or self.number.strip() == '':
                raise ValidationError({
                    'number': f"{self.ac_type} accounts must have an account number."
                })
        
        # Check for duplicates (only for Bank and Mobile banking with numbers)
        if self.ac_type in [self.TYPE_BANK, self.TYPE_MOBILE] and self.number:
            existing_account = Account.objects.filter(
                ac_type=self.ac_type,
                number=self.number
            ).exclude(pk=self.pk).first()
            
            if existing_account:
                raise ValidationError(
                    f"A {self.ac_type} account with number '{self.number}' already exists."
                )
        
        # Validate opening balance
        if self.opening_balance is None:
            self.opening_balance = Decimal('0.00')