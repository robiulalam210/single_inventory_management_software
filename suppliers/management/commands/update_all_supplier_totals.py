# management/commands/fix_supplier_totals.py
from django.core.management.base import BaseCommand
from suppliers.models import Supplier
from purchases.models import Purchase
from decimal import Decimal

class Command(BaseCommand):
    help = 'Fix all supplier purchase totals with detailed calculation'
    
    def handle(self, *args, **options):
        self.stdout.write("🔄 Fixing ALL supplier purchase totals...")
        
        suppliers = Supplier.objects.all()
        
        for supplier in suppliers:
            self.stdout.write(f"\n📊 Processing: {supplier.name} (ID: {supplier.id})")
            
            # Get all purchases for this supplier
            purchases = Purchase.objects.filter(supplier_id=supplier.id)
            self.stdout.write(f"   Found {purchases.count()} purchases")
            
            # Manual calculation
            total_purchases = Decimal('0')
            total_paid = Decimal('0')
            
            for purchase in purchases:
                self.stdout.write(f"   Purchase {purchase.id}: {purchase.invoice_no} - "
                                f"Total: {purchase.grand_total}, Paid: {purchase.paid_amount}")
                total_purchases += purchase.grand_total
                total_paid += purchase.paid_amount
            
            purchase_count = purchases.count()
            total_due = total_purchases - total_paid
            
            # Update supplier
            supplier.total_purchases = total_purchases
            supplier.total_paid = total_paid
            supplier.total_due = total_due
            supplier.purchase_count = purchase_count
            
            supplier.save(update_fields=[
                'total_purchases', 'total_paid', 'total_due', 'purchase_count'
            ])
            
            self.stdout.write(
                self.style.SUCCESS(f"   SUCCESS: Fixed: Purchases=${total_purchases}, Due=${total_due}, Count={purchase_count}")
            )
        
        self.stdout.write(self.style.SUCCESS("\n🎉 All suppliers fixed successfully!"))