# supplier_payment/views.py
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Q, Sum
from django.core.exceptions import ValidationError
from core.utils import custom_response
from core.pagination import CustomPageNumberPagination
from .serializers import SupplierPaymentSerializer
from .model import SupplierPayment
from purchases.models import Purchase
import logging

logger = logging.getLogger(__name__)

class SupplierPaymentListCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPageNumberPagination

    def get_paginated_response(self, queryset, request, serializer_class, message="Data fetched successfully."):
        """Helper method to handle pagination"""
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        
        if page is not None:
            serializer = serializer_class(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data, message=message)
        
        # If no pagination, return all results
        serializer = serializer_class(queryset, many=True, context={'request': request})
        return custom_response(
            success=True,
            message=message,
            data=serializer.data,
            status_code=status.HTTP_200_OK
        )

    def get_queryset(self):
        """Base queryset"""
        return SupplierPayment.objects.filter() \
                                    .select_related('supplier', 'purchase')

    def apply_filters(self, queryset, request):
        """Apply filters to the queryset"""
        # Filter by supplier
        supplier_id = request.query_params.get('supplier_id')
        if supplier_id:
            queryset = queryset.filter(supplier_id=supplier_id)
            
        # Filter by payment method
        payment_method = request.query_params.get('payment_method')
        if payment_method:
            queryset = queryset.filter(payment_method=payment_method)
            
        # Filter by status
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
            
        # Filter by date range (FIX: আগে দুই তারিখই না দিলে কোনোটাই কাজ করত না)
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(payment_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(payment_date__lte=end_date)

        payment_type = request.query_params.get('payment_type')
        if payment_type:
            queryset = queryset.filter(payment_type=payment_type)
            
        # Search
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(sp_no__icontains=search) |
                Q(supplier__name__icontains=search) |
                Q(supplier__phone__icontains=search) |
                Q(purchase__invoice_no__icontains=search) |
                Q(reference_no__icontains=search)
            )
            
        return queryset

    def get(self, request):
        try:
            # Get base queryset
            queryset = self.get_queryset()
            
            # Apply filters
            queryset = self.apply_filters(queryset, request)
            
            # Return paginated response
            return self.get_paginated_response(
                queryset, 
                request, 
                SupplierPaymentSerializer,
                message="Supplier payments fetched successfully."
            )
            
        except Exception as e:
            logger.error(f"Error fetching supplier payments: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        """Create a new supplier payment with PROPER error handling"""
        try:
            logger.info(f"=== SUPPLIER PAYMENT CREATION DEBUG ===")
            logger.info(f"Raw request data: {request.data}")
            
            # Create a mutable copy of the data
            data = request.data.copy()
            
            # Field mappings
            field_mappings = {
                'account_id': 'account',
                'supplier_id': 'supplier', 
                'seller_id': 'created_by',
                'purchase_id': 'purchase',
            }
            
            for old_field, new_field in field_mappings.items():
                if old_field in data:
                    data[new_field] = data.pop(old_field)
                    logger.info(f"Mapped {old_field} -> {new_field}: {data[new_field]}")
            
            # FIX: app "mobile banking" / "Cash" পাঠায়, অথচ model এর choice হলো cash/bank/cheque/mobile —
            # mobile banking এ payment সবসময় validation error দিত। এখন মিলিয়ে নেওয়া হয়।
            if data.get('payment_method'):
                pm = str(data['payment_method']).strip().lower()
                data['payment_method'] = ('mobile' if 'mobile' in pm or 'bkash' in pm or 'nagad' in pm
                                          else 'cheque' if 'cheque' in pm
                                          else 'bank' if 'bank' in pm
                                          else 'cash')

            # Handle specific_invoice logic
            specific_invoice = data.get('specific_invoice', False)
            invoice_no = data.get('invoice_no')
            
            if specific_invoice and invoice_no:
                try:
                    # Find the purchase by invoice_no
                    purchase = Purchase.objects.get(
                        invoice_no=invoice_no
                    )
                    data['purchase'] = purchase.id
                    logger.info(f"Found purchase for invoice {invoice_no}: {purchase.id}")
                except Purchase.DoesNotExist:
                    logger.warning(f"Purchase not found for invoice: {invoice_no}")
                    return custom_response(
                        success=False,
                        message=f"Purchase with invoice number {invoice_no} not found",
                        data=None,
                        status_code=status.HTTP_400_BAD_REQUEST
                    )
            
            logger.info(f"Final data before serializer: {data}")
            
            # Validate with serializer
            serializer = SupplierPaymentSerializer(data=data, context={'request': request})
            
            if not serializer.is_valid():
                logger.warning(f"Serializer validation errors: {serializer.errors}")
                
                # SUCCESS: PROPER ERROR MESSAGE FORMATTING
                error_message = self._format_validation_errors(serializer.errors)
                
                return custom_response(
                    success=False,
                    message=error_message,
                    data=serializer.errors,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            # SUCCESS: MANUALLY VALIDATE MODEL CONSTRAINTS
            try:
                # Create instance for validation
                payment_instance = SupplierPayment(**serializer.validated_data)
                payment_instance.created_by = request.user
                
                # This triggers model.clean() method
                payment_instance.full_clean()
                
            except ValidationError as e:
                logger.warning(f"Model validation error: {e.message_dict}")
                
                # SUCCESS: FORMAT MODEL VALIDATION ERRORS
                model_error_message = self._format_validation_errors(e.message_dict)
                
                return custom_response(
                    success=False,
                    message=model_error_message,
                    data=e.message_dict,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            # SUCCESS: SAVE THE PAYMENT
            try:
                payment = serializer.save(
                    created_by=request.user
                )
                
                logger.info(f"SUCCESS: Supplier payment created successfully: {payment.sp_no}")
                logger.info(f"💰 Payment amount: {payment.amount}, Status: {payment.status}")
                logger.info("=== SUPPLIER PAYMENT CREATION COMPLETE ===")
                
                return custom_response(
                    success=True,
                    message="Supplier payment created successfully",
                    data=SupplierPaymentSerializer(payment, context={'request': request}).data,
                    status_code=status.HTTP_201_CREATED
                )
                
            except Exception as save_error:
                logger.error(f"Error during payment save: {str(save_error)}", exc_info=True)
                return custom_response(
                    success=False,
                    message=f"Error saving payment: {str(save_error)}",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
        except Exception as e:
            logger.error(f"Unexpected error creating supplier payment: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error occurred",
                data={"debug_info": str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _format_validation_errors(self, errors):
        """Convert validation errors dictionary to user-friendly string message"""
        if not errors:
            return "Validation error occurred"
        
        error_messages = []
        
        for field, field_errors in errors.items():
            if isinstance(field_errors, list):
                # Handle list of errors for a field
                for error in field_errors:
                    if field == 'non_field_errors':
                        error_messages.append(str(error))
                    else:
                        # Convert field name to readable format
                        readable_field = self._get_field_display_name(field)
                        error_messages.append(f"{readable_field}: {error}")
            elif isinstance(field_errors, dict):
                # Handle nested errors
                for nested_field, nested_errors in field_errors.items():
                    readable_field = self._get_field_display_name(f"{field}.{nested_field}")
                    if isinstance(nested_errors, list):
                        for nested_error in nested_errors:
                            error_messages.append(f"{readable_field}: {nested_error}")
                    else:
                        error_messages.append(f"{readable_field}: {nested_errors}")
            else:
                # Handle single error string
                readable_field = self._get_field_display_name(field)
                error_messages.append(f"{readable_field}: {field_errors}")
        
        # Join all error messages
        if error_messages:
            return " • ".join(error_messages)
        else:
            return "Please check your input and try again"

    def _get_field_display_name(self, field_name):
        """Convert field names to user-friendly display names"""
        field_display_names = {
            'account': 'Payment Account',
            'supplier': 'Supplier',
            'amount': 'Payment Amount',
            'payment_date': 'Payment Date',
            'payment_method': 'Payment Method',
            'created_by': 'Prepared By',
            'purchase': 'Purchase Invoice',
            'reference_no': 'Reference Number',
            'description': 'Description',
            'use_advance': 'Use Advance',
            'advance_amount_used': 'Advance Amount Used',
        }
        
        return field_display_names.get(field_name, field_name.replace('_', ' ').title())


class SupplierPaymentDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk):
        """Get supplier payment object"""
        try:
            return SupplierPayment.objects.get(pk=pk)
        except SupplierPayment.DoesNotExist:
            return None

    def get(self, request, pk):
        try:
            payment = self.get_object(pk)
            if not payment:
                logger.warning(f"Supplier payment not found: {pk}")
                return custom_response(
                    success=False,
                    message="Supplier payment not found.",
                    data=None,
                    status_code=status.HTTP_404_NOT_FOUND
                )
            
            serializer = SupplierPaymentSerializer(payment, context={'request': request})
            return custom_response(
                success=True,
                message="Supplier payment fetched successfully.",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error fetching supplier payment {pk}: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def put(self, request, pk):
        try:
            payment = self.get_object(pk)
            if not payment:
                logger.warning(f"Supplier payment not found for update: {pk}")
                return custom_response(
                    success=False,
                    message="Supplier payment not found.",
                    data=None,
                    status_code=status.HTTP_404_NOT_FOUND
                )
            
            data = request.data.copy()
            
            # Convert amount to decimal if it's string
            if 'amount' in data and isinstance(data['amount'], str):
                try:
                    data['amount'] = float(data['amount'])
                except ValueError:
                    logger.warning(f"Invalid amount format in update: {data['amount']}")
                    return custom_response(
                        success=False,
                        message="Invalid amount format",
                        data=None,
                        status_code=status.HTTP_400_BAD_REQUEST
                    )
            
            serializer = SupplierPaymentSerializer(
                payment, 
                data=data, 
                context={'request': request},
                partial=True
            )
            
            if serializer.is_valid():
                # Validate model constraints for update
                try:
                    update_instance = SupplierPayment(**serializer.validated_data)
                    update_instance.id = payment.id
                    update_instance.full_clean()
                except ValidationError as e:
                    error_message = self._format_validation_errors(e.message_dict)
                    return custom_response(
                        success=False,
                        message=error_message,
                        data=e.message_dict,
                        status_code=status.HTTP_400_BAD_REQUEST
                    )
                
                instance = serializer.save()
                logger.info(f"Supplier payment updated successfully: {instance.id}")
                
                return custom_response(
                    success=True,
                    message="Supplier payment updated successfully.",
                    data=SupplierPaymentSerializer(instance, context={'request': request}).data,
                    status_code=status.HTTP_200_OK
                )
            else:
                logger.warning(f"Supplier payment update validation errors: {serializer.errors}")
                error_message = self._format_validation_errors(serializer.errors)
                return custom_response(
                    success=False,
                    message=error_message,
                    data=serializer.errors,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            logger.error(f"Error updating supplier payment {pk}: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def delete(self, request, pk):
        try:
            payment = self.get_object(pk)
            if not payment:
                logger.warning(f"Supplier payment not found for deletion: {pk}")
                return custom_response(
                    success=False,
                    message="Supplier payment not found.",
                    data=None,
                    status_code=status.HTTP_404_NOT_FOUND
                )
            
            payment_id = payment.id
            sp_no = payment.sp_no
            # FIX: আগে সরাসরি মুছে যেত — supplier এর invoice "paid" থেকে যেত আর account এর টাকাও ফিরত না।
            # এখন আগে সব উল্টে দিয়ে তারপর মোছা হয়।
            from django.db import transaction as db_transaction
            try:
                with db_transaction.atomic():
                    if payment.status == 'completed':
                        payment.cancel_payment('Deleted')
                    payment.delete()
            except ValidationError as ve:
                return custom_response(success=False, message='; '.join(ve.messages), data=None,
                                       status_code=status.HTTP_400_BAD_REQUEST)
            logger.info(f"Supplier payment deleted successfully: {sp_no} (ID: {payment_id})")
            
            return custom_response(
                success=True,
                message="Supplier payment deleted successfully.",
                data=None,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error deleting supplier payment {pk}: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _format_validation_errors(self, errors):
        """Helper method to format validation errors (same as above)"""
        if not errors:
            return "Validation error occurred"
        
        error_messages = []
        
        for field, field_errors in errors.items():
            if isinstance(field_errors, list):
                for error in field_errors:
                    if field == 'non_field_errors':
                        error_messages.append(str(error))
                    else:
                        readable_field = field.replace('_', ' ').title()
                        error_messages.append(f"{readable_field}: {error}")
            else:
                readable_field = field.replace('_', ' ').title()
                error_messages.append(f"{readable_field}: {field_errors}")
        
        return " • ".join(error_messages) if error_messages else "Validation error occurred"


class SupplierPaymentCancelAPIView(APIView):
    """POST /api/supplier-payments/<pk>/cancel/ — সব উল্টে দিয়ে payment "cancelled" করে (record থেকে যায়)"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        payment = SupplierPayment.objects.filter(pk=pk).first()
        if not payment:
            return custom_response(success=False, message="Supplier payment not found.", data=None,
                                   status_code=status.HTTP_404_NOT_FOUND)
        try:
            payment.cancel_payment(request.data.get('reason'))
        except ValidationError as ve:
            return custom_response(success=False, message='; '.join(ve.messages), data=None,
                                   status_code=status.HTTP_400_BAD_REQUEST)
        payment.refresh_from_db()
        return custom_response(success=True, message="Supplier payment cancelled. Everything it changed was reversed.",
                               data=SupplierPaymentSerializer(payment, context={'request': request}).data,
                               status_code=status.HTTP_200_OK)


class SupplierPaymentSummaryAPIView(SupplierPaymentListCreateAPIView):
    """GET /api/supplier-payments/summary/ — list এর একই filter এ মোট (বাতিল বাদে)"""

    def get(self, request):
        from django.db.models import Count
        qs = self.apply_filters(self.get_queryset(), request).order_by()
        counted = qs if request.query_params.get('status') == 'cancelled' else qs.exclude(status='cancelled')
        agg = counted.aggregate(n=Count('id'), amount=Sum('amount'), adv=Sum('advance_amount_used'))
        by_method = [{'method': r['payment_method'], 'count': r['n'], 'amount': float(r['amount'] or 0)}
                     for r in counted.values('payment_method').annotate(n=Count('id'), amount=Sum('amount')).order_by('-amount')]
        return custom_response(success=True, message="Supplier payment summary.", data={
            'total_payments': agg['n'] or 0,
            'total_amount': float(agg['amount'] or 0),
            'advance_used': float(agg['adv'] or 0),
            'cash_paid': float((agg['amount'] or 0) - (agg['adv'] or 0)),
            'cancelled_count': qs.filter(status='cancelled').count(),
            'by_method': by_method,
        }, status_code=status.HTTP_200_OK)
