# products/utils.py

from decimal import Decimal
from django.db import transaction
from products.models import Product, SaleMode, ProductSaleMode
from sales.models import Sale, SaleItem

class SaleModeCalculator:
    """Utility class for sale mode calculations"""
    
    @staticmethod
    def calculate_sale(product, sale_mode_code, quantity):
        """
        Calculate sale details for a product and sale mode
        
        Args:
            product: Product instance
            sale_mode_code: Sale mode code (e.g., 'KG', 'BOSTA', 'DOZEN')
            quantity: Quantity in sale mode units
        
        Returns:
            dict: Sale calculation details
        """
        try:
            # Get sale mode
            sale_mode = SaleMode.objects.get(
                code=sale_mode_code
            )
            
            # Get product sale mode configuration
            product_sale_mode = ProductSaleMode.objects.get(
                product=product,
                sale_mode=sale_mode,
                is_active=True
            )
            
            # Calculate base quantity
            base_quantity = sale_mode.convert_to_base(quantity)
            
            # Calculate price
            total_price = product_sale_mode.get_final_price(quantity)
            
            return {
                'product': product.name,
                'sale_mode': sale_mode.name,
                'sale_quantity': quantity,
                'base_quantity': float(base_quantity),
                'unit_price': float(product_sale_mode.get_unit_price(base_quantity)),
                'total_price': float(total_price),
                'price_type': sale_mode.price_type,
                'stock_available': product.stock_qty,
                'stock_after': product.stock_qty - float(base_quantity),
                'can_sell': product.stock_qty >= float(base_quantity)
            }
            
        except SaleMode.DoesNotExist:
            raise ValueError(f"Sale mode '{sale_mode_code}' not found")
        except ProductSaleMode.DoesNotExist:
            raise ValueError(f"Product '{product.name}' not configured for sale mode '{sale_mode_code}'")
    
    @staticmethod
    def get_available_sale_modes(product):
        """Get all available sale modes for a product"""
        sale_modes = ProductSaleMode.objects.filter(
            product=product,
            is_active=True
        ).select_related('sale_mode')
        
        return [
            {
                'id': ps.sale_mode.id,
                'code': ps.sale_mode.code,
                'name': ps.sale_mode.name,
                'price_type': ps.sale_mode.price_type,
                'unit_price': float(ps.unit_price) if ps.unit_price else None,
                'flat_price': float(ps.flat_price) if ps.flat_price else None,
                'conversion': float(ps.sale_mode.conversion_factor),
                'has_tiers': ps.tiers.exists() if hasattr(ps, 'tiers') else False
            }
            for ps in sale_modes
        ]


class SaleProcessor:
    """Process sales with multi-mode support"""
    
    @staticmethod
    @transaction.atomic
    def process_sale(sale_data, created_by):
        """
        Process a complete sale with multiple items
        
        Args:
            sale_data: Dict containing sale information
            created_by: User who created the sale
        
        Returns:
            Sale instance
        """
        # Create sale record
        sale = Sale(
            created_by=created_by,
            sale_type=sale_data.get('sale_type', 'retail'),
            customer_type=sale_data.get('customer_type', 'walk_in'),
            customer_name=sale_data.get('customer_name'),
            payment_method=sale_data.get('payment_method'),
            paid_amount=sale_data.get('paid_amount', Decimal('0.00'))
        )
        
        if sale_data.get('customer_id'):
            from customers.models import Customer
            sale.customer = Customer.objects.get(
                id=sale_data['customer_id']
            )
        
        sale.save()
        
        # Process items
        items = sale_data.get('items', [])
        for item_data in items:
            SaleProcessor._process_sale_item(sale, item_data)
        
        # Calculate final totals
        sale.calculate_totals()
        
        return sale
    
    @staticmethod
    def _process_sale_item(sale, item_data):
        """Process individual sale item"""
        product = Product.objects.get(
            id=item_data['product_id']
        )
        
        sale_mode = None
        if item_data.get('sale_mode_code'):
            sale_mode = SaleMode.objects.get(
                code=item_data['sale_mode_code']
            )
        
        # Create sale item
        sale_item = SaleItem(
            sale=sale,
            product=product,
            sale_mode=sale_mode,
            sale_quantity=Decimal(str(item_data['quantity'])),
            price_type=item_data.get('price_type', 'unit'),
            discount=Decimal(str(item_data.get('discount', 0))),
            discount_type=item_data.get('discount_type', 'fixed')
        )
        
        if item_data.get('flat_price'):
            sale_item.flat_price = Decimal(str(item_data['flat_price']))
        
        sale_item.save()