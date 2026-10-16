# branch_warehouse/views.py
from rest_framework import viewsets, status, permissions, serializers
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from django.db.models import Q
import logging
from core.utils import custom_response
from core.base_viewsets import BaseViewSet
from core.pagination import CustomPageNumberPagination
from .models import Purchase, PurchaseItem
from .serializers import PurchaseSerializer, PurchaseItemSerializer
from suppliers.models import Supplier
from accounts.models import Account  # Added missing import
from django.db import models
from rest_framework import filters
from decimal import Decimal  # Added missing import

logger = logging.getLogger(__name__)


@api_view(['GET'])
def get_due_purchases(request, supplier_id=None):
    """
    Get due purchases for a Supplier
    
    URL patterns:
    - /api/purchase-due/?supplier_id=3
    - /api/purchase-due/3/
    """
    logger.info("Due purchases API called", extra={
        'user': request.user.id,
        'supplier_id': supplier_id,
        'query_params': dict(request.GET)
    })

    # Get supplier_id from URL parameter or query parameter
    supplier_id = supplier_id or request.GET.get('supplier_id')
    due_only = request.GET.get('due', 'true').lower() == 'true'

    if not supplier_id:
        logger.warning("No supplier_id provided")
        return Response({
            "status": False,
            "message": "Supplier ID is required. Use /api/purchase-due/3/ or /api/purchase-due/?supplier_id=3",
            "data": []
        }, status=400)
    
    try:
        # Convert to integer if it's string
        if isinstance(supplier_id, str):
            supplier_id = int(supplier_id)

        # Check if supplier exists
        supplier = Supplier.objects.get(id=supplier_id)
        logger.info(f"Supplier found: {supplier.name} (ID: {supplier.id})")

        # Filter purchases by supplier AND company (multi-tenant)
        queryset = Purchase.objects.filter(
            supplier_id=supplier_id
        )
        
        # If due_only is true, filter only purchases with due amount > 0
        if due_only:
            queryset = queryset.filter(due_amount__gt=0)
        
        # Order by purchase date (oldest first)
        queryset = queryset.order_by('purchase_date')
        
        # Use serializer for consistent data format
        serializer = PurchaseSerializer(queryset, many=True)
        
        logger.info(f"Found {queryset.count()} due purchases for supplier {supplier_id}")
        
        return Response({
            "status": True,
            "message": f"Found {queryset.count()} due purchases for {supplier.name}",
            "data": serializer.data
        })
        
    except ValueError:
        logger.error(f"Invalid supplier_id format: {supplier_id}")
        return Response({
            "status": False,
            "message": "Invalid supplier ID format",
            "data": []
        }, status=400)
    except Supplier.DoesNotExist:
        logger.error(f"Supplier not found with ID: {supplier_id}")
        return Response({
            "status": False,
            "message": f"Supplier with ID {supplier_id} not found",
            "data": []
        }, status=404)
    except Exception as e:
        logger.error(f"Error in get_due_purchases: {str(e)}", exc_info=True)
        return Response({
            "status": False,
            "message": f"Error fetching due purchases: {str(e)}",
            "data": []
        }, status=500)


