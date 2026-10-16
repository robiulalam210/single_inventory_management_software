from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Q
from core.utils import custom_response
from core.pagination import CustomPageNumberPagination
from .serializers import MoneyReceiptSerializer
from .models import MoneyReceipt
import logging
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

class MoneyReceiptCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """Base queryset """
        user = self.request.user
        queryset = MoneyReceipt.objects.filter()
        
        # SAFE select_related - only include essential relationships
        try:
            queryset = queryset.select_related(
                'customer', 'seller'
            )
            # Use prefetch_related for optional relationships
            queryset = queryset.prefetch_related('sale', 'account')
        except Exception as e:
            logger.warning(f"Error in select_related: {e}. Using minimal queryset.")
        
        return queryset

    def apply_filters(self, queryset, request):
        """Apply filters to the queryset"""
        params = request.GET
        
        # Date range filtering
        # FIX: payment_date একটা DateTimeField — আগে end_date="2026-10-08" মানে রাত ১২টা ধরা হত,
        # তাই শেষ দিনের সব receipt বাদ পড়ত। এখন তারিখ (date) দিয়ে তুলনা — শেষ দিনও পুরোটা আসে।
        start_date = params.get('start_date')
        end_date = params.get('end_date')
        if start_date:
            queryset = queryset.filter(payment_date__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(payment_date__date__lte=end_date)

        # Customer filtering
        # FIX: app পাঠায় ?customer= / ?seller= — আগে শুধু customer_id বোঝা হত, তাই app এর
        # customer/seller filter কাজই করত না। এখন দুই নামই চলে।
        customer_id = params.get('customer_id') or params.get('customer')
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)

        # Collected by (seller) filtering
        seller_id = params.get('seller_id') or params.get('seller')
        if seller_id:
            queryset = queryset.filter(seller_id=seller_id)

        # Payment type filtering
        payment_type = params.get('payment_type')
        if payment_type:
            queryset = queryset.filter(payment_type=payment_type)

        # Payment method filtering
        payment_method = params.get('payment_method')
        if payment_method:
            queryset = queryset.filter(payment_method__iexact=payment_method)

        # Payment status filtering
        payment_status = params.get('payment_status')
        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)

        # Search filtering
        # FIX: আগে দুইটা filter পরপর (AND) ছিল — "MR-1002" খুঁজলে customer এর নামেও
        # "MR-1002" থাকতে হত, তাই প্রায় কিছুই পাওয়া যেত না। এখন যেকোনো একটায় মিললেই হবে (OR)।
        search = (params.get('search') or '').strip()
        if search:
            queryset = queryset.filter(
                Q(mr_no__icontains=search) |
                Q(remark__icontains=search) |
                Q(payment_method__icontains=search) |
                Q(customer__name__icontains=search) |
                Q(customer__phone__icontains=search) |
                Q(sale__invoice_no__icontains=search) |
                Q(sale_invoice_no__icontains=search)
            )

        # Order by
        order_by = params.get('order_by', '-payment_date')
        valid_order_fields = ['payment_date', 'amount', 'created_at', 'mr_no', 'id']
        
        # Remove - prefix to check field
        order_field = order_by.lstrip('-')
        if order_field in valid_order_fields:
            try:
                queryset = queryset.order_by(order_by)
            except Exception as e:
                logger.warning(f"Error ordering by {order_by}: {e}")
                queryset = queryset.order_by('-payment_date')
        else:
            queryset = queryset.order_by('-payment_date')

        return queryset

    def get(self, request):
        """Get money receipts with filtering - FIXED VERSION"""
        try:
            
            # Get base queryset
            queryset = self.get_queryset()
            logger.info(f"Initial queryset count: {queryset.count()}")
            
            # Apply filters
            filtered_queryset = self.apply_filters(queryset, request)
            logger.info(f"After filtering count: {filtered_queryset.count()}")
            
            # Handle pagination
            paginator = self.pagination_class()
            page = paginator.paginate_queryset(filtered_queryset, request, view=self)
            
            if page is not None:
                try:
                    serializer = MoneyReceiptSerializer(page, many=True, context={'request': request})
                    return paginator.get_paginated_response(serializer.data, message="Money receipts fetched successfully.")
                except Exception as serializer_error:
                    logger.error(f"Serializer error: {serializer_error}", exc_info=True)
                    
                    # Fallback to simple data
                    simple_data = []
                    for receipt in page:
                        simple_data.append({
                            'id': receipt.id,
                            'mr_no': receipt.mr_no,
                            'amount': float(receipt.amount),
                            'payment_date': receipt.payment_date,
                            'customer_name': receipt.customer.name if receipt.customer else None,
                            'payment_method': receipt.payment_method,
                            'payment_status': receipt.payment_status
                        })
                    
                    return paginator.get_paginated_response(simple_data, message="Money receipts fetched (simplified).")
            
            # Non-paginated response
            try:
                serializer = MoneyReceiptSerializer(filtered_queryset, many=True, context={'request': request})
                return custom_response(
                    success=True,
                    message=f"Found {filtered_queryset.count()} money receipts",
                    data=serializer.data,
                    status_code=status.HTTP_200_OK
                )
            except Exception as serializer_error:
                logger.error(f"Non-paginated serializer error: {serializer_error}")
                # Return minimal data
                minimal_data = list(filtered_queryset.values(
                    'id', 'mr_no', 'amount', 'payment_date', 'payment_method', 'payment_status'
                ))
                return custom_response(
                    success=True,
                    message=f"Found {filtered_queryset.count()} money receipts (minimal data)",
                    data=minimal_data,
                    status_code=status.HTTP_200_OK
                )
            
        except Exception as e:
            logger.error(f"Error fetching money receipts: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=f"An error occurred while fetching money receipts: {str(e)}",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        """Create new money receipt - FIXED VERSION"""
        try:
            logger.info("Creating money receipt", extra={
                'user': request.user.username,
                'data_keys': list(request.data.keys())
            })
            # Prepare data
            data = request.data.copy()
            logger.info(f"Received data: {data}")
            
            # Validate required fields
            required_fields = ['amount', 'payment_date', 'payment_method']
            missing_fields = [field for field in required_fields if field not in data or data[field] in [None, '']]
            
            if missing_fields:
                return custom_response(
                    success=False,
                    message=f"Missing required fields: {', '.join(missing_fields)}",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate amount
            try:
                amount = Decimal(str(data['amount']))
                if amount <= 0:
                    return custom_response(
                        success=False,
                        message="Amount must be greater than 0.",
                        data=None,
                        status_code=status.HTTP_400_BAD_REQUEST
                    )
            except (ValueError, TypeError):
                return custom_response(
                    success=False,
                    message="Invalid amount format.",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            # Create serializer with context
            serializer = MoneyReceiptSerializer(data=data, context={'request': request})
            
            if serializer.is_valid():
                try:
                    receipt = serializer.save()
                    logger.info(f"Money receipt created successfully: {receipt.mr_no}")
                    
                    # Return full receipt data
                    response_serializer = MoneyReceiptSerializer(receipt, context={'request': request})
                    return custom_response(
                        success=True,
                        message="Money receipt created successfully.",
                        data=response_serializer.data,
                        status_code=status.HTTP_201_CREATED
                    )
                except DjangoValidationError as ve:
                    return custom_response(
                        success=False,
                        message="; ".join(ve.messages),
                        data=None,
                        status_code=status.HTTP_400_BAD_REQUEST
                    )
                except serializers.ValidationError as ve:
                    return custom_response(
                        success=False,
                        message="Validation error occurred.",
                        data=ve.detail,
                        status_code=status.HTTP_400_BAD_REQUEST
                    )
                except Exception as save_error:
                    logger.error(f"Error saving money receipt: {save_error}", exc_info=True)
                    return custom_response(
                        success=False,
                        message=f"Error saving money receipt: {str(save_error)}",
                        data=None,
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            else:
                logger.warning(f"Money receipt validation errors: {serializer.errors}")
                return custom_response(
                    success=False,
                    message="Validation error occurred.",
                    data=serializer.errors,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            logger.error(f"Error creating money receipt: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=f"An error occurred while creating money receipt: {str(e)}",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MoneyReceiptSummaryAPIView(MoneyReceiptCreateAPIView):
    """
    /api/money-receipts/summary/ — list এর একই filter এ মোট হিসাব (তালিকা page ধরে নয়, পুরো filter এর)।
    web app এর totals bar এটা দেখায়; list API এর filter হুবহু একই, তাই সংখ্যা সবসময় মেলে।
    """

    def get(self, request):
        from django.db.models import Sum, Count
        qs = self.apply_filters(self.get_queryset(), request).order_by()
        total = qs.aggregate(n=Count('id'), amount=Sum('amount'))
        by_type = {row['payment_type']: {'count': row['n'], 'amount': float(row['amount'] or 0)}
                   for row in qs.values('payment_type').annotate(n=Count('id'), amount=Sum('amount'))}
        by_method = [{'method': row['payment_method'] or '—', 'count': row['n'], 'amount': float(row['amount'] or 0)}
                     for row in qs.values('payment_method').annotate(n=Count('id'), amount=Sum('amount')).order_by('-amount')]
        return custom_response(
            success=True,
            message="Money receipt summary.",
            data={
                'total_receipts': total['n'] or 0,
                'total_amount': float(total['amount'] or 0),
                'by_type': by_type,
                'by_method': by_method,
            },
            status_code=status.HTTP_200_OK,
        )


class MoneyReceiptDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, receipt_id):
        """Get money receipt object"""
        try:
            return MoneyReceipt.objects.filter(
                id=receipt_id
            ).select_related('customer').first()
        except Exception as e:
            logger.error(f"Error getting money receipt {receipt_id}: {e}")
            return None

    def get(self, request, receipt_id):
        """Get money receipt details - FIXED"""
        try:
            receipt = self.get_object(receipt_id)
            if not receipt:
                return custom_response(
                    success=False,
                    message="Money receipt not found.",
                    data=None,
                    status_code=status.HTTP_404_NOT_FOUND
                )
            
            serializer = MoneyReceiptSerializer(receipt, context={'request': request})
            return custom_response(
                success=True,
                message="Money receipt fetched successfully.",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Error fetching money receipt {receipt_id}: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=f"An error occurred while fetching money receipt: {str(e)}",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def put(self, request, receipt_id):
        """Update money receipt - FIXED"""
        try:
            receipt = self.get_object(receipt_id)
            if not receipt:
                return custom_response(
                    success=False,
                    message="Money receipt not found.",
                    data=None,
                    status_code=status.HTTP_404_NOT_FOUND
                )
            
            data = request.data.copy()
            
            # Remove immutable fields
            immutable_fields = ['mr_no', 'created_at', 'updated_at']
            for field in immutable_fields:
                if field in data:
                    del data[field]
            
            serializer = MoneyReceiptSerializer(
                receipt, 
                data=data, 
                context={'request': request},
                partial=True
            )
            
            if serializer.is_valid():
                try:
                    updated_receipt = serializer.save()
                    logger.info(f"Money receipt updated: {updated_receipt.mr_no}")
                    
                    return custom_response(
                        success=True,
                        message="Money receipt updated successfully.",
                        data=MoneyReceiptSerializer(updated_receipt, context={'request': request}).data,
                        status_code=status.HTTP_200_OK
                    )
                except Exception as save_error:
                    logger.error(f"Error saving updated money receipt: {save_error}")
                    return custom_response(
                        success=False,
                        message=f"Error saving updates: {str(save_error)}",
                        data=None,
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            else:
                logger.warning(f"Money receipt update validation errors: {serializer.errors}")
                return custom_response(
                    success=False,
                    message="Validation error occurred.",
                    data=serializer.errors,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            logger.error(f"Error updating money receipt {receipt_id}: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=f"An error occurred while updating money receipt: {str(e)}",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def delete(self, request, receipt_id):
        """Delete money receipt - FIXED"""
        try:
            receipt = self.get_object(receipt_id)
            if not receipt:
                return custom_response(
                    success=False,
                    message="Money receipt not found.",
                    data=None,
                    status_code=status.HTTP_404_NOT_FOUND
                )
            
            mr_no = receipt.mr_no
            try:
                receipt.reverse_and_delete()  # sale paid / advance / account সব উল্টে দেয়
            except DjangoValidationError as ve:
                return custom_response(
                    success=False,
                    message="; ".join(ve.messages),
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            logger.info(f"Money receipt deleted: {mr_no}")
            
            return custom_response(
                success=True,
                message="Money receipt deleted successfully.",
                data=None,
                status_code=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Error deleting money receipt {receipt_id}: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=f"An error occurred while deleting money receipt: {str(e)}",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )