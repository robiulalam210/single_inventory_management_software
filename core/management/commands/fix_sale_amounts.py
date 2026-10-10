from django.core.management.base import BaseCommand
from sales.models import Sale
from decimal import Decimal, InvalidOperation

class Command(BaseCommand):
    help = 'FINAL FIX: Clean up all sales data'

    def handle(self, *args, **options):
        self.stdout.write('🔧 FINAL FIX: Cleaning sales data...')
        
        sales = Sale.objects.all()
        fixed_count = 0
        
        for sale in sales:
            try:
                # Reset all amounts to safe values
                sale.gross_total = Decimal('0.00')
                sale.net_total = Decimal('0.00')
                sale.grand_total = Decimal('0.00')
                sale.payable_amount = Decimal('0.00')
                sale.paid_amount = Decimal('0.00')
                sale.due_amount = Decimal('0.00')
                sale.change_amount = Decimal('0.00')
                sale.overall_discount = Decimal('0.00')
                sale.overall_delivery_charge = Decimal('0.00')
                sale.overall_service_charge = Decimal('0.00')
                sale.overall_vat_amount = Decimal('0.00')
                
                # Recalculate from items
                items = sale.items.all()
                if items.exists():
                    gross = sum([item.subtotal() for item in items])
                    sale.gross_total = gross
                    sale.grand_total = gross
                    sale.payable_amount = gross
                    sale.due_amount = max(gross - sale.paid_amount, Decimal('0.00'))
                
                # Update payment status
                if sale.paid_amount >= sale.payable_amount:
                    sale.payment_status = 'paid'
                    sale.due_amount = Decimal('0.00')
                elif sale.paid_amount > Decimal('0.00'):
                    sale.payment_status = 'partial'
                else:
                    sale.payment_status = 'pending'
                
                sale.save()
                fixed_count += 1
                self.stdout.write(f'SUCCESS: Fixed sale {sale.invoice_no}')
                
            except Exception as e:
                self.stdout.write(f'ERROR:Error fixing {sale.invoice_no}: {e}')
        
        self.stdout.write(f'🎉 Fixed {fixed_count} sales!')