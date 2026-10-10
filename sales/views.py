from django.core.exceptions import ValidationError as DjangoValidationError
# sales/views.py
from rest_framework import viewsets, status, serializers
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from django.db import models
from django.db.models import Q, F, Sum, Value, Count
from django.db.models.functions import Coalesce
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
import logging

from core.utils import custom_response
from core.pagination import CustomPageNumberPagination    
from core.base_viewsets import BaseViewSet
from sales.models import Sale, SaleItem
from .serializers import SaleSerializer, SaleItemSerializer
from customers.models import Customer
from accounts.models import Account

logger = logging.getLogger(__name__)


# -----------------------------
# Due Sales API View
# -----------------------------
@api_view(['GET'])
def get_due_sales(request):
    """Get due sales for a customer"""
    customer_id = request.GET.get('customer_id')
    due_only = request.GET.get('due', 'true').lower() == 'true'
    
    if not customer_id:
        return Response({
            "status": False,
            "message": "Customer ID is required",
            "data": []
        }, status=400)
    
    try:
        # Check if customer exists
        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            return Response({
                "status": False,
                "message": f"Customer with ID {customer_id} not found",
                "data": []
            }, status=404)

        # Filter sales by customer AND company
        queryset = Sale.objects.filter(
            customer_id=customer_id
        )
        
        # If due_only is true, filter only sales with due amount > 0
        if due_only:
            queryset = queryset.filter(due_amount__gt=0)
        
        # Order by sale date
        queryset = queryset.order_by('sale_date')
        
        serializer = SaleSerializer(queryset, many=True)
        
        return Response({
            "status": True,
            "message": f"Found {queryset.count()} due sales for {customer.name}",
            "data": serializer.data
        })
        
    except Exception as e:
        logger.error(f"ERROR in get_due_sales: {str(e)}")
        return Response({
            "status": False,
            "message": f"Error fetching due sales: {str(e)}",
            "data": []
        }, status=500)


