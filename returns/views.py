# returns/views.py - COMPLETE FIXED VERSION
from rest_framework import viewsets, status, permissions, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Sum, Count
from django.db import transaction as db_transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from core.utils import custom_response
from core.pagination import CustomPageNumberPagination
from .models import SalesReturn, PurchaseReturn, BadStock, SalesReturnItem, PurchaseReturnItem
from .serializers import SalesReturnSerializer, PurchaseReturnSerializer, BadStockSerializer
from products.models import Product
from accounts.models import Account
import logging

logger = logging.getLogger(__name__)


class BaseViewSet(viewsets.ModelViewSet):
    """Base viewset: authenticated users only"""
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_authenticated:
            return queryset
        return queryset.none()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.filter_queryset(self.get_queryset())
            
            # Get summary data if requested
            get_summary = request.query_params.get('summary', 'false').lower() == 'true'
            if get_summary:
                summary = self._get_summary(queryset)
                return custom_response(
                    success=True,
                    message="Summary fetched successfully.",
                    data=summary,
                    status_code=status.HTTP_200_OK
                )
            
            page = self.paginate_queryset(queryset)
            
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(queryset, many=True)
            return custom_response(
                success=True,
                message="Data fetched successfully.",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error in list: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _get_summary(self, queryset):
        """Get summary data for the queryset"""
        return {}


class SalesReturnViewSet(BaseViewSet):
    serializer_class = SalesReturnSerializer
    model = SalesReturn

    def get_queryset(self):
        user = self.request.user
        queryset = SalesReturn.objects.filter().prefetch_related('items')
        
        # Apply filters
        search = self.request.query_params.get('search', None)
        status_filter = self.request.query_params.get('status', None)
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)
        customer_name = self.request.query_params.get('customer_name', None)
        receipt_no = self.request.query_params.get('receipt_no', None)
        
        if search:
            queryset = queryset.filter(
                Q(receipt_no__icontains=search) |
                Q(customer_name__icontains=search) |
                Q(reason__icontains=search)
            )
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
            
        if customer_name:
            queryset = queryset.filter(customer_name__icontains=customer_name)
            
        if receipt_no:
            queryset = queryset.filter(receipt_no__icontains=receipt_no)
            
        if start_date and end_date:
            queryset = queryset.filter(return_date__range=[start_date, end_date])
        elif start_date:
            queryset = queryset.filter(return_date__gte=start_date)
        elif end_date:
            queryset = queryset.filter(return_date__lte=end_date)
        
        return queryset.order_by('-return_date', '-id')
    
    def _get_summary(self, queryset):
        """Get sales return summary"""
        total_count = queryset.count()
        
        # Status counts
        status_counts = queryset.values('status').annotate(
            count=Count('id'),
            total_amount=Sum('return_amount')
        )
        
        # Monthly summary
        monthly_summary = queryset.values('return_date__year', 'return_date__month').annotate(
            count=Count('id'),
            total_amount=Sum('return_amount')
        ).order_by('-return_date__year', '-return_date__month')[:12]
        
        return {
            'total_count': total_count,
            'total_amount': queryset.aggregate(total=Sum('return_amount'))['total'] or 0,
            'status_summary': list(status_counts),
            'monthly_summary': list(monthly_summary)
        }

    @action(detail=False, methods=['get'])
    def get_initial_data(self, request):
        """Get initial data for sales return form"""
        try:
            user = request.user
            # Get products and accounts
            products = Product.objects.filter().values('id', 'name', 'price', 'stock_qty', 'code')
            accounts = Account.objects.filter().values('id', 'name', 'balance', 'account_type')
            
            # Get recent sales for reference
            recent_sales = []
            # Uncomment if you have sales app
            # from sales.models import Sale
            # recent_sales = Sale.objects.filter().order_by('-sale_date')[:10].values(
            #     'id', 'invoice_no', 'customer_name', 'total_amount'
            # )
            
            data = {
                'products': list(products),
                'accounts': list(accounts),
                'recent_sales': list(recent_sales),
                'payment_methods': [
                    {'value': 'cash', 'label': 'Cash'},
                    {'value': 'bank', 'label': 'Bank Transfer'},
                    {'value': 'mobile', 'label': 'Mobile Banking'},
                    {'value': 'card', 'label': 'Card'},
                    {'value': 'credit', 'label': 'Credit'}
                ]
            }
            
            return custom_response(
                success=True,
                message="Initial data fetched successfully.",
                data=data,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error in get_initial_data: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def create(self, request, *args, **kwargs):
        try:
            with db_transaction.atomic():
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                instance = serializer.save(
                    created_by=request.user
                )
                
                # Auto-approve if requested
                auto_approve = request.data.get('auto_approve', False)
                if auto_approve:
                    try:
                        instance.approve()
                    except ValidationError as e:
                        return custom_response(
                            success=False,
                            message=f"Created but could not approve: {str(e)}",
                            data=serializer.data,
                            status_code=status.HTTP_201_CREATED
                        )
                
                return custom_response(
                    success=True,
                    message="Sales return created successfully.",
                    data=self.get_serializer(instance).data,
                    status_code=status.HTTP_201_CREATED
                )
        except serializers.ValidationError as e:
            return custom_response(
                success=False,
                message="Validation Error.",
                data=e.detail,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except ValidationError as e:
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error creating sales return: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            
            # Only allow update if pending
            if instance.status != 'pending':
                return custom_response(
                    success=False,
                    message=f"Cannot update {instance.status} return",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            with db_transaction.atomic():
                serializer = self.get_serializer(instance, data=request.data, partial=kwargs.get('partial', False))
                serializer.is_valid(raise_exception=True)
                serializer.save()
                
                return custom_response(
                    success=True,
                    message="Sales return updated successfully.",
                    data=serializer.data,
                    status_code=status.HTTP_200_OK
                )
        except serializers.ValidationError as e:
            return custom_response(
                success=False,
                message="Validation Error.",
                data=e.detail,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error updating sales return: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            
            # Only allow delete if pending or rejected
            if instance.status not in ['pending', 'rejected']:
                return custom_response(
                    success=False,
                    message=f"Cannot delete {instance.status} return",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            instance.delete()
            return custom_response(
                success=True,
                message="Sales return deleted successfully.",
                data=None,
                status_code=status.HTTP_204_NO_CONTENT
            )
        except Exception as e:
            logger.error(f"Error deleting sales return: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a sales return"""
        try:
            instance = self.get_object()
            
            with db_transaction.atomic():
                instance.approve()
                
                return custom_response(
                    success=True,
                    message="Sales return approved successfully.",
                    data=self.get_serializer(instance).data,
                    status_code=status.HTTP_200_OK
                )
        except ValidationError as e:
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error approving sales return: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Mark sales return as completed"""
        try:
            instance = self.get_object()
            
            with db_transaction.atomic():
                instance.complete()
                
                return custom_response(
                    success=True,
                    message="Sales return marked as completed.",
                    data=self.get_serializer(instance).data,
                    status_code=status.HTTP_200_OK
                )
        except ValidationError as e:
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error completing sales return: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a sales return"""
        try:
            instance = self.get_object()
            
            with db_transaction.atomic():
                instance.reject()
                
                return custom_response(
                    success=True,
                    message="Sales return rejected successfully.",
                    data=self.get_serializer(instance).data,
                    status_code=status.HTTP_200_OK
                )
        except ValidationError as e:
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error rejecting sales return: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def get_stats(self, request):
        """Get sales return statistics"""
        try:
            user = request.user
            # Today's returns
            today = timezone.now().date()
            todays_returns = SalesReturn.objects.filter(
                return_date=today
            )
            
            # This month's returns
            month_start = today.replace(day=1)
            this_months_returns = SalesReturn.objects.filter(
                return_date__gte=month_start
            )
            
            stats = {
                'today': {
                    'count': todays_returns.count(),
                    'amount': todays_returns.aggregate(total=Sum('return_amount'))['total'] or 0
                },
                'this_month': {
                    'count': this_months_returns.count(),
                    'amount': this_months_returns.aggregate(total=Sum('return_amount'))['total'] or 0
                },
                'by_status': list(SalesReturn.objects.filter().values('status').annotate(
                    count=Count('id'),
                    amount=Sum('return_amount')
                ))
            }
            
            return custom_response(
                success=True,
                message="Statistics fetched successfully.",
                data=stats,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PurchaseReturnViewSet(BaseViewSet):
    serializer_class = PurchaseReturnSerializer
    model = PurchaseReturn

    def get_queryset(self):
        user = self.request.user
        queryset = PurchaseReturn.objects.filter().prefetch_related('items')
        
        # Apply filters
        search = self.request.query_params.get('search', None)
        status_filter = self.request.query_params.get('status', None)
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)
        supplier = self.request.query_params.get('supplier', None)
        invoice_no = self.request.query_params.get('invoice_no', None)
        
        if search:
            queryset = queryset.filter(
                Q(invoice_no__icontains=search) |
                Q(supplier__icontains=search) |
                Q(reason__icontains=search)
            )
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
            
        if supplier:
            queryset = queryset.filter(supplier__icontains=supplier)
            
        if invoice_no:
            queryset = queryset.filter(invoice_no__icontains=invoice_no)
            
        if start_date and end_date:
            queryset = queryset.filter(return_date__range=[start_date, end_date])
        elif start_date:
            queryset = queryset.filter(return_date__gte=start_date)
        elif end_date:
            queryset = queryset.filter(return_date__lte=end_date)
        
        return queryset.order_by('-return_date', '-id')
    
    def _get_summary(self, queryset):
        """Get purchase return summary"""
        total_count = queryset.count()
        
        # Status counts
        status_counts = queryset.values('status').annotate(
            count=Count('id'),
            total_amount=Sum('return_amount')
        )
        
        # Supplier summary
        supplier_summary = queryset.values('supplier').annotate(
            count=Count('id'),
            total_amount=Sum('return_amount')
        ).order_by('-total_amount')[:10]
        
        return {
            'total_count': total_count,
            'total_amount': queryset.aggregate(total=Sum('return_amount'))['total'] or 0,
            'status_summary': list(status_counts),
            'supplier_summary': list(supplier_summary)
        }

    @action(detail=False, methods=['get'])
    def get_initial_data(self, request):
        """Get initial data for purchase return form"""
        try:
            user = request.user
            # Get products and accounts
            products = Product.objects.filter().values('id', 'name', 'cost_price', 'stock_qty', 'code')
            accounts = Account.objects.filter().values('id', 'name', 'balance', 'account_type')
            
            # Get recent purchases for reference
            recent_purchases = []
            # Uncomment if you have purchases app
            # from purchases.models import Purchase
            # recent_purchases = Purchase.objects.filter().order_by('-purchase_date')[:10].values(
            #     'id', 'invoice_no', 'supplier__name', 'total_amount'
            # )
            
            data = {
                'products': list(products),
                'accounts': list(accounts),
                'recent_purchases': list(recent_purchases),
                'payment_methods': [
                    {'value': 'cash', 'label': 'Cash'},
                    {'value': 'bank', 'label': 'Bank Transfer'},
                    {'value': 'mobile', 'label': 'Mobile Banking'},
                    {'value': 'card', 'label': 'Card'},
                    {'value': 'credit', 'label': 'Credit'}
                ]
            }
            
            return custom_response(
                success=True,
                message="Initial data fetched successfully.",
                data=data,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error in get_initial_data: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def create(self, request, *args, **kwargs):
        try:
            with db_transaction.atomic():
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                instance = serializer.save(
                    created_by=request.user
                )
                
                # Auto-approve if requested
                auto_approve = request.data.get('auto_approve', False)
                if auto_approve:
                    try:
                        instance.approve()
                    except ValidationError as e:
                        return custom_response(
                            success=False,
                            message=f"Created but could not approve: {str(e)}",
                            data=serializer.data,
                            status_code=status.HTTP_201_CREATED
                        )
                
                return custom_response(
                    success=True,
                    message="Purchase return created successfully.",
                    data=self.get_serializer(instance).data,
                    status_code=status.HTTP_201_CREATED
                )
        except serializers.ValidationError as e:
            return custom_response(
                success=False,
                message="Validation Error.",
                data=e.detail,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except ValidationError as e:
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error creating purchase return: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            
            # Only allow update if pending
            if instance.status != 'pending':
                return custom_response(
                    success=False,
                    message=f"Cannot update {instance.status} return",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            with db_transaction.atomic():
                serializer = self.get_serializer(instance, data=request.data, partial=kwargs.get('partial', False))
                serializer.is_valid(raise_exception=True)
                serializer.save()
                
                return custom_response(
                    success=True,
                    message="Purchase return updated successfully.",
                    data=serializer.data,
                    status_code=status.HTTP_200_OK
                )
        except serializers.ValidationError as e:
            return custom_response(
                success=False,
                message="Validation Error.",
                data=e.detail,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error updating purchase return: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            
            # Only allow delete if pending or rejected
            if instance.status not in ['pending', 'rejected']:
                return custom_response(
                    success=False,
                    message=f"Cannot delete {instance.status} return",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            instance.delete()
            return custom_response(
                success=True,
                message="Purchase return deleted successfully.",
                data=None,
                status_code=status.HTTP_204_NO_CONTENT
            )
        except Exception as e:
            logger.error(f"Error deleting purchase return: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # CRITICAL FIX: ADD @action DECORATOR HERE
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a purchase return"""
        try:
            instance = self.get_object()
            
            with db_transaction.atomic():
                instance.approve()
                
                return custom_response(
                    success=True,
                    message="Purchase return approved successfully.",
                    data=self.get_serializer(instance).data,
                    status_code=status.HTTP_200_OK
                )
        except ValidationError as e:
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error approving purchase return: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # CRITICAL FIX: ADD @action DECORATOR HERE
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Mark purchase return as completed"""
        try:
            instance = self.get_object()
            
            with db_transaction.atomic():
                instance.complete()
                
                return custom_response(
                    success=True,
                    message="Purchase return marked as completed.",
                    data=self.get_serializer(instance).data,
                    status_code=status.HTTP_200_OK
                )
        except ValidationError as e:
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error completing purchase return: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # CRITICAL FIX: ADD @action DECORATOR HERE
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a purchase return"""
        try:
            instance = self.get_object()
            
            with db_transaction.atomic():
                instance.reject()
                
                return custom_response(
                    success=True,
                    message="Purchase return rejected successfully.",
                    data=self.get_serializer(instance).data,
                    status_code=status.HTTP_200_OK
                )
        except ValidationError as e:
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error rejecting purchase return: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def get_stats(self, request):
        """Get purchase return statistics"""
        try:
            user = request.user
            # Today's returns
            today = timezone.now().date()
            todays_returns = PurchaseReturn.objects.filter(
                return_date=today
            )
            
            # This month's returns
            month_start = today.replace(day=1)
            this_months_returns = PurchaseReturn.objects.filter(
                return_date__gte=month_start
            )
            
            stats = {
                'today': {
                    'count': todays_returns.count(),
                    'amount': todays_returns.aggregate(total=Sum('return_amount'))['total'] or 0
                },
                'this_month': {
                    'count': this_months_returns.count(),
                    'amount': this_months_returns.aggregate(total=Sum('return_amount'))['total'] or 0
                },
                'by_status': list(PurchaseReturn.objects.filter().values('status').annotate(
                    count=Count('id'),
                    amount=Sum('return_amount')
                ))
            }
            
            return custom_response(
                success=True,
                message="Statistics fetched successfully.",
                data=stats,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class BadStockViewSet(BaseViewSet):
    serializer_class = BadStockSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = BadStock.objects.filter().select_related('product')
        
        # Apply filters
        search = self.request.query_params.get('search', None)
        reference_type = self.request.query_params.get('reference_type', None)
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)
        product_id = self.request.query_params.get('product_id', None)
        
        if search:
            queryset = queryset.filter(
                Q(product__name__icontains=search) |
                Q(reason__icontains=search) |
                Q(product__code__icontains=search)
            )
        
        if reference_type:
            queryset = queryset.filter(reference_type=reference_type)
            
        if product_id:
            queryset = queryset.filter(product_id=product_id)
            
        if start_date and end_date:
            queryset = queryset.filter(date__range=[start_date, end_date])
        elif start_date:
            queryset = queryset.filter(date__gte=start_date)
        elif end_date:
            queryset = queryset.filter(date__lte=end_date)
        
        return queryset.order_by('-date', '-id')
    
    def _get_summary(self, queryset):
        """Get bad stock summary"""
        total_quantity = queryset.aggregate(total=Sum('quantity'))['total'] or 0
        
        # By reference type
        by_reference_type = queryset.values('reference_type').annotate(
            count=Count('id'),
            total_quantity=Sum('quantity')
        )
        
        # By product
        by_product = queryset.values('product__name', 'product__code').annotate(
            count=Count('id'),
            total_quantity=Sum('quantity')
        ).order_by('-total_quantity')[:10]
        
        return {
            'total_count': queryset.count(),
            'total_quantity': total_quantity,
            'by_reference_type': list(by_reference_type),
            'top_products': list(by_product)
        }

    def create(self, request, *args, **kwargs):
        try:
            with db_transaction.atomic():
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                serializer.save()
                
                return custom_response(
                    success=True,
                    message="Bad stock entry created successfully.",
                    data=serializer.data,
                    status_code=status.HTTP_201_CREATED
                )
        except serializers.ValidationError as e:
            return custom_response(
                success=False,
                message="Validation Error.",
                data=e.detail,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error creating bad stock: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            
            with db_transaction.atomic():
                serializer = self.get_serializer(instance, data=request.data, partial=kwargs.get('partial', False))
                serializer.is_valid(raise_exception=True)
                serializer.save()
                
                return custom_response(
                    success=True,
                    message="Bad stock entry updated successfully.",
                    data=serializer.data,
                    status_code=status.HTTP_200_OK
                )
        except serializers.ValidationError as e:
            return custom_response(
                success=False,
                message="Validation Error.",
                data=e.detail,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error updating bad stock: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            instance.delete()
            return custom_response(
                success=True,
                message="Bad stock entry deleted successfully.",
                data=None,
                status_code=status.HTTP_204_NO_CONTENT
            )
        except Exception as e:
            logger.error(f"Error deleting bad stock: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def get_summary(self, request):
        """Get bad stock summary"""
        try:
            user = request.user
            total_bad_stock = BadStock.objects.filter().count()
            total_quantity = BadStock.objects.filter().aggregate(
                total_quantity=Sum('quantity')
            )['total_quantity'] or 0
            
            by_reference_type = BadStock.objects.filter().values(
                'reference_type'
            ).annotate(
                count=Count('id'),
                total_quantity=Sum('quantity')
            )
            
            # Monthly trend
            monthly_trend = BadStock.objects.filter(
                date__gte=timezone.now().date().replace(day=1, month=timezone.now().month-5)
            ).values('date__year', 'date__month').annotate(
                count=Count('id'),
                total_quantity=Sum('quantity')
            ).order_by('date__year', 'date__month')
            
            data = {
                'total_bad_stock': total_bad_stock,
                'total_quantity': total_quantity,
                'by_reference_type': list(by_reference_type),
                'monthly_trend': list(monthly_trend)
            }
            
            return custom_response(
                success=True,
                message="Bad stock summary fetched successfully.",
                data=data,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error getting bad stock summary: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def create_direct(self, request):
        """Create direct bad stock entry (not from return)"""
        try:
            with db_transaction.atomic():
                data = request.data.copy()
                data['reference_type'] = 'direct'
                
                serializer = self.get_serializer(data=data)
                serializer.is_valid(raise_exception=True)
                instance = serializer.save()
                
                # Update product stock (decrease)
                product = instance.product
                if hasattr(product, 'stock_qty'):
                    product.stock_qty -= instance.quantity
                    product.save(update_fields=['stock_qty', 'updated_at'])
                
                return custom_response(
                    success=True,
                    message="Bad stock entry created successfully.",
                    data=serializer.data,
                    status_code=status.HTTP_201_CREATED
                )
        except serializers.ValidationError as e:
            return custom_response(
                success=False,
                message="Validation Error.",
                data=e.detail,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error creating direct bad stock: {e}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )