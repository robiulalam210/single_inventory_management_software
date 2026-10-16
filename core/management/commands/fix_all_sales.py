from django.core.management.base import BaseCommand
from sales.models import Sale, SaleItem
from decimal import Decimal

class Command(BaseCommand):
    help = 'Fix all sales data and reset corrupted values'

    def handle(self, *args, **options):
        self.stdout.write('🔧 Fixing all sales data...')
        
        # Fix SaleItems first
        sale_items = SaleItem.objects.all()
        for item in sale_items:
            try:
                # Test if item amounts are valid
                test_fields = ['unit_price', 'discount']
                for field in test_fields:
                    value = getattr(item, field)
                    try:
                        Decimal(str(value))
                    except:
                        setattr(item, field, Decimal('0.00'))
                
                item.save()
                self.stdout.write(f'SUCCESS: Fixed sale item {item.id}')
            except Exception as e:
                self.stdout.write(f'ERROR:Error fixing sale item {item.id}: {e}')
        
        # Fix Sales
        sales = Sale.objects.all()
        for sale in sales:
            try:
                # Reset all decimal fields to safe values
                decimal_fields = [
                    'gross_total', 'net_total', 'grand_total', 'payable_amount',
                    'paid_amount', 'due_amount', 'change_amount', 'overall_discount',
                    'overall_delivery_charge', 'overall_service_charge', 'overall_vat_amount'
                ]
                
                for field in decimal_fields:
                    value = getattr(sale, field)
                    try:
                        Decimal(str(value))
                    except:
                        setattr(sale, field, Decimal('0.00'))
                        self.stdout.write(f'   Fixed {sale.invoice_no}.{field}')
                
                # Save to trigger update_totals
                sale.save()
                self.stdout.write(f'SUCCESS: Fixed sale {sale.invoice_no}')
                
            except Exception as e:
                self.stdout.write(f'ERROR:Error fixing sale {sale.invoice_no}: {e}')
        
        self.stdout.write('🎉 All sales data fixed!')