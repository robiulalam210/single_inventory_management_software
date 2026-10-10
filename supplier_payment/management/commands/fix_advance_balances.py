from django.core.management.base import BaseCommand
from suppliers.models import Supplier
from supplier_payment.model import SupplierPayment
from purchases.models import Purchase
from django.db import transaction
from decimal import Decimal

class Command(BaseCommand):
    help = 'Emergency fix for supplier advance balances'

    def handle(self, *args, **options):
        self.stdout.write('🚨 Starting emergency advance balance fix...')
        
        with transaction.atomic():
            suppliers = Supplier.objects.all()
            
            for supplier in suppliers:
                self.stdout.write(f'🔧 Processing supplier: {supplier.name} (ID: {supplier.id})')
                
                try:
                    # Get all overall payments for this supplier
                    overall_payments = SupplierPayment.objects.filter(
                        supplier=supplier,
                        payment_type='overall'
                    )
                    
                    total_payments = Decimal('0.00')
                    total_applied_to_purchases = Decimal('0.00')
                    
                    for payment in overall_payments:
                        self.stdout.write(f'   Payment: {payment.sp_no} - {payment.amount}')
                        total_payments += payment.amount
                        
                        # Calculate total due purchases at the time of payment
                        # This is a simplified calculation
                        due_purchases_at_time = Purchase.objects.filter(
                            supplier=supplier,
                            due_amount__gt=0
                        )
                        
                        total_due_at_time = sum(p.due_amount for p in due_purchases_at_time)
                        applied = min(payment.amount, total_due_at_time)
                        total_applied_to_purchases += applied
                    
                    # Also include advance payments
                    advance_payments = SupplierPayment.objects.filter(
                        supplier=supplier,
                        payment_type='advance'
                    )
                    
                    for payment in advance_payments:
                        self.stdout.write(f'   Advance Payment: {payment.sp_no} - {payment.amount}')
                        total_payments += payment.amount
                    
                    # Calculate advance balance (total payments - amount applied to purchases)
                    calculated_advance = total_payments - total_applied_to_purchases
                    
                    if calculated_advance > 0:
                        old_balance = supplier.advance_balance
                        supplier.advance_balance = calculated_advance
                        supplier.save()
                        
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'   SUCCESS: Updated advance balance: '
                                f'{old_balance} -> {supplier.advance_balance}'
                            )
                        )
                    else:
                        self.stdout.write(f'   ℹ️  No advance to add (calculated: {calculated_advance})')
                    
                    # Also update purchase totals
                    supplier.update_purchase_totals()
                    
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'   ERROR:Error: {e}')
                    )
        
        self.stdout.write(self.style.SUCCESS('🎉 Emergency advance balance fix completed!'))