# -----------------------------
# Sale ViewSet
# -----------------------------
class SaleViewSet(BaseViewSet):
    queryset = Sale.objects.all()
    serializer_class = SaleSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = self.apply_filters(queryset)
        return queryset

    def apply_filters(self, queryset):
        """Apply comprehensive filtering to sales queryset"""
        params = self.request.GET

        # Customer filter
        customer_id = params.get('customer')
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)

        # Seller filter
        seller_id = params.get('seller')
        if seller_id:
            queryset = queryset.filter(sale_by_id=seller_id)

        # Sale type filter
        sale_type = params.get('sale_type')
        if sale_type:
            queryset = queryset.filter(sale_type=sale_type)

        # Customer type filter
        customer_type = params.get('customer_type')
        if customer_type:
            queryset = queryset.filter(customer_type=customer_type)

        # Payment status filter
        payment_status = params.get('payment_status')
        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)

        # Date range filters
        start_date = params.get('start_date')
        end_date = params.get('end_date')
        
        if start_date and end_date:
            try:
                start = self._parse_date(start_date)
                end = self._parse_date(end_date)
                
                if start and end:
                    # FIX: আগে এক বছরের বেশি পুরনো তারিখ চুপচাপ এই বছরে বদলে দেওয়া হতো —
                    # তাই পুরনো বিক্রি খুঁজলে ভুল (এই বছরের) data আসত। এখন যে তারিখ চাওয়া হয় সেটাই।
                    
                    
                    
                    if start > end:
                        start, end = end, start
                        logger.warning(f"Swapped dates: start was after end")
                    
                    end = end + timedelta(days=1) - timedelta(seconds=1)
                    
                    queryset = queryset.filter(sale_date__range=[start, end])
                    
            except ValueError as e:
                logger.error(f"Invalid date format: {e}")
        
        elif start_date:
            try:
                start = self._parse_date(start_date)
                if start:
                    # FIX: আগে এক বছরের বেশি পুরনো তারিখ চুপচাপ এই বছরে বদলে দেওয়া হতো —
                    # তাই পুরনো বিক্রি খুঁজলে ভুল (এই বছরের) data আসত। এখন যে তারিখ চাওয়া হয় সেটাই।
                    
                    queryset = queryset.filter(sale_date__gte=start)
            except ValueError as e:
                logger.error(f"Invalid start date format: {e}")
        
        elif end_date:
            try:
                end = self._parse_date(end_date)
                if end:
                    # FIX: আগে এক বছরের বেশি পুরনো তারিখ চুপচাপ এই বছরে বদলে দেওয়া হতো —
                    # তাই পুরনো বিক্রি খুঁজলে ভুল (এই বছরের) data আসত। এখন যে তারিখ চাওয়া হয় সেটাই।
                    
                    end = end + timedelta(days=1) - timedelta(seconds=1)
                    
                    queryset = queryset.filter(sale_date__lte=end)
            except ValueError as e:
                logger.error(f"Invalid end date format: {e}")

        # Search filter
        search = params.get('search')
        if search:
            queryset = queryset.filter(
                Q(invoice_no__icontains=search) |
                Q(customer__name__icontains=search) |
                Q(customer__phone__icontains=search) |
                Q(customer_name__icontains=search)
            )
        
        # Due only filter
        due_only = params.get('due_only')
        if due_only and due_only.lower() == 'true':
            queryset = queryset.filter(due_amount__gt=0)
        
        return queryset

    def _parse_date(self, date_str):
        """Helper method to parse date strings"""
        try:
            if not date_str:
                return None
            
            if 'T' in date_str:
                if '+' in date_str or 'Z' in date_str:
                    if 'Z' in date_str:
                        date_str = date_str.replace('Z', '+00:00')
                    return datetime.fromisoformat(date_str)
                else:
                    return datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S')
            else:
                return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError as e:
            logger.error(f"Date parsing error for '{date_str}': {e}")
            return None

    def create(self, request, *args, **kwargs):
        """Create a new sale"""
        try:
            logger.info(f"Creating sale with data: {request.data}")
            
            # Validate stock before creating sale
            items = request.data.get('items', [])
            for item in items:
                product_id = item.get('product_id')
                quantity = Decimal(str(item.get('quantity', 0)))
                if product_id and quantity > 0:
                    try:
                        from products.models import Product
                        product = Product.objects.get(id=product_id)
                        if product.stock_qty < float(quantity):
                            return custom_response(
                                success=False,
                                message=f'Insufficient stock for {product.name}. '
                                       f'Available: {product.stock_qty}, '
                                       f'Requested: {quantity}',
                                data=None,
                                status_code=status.HTTP_400_BAD_REQUEST
                            )
                    except Product.DoesNotExist:
                        return custom_response(
                            success=False,
                            message=f'Product with id {product_id} does not exist',
                            data=None,
                            status_code=status.HTTP_400_BAD_REQUEST
                        )
            
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            
            sale = serializer.save()
            
            logger.info(f"Sale created successfully: {sale.invoice_no}")
            
            return custom_response(
                success=True,
                message=f"Sale created successfully. Invoice: {sale.invoice_no}",
                data=serializer.data,
                status_code=status.HTTP_201_CREATED
            )
            
        except serializers.ValidationError as e:
            logger.error(f"Validation error creating sale: {e.detail}")
            return custom_response(
                success=False,
                message="Validation error",
                data=e.detail,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error creating sale: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=f"Error creating sale: {str(e)}",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def list(self, request, *args, **kwargs):
        """List sales with filtering"""
        try:
            queryset = self.filter_queryset(self.get_queryset())
            page = self.paginate_queryset(queryset)
            
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            
            serializer = self.get_serializer(queryset, many=True)
            
            return custom_response(
                success=True,
                message=f"Found {queryset.count()} sales",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Error listing sales: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=f"Error fetching sales: {str(e)}",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # Custom actions
    @action(detail=False, methods=['get'])
    def due_sales(self, request):
        """Get all due sales"""
        self.request.GET = self.request.GET.copy()
        self.request.GET['due_only'] = 'true'
        return self.list(request)

    @action(detail=False, methods=['get'])
    def today_sales(self, request):
        """Get today's sales"""
        self.request.GET = self.request.GET.copy()
        today = timezone.now().date()
        self.request.GET['start_date'] = today.isoformat()
        self.request.GET['end_date'] = today.isoformat()
        return self.list(request)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get sales summary"""
        try:
            queryset = self.filter_queryset(self.get_queryset())
            
            summary = queryset.aggregate(
                total_sales=Count('id'),
                total_amount=Coalesce(Sum('grand_total'), Decimal('0.00')),
                total_paid=Coalesce(Sum('paid_amount'), Decimal('0.00')),
                total_due=Coalesce(Sum('due_amount'), Decimal('0.00'))
            )
            
            summary_data = {
                'total_sales': summary['total_sales'],
                'total_amount': float(summary['total_amount']),
                'total_paid': float(summary['total_paid']),
                'total_due': float(summary['total_due']),
                'average_sale': float(summary['total_amount'] / summary['total_sales']) if summary['total_sales'] > 0 else 0.0
            }
            
            return custom_response(
                success=True,
                message="Sales summary fetched successfully",
                data=summary_data,
                status_code=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Error fetching sales summary: {str(e)}")
            return custom_response(
                success=False,
                message=f"Error fetching summary: {str(e)}",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def add_payment(self, request, pk=None):
        """Add payment to existing sale"""
        try:
            sale = self.get_object()
            
            amount = Decimal(str(request.data.get('amount', 0)))
            payment_method = request.data.get('payment_method')
            account_id = request.data.get('account_id')
            
            if amount <= 0:
                return custom_response(
                    success=False,
                    message="Payment amount must be greater than 0",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            if not payment_method:
                return custom_response(
                    success=False,
                    message="Payment method is required",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            account = None
            if account_id:
                account = Account.objects.filter(id=account_id).first()
                if account is None:
                    return custom_response(
                        success=False,
                        message="Account not found",
                        data=None,
                        status_code=status.HTTP_404_NOT_FOUND
                    )

            if amount > sale.due_amount and sale.customer_type == 'walk_in':
                return custom_response(
                    success=False,
                    message=f"Amount {amount} is more than due {sale.due_amount}",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )

            # FIX: আগে sale.paid_amount += amount; sale.save() → পুরো paid_amount আবার account এ যোগ হত।
            # এখন MoneyReceipt + Transaction দিয়ে শুধু এই amount টাই জমা হয়।
            sale.add_payment(amount, payment_method=payment_method, account=account, received_by=request.user)
            sale.refresh_from_db()

            return custom_response(
                success=True,
                message=f"Payment of {amount} added to sale {sale.invoice_no}",
                data=self.get_serializer(sale).data,
                status_code=status.HTTP_200_OK
            )
            
        except (DjangoValidationError, ValueError) as e:
            msg = "; ".join(e.messages) if hasattr(e, 'messages') else str(e)
            return custom_response(
                success=False,
                message=msg,
                data=None,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error adding payment: {str(e)}")
            return custom_response(
                success=False,
                message=f"Error adding payment: {str(e)}",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# -----------------------------
# SaleItem ViewSet
# -----------------------------
class SaleItemViewSet(BaseViewSet):
    queryset = SaleItem.objects.all().select_related('sale', 'product')
    serializer_class = SaleItemSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by sale ID if provided
        sale_id = self.request.GET.get('sale_id')
        if sale_id:
            queryset = queryset.filter(sale_id=sale_id)
        
        return queryset

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.filter_queryset(self.get_queryset())
            page = self.paginate_queryset(queryset)
            
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            
            serializer = self.get_serializer(queryset, many=True)
            return custom_response(
                success=True,
                message="Sale items fetched successfully.",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            return custom_response(
                success=False,
                message=f"Error fetching sale items: {str(e)}",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# -----------------------------
# SaleAllListViewSet
# -----------------------------
class SaleAllListViewSet(BaseViewSet):
    queryset = Sale.objects.all()
    serializer_class = SaleSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = self.apply_filters(queryset)
        return queryset

    def apply_filters(self, queryset):
        """Apply filtering to sales queryset"""
        params = self.request.GET

        # Customer filter
        customer_id = params.get('customer')
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)

        # Seller filter
        seller_id = params.get('seller')
        if seller_id:
            queryset = queryset.filter(sale_by_id=seller_id)

        # Sale type filter
        sale_type = params.get('sale_type')
        if sale_type:
            queryset = queryset.filter(sale_type=sale_type)

        # Customer type filter
        customer_type = params.get('customer_type')
        if customer_type:
            queryset = queryset.filter(customer_type=customer_type)

        # Payment status filter
        payment_status = params.get('payment_status')
        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)

        # Date range filter
        start_date = params.get('start_date')
        end_date = params.get('end_date')
        
        if start_date or end_date:
            try:
                def parse_date(date_str):
                    if not date_str:
                        return None
                    try:
                        if 'T' in date_str:
                            if '+' in date_str or 'Z' in date_str:
                                if 'Z' in date_str:
                                    date_str = date_str.replace('Z', '+00:00')
                                dt = datetime.fromisoformat(date_str)
                            else:
                                dt = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S')
                        else:
                            dt = datetime.strptime(date_str, '%Y-%m-%d')
                        
                        # FIX: আগে এক বছরের বেশি পুরনো তারিখ চুপচাপ এই বছরে বদলে দেওয়া হতো —
                        # তাই পুরনো বিক্রি খুঁজলে ভুল (এই বছরের) data আসত। এখন যে তারিখ চাওয়া হয় সেটাই।
                        return dt.date()
                    except Exception as e:
                        logger.error(f"Error parsing date '{date_str}': {e}")
                        return None

                start = parse_date(start_date)
                end = parse_date(end_date)

                if start and end:
                    if start > end:
                        start, end = end, start
                        logger.warning(f"Swapped dates: start was after end")
                    
                    queryset = queryset.filter(sale_date__date__range=[start, end])
                elif start:
                    queryset = queryset.filter(sale_date__date__gte=start)
                elif end:
                    queryset = queryset.filter(sale_date__date__lte=end)

            except ValueError as e:
                logger.error(f"Invalid date format: {e}")

        # Search filter
        search = params.get('search')
        if search:
            queryset = queryset.filter(
                Q(invoice_no__icontains=search) |
                Q(customer__name__icontains=search) |
                Q(customer__phone__icontains=search) |
                Q(customer_name__icontains=search)
            )

        # Due-only filter
        due_only = params.get('due_only')
        if due_only and due_only.lower() == 'true':
            queryset = queryset.filter(due_amount__gt=0)

        return queryset

    def list(self, request, *args, **kwargs):
        """List method with filtering"""
        try:
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
        
            return custom_response(
                success=True,
                message=f"Found {queryset.count()} sales",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )

        except Exception as e:
            logger.error(f"Error in sales list: {str(e)}")
            return custom_response(
                success=False,
                message=f"Error fetching sales: {str(e)}",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )