# myapp/filters.py — minimal ProductFilter stub (replace with your real filters)
import django_filters
from .models import Product

class ProductFilter(django_filters.FilterSet):
    """
    Example FilterSet. Add fields/filters you need.
    """
    min_price = django_filters.NumberFilter(field_name='selling_price', lookup_expr='gte')
    max_price = django_filters.NumberFilter(field_name='selling_price', lookup_expr='lte')
    min_stock = django_filters.NumberFilter(field_name='stock_qty', lookup_expr='gte')
    max_stock = django_filters.NumberFilter(field_name='stock_qty', lookup_expr='lte')

    class Meta:
        model = Product
        fields = {
            'category': ['exact'],
            'brand': ['exact'],
            'unit': ['exact'],
            'name': ['icontains'],
            'sku': ['icontains'],
            'is_active': ['exact'],
        }