from offline_sync.utils import touch
# returns/models.py - COMPLETE FIXED VERSION
from django.db import models, transaction
from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import F  # IMPORTANT: Add this import
from products.models import Product
from accounts.models import Account
from transactions.models import Transaction
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class SalesReturn(models.Model):
    RETURN_STATUS = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
    ]
    
    receipt_no = models.CharField(max_length=100, blank=True, null=True)
    customer_name = models.CharField(max_length=255, blank=True, null=True)
    return_date = models.DateField()
    account = models.ForeignKey(Account, on_delete=models.SET_NULL, blank=True, null=True, related_name='sale_returns')
    payment_method = models.CharField(max_length=100, blank=True, null=True)
    reason = models.TextField(blank=True, null=True)
    return_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    return_charge_type = models.CharField(max_length=50, blank=True, null=True, choices=[('fixed', 'Fixed'), ('percentage', 'Percentage')])
    return_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=RETURN_STATUS, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    original_sale = models.ForeignKey('sales.Sale', on_delete=models.SET_NULL, null=True, blank=True, related_name='sales_returns')
    
    class Meta:
        ordering = ['-return_date', '-id']

    def __str__(self):
        return f"SalesReturn #{self.id} - {self.receipt_no or 'No Receipt'}"

    def save(self, *args, **kwargs):
        if not self.receipt_no:
            self._generate_receipt_no()
        
        if not self.return_date:
            self.return_date = timezone.now().date()
            
        super().save(*args, **kwargs)
    
    def _generate_receipt_no(self):
        """Receipt number: SR-000001"""
        try:
            last = SalesReturn.objects.filter(
                receipt_no__regex=r'^SR-\d+$'
            ).order_by('-id').first()
            new_number = 1
            if last and last.receipt_no:
                try:
                    new_number = int(last.receipt_no.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    new_number = SalesReturn.objects.count() + 1
            candidate = f"SR-{new_number:06d}"
            while SalesReturn.objects.filter(receipt_no=candidate).exists():
                new_number += 1
                candidate = f"SR-{new_number:06d}"
            self.receipt_no = candidate
        except Exception as e:
            logger.error(f"Error generating receipt_no: {e}")
            self.receipt_no = f"SR-{timezone.now().strftime('%Y%m%d%H%M%S')}"

    def calculate_return_amount(self):
        """Calculate total return amount from items"""
        total = Decimal('0.00')
        
        for item in self.items.all():
            base_amount = item.unit_price * item.quantity
            
            if item.discount_type == 'percentage' and item.discount > 0:
                discount_amount = (base_amount * item.discount) / 100
            else:
                discount_amount = item.discount
                
            total += base_amount - discount_amount
        
        # Add return charge
        if self.return_charge_type == 'percentage' and self.return_charge > 0:
            return_charge_amount = (total * self.return_charge) / 100
        else:
            return_charge_amount = self.return_charge
            
        return total + return_charge_amount
    
    @transaction.atomic
    def approve(self):
        """Approve the sales return"""
        if self.status != 'pending':
            raise ValidationError(f"Cannot approve {self.status} return")
        
        # Update product stock
        self._update_product_stock()
        
        # Create transaction
        self._create_transaction()
        
        # Create bad stock entries
        self._create_bad_stock()
        
        # Update status
        self.status = 'approved'
        self.save(update_fields=['status'])
        
        return True
    
    @transaction.atomic
    def complete(self):
        """Mark return as completed"""
        if self.status != 'approved':
            raise ValidationError("Return must be approved first")
        
        self.status = 'completed'
        self.save(update_fields=['status'])
        return True
    
    @transaction.atomic
    def reject(self):
        """Reject the return"""
        if self.status != 'pending':
            raise ValidationError(f"Cannot reject {self.status} return")
        
        self.status = 'rejected'
        self.save(update_fields=['status'])
        return True
    
    def _update_product_stock(self):
        """Update product stock_qty for returned items"""
        for item in self.items.all():
            # Calculate good quantity (non-damaged)
            good_quantity = item.quantity - item.damage_quantity
            
            if good_quantity > 0:
                # FIXED: Use stock_qty instead of stock
                Product.objects.filter(id=item.product.id).update(
                    stock_qty=F('stock_qty') + good_quantity
                )
                touch(Product, item.product.id)  # audit + desktop sync এ পরিবর্তন পৌঁছানোর জন্য
                
                # Optional: Create stock movement
                self._create_stock_movement(item.product, good_quantity, 'in', 'sales_return')
    
    def _create_stock_movement(self, product, quantity, movement_type, reference_type):
        """Create stock movement record"""
        # Implement based on your stock movement model
        pass
    
    def _create_transaction(self):
        """Create transaction for the return amount"""
        if not self.account:
            raise ValidationError("Account is required for transaction")
        
        # For sales return, we DEBIT the account (money going out)
        Transaction.objects.create(
            transaction_type='debit',
            amount=self.return_amount,
            account=self.account,
            payment_method=self.payment_method or 'cash',
            description=f"Sales Return: {self.receipt_no} - Customer: {self.customer_name}",
            created_by=self.created_by,
            status='completed',
            transaction_date=self.return_date,
            is_opening_balance=False
        )
    
    def _create_bad_stock(self):
        """Create bad stock entries for damaged items"""
        for item in self.items.all():
            if item.damage_quantity > 0:
                BadStock.objects.create(
                    product=item.product,
                    quantity=item.damage_quantity,
                    reason=f"Damaged in sales return {self.receipt_no} - {self.reason or 'No reason provided'}",
                    reference_type='sales_return',
                    reference_id=self.id,
                    date=self.return_date
                )
    
    @transaction.atomic
    def delete(self, *args, **kwargs):
        """Override delete to handle reversal if approved"""
        try:
            if self.status == 'approved':
                # Reverse stock updates
                for item in self.items.all():
                    good_quantity = item.quantity - item.damage_quantity
                    if good_quantity > 0:
                        # FIXED: Use stock_qty instead of stock
                        Product.objects.filter(id=item.product.id).update(
                            stock_qty=F('stock_qty') - good_quantity
                        )
                        touch(Product, item.product.id)  # audit + desktop sync এ পরিবর্তন পৌঁছানোর জন্য
                
                # Delete related bad stock
                BadStock.objects.filter(reference_type='sales_return', reference_id=self.id).delete()
            
            super().delete(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error deleting sales return {self.id}: {e}")
            raise


class SalesReturnItem(models.Model):
    sales_return = models.ForeignKey(SalesReturn, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    product_name = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(default=1)
    damage_quantity = models.PositiveIntegerField(default=0)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_type = models.CharField(max_length=50, blank=True, null=True, choices=[('fixed', 'Fixed'), ('percentage', 'Percentage')])
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ['id']

    def save(self, *args, **kwargs):
        # Validate quantities
        if self.damage_quantity > self.quantity:
            raise ValidationError("Damage quantity cannot exceed total quantity")
        
        # Calculate total
        base_amount = self.unit_price * self.quantity
        
        if self.discount_type == 'percentage' and self.discount > 0:
            discount_amount = (base_amount * self.discount) / 100
        else:
            discount_amount = self.discount
            
        self.total = base_amount - discount_amount
        
        # Save product name if not set
        if not self.product_name and self.product:
            self.product_name = self.product.name
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product_name} ({self.quantity} units, {self.damage_quantity} damaged)"


class PurchaseReturn(models.Model):
    RETURN_STATUS = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
    ]
    
    supplier = models.CharField(max_length=255, blank=True, null=True)
    invoice_no = models.CharField(max_length=100, blank=True, null=True)
    return_date = models.DateField()
    account = models.ForeignKey(Account, on_delete=models.SET_NULL, blank=True, null=True, related_name='purchase_returns')
    payment_method = models.CharField(max_length=100, blank=True, null=True)
    return_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    return_charge_type = models.CharField(max_length=50, blank=True, null=True, choices=[('fixed', 'Fixed'), ('percentage', 'Percentage')])
    return_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reason = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=RETURN_STATUS, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    original_purchase = models.ForeignKey('purchases.Purchase', on_delete=models.SET_NULL, null=True, blank=True, related_name='purchase_returns')
    
    class Meta:
        ordering = ['-return_date', '-id']

    def __str__(self):
        return f"PurchaseReturn #{self.id} - {self.invoice_no or 'No Invoice'}"

    def save(self, *args, **kwargs):
        if not self.return_date:
            self.return_date = timezone.now().date()
        
        if not self.invoice_no:
            self._generate_invoice_no()
            
        super().save(*args, **kwargs)
    
    def _generate_invoice_no(self):
        """Invoice number: PR-000001"""
        try:
            last = PurchaseReturn.objects.filter(
                invoice_no__regex=r'^PR-\d+$'
            ).order_by('-id').first()
            new_number = 1
            if last and last.invoice_no:
                try:
                    new_number = int(last.invoice_no.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    new_number = PurchaseReturn.objects.count() + 1
            candidate = f"PR-{new_number:06d}"
            while PurchaseReturn.objects.filter(invoice_no=candidate).exists():
                new_number += 1
                candidate = f"PR-{new_number:06d}"
            self.invoice_no = candidate
        except Exception as e:
            logger.error(f"Error generating invoice_no: {e}")
            self.invoice_no = f"PR-{timezone.now().strftime('%Y%m%d%H%M%S')}"

    def calculate_return_amount(self):
        """Calculate total return amount from items"""
        total = Decimal('0.00')
        
        for item in self.items.all():
            base_amount = item.unit_price * item.quantity
            
            if item.discount_type == 'percentage' and item.discount > 0:
                discount_amount = (base_amount * item.discount) / 100
            else:
                discount_amount = item.discount
                
            total += base_amount - discount_amount
        
        # Deduct return charge (we receive less money back)
        if self.return_charge_type == 'percentage' and self.return_charge > 0:
            return_charge_amount = (total * self.return_charge) / 100
        else:
            return_charge_amount = self.return_charge
            
        return total - return_charge_amount  # Note: minus charge
    
    @transaction.atomic
    def approve(self):
        """Approve the purchase return"""
        if self.status != 'pending':
            raise ValidationError(f"Cannot approve {self.status} return")
        
        # Update product stock (decrease)
        self._update_product_stock()
        
        # Create transaction (credit - money coming in)
        self._create_transaction()
        
        # Create bad stock entries if needed
        self._create_bad_stock()
        
        # Update status
        self.status = 'approved'
        self.save(update_fields=['status'])
        
        return True
    
    @transaction.atomic
    def complete(self):
        """Mark return as completed"""
        if self.status != 'approved':
            raise ValidationError("Return must be approved first")
        
        self.status = 'completed'
        self.save(update_fields=['status'])
        return True
    
    @transaction.atomic
    def reject(self):
        """Reject the return"""
        if self.status != 'pending':
            raise ValidationError(f"Cannot reject {self.status} return")
        
        self.status = 'rejected'
        self.save(update_fields=['status'])
        return True
    
    def _update_product_stock(self):
        """Decrease product stock_qty for returned items"""
        for item in self.items.all():
            # Decrease product stock_qty (items going back to supplier)
            # FIXED: Use stock_qty instead of stock
            Product.objects.filter(id=item.product.id).update(
                stock_qty=F('stock_qty') - item.quantity
            )
            touch(Product, item.product.id)  # audit + desktop sync এ পরিবর্তন পৌঁছানোর জন্য
            
            # Optional: Create stock movement
            self._create_stock_movement(item.product, item.quantity, 'out', 'purchase_return')
    
    def _create_stock_movement(self, product, quantity, movement_type, reference_type):
        """Create stock movement record"""
        pass
    
    def _create_transaction(self):
        """Create transaction for the return amount"""
        if not self.account:
            raise ValidationError("Account is required for transaction")
        
        # For purchase return, we CREDIT the account (money coming in)
        Transaction.objects.create(
            transaction_type='credit',
            amount=self.return_amount,
            account=self.account,
            payment_method=self.payment_method or 'cash',
            description=f"Purchase Return: {self.invoice_no} - Supplier: {self.supplier}",
            created_by=self.created_by,
            status='completed',
            transaction_date=self.return_date,
            is_opening_balance=False
        )
    
    def _create_bad_stock(self):
        """Create bad stock entries for returned items"""
        for item in self.items.all():
            BadStock.objects.create(
                product=item.product,
                quantity=item.quantity,
                reason=f"Returned to supplier: {self.invoice_no} - {self.reason or 'No reason provided'}",
                reference_type='purchase_return',
                reference_id=self.id,
                date=self.return_date
            )
    
    @transaction.atomic
    def delete(self, *args, **kwargs):
        """Override delete to handle reversal if approved"""
        try:
            if self.status == 'approved':
                # Reverse stock updates
                for item in self.items.all():
                    # FIXED: Use stock_qty instead of stock
                    Product.objects.filter(id=item.product.id).update(
                        stock_qty=F('stock_qty') + item.quantity
                    )
                    touch(Product, item.product.id)  # audit + desktop sync এ পরিবর্তন পৌঁছানোর জন্য
                
                # Delete related bad stock
                BadStock.objects.filter(reference_type='purchase_return', reference_id=self.id).delete()
            
            super().delete(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error deleting purchase return {self.id}: {e}")
            raise


class PurchaseReturnItem(models.Model):
    purchase_return = models.ForeignKey(PurchaseReturn, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    product_name = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_type = models.CharField(max_length=50, blank=True, null=True, choices=[('fixed', 'Fixed'), ('percentage', 'Percentage')])
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ['id']

    def save(self, *args, **kwargs):
        # Calculate total
        base_amount = self.unit_price * self.quantity
        
        if self.discount_type == 'percentage' and self.discount > 0:
            discount_amount = (base_amount * self.discount) / 100
        else:
            discount_amount = self.discount
            
        self.total = base_amount - discount_amount
        
        # Save product name if not set
        if not self.product_name and self.product:
            self.product_name = self.product.name
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"


class BadStock(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='bad_stocks')
    quantity = models.PositiveIntegerField()
    reason = models.TextField()
    date = models.DateField(auto_now_add=True)
    reference_type = models.CharField(max_length=50, choices=[('sales_return', 'Sales Return'), ('purchase_return', 'Purchase Return'), ('direct', 'Direct')])
    reference_id = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['reference_type', 'reference_id']),
            models.Index(fields=['product', 'date']),
        ]

    def __str__(self):
        return f"Bad Stock: {self.quantity} of {self.product.name}"