class PurchaseViewSet(BaseViewSet):
    queryset = Purchase.objects.all().select_related('supplier', 'account')
    serializer_class = PurchaseSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPageNumberPagination
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering_fields = ['purchase_date', 'grand_total', 'due_amount', 'invoice_no', 'created_at']
    search_fields = ['invoice_no', 'supplier__name', 'remark']
    ordering = ['-purchase_date']  # Default: newest first

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({"request": self.request})
        return context

    def get_queryset(self):
        """Apply filters to queryset"""
        queryset = super().get_queryset()
        
        # Get filter parameters
        payment_status = self.request.query_params.get('payment_status')
        supplier_id = self.request.query_params.get('supplier_id')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        invoice_no = self.request.query_params.get('invoice_no')
        search = self.request.query_params.get('search')
        
        # Apply filters
        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)

        # শুধু যেগুলোতে supplier এর কাছে বাকি আছে (বাতিল বাদে)
        if (self.request.query_params.get('due_only') or '').lower() in ('true', '1', 'yes'):
            queryset = queryset.filter(due_amount__gt=0).exclude(payment_status='cancelled')
            
        if supplier_id:
            queryset = queryset.filter(supplier_id=supplier_id)
            
        if start_date and end_date:
            queryset = queryset.filter(purchase_date__range=[start_date, end_date])
        elif start_date:
            queryset = queryset.filter(purchase_date__gte=start_date)
        elif end_date:
            queryset = queryset.filter(purchase_date__lte=end_date)
            
        if invoice_no:
            queryset = queryset.filter(invoice_no__icontains=invoice_no)
        
        # Handle search parameter
        if search:
            queryset = queryset.filter(
                Q(invoice_no__icontains=search) |
                Q(supplier__name__icontains=search) |
                Q(remark__icontains=search)
            )
            
        return queryset

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.filter_queryset(self.get_queryset())
            
            # Check if pagination should be disabled
            no_pagination = request.query_params.get('no_pagination', '').lower() in ['true', '1', 'yes']
            
            if no_pagination:
                serializer = self.get_serializer(queryset, many=True)
                return custom_response(
                    success=True,
                    message=f"Purchases fetched successfully (no pagination). Total: {queryset.count()}",
                    data=serializer.data,
                    status_code=status.HTTP_200_OK
                )
            
            # Apply pagination
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            
            # If no pagination, return all results
            serializer = self.get_serializer(queryset, many=True)
            return custom_response(
                success=True,
                message="Purchases fetched successfully.",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error in purchase list: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return custom_response(
                success=True,
                message="Purchase details fetched successfully.",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error in purchase retrieve: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()
            return custom_response(
                success=True,
                message="Purchase created successfully.",
                data=self.get_serializer(instance).data,
                status_code=status.HTTP_201_CREATED
            )
        except serializers.ValidationError as e:
            logger.warning(f"Purchase validation error: {e.detail}")
            return custom_response(
                success=False,
                message="Validation Error.",
                data=e.detail,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error in purchase create: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        try:
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()
            return custom_response(
                success=True,
                message="Purchase updated successfully.",
                data=self.get_serializer(instance).data,
                status_code=status.HTTP_200_OK
            )
        except serializers.ValidationError as e:
            logger.warning(f"Purchase update validation error: {e.detail}")
            return custom_response(
                success=False,
                message="Validation Error.",
                data=e.detail,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error in purchase update: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            # FIX: আগে সরাসরি delete হত — কেনা stock আর দেওয়া টাকা কোনোটাই ফিরত না।
            # এখন আগে বাতিলের নিয়মে stock ও টাকা উল্টে দিয়ে তারপর মুছে ফেলা হয়।
            from django.db import transaction as db_transaction
            try:
                with db_transaction.atomic():
                    if instance.payment_status != 'cancelled':
                        instance.cancel_purchase('Deleted')
                    instance.delete()
            except ValueError as ve:
                return custom_response(success=False, message=str(ve), data=None,
                                       status_code=status.HTTP_400_BAD_REQUEST)
            return custom_response(
                success=True,
                message="Purchase deleted successfully.",
                data=None,
                status_code=status.HTTP_204_NO_CONTENT
            )
        except Exception as e:
            logger.error(f"Error in purchase delete: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Purchase এর মোট হিসাব — list এর একই filter এ।
        FIX: আগে EXTRACT(...) দিয়ে raw SQL ছিল, যা SQLite এ চলে না — endpoint টা সবসময় 500 দিত।
        এখন TruncMonth (সব database এ চলে)। বাতিল purchase মোট হিসাবে ধরা হয় না
        (শুধু "cancelled" filter দিলে সেগুলোই দেখায়)।
        """
        from django.db.models.functions import TruncMonth
        try:
            queryset = self.filter_queryset(self.get_queryset()).order_by()
            counted = queryset
            if request.query_params.get('payment_status') != 'cancelled':
                counted = queryset.exclude(payment_status='cancelled')

            agg = counted.aggregate(
                n=models.Count('id'),
                amount=models.Sum('grand_total'),
                due=models.Sum('due_amount'),
                paid=models.Sum('paid_amount'),
            )
            status_count = list(queryset.values('payment_status').annotate(
                count=models.Count('id'), amount=models.Sum('grand_total')))
            monthly = [
                {'year': row['m'].year, 'month': row['m'].month, 'count': row['count'], 'total': float(row['total'] or 0)}
                for row in counted.annotate(m=TruncMonth('purchase_date')).values('m')
                .annotate(count=models.Count('id'), total=models.Sum('grand_total')).order_by('-m')[:12]
                if row['m']
            ]
            summary_data = {
                'total_purchases': agg['n'] or 0,
                'total_amount': float(agg['amount'] or 0),
                'total_due': float(agg['due'] or 0),
                'total_paid': float(agg['paid'] or 0),
                'cancelled_count': queryset.filter(payment_status='cancelled').count(),
                'payment_status_breakdown': [
                    {'payment_status': r['payment_status'], 'count': r['count'], 'amount': float(r['amount'] or 0)}
                    for r in status_count
                ],
                'monthly_summary': monthly,
            }
            return custom_response(
                success=True,
                message="Purchase summary fetched successfully.",
                data=summary_data,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error in purchase summary: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def make_payment(self, request, pk=None):
        """Make a payment towards a purchase"""
        try:
            instance = self.get_object()
            amount = request.data.get('amount')
            payment_method = request.data.get('payment_method')
            account_id = request.data.get('account_id')
            
            if not amount or Decimal(amount) <= 0:
                return custom_response(
                    success=False,
                    message="Payment amount must be greater than 0",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            # Get account if provided
            account = None
            if account_id:
                try:
                    account = Account.objects.get(id=account_id)
                except Account.DoesNotExist:
                    return custom_response(
                        success=False,
                        message="Account not found",
                        data=None,
                        status_code=status.HTTP_404_NOT_FOUND
                    )
            
            # Make payment
            instance.make_payment(
                amount=Decimal(amount),
                payment_method=payment_method,
                account=account
            )
            
            return custom_response(
                success=True,
                message="Payment applied successfully",
                data=self.get_serializer(instance).data,
                status_code=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Error making payment: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a purchase"""
        try:
            instance = self.get_object()
            reason = request.data.get('reason', 'No reason provided')
            
            instance.cancel_purchase(reason)
            
            return custom_response(
                success=True,
                message="Purchase cancelled successfully",
                data=self.get_serializer(instance).data,
                status_code=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Error cancelling purchase: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_400_BAD_REQUEST
            )


class PurchaseItemViewSet(BaseViewSet):
    queryset = PurchaseItem.objects.all().select_related('purchase', 'product')
    serializer_class = PurchaseItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """Apply filters to purchase items queryset"""
        queryset = super().get_queryset()
        
        purchase_id = self.request.query_params.get('purchase_id')
        product_id = self.request.query_params.get('product_id')
        
        if purchase_id:
            queryset = queryset.filter(purchase_id=purchase_id)
            
        if product_id:
            queryset = queryset.filter(product_id=product_id)
            
        return queryset.order_by('-purchase__purchase_date', 'id')

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.filter_queryset(self.get_queryset())
            
            # Check if pagination should be disabled
            no_pagination = request.query_params.get('no_pagination', '').lower() in ['true', '1', 'yes']
            
            if no_pagination:
                serializer = self.get_serializer(queryset, many=True)
                return custom_response(
                    success=True,
                    message=f"Purchase items fetched successfully (no pagination). Total: {queryset.count()}",
                    data=serializer.data,
                    status_code=status.HTTP_200_OK
                )
            
            # Apply pagination
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            
            serializer = self.get_serializer(queryset, many=True)
            return custom_response(
                success=True,
                message="Purchase items fetched successfully.",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error in purchase item list: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return custom_response(
                success=True,
                message="Purchase item details fetched successfully.",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error in purchase item retrieve: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def create(self, request, *args, **kwargs):
        """Create a purchase item"""
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()
            return custom_response(
                success=True,
                message="Purchase item created successfully.",
                data=self.get_serializer(instance).data,
                status_code=status.HTTP_201_CREATED
            )
        except serializers.ValidationError as e:
            logger.warning(f"Purchase item validation error: {e.detail}")
            return custom_response(
                success=False,
                message="Validation Error.",
                data=e.detail,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error in purchase item create: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def update(self, request, *args, **kwargs):
        """Update a purchase item"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        try:
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()
            return custom_response(
                success=True,
                message="Purchase item updated successfully.",
                data=self.get_serializer(instance).data,
                status_code=status.HTTP_200_OK
            )
        except serializers.ValidationError as e:
            logger.warning(f"Purchase item update validation error: {e.detail}")
            return custom_response(
                success=False,
                message="Validation Error.",
                data=e.detail,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error in purchase item update: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def destroy(self, request, *args, **kwargs):
        """Delete a purchase item"""
        try:
            instance = self.get_object()
            instance.delete()
            return custom_response(
                success=True,
                message="Purchase item deleted successfully.",
                data=None,
                status_code=status.HTTP_204_NO_CONTENT
            )
        except Exception as e:
            logger.error(f"Error in purchase item delete: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PurchaseAllListViewSet(BaseViewSet):
    queryset = Purchase.objects.all().select_related('supplier', 'account')
    serializer_class = PurchaseSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({"request": self.request})
        return context

    def get_queryset(self):
        """Apply filters to queryset"""
        queryset = super().get_queryset()
        
        # Get filter parameters
        payment_status = self.request.query_params.get('payment_status')
        supplier_id = self.request.query_params.get('supplier_id')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        invoice_no = self.request.query_params.get('invoice_no')
       
        # Apply filters
        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)

        # শুধু যেগুলোতে supplier এর কাছে বাকি আছে (বাতিল বাদে)
        if (self.request.query_params.get('due_only') or '').lower() in ('true', '1', 'yes'):
            queryset = queryset.filter(due_amount__gt=0).exclude(payment_status='cancelled')
            
        if supplier_id:
            queryset = queryset.filter(supplier_id=supplier_id)
            
        if start_date and end_date:
            queryset = queryset.filter(purchase_date__range=[start_date, end_date])
        elif start_date:
            queryset = queryset.filter(purchase_date__gte=start_date)
        elif end_date:
            queryset = queryset.filter(purchase_date__lte=end_date)
            
        if invoice_no:
            queryset = queryset.filter(invoice_no__icontains=invoice_no)
            
        return queryset.order_by('-purchase_date', '-id')

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.filter_queryset(self.get_queryset())
            
            serializer = self.get_serializer(queryset, many=True)
            return custom_response(
                success=True,
                message=f"Purchases fetched successfully. Total: {queryset.count()}",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error in purchase list: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get purchase summary statistics"""
        try:
            queryset = self.filter_queryset(self.get_queryset())
            
            total_purchases = queryset.count()
            total_amount = queryset.aggregate(total=models.Sum('grand_total'))['total'] or 0
            total_due = queryset.aggregate(total=models.Sum('due_amount'))['total'] or 0
            total_paid = queryset.aggregate(total=models.Sum('paid_amount'))['total'] or 0
            
            # Count by payment status
            status_count = queryset.values('payment_status').annotate(
                count=models.Count('id')
            )
            
            summary_data = {
                'total_purchases': total_purchases,
                'total_amount': float(total_amount),
                'total_due': float(total_due),
                'total_paid': float(total_paid),
                'payment_status_breakdown': list(status_count)
            }
            
            return custom_response(
                success=True,
                message="Purchase summary fetched successfully.",
                data=summary_data,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error in purchase summary: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], url_path='supplier/(?P<supplier_id>[^/.]+)')
    def supplier_invoices(self, request, supplier_id=None):
        """Get all invoices for a specific supplier"""
        try:
            if not supplier_id:
                return custom_response(
                    success=False,
                    message="Supplier ID is required",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            # Filter purchases by supplier
            purchases = Purchase.objects.filter(
                supplier_id=supplier_id
            ).select_related('supplier', 'account').order_by('-purchase_date')
            
            serializer = self.get_serializer(purchases, many=True)
            
            return custom_response(
                success=True,
                message=f"Invoices fetched successfully for supplier {supplier_id}",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Error fetching supplier invoices: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], url_path='suppliers-with-invoices')
    def suppliers_with_invoices(self, request):
        """Get all suppliers who have purchases with their invoice counts"""
        try:
            # Get distinct suppliers who have purchases
            suppliers_with_purchases = Purchase.objects.filter().values(
                'supplier_id',
                'supplier__name',
                'supplier__phone',
                'supplier__email'
            ).annotate(
                invoice_count=models.Count('id'),
                total_purchase_amount=models.Sum('grand_total'),
                last_purchase_date=models.Max('purchase_date')
            ).order_by('supplier__name')
            
            supplier_list = []
            for supplier in suppliers_with_purchases:
                supplier_list.append({
                    'id': supplier['supplier_id'],
                    'name': supplier['supplier__name'],
                    'phone': supplier['supplier__phone'],
                    'email': supplier['supplier__email'],
                    'invoice_count': supplier['invoice_count'],
                    'total_purchase_amount': float(supplier['total_purchase_amount'] or 0),
                    'last_purchase_date': supplier['last_purchase_date']
                })
            
            return custom_response(
                success=True,
                message="Suppliers with invoices fetched successfully",
                data=supplier_list,
                status_code=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Error fetching suppliers with invoices: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )