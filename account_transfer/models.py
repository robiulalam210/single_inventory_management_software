from offline_sync.utils import touch
from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from accounts.models import Account
from django.conf import settings
from django.db.models import F
import logging

logger = logging.getLogger(__name__)

class AccountTransfer(models.Model):
    TRANSFER_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    TRANSFER_TYPE_CHOICES = [
        ('internal', 'Internal Transfer'),
        ('external', 'External Transfer'),
        ('adjustment', 'Balance Adjustment'),
    ]
    
    # Basic Info
    transfer_no = models.CharField(max_length=50, unique=True, blank=True)
    transfer_type = models.CharField(max_length=20, choices=TRANSFER_TYPE_CHOICES, default='internal')
    
    # Accounts involved
    from_account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='transfers_out')
    to_account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='transfers_in')
    
    # Transfer details
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    
    # Status and dates
    status = models.CharField(max_length=20, choices=TRANSFER_STATUS_CHOICES, default='pending')
    transfer_date = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Reference to transactions created
    debit_transaction = models.ForeignKey(
        'transactions.Transaction',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='debit_for_transfer'
    )
    credit_transaction = models.ForeignKey(
        'transactions.Transaction',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='credit_for_transfer'
    )
    
    # User who initiated the transfer
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_transfers'
    )
    
    # Additional fields
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    is_reversal = models.BooleanField(default=False)
    original_transfer = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reversals'
    )

    class Meta:
        ordering = ['-transfer_date', '-id']
        indexes = [
            models.Index(fields=['transfer_date']),
            models.Index(fields=['from_account', 'transfer_date']),
            models.Index(fields=['to_account', 'transfer_date']),
            models.Index(fields=['transfer_no']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Transfer {self.transfer_no}: {self.from_account.name} → {self.to_account.name} - {self.amount}"

    def clean(self):
        """Validate the transfer before saving"""
        if self.from_account == self.to_account:
            raise ValidationError("Cannot transfer to the same account")
        
        if self.amount <= 0:
            raise ValidationError("Transfer amount must be greater than 0")
        
        # Check sufficient balance for pending transfers (only if it's not a reversal)
        if self.status == 'pending' and not self.is_reversal:
            if self.from_account.balance < self.amount:
                raise ValidationError(
                    f"Insufficient balance in source account. "
                    f"Available: {self.from_account.balance}, Required: {self.amount}"
                )

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        
        # Generate transfer number if new
        if is_new and not self.transfer_no:
            self.transfer_no = self._generate_transfer_no()
        
        # Validate before saving
        self.clean()
        
        super().save(*args, **kwargs)

    def _generate_transfer_no(self):
        """Generate unique transfer number: TRF-100001"""
        try:
            last = AccountTransfer.objects.filter(
                transfer_no__regex=r'^TRF-\d+$'
            ).order_by('-id').first()
            new_number = 100001
            if last and last.transfer_no:
                try:
                    new_number = int(last.transfer_no.split('-')[1]) + 1
                except (ValueError, IndexError):
                    new_number = 100001 + AccountTransfer.objects.count()
            candidate = f"TRF-{new_number:06d}"
            while AccountTransfer.objects.filter(transfer_no=candidate).exists():
                new_number += 1
                candidate = f"TRF-{new_number:06d}"
            return candidate
        except Exception as e:
            logger.error(f"Error generating transfer number: {str(e)}")
            return f"TRF-{int(timezone.now().timestamp())}"

    def execute_transfer(self, user=None):
        """Execute the transfer by creating transactions"""
        if self.status == 'completed':
            raise ValidationError("Transfer is already completed")
        
        if self.status == 'cancelled':
            raise ValidationError("Cannot execute a cancelled transfer")
        
        # Refresh account to get current balance
        self.from_account.refresh_from_db()
        if self.from_account.balance < self.amount:
            raise ValidationError(
                f"Insufficient balance in {self.from_account.name}. "
                f"Available: {self.from_account.balance}, Required: {self.amount}"
            )
        
        try:
            from transactions.models import Transaction
            
            # Use atomic transaction to ensure data consistency
            with transaction.atomic():
                # SUCCESS: FIXED: Update account balances using F() expressions
                Account.objects.filter(id=self.from_account.id).update(
                    balance=F('balance') - self.amount
                )
                touch(Account, self.from_account.id)  # audit + desktop sync এ পরিবর্তন পৌঁছানোর জন্য
                Account.objects.filter(id=self.to_account.id).update(
                    balance=F('balance') + self.amount
                )
                touch(Account, self.to_account.id)  # audit + desktop sync এ পরিবর্তন পৌঁছানোর জন্য
                
                # Refresh accounts to get updated balances
                self.from_account.refresh_from_db()
                self.to_account.refresh_from_db()
                
                logger.info(f"SUCCESS: Account balances updated: "
                          f"From {self.from_account.name}: {self.from_account.balance}, "
                          f"To {self.to_account.name}: {self.to_account.balance}")
                
                # Create debit transaction
                debit_transaction = Transaction.objects.create(
                    transaction_type='debit',
                    amount=self.amount,
                    account=self.from_account,
                    payment_method='transfer',
                    description=f"Transfer to {self.to_account.name} - {self.description or 'No description'}",
                    created_by=user or self.created_by,
                    status='completed',
                    transaction_date=self.transfer_date,
                    is_opening_balance=False,
                    balance_already_updated=True  # SUCCESS: Prevents double balance update
                )
                
                # Create credit transaction
                credit_transaction = Transaction.objects.create(
                    transaction_type='credit',
                    amount=self.amount,
                    account=self.to_account,
                    payment_method='transfer',
                    description=f"Transfer from {self.from_account.name} - {self.description or 'No description'}",
                    created_by=user or self.created_by,
                    status='completed',
                    transaction_date=self.transfer_date,
                    is_opening_balance=False,
                    balance_already_updated=True  # SUCCESS: Prevents double balance update
                )
                
                # Update transfer status and link transactions
                self.debit_transaction = debit_transaction
                self.credit_transaction = credit_transaction
                self.status = 'completed'
                self.approved_by = user or self.created_by
                
                # Save the transfer with the linked transactions
                self.save(update_fields=[
                    'debit_transaction', 
                    'credit_transaction', 
                    'status', 
                    'approved_by',
                    'updated_at'
                ])
            
            logger.info(f"SUCCESS: Transfer {self.transfer_no} executed successfully")
            return True
            
        except Exception as e:
            logger.error(f"ERROR:Error executing transfer {self.transfer_no}: {str(e)}")
            self.status = 'failed'
            self.save(update_fields=['status', 'updated_at'])
            raise ValidationError(f"Failed to execute transfer: {str(e)}")

    def cancel_transfer(self, reason=None, user=None):
        """Cancel the transfer"""
        if self.status == 'completed':
            raise ValidationError("Cannot cancel a completed transfer. Use reverse_transfer instead.")
        
        if self.status == 'cancelled':
            raise ValidationError("Transfer is already cancelled")
        
        self.status = 'cancelled'
        self.remarks = f"Cancelled: {reason}" if reason else "Cancelled by user"
        self.approved_by = user or self.created_by
        self.save()
        
        logger.info(f"Transfer {self.transfer_no} cancelled: {reason}")
        return True

    def reverse_transfer(self, reason=None, user=None):
        """Reverse a completed transfer"""
        if self.status != 'completed':
            raise ValidationError("Only completed transfers can be reversed")
        
        if self.is_reversal:
            raise ValidationError("Cannot reverse a reversal transfer")
        
        try:
            # Use atomic transaction for consistency
            with transaction.atomic():
                # Create reversal transfer
                reversal = AccountTransfer.objects.create(
                    from_account=self.to_account,
                    to_account=self.from_account,
                    amount=self.amount,
                    description=f"Reversal: {self.description or 'No description'}",
                    remarks=f"Reversal of {self.transfer_no}. Reason: {reason or 'No reason provided'}",
                    created_by=user or self.created_by,
                    is_reversal=True,
                    original_transfer=self
                )
                
                # Execute the reversal (this will update balances)
                reversal.execute_transfer(user)
                
                # Mark original transfer as reversed
                self.status = 'cancelled'
                self.remarks = f"Reversed by {reversal.transfer_no}. Reason: {reason}"
                self.save()
            
            logger.info(f"SUCCESS: Transfer {self.transfer_no} reversed by {reversal.transfer_no}")
            return reversal
            
        except Exception as e:
            logger.error(f"ERROR:Error reversing transfer {self.transfer_no}: {str(e)}")
            raise ValidationError(f"Failed to reverse transfer: {str(e)}")

    def get_transfer_summary(self):
        """Get transfer summary for API responses"""
        # Refresh account balances to ensure fresh data
        self.from_account.refresh_from_db()
        self.to_account.refresh_from_db()
        
        return {
            'transfer_no': self.transfer_no,
            'from_account': {
                'id': self.from_account.id,
                'name': self.from_account.name,
                'ac_type': self.from_account.ac_type,
                'balance_before': float(self.from_account.balance + self.amount) if self.status == 'completed' else float(self.from_account.balance),
                'balance_after': float(self.from_account.balance) if self.status == 'completed' else None,
            },
            'to_account': {
                'id': self.to_account.id,
                'name': self.to_account.name,
                'ac_type': self.to_account.ac_type,
                'balance_before': float(self.to_account.balance - self.amount) if self.status == 'completed' else float(self.to_account.balance),
                'balance_after': float(self.to_account.balance) if self.status == 'completed' else None,
            },
            'amount': float(self.amount),
            'status': self.status,
            'transfer_date': self.transfer_date.isoformat(),
            'description': self.description,
            'is_reversal': self.is_reversal,
            'has_debit_transaction': bool(self.debit_transaction),
            'has_credit_transaction': bool(self.credit_transaction),
        }

    @property
    def can_execute(self):
        """Check if transfer can be executed"""
        # Refresh balance for accurate check
        self.from_account.refresh_from_db()
        return (
            self.status == 'pending' and
            self.from_account.balance >= self.amount and
            not self.is_reversal
        )

    @property
    def can_cancel(self):
        """Check if transfer can be cancelled"""
        return self.status in ['pending']

    @property
    def can_reverse(self):
        """Check if transfer can be reversed"""
        # Refresh balance for accurate check
        self.to_account.refresh_from_db()
        return (
            self.status == 'completed' and
            not self.is_reversal and
            self.to_account.balance >= self.amount
        )

    # Helper methods for UI
    def get_status_color(self):
        """Get color for status badge"""
        status_colors = {
            'pending': 'warning',
            'completed': 'success',
            'failed': 'danger',
            'cancelled': 'secondary',
        }
        return status_colors.get(self.status, 'secondary')

    def get_status_display_text(self):
        """Get human-readable status text"""
        status_display = {
            'pending': 'Pending',
            'completed': 'Completed',
            'failed': 'Failed',
            'cancelled': 'Cancelled',
        }
        return status_display.get(self.status, 'Unknown')

    def validate_for_execution(self):
        """Validate if transfer can be executed with detailed error messages"""
        errors = []
        
        if self.status != 'pending':
            errors.append(f"Transfer status is '{self.get_status_display_text()}', not 'Pending'")
        
        if self.is_reversal:
            errors.append("Cannot execute a reversal transfer")
        
        self.from_account.refresh_from_db()
        if self.from_account.balance < self.amount:
            errors.append(
                f"Insufficient balance in {self.from_account.name}. "
                f"Available: {self.from_account.balance}, Required: {self.amount}"
            )
        
        return errors