from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import models
from django.db.models import Q
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
import logging

from core.utils import custom_response
from core.base_viewsets import BaseViewSet
from core.pagination import CustomPageNumberPagination
from accounts.models import Account
from .models import AccountTransfer
# from account_tr.models import AccountTransfer 
from .serializers import (
    AccountTransferSerializer,
    AccountTransferCreateSerializer,
    ExecuteTransferSerializer,
    ReverseTransferSerializer,
    CancelTransferSerializer,
    TransferAccountSerializer
)

logger = logging.getLogger(__name__)

class AccountTransferViewSet(BaseViewSet):
    """API for account balance transfers"""
    queryset = AccountTransfer.objects.all()
    serializer_class = AccountTransferSerializer
    pagination_class = CustomPageNumberPagination
    
    def get_queryset(self):
        """Apply filters to the queryset"""
        queryset = super().get_queryset()
        
        # Get filter parameters
        from_account_id = self.request.query_params.get('from_account_id')
        to_account_id = self.request.query_params.get('to_account_id')
        status_filter = self.request.query_params.get('status')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        transfer_type = self.request.query_params.get('transfer_type')
        is_reversal = self.request.query_params.get('is_reversal')
        
        # Apply filters
        if from_account_id:
            queryset = queryset.filter(from_account_id=from_account_id)
        
        if to_account_id:
            queryset = queryset.filter(to_account_id=to_account_id)
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        if transfer_type:
            queryset = queryset.filter(transfer_type=transfer_type)
        
        if is_reversal is not None:
            is_reversal_bool = is_reversal.lower() == 'true'
            queryset = queryset.filter(is_reversal=is_reversal_bool)
        
        # Date range filter
        if start_date and end_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d')
                end_date = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                queryset = queryset.filter(transfer_date__range=[start_date, end_date])
            except ValueError:
                pass
        
        # Order by transfer date (newest first)
        queryset = queryset.order_by('-transfer_date', '-id')
        
        return queryset

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return AccountTransferCreateSerializer
        elif self.action == 'execute':
            return ExecuteTransferSerializer
        elif self.action == 'reverse':
            return ReverseTransferSerializer
        elif self.action == 'cancel':
            return CancelTransferSerializer
        return AccountTransferSerializer

    def create(self, request, *args, **kwargs):
        """Create a new transfer request"""
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            transfer = serializer.save()
            
            logger.info(f"Transfer {transfer.transfer_no} created successfully")
            
            return custom_response(
                success=True,
                message="Transfer request created successfully. Use execute endpoint to complete the transfer.",
                data=self.get_serializer(transfer).data,
                status_code=status.HTTP_201_CREATED
            )
            
        except serializers.ValidationError as e:
            logger.warning(f"Transfer validation error: {e.detail}")
            return custom_response(
                success=False,
                message="Validation Error",
                data=e.detail,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error creating transfer: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        """Execute a pending transfer"""
        try:
            transfer = self.get_object()
            
            # Validate transfer can be executed
            if transfer.status != 'pending':
                return custom_response(
                    success=False,
                    message=f"Transfer cannot be executed. Current status: {transfer.status}",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            
            # Execute the transfer
            user = request.user
            transfer.execute_transfer(user)
            
            logger.info(f"Transfer {transfer.transfer_no} executed successfully")
            
            return custom_response(
                success=True,
                message="Transfer executed successfully",
                data=self.get_serializer(transfer).data,
                status_code=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Error executing transfer: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        """Reverse a completed transfer"""
        try:
            transfer = self.get_object()
            
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            
            reason = serializer.validated_data.get('reason', 'No reason provided')
            user = request.user
            
            # Reverse the transfer
            reversal = transfer.reverse_transfer(reason, user)
            
            logger.info(f"Transfer {transfer.transfer_no} reversed successfully")
            
            return custom_response(
                success=True,
                message="Transfer reversed successfully",
                data={
                    'original_transfer': self.get_serializer(transfer).data,
                    'reversal_transfer': AccountTransferSerializer(reversal).data
                },
                status_code=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Error reversing transfer: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a pending transfer"""
        try:
            transfer = self.get_object()
            
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            
            reason = serializer.validated_data.get('reason', 'No reason provided')
            user = request.user
            
            # Cancel the transfer
            transfer.cancel_transfer(reason, user)
            
            logger.info(f"Transfer {transfer.transfer_no} cancelled successfully")
            
            return custom_response(
                success=True,
                message="Transfer cancelled successfully",
                data=self.get_serializer(transfer).data,
                status_code=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Error cancelling transfer: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'])
    def available_accounts(self, request):
        """Get all active accounts available for transfer"""
        try:
            user = request.user
            accounts = Account.objects.filter(
                is_active=True
            ).order_by('ac_type', 'name')
            
            serializer = TransferAccountSerializer(accounts, many=True)
            
            return custom_response(
                success=True,
                message="Available accounts fetched successfully",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error fetching available accounts: {str(e)}")
            return custom_response(
                success=False,
                message="Internal server error",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get transfer summary statistics"""
        try:
            user = request.user
            queryset = self.filter_queryset(self.get_queryset())
            
            total_transfers = queryset.count()
            total_amount = queryset.aggregate(total=models.Sum('amount'))['total'] or 0
            
            # Count by status
            status_count = queryset.values('status').annotate(
                count=models.Count('id'),
                amount=models.Sum('amount')
            )
            
            # Count by transfer type
            type_count = queryset.values('transfer_type').annotate(
                count=models.Count('id'),
                amount=models.Sum('amount')
            )
            
            # Recent transfers
            recent_transfers = queryset.order_by('-transfer_date')[:10]
            recent_serializer = AccountTransferSerializer(recent_transfers, many=True)
            
            summary_data = {
                'total_transfers': total_transfers,
                'total_amount': float(total_amount),
                'status_breakdown': list(status_count),
                'type_breakdown': list(type_count),
                'recent_transfers': recent_serializer.data
            }
            
            return custom_response(
                success=True,
                message="Transfer summary fetched successfully",
                data=summary_data,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error fetching transfer summary: {str(e)}")
            return custom_response(
                success=False,
                message="Internal server error",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def quick_transfer(self, request):
        """Create and execute a transfer in one step"""
        try:
            # Validate request data
            required_fields = ['from_account_id', 'to_account_id', 'amount']
            for field in required_fields:
                if field not in request.data:
                    return custom_response(
                        success=False,
                        message=f"Missing required field: {field}",
                        data=None,
                        status_code=status.HTTP_400_BAD_REQUEST
                    )
            
            # Create the transfer
            create_serializer = AccountTransferCreateSerializer(
                data=request.data,
                context={'request': request}
            )
            create_serializer.is_valid(raise_exception=True)
            transfer = create_serializer.save()
            
            # Execute the transfer
            user = request.user
            transfer.execute_transfer(user)
            
            logger.info(f"Quick transfer {transfer.transfer_no} completed successfully")
            
            return custom_response(
                success=True,
                message="Transfer completed successfully",
                data=AccountTransferSerializer(transfer).data,
                status_code=status.HTTP_201_CREATED
            )
            
        except serializers.ValidationError as e:
            logger.warning(f"Quick transfer validation error: {e.detail}")
            return custom_response(
                success=False,
                message="Validation Error",
                data=e.detail,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error in quick transfer: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )