import logging
from rest_framework import viewsets, status, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count, Sum, F, Case, When, Value, DecimalField
from core.utils import custom_response
from core.pagination import CustomPageNumberPagination
from .models import Customer
from .serializers import CustomerSerializer
from decimal import Decimal
from rest_framework.exceptions import PermissionDenied, NotFound
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
logger = logging.getLogger(__name__)



class CustomerViewSet(viewsets.ModelViewSet):
    """
    Customer ViewSet with complete company-based isolation
    """
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    search_fields = ['name', 'phone', 'email', 'address']
    filterset_fields = ['is_active', 'special_customer']
    ordering_fields = ['name', 'client_no', 'date_created', 'special_customer', 
                      'net_due_amount', 'advance_balance']
    ordering = ['client_no']

    def get_queryset(self):
        """
        Base queryset filtered by company
        """
        user = self.request.user
        return Customer.objects.filter()

    def _get_optimized_queryset(self):
        """
        Get queryset with optimized annotations for list/detail views
        """
        queryset = self.get_queryset()
        
        # Only apply expensive annotations for list/detail actions
        if self.action in ['list', 'retrieve', 'summary', 'special_summary']:
            queryset = queryset.annotate(
                sales_count=Count('sale', distinct=True),
                total_paid_amount=Sum('sale__paid_amount'),
                total_grand_total=Sum('sale__grand_total'),
                basic_due_amount=Case(
                    When(
                        total_grand_total__isnull=True,
                        then=Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
                    ),
                    default=F('total_grand_total') - F('total_paid_amount'),
                    output_field=DecimalField(max_digits=12, decimal_places=2)
                ),
                net_due_amount=Case(
                    When(
                        advance_balance__gte=F('total_grand_total') - F('total_paid_amount'),
                        then=Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
                    ),
                    default=F('total_grand_total') - F('total_paid_amount') - F('advance_balance'),
                    output_field=DecimalField(max_digits=12, decimal_places=2)
                ),
                remaining_advance=Case(
                    When(
                        advance_balance__gt=F('total_grand_total') - F('total_paid_amount'),
                        then=F('advance_balance') - (F('total_grand_total') - F('total_paid_amount'))
                    ),
                    default=Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
                )
            )
        
        return queryset

    def get_object(self):
        """
        Secure object retrieval with company check
        """
        try:
            # Use base queryset without annotations for performance
            queryset = self.get_queryset()
            
            # Perform the lookup filtering
            lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
            filter_kwargs = {self.lookup_field: self.kwargs[lookup_url_kwarg]}
            obj = queryset.get(**filter_kwargs)
            
            # Check permissions
            self.check_object_permissions(self.request, obj)
            
            return obj
            
        except Customer.DoesNotExist:
            raise NotFound("Customer not found")
        except Exception as e:
            logger.error(f"Error retrieving customer: {str(e)}")
            raise

    def filter_queryset(self, queryset):
        """
        Apply all filters including custom filters
        """
        # Apply DRF filters first
        for backend in list(self.filter_backends):
            queryset = backend().filter_queryset(self.request, queryset, self)
        
        # Apply custom filters
        queryset = self._apply_custom_filters(queryset)
        
        return queryset

    def _apply_custom_filters(self, queryset):
        """
        Apply additional custom filters not covered by DjangoFilterBackend
        """
        params = self.request.GET
        
        # Amount type filter (advance/due/paid) - only for list views
        # FIX: আগে sale এর সাথে join করে প্রতিটা sale ধরে তুলনা হত — ফলে "due" এ একই customer অনেকবার আসত
        # (যতগুলো বাকি invoice, ততবার), আর "paid" এ বাকি থাকা customer ও চলে আসত।
        # এখন প্রতি customer এর মোট বাকি একটা subquery দিয়ে, একবারই।
        amount_type = params.get('amount_type')
        if amount_type and self.action == 'list':
            from django.db.models import OuterRef, Subquery
            from django.db.models.functions import Coalesce
            from sales.models import Sale
            due_sub = (Sale.objects.filter(customer=OuterRef('pk'))
                       .values('customer').annotate(s=Sum('due_amount')).values('s')[:1])
            zero = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
            queryset = queryset.annotate(
                _sales_due=Coalesce(Subquery(due_sub, output_field=DecimalField(max_digits=12, decimal_places=2)), zero))
            amount_type = amount_type.lower()
            if amount_type == 'advance':
                queryset = queryset.filter(advance_balance__gt=0)
            elif amount_type == 'due':
                queryset = queryset.filter(_sales_due__gt=F('advance_balance'))
            elif amount_type == 'paid':
                queryset = queryset.filter(_sales_due=0, advance_balance=0)

        # Date range filter
        start_date = params.get('start_date')
        end_date = params.get('end_date')
        if start_date and end_date:
            queryset = queryset.filter(date_created__date__range=[start_date, end_date])
        
        return queryset

    def list(self, request, *args, **kwargs):
        """
        List customers with optimized queryset
        """
        try:
            # Use optimized queryset with annotations
            queryset = self._get_optimized_queryset()
            queryset = self.filter_queryset(queryset)
            
            # Apply pagination
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            
            # If no pagination, return all results
            serializer = self.get_serializer(queryset, many=True)
            return custom_response(
                success=True,
                message=f"Found {queryset.count()} customers",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Error in CustomerViewSet list: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Error fetching customers",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def retrieve(self, request, *args, **kwargs):
        """
        Get single customer with detailed information
        """
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return custom_response(
                success=True,
                message="Customer details fetched successfully",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )
        except NotFound:
            return custom_response(
                success=False,
                message="Customer not found",
                data=None,
                status_code=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error retrieving customer: {str(e)}")
            return custom_response(
                success=False,
                message="Error fetching customer details",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def create(self, request, *args, **kwargs):
        """
        Create a new customer with company validation
        """
        from rest_framework import serializers
        
        with transaction.atomic():
            serializer = self.get_serializer(data=request.data)
            try:
                serializer.is_valid(raise_exception=True)
                
                # Get user's company
                user = request.user
                # Check for duplicate phone number in same company
                phone = serializer.validated_data.get('phone')
                if phone and Customer.objects.filter(phone=phone).exists():
                    return custom_response(
                        success=False,
                        message="A customer with this phone number already exists in your company",
                        data=None,
                        status_code=status.HTTP_400_BAD_REQUEST
                    )

                # Create customer
                instance = serializer.save(
                    created_by=user
                )
                
                logger.info(f"Customer created: {instance.name} (ID: {instance.id}) by user {user.username}")
                
                return custom_response(
                    success=True,
                    message="Customer created successfully",
                    data=self.get_serializer(instance).data,
                    status_code=status.HTTP_201_CREATED
                )
                
            except serializers.ValidationError as e:
                # Extract first error message
                if isinstance(e.detail, dict):
                    first_field = next(iter(e.detail.values()))
                    if isinstance(first_field, list):
                        message = str(first_field[0])
                    else:
                        message = str(first_field)
                else:
                    message = str(e.detail)
                
                return custom_response(
                    success=False,
                    message=message,
                    data=e.detail,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            except Exception as e:
                logger.error(f"Error creating customer: {str(e)}", exc_info=True)
                return custom_response(
                    success=False,
                    message="Error creating customer",
                    data=None,
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

    def update(self, request, *args, **kwargs):
        """
        Update customer with company validation
        """
        with transaction.atomic():
            try:
                instance = self.get_object()
                serializer = self.get_serializer(instance, data=request.data, partial=True)
                serializer.is_valid(raise_exception=True)
                
                # Check for duplicate phone number (excluding current instance)
                phone = serializer.validated_data.get('phone')
                if phone:
                    if Customer.objects.filter(
                        phone=phone
                    ).exclude(id=instance.id).exists():
                        return custom_response(
                            success=False,
                            message="A customer with this phone number already exists",
                            data=None,
                            status_code=status.HTTP_400_BAD_REQUEST
                        )
                
                # Update customer
                self.perform_update(serializer)
                
                logger.info(f"Customer updated: {instance.name} (ID: {instance.id}) by user {request.user.username}")
                
                return custom_response(
                    success=True,
                    message="Customer updated successfully",
                    data=serializer.data,
                    status_code=status.HTTP_200_OK
                )
                
            except NotFound:
                return custom_response(
                    success=False,
                    message="Customer not found",
                    data=None,
                    status_code=status.HTTP_404_NOT_FOUND
                )
            except Exception as e:
                logger.error(f"Error updating customer: {str(e)}", exc_info=True)
                return custom_response(
                    success=False,
                    message="Error updating customer",
                    data=None,
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

    def destroy(self, request, *args, **kwargs):
        """
        Delete or deactivate customer
        """
        try:
            instance = self.get_object()
            customer_name = instance.name
            
            # Check for related records
            has_related = False
            blocking_relationships = []
            
            # Check sales
            try:
                from sales.models import Sale
                sales_count = Sale.objects.filter(customer=instance).count()
                if sales_count > 0:
                    has_related = True
                    blocking_relationships.append(f"{sales_count} sales")
            except ImportError:
                pass
            
            # Check money receipts
            try:
                from money_receipts.models import MoneyReceipt
                receipts_count = MoneyReceipt.objects.filter(customer=instance).count()
                if receipts_count > 0:
                    has_related = True
                    blocking_relationships.append(f"{receipts_count} money receipts")
            except ImportError:
                pass
            
            if has_related:
                # Deactivate instead of delete
                instance.is_active = False
                instance.save(update_fields=['is_active'])
                
                message = f"Customer has related records ({', '.join(blocking_relationships)}). Marked as inactive."
                
                logger.info(f"Customer deactivated: {customer_name} (ID: {instance.id}) due to related records")
                
                return custom_response(
                    success=True,
                    message=message,
                    data={
                        'customer_id': instance.id,
                        'customer_name': customer_name,
                        'is_active': False,
                        'action': 'deactivated'
                    },
                    status_code=status.HTTP_200_OK
                )
            else:
                # Delete the customer
                self.perform_destroy(instance)
                
                logger.info(f"Customer deleted: {customer_name} (ID: {instance.id})")
                
                return custom_response(
                    success=True,
                    message=f"Customer '{customer_name}' deleted successfully",
                    data={
                        'customer_id': instance.id,
                        'customer_name': customer_name,
                        'action': 'deleted'
                    },
                    status_code=status.HTTP_200_OK
                )
                
        except NotFound:
            return custom_response(
                success=False,
                message="Customer not found",
                data=None,
                status_code=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error deleting customer: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Error deleting customer",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # Custom actions with proper company filtering
    # All detail=True actions automatically get company check via get_object()
    
    @action(detail=True, methods=['get'])
    def payment_details(self, request, pk=None):
        """Get detailed payment information for a customer"""
        try:
            customer = self.get_object()
            breakdown = customer.get_detailed_payment_breakdown()
            
            return custom_response(
                success=True,
                message="Payment details fetched successfully",
                data=breakdown,
                status_code=status.HTTP_200_OK
            )
        except NotFound:
            return custom_response(
                success=False,
                message="Customer not found",
                data=None,
                status_code=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error fetching payment details: {str(e)}")
            return custom_response(
                success=False,
                message="Error fetching payment details",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get summary of all customers' payment status"""
        try:
            queryset = self._get_optimized_queryset()
            queryset = self.filter_queryset(queryset)
            
            # Calculate summary from annotations
            summary_data = queryset.aggregate(
                total_customers=Count('id'),
                total_advance=Sum('advance_balance'),
                total_net_due=Sum('net_due_amount'),
                total_paid=Sum('total_paid_amount'),
                total_grand=Sum('total_grand_total')
            )
            
            # Count by status using annotations
            advance_count = queryset.filter(advance_balance__gt=0).count()
            due_count = queryset.filter(net_due_amount__gt=0).count()
            paid_count = queryset.filter(net_due_amount=0, advance_balance=0).count()
            
            summary = {
                'total_customers': summary_data['total_customers'],
                'financial_summary': {
                    'total_advance': float(summary_data['total_advance'] or 0),
                    'total_due': float(summary_data['total_net_due'] or 0),
                    'total_paid': float(summary_data['total_paid'] or 0),
                    'total_sales': float(summary_data['total_grand'] or 0)
                },
                'status_counts': {
                    'advance_customers': advance_count,
                    'due_customers': due_count,
                    'paid_customers': paid_count
                }
            }
            
            return custom_response(
                success=True,
                message="Customer summary fetched successfully",
                data=summary,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error fetching customer summary: {str(e)}")
            return custom_response(
                success=False,
                message="Error fetching customer summary",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
class CustomerNonPaginationViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    pagination_class = None
    
    search_fields = ['name', 'phone', 'email', 'address']
    ordering_fields = ['name', 'date_created', 'special_customer']
    ordering = ['name']

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by company only (no active/inactive filter)
        user = self.request.user
        if user.is_authenticated:
            queryset = queryset.filter()
        else:
            return Customer.objects.none()
        
        # Apply special customer filter if provided
        is_special = self.request.GET.get('is_special')
        if is_special is not None:
            is_special_bool = is_special.lower() in ['true', '1', 'yes']
            queryset = queryset.filter(special_customer=is_special_bool)
        
        # Apply customer type filter
        customer_type = self.request.GET.get('customer_type')
        if customer_type:
            if customer_type.lower() == 'special':
                queryset = queryset.filter(special_customer=True)
            elif customer_type.lower() == 'regular':
                queryset = queryset.filter(special_customer=False)
        
        # Optimize queryset with annotations
        queryset = queryset.annotate(
            sales_count=Count('sale', distinct=True),
            total_paid_amount=Sum('sale__paid_amount'),
            total_grand_total=Sum('sale__grand_total')
        )
        
        return queryset

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.filter_queryset(self.get_queryset())
            
            # No pagination - return all results
            serializer = self.get_serializer(queryset, many=True)
            return custom_response(
                success=True,
                message=f"Found {queryset.count()} customers",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )
            
        except Exception as e:
            return custom_response(
                success=False,
                message=f"Error fetching customers: {str(e)}",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )