# Create this as management command: fix_purchase_data.py
from django.core.management.base import BaseCommand
from purchases.models import Purchase
from decimal import Decimal

class Command(BaseCommand):
    help = 'Fix purchase due_amount inconsistencies'
    
    def handle(self, *args, **options):
        self.stdout.write("🔧 Fixing purchase due_amount inconsistencies...")
        
        # Fix all purchases where due_amount doesn't match calculation
        purchases = Purchase.objects.all()
        fixed_count = 0
        
        for purchase in purchases:
            expected_due = max(Decimal('0.00'), purchase.grand_total - purchase.paid_amount)
            
            if purchase.due_amount != expected_due:
                self.stdout.write(
                    f"Fixing purchase {purchase.invoice_no}: "
                    f"due_amount {purchase.due_amount} → {expected_due}"
                )
                
                # Use direct update to avoid signals
                Purchase.objects.filter(pk=purchase.pk).update(
                    due_amount=expected_due,
                    change_amount=max(Decimal('0.00'), purchase.paid_amount - purchase.grand_total)
                )
                fixed_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(f"SUCCESS: Fixed {fixed_count} purchase records")
        )
        
        # Also update all supplier totals
        from suppliers.models import Supplier
        Supplier.recalculate_all_supplier_totals()
        
        self.stdout.write(
            self.style.SUCCESS("SUCCESS: Updated all supplier totals")
        )