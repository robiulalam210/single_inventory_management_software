# suppliers/views.py
from rest_framework import viewsets, status, permissions, serializers
from django.db.models import Q
from core.utils import custom_response
from core.pagination import CustomPageNumberPagination
from .models import Supplier
from .serializers import SupplierSerializer, SupplierCreateSerializer  # Import the create serializer
import logging

logger = logging.getLogger(__name__)

# Create a simplified base viewset if BaseViewSet doesn't exist
class BaseViewSet(viewsets.ModelViewSet):
    """Base ViewSet that automatically filters by user's company"""
    
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        
        # Filter by company if user has a company
        if user.is_authenticated:
            queryset = queryset.filter()
        
        return queryset

class SupplierViewSet(BaseViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPageNumberPagination
    
    def get_serializer_class(self):
        """Use different serializers for different actions"""
        if self.action in ['create', 'update', 'partial_update']:
            return SupplierCreateSerializer
        return SupplierSerializer

    def get_queryset(self):
        """Apply filters and search to the queryset"""
        queryset = super().get_queryset()
        
        # Filter by company
        user = self.request.user
        if user.is_authenticated:
            queryset = queryset.filter()
        else:
            return Supplier.objects.none()  # FIXED: Use Supplier, not Customer
        
        # Get filter parameters
        search = self.request.query_params.get('search')
        status_filter = self.request.query_params.get('status')
        shop_name = self.request.query_params.get('shop_name')
        product_name = self.request.query_params.get('product_name')
        
        # Apply filters
        if search:
            queryset = queryset.filter(
                Q(supplier_no__icontains=search) |
                Q(name__icontains=search) |
                Q(address__icontains=search) |
                Q(email__icontains=search) |
                Q(phone__icontains=search) |
                Q(shop_name__icontains=search) |  # ADDED: Search in shop_name
                Q(product_name__icontains=search)  # ADDED: Search in product_name
            )
            
        # Filter by shop name
        if shop_name:
            queryset = queryset.filter(shop_name__icontains=shop_name)
            
        # Filter by product name
        if product_name:
            queryset = queryset.filter(product_name__icontains=product_name)
            
        if status_filter:
            if status_filter.lower() == 'active':
                queryset = queryset.filter(is_active=True)
            elif status_filter.lower() == 'inactive':
                queryset = queryset.filter(is_active=False)

        # যাদের কাছে বাকি / যাদের কাছে অগ্রিম দেওয়া আছে
        balance = (self.request.query_params.get('balance') or '').lower()
        if balance == 'due':
            queryset = queryset.filter(total_due__gt=0)
        elif balance == 'advance':
            queryset = queryset.filter(advance_balance__gt=0)
        
        # Order by name by default
        order_by = self.request.query_params.get('order_by', 'supplier_no')
        valid_order_fields = ['name', 'email', 'shop_name', 'created_at', 'updated_at', 'total_purchases',
                              'total_due', 'total_paid', 'advance_balance', 'purchase_count']
        if order_by.lstrip('-') in valid_order_fields:
            queryset = queryset.order_by(order_by)
        else:
            queryset = queryset.order_by('supplier_no')
            
        return queryset

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.filter_queryset(self.get_queryset())
            
            # Apply pagination
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            
            # If no pagination, return all results
            serializer = self.get_serializer(queryset, many=True)
            return custom_response(
                success=True,
                message="Supplier list fetched successfully.",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Error fetching supplier list: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def retrieve(self, request, *args, **kwargs):
        try:
            supplier = self.get_object()
            serializer = self.get_serializer(supplier)
            return custom_response(
                success=True,
                message="Supplier details fetched successfully.",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error fetching supplier details: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            # Check for duplicate supplier phone in the same company
            phone = serializer.validated_data.get('phone')
            if phone and Supplier.objects.filter(phone=phone).exists():
                return custom_response(
                    success=False,
                    message="A supplier with this phone already exists .",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            # NEW: Check for duplicate shop name if provided
            shop_name = serializer.validated_data.get('shop_name')
            if shop_name and Supplier.objects.filter(shop_name=shop_name).exists():
                return custom_response(
                    success=False,
                    message="A supplier with this shop name already exists .",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            instance = serializer.save(created_by=request.user)
            logger.info(f"Supplier created successfully: {instance.id}")
            
            return custom_response(
                success=True,
                message="Supplier created successfully.",
                data=SupplierSerializer(instance).data,
                status_code=status.HTTP_201_CREATED
            )
        except serializers.ValidationError as e:
            logger.warning(f"Supplier validation error: {e.detail}")
            return custom_response(
                success=False,
                message="Validation Error",
                data=e.detail,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error creating supplier: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        
        try:
            serializer.is_valid(raise_exception=True)
            # Check for duplicate supplier phone (excluding current instance)
            phone = serializer.validated_data.get('phone')
            if phone and Supplier.objects.filter(phone=phone).exclude(id=instance.id).exists():
                return custom_response(
                    success=False,
                    message="A supplier with this phone already exists .",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            # NEW: Check for duplicate shop name (excluding current instance)
            shop_name = serializer.validated_data.get('shop_name')
            if shop_name and Supplier.objects.filter(shop_name=shop_name).exclude(id=instance.id).exists():
                return custom_response(
                    success=False,
                    message="A supplier with this shop name already exists .",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            updated_instance = serializer.save()
            logger.info(f"Supplier updated successfully: {instance.id}")
            
            return custom_response(
                success=True,
                message="Supplier updated successfully.",
                data=SupplierSerializer(updated_instance).data,
                status_code=status.HTTP_200_OK
            )
        except serializers.ValidationError as e:
            logger.warning(f"Supplier update validation error: {e.detail}")
            return custom_response(
                success=False,
                message="Validation Error",
                data=e.detail,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error updating supplier: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def destroy(self, request, *args, **kwargs):
        """
        Delete a supplier - Only allow if no purchases or supplier payments exist
        """
        try:
            instance = self.get_object()
            supplier_id = instance.id
            supplier_name = instance.name
            
            # Check for purchases
            has_purchases = False
            try:
                from purchases.models import Purchase
                has_purchases = Purchase.objects.filter(supplier=instance).exists()
            except (ImportError, Exception):
                # Fallback to relationship check
                if hasattr(instance, 'purchases'):
                    has_purchases = instance.purchases.exists()
                elif hasattr(instance, 'purchase_set'):
                    has_purchases = instance.purchase_set.exists()
            
            # Check for supplier payments
            has_supplier_payments = False
            try:
                from transactions.models import SupplierPayment
                has_supplier_payments = SupplierPayment.objects.filter(supplier=instance).exists()
            except (ImportError, Exception):
                # Fallback to relationship check
                if hasattr(instance, 'supplier_payments'):
                    has_supplier_payments = instance.supplier_payments.exists()
                elif hasattr(instance, 'supplierpayment_set'):
                    has_supplier_payments = instance.supplierpayment_set.exists()
            
            # If any transactions exist, mark as inactive instead of deleting
            if has_purchases or has_supplier_payments:
                instance.is_active = False
                instance.save(update_fields=['is_active'])
                
                reasons = []
                if has_purchases:
                    reasons.append("purchases")
                if has_supplier_payments:
                    reasons.append("supplier payments")
                
                message = f"Supplier cannot be deleted as it has {', '.join(reasons)} history. It has been marked as inactive instead."
                
                return custom_response(
                    success=True,
                    message=message,
                    data={
                        'is_active': instance.is_active,
                        'deletion_blocked': True,
                        'blocking_reasons': reasons
                    },
                    status_code=status.HTTP_200_OK
                )
            
            # If no transactions, proceed with actual deletion
            instance.delete()
            
            logger.info(f"Supplier deleted successfully: {supplier_id} - {supplier_name}")
            
            return custom_response(
                success=True,
                message="Supplier deleted successfully.",
                data=None,
                status_code=status.HTTP_200_OK
            )
                
        except Exception as e:
            logger.error(f"Error deleting supplier: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
class SupplierNonPaginationViewSet(BaseViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None  # Explicitly disable pagination

    def get_queryset(self):
        """Apply filters and search to the queryset"""
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_authenticated:
            queryset = queryset.filter()
        else:
            return Supplier.objects.none()  # FIXED: Use Supplier, not Customer
        
        # Get filter parameters
        search = self.request.query_params.get('search')
        status_filter = self.request.query_params.get('status')
        shop_name = self.request.query_params.get('shop_name')
        product_name = self.request.query_params.get('product_name')
        
        # Apply filters
        if search:
            queryset = queryset.filter(
                Q(supplier_no__icontains=search) |
                Q(name__icontains=search) |
                Q(address__icontains=search) |
                Q(email__icontains=search) |
                Q(phone__icontains=search) |
                Q(shop_name__icontains=search) |  # ADDED
                Q(product_name__icontains=search)  # ADDED
            )
            
        # Filter by shop name
        if shop_name:
            queryset = queryset.filter(shop_name__icontains=shop_name)
            
        # Filter by product name
        if product_name:
            queryset = queryset.filter(product_name__icontains=product_name)
            
        if status_filter:
            if status_filter.lower() == 'active':
                queryset = queryset.filter(is_active=True)
            elif status_filter.lower() == 'inactive':
                queryset = queryset.filter(is_active=False)
        
        # Order by name by default
        order_by = self.request.query_params.get('order_by', 'name')
        valid_order_fields = ['name', 'email', 'shop_name', 'created_at', 'updated_at', 'total_purchases']
        if order_by.lstrip('-') in valid_order_fields:
            queryset = queryset.order_by(order_by)
        else:
            queryset = queryset.order_by('name')
            
        return queryset

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.filter_queryset(self.get_queryset())
            
            # Return all results without pagination
            serializer = self.get_serializer(queryset, many=True)
            return custom_response(
                success=True,
                message="Supplier list fetched successfully.",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Error fetching supplier list: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )