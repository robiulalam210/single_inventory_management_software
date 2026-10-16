# accounts/views.py
from rest_framework import status, serializers
from rest_framework.decorators import action
from django.db.models import Q, Sum, Count, DecimalField
from core.base_viewsets import BaseInventoryViewSet
from core.pagination import CustomPageNumberPagination
from core.utils import custom_response
from .models import Account
from .serializers import AccountSerializer
import logging
from rest_framework import viewsets, filters
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from decimal import Decimal
from django.http import Http404

logger = logging.getLogger(__name__)


class AccountViewSet(BaseInventoryViewSet):
    """CRUD API for accounts with pagination control and search."""
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'number', 'bank_name', 'branch', 'ac_type']
    ordering_fields = ['name', 'ac_type', 'balance', 'created_at', 'number', 'bank_name', 'branch']
    ordering = ['-created_at']
    
    def get_page_size(self, request):
        """Get page size from request or use default"""
        page_size = request.query_params.get('page_size')
        if page_size and page_size.isdigit():
            size = int(page_size)
            # Limit page size to reasonable values
            return min(size, 100)  # Max 100 items per page
        # Return default from pagination class
        return self.pagination_class.page_size if hasattr(self.pagination_class, 'page_size') else 10
    
    def get_paginated_response(self, data):
        """Override to return custom paginated response"""
        if self.paginator is None:
            return Response(data)
        
        return Response({
            'count': self.paginator.page.paginator.count,
            'total_pages': self.paginator.page.paginator.num_pages,
            'current_page': self.paginator.page.number,
            'page_size': self.paginator.page_size,
            'next': self.paginator.get_next_link(),
            'previous': self.paginator.get_previous_link(),
            'results': data
        })
    
    def get_queryset(self):
        """Apply filters and search to the queryset"""
        # Start with base queryset
        queryset = super().get_queryset()
        
        # Apply account type filter
        ac_type = self.request.query_params.get('ac_type')
        if ac_type:
            queryset = queryset.filter(ac_type__iexact=ac_type)
        
        # Apply search
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(number__icontains=search) |
                Q(bank_name__icontains=search) |
                Q(branch__icontains=search) |
                Q(ac_no__icontains=search)
            )
        
        # Apply balance filters
        min_balance = self.request.query_params.get('min_balance')
        max_balance = self.request.query_params.get('max_balance')
        
        if min_balance:
            try:
                queryset = queryset.filter(balance__gte=Decimal(min_balance))
            except (ValueError, TypeError):
                pass
        
        if max_balance:
            try:
                queryset = queryset.filter(balance__lte=Decimal(max_balance))
            except (ValueError, TypeError):
                pass
        
        # Apply status filter
        status_filter = self.request.query_params.get('status')
        if status_filter:
            if status_filter.lower() == 'active':
                queryset = queryset.filter(is_active=True)
            elif status_filter.lower() == 'inactive':
                queryset = queryset.filter(is_active=False)
        
        # Apply is_active filter
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            if isinstance(is_active, str):
                is_active = is_active.lower()
                if is_active in ['true', '1', 'yes']:
                    queryset = queryset.filter(is_active=True)
                elif is_active in ['false', '0', 'no']:
                    queryset = queryset.filter(is_active=False)
        
        # Ordering
        order_by = self.request.query_params.get('order_by', '-created_at')
        if order_by.lstrip('-') in ['name', 'ac_type', 'balance', 'created_at', 'number', 'bank_name', 'branch', 'ac_no']:
            queryset = queryset.order_by(order_by)
        else:
            queryset = queryset.order_by('-created_at')
            
        return queryset

    def list(self, request, *args, **kwargs):
        """
        Get accounts with pagination control and filtering
        """
        try:
            # Get query parameters
            params = dict(request.query_params)
            logger.debug(f"Account list called with params: {params}")
            
            # Check if pagination should be disabled
            no_pagination = request.query_params.get('no_pagination', '').lower() in ['true', '1', 'yes']
            
            # Get filtered queryset
            queryset = self.filter_queryset(self.get_queryset())
            total_count = queryset.count()
            logger.debug(f"Filtered queryset count: {total_count}")
            
            # Handle empty queryset
            if total_count == 0:
                return custom_response(
                    success=True,
                    message="No accounts found.",
                    data={
                        'results': [],
                        'count': 0,
                        'total_pages': 0,
                        'current_page': 1,
                        'page_size': 0,
                        'next': None,
                        'previous': None,
                        'pagination': 'disabled' if no_pagination else 'enabled'
                    },
                    status_code=status.HTTP_200_OK
                )
            
            # Handle non-paginated response
            if no_pagination:
                serializer = self.get_serializer(queryset, many=True)
                data = self._process_account_data(serializer.data)
                
                return custom_response(
                    success=True,
                    message=f"Accounts fetched successfully (no pagination). Total: {total_count}",
                    data={
                        'results': data,
                        'count': total_count,
                        'total_pages': 1,
                        'current_page': 1,
                        'page_size': total_count,
                        'next': None,
                        'previous': None,
                        'pagination': 'disabled'
                    },
                    status_code=status.HTTP_200_OK
                )
            
            # Apply pagination (when no_pagination=false or not specified)
            # Configure paginator
            page_size = self.get_page_size(request)
            
            # Create a new paginator instance with the requested page size
            paginator = CustomPageNumberPagination()
            paginator.page_size = page_size
            
            # Get the requested page
            page_number = request.query_params.get('page', 1)
            if isinstance(page_number, str) and page_number.isdigit():
                page_number = int(page_number)
            
            # Paginate the queryset
            paginated_queryset = paginator.paginate_queryset(queryset, request)
            
            if paginated_queryset is not None:
                serializer = self.get_serializer(paginated_queryset, many=True)
                data = self._process_account_data(serializer.data)
                
                # Get pagination info
                current_page = paginator.page.number
                total_pages = paginator.page.paginator.num_pages
                page_size = paginator.page_size
                
                # Build response data
                response_data = {
                    'results': data,
                    'count': total_count,
                    'total_pages': total_pages,
                    'current_page': current_page,
                    'page_size': page_size,
                    'next': paginator.get_next_link(),
                    'previous': paginator.get_previous_link(),
                    'pagination': 'enabled'
                }
                
                return custom_response(
                    success=True,
                    message=f"Accounts fetched successfully. Showing page {current_page} of {total_pages}. Total: {total_count}",
                    data=data,
                    status_code=status.HTTP_200_OK
                )
            
            # If pagination fails for some reason, fall back to non-paginated
            logger.warning("Pagination failed, falling back to non-paginated response")
            serializer = self.get_serializer(queryset, many=True)
            data = self._process_account_data(serializer.data)
            
            return custom_response(
                success=True,
                message=f"Accounts fetched successfully (pagination failed). Total: {total_count}",
                data={
                    'results': data,
                    'count': total_count,
                    'total_pages': 1,
                    'current_page': 1,
                    'page_size': total_count,
                    'next': None,
                    'previous': None,
                    'pagination': 'failed'
                },
                status_code=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Error fetching account list: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data={'error': str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _process_account_data(self, data):
        """Process account data to ensure consistent format"""
        if not data:
            return data
            
        for item in data:
            # Ensure number is None if blank or empty string
            if item.get('ac_number') in ('', None):
                item['ac_number'] = None
            
            # Add number field from ac_number for consistency
            item['number'] = item.get('ac_number')
            
            # Ensure balance is float
            if 'balance' in item and item['balance'] is not None:
                try:
                    item['balance'] = float(item['balance'])
                except (ValueError, TypeError):
                    item['balance'] = 0.0
                
            # Ensure opening_balance is float
            if 'opening_balance' in item and item['opening_balance'] is not None:
                try:
                    item['opening_balance'] = float(item['opening_balance'])
                except (ValueError, TypeError):
                    item['opening_balance'] = 0.0
                
            # Ensure bank_name and branch are None if empty
            if item.get('bank_name') in ('', None):
                item['bank_name'] = None
                
            if item.get('branch') in ('', None):
                item['branch'] = None
                
            # Add status field
            if 'is_active' in item:
                item['status'] = 'Active' if item['is_active'] else 'Inactive'
                
        return data

    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            data = self._process_account_data([serializer.data])[0]
            
            return custom_response(
                success=True,
                message="Account details fetched successfully.",
                data=data,
                status_code=status.HTTP_200_OK
            )
            
        except Http404:
            logger.warning(f"Account not found: {kwargs.get('pk')}")
            return custom_response(
                success=False,
                message="Account not found.",
                data=None,
                status_code=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error fetching account details: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data={'error': str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            account = serializer.save()
            
            logger.info(f"Account created successfully: {account.id} - {account.name}")
            
            # Get the serialized data
            response_serializer = self.get_serializer(account)
            data = self._process_account_data([response_serializer.data])[0]
            
            return custom_response(
                success=True,
                message="Account created successfully." + (f" Opening balance transaction created." if account.opening_balance > 0 else ""),
                data=data,
                status_code=status.HTTP_201_CREATED
            )

        except serializers.ValidationError as e:
            logger.warning(f"Account validation error: {e.detail}")
            return custom_response(
                success=False,
                message="Validation Error",
                data=e.detail,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error creating account: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data={'error': str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
  
    def update(self, request, *args, **kwargs):
        """
        Update an existing account
        """
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=False)
            serializer.is_valid(raise_exception=True)
            
            # Update the instance
            serializer.save()
            
            logger.info(f"Account updated successfully: {instance.id}")
            
            # Return updated data
            updated_serializer = self.get_serializer(instance)
            data = self._process_account_data([updated_serializer.data])[0]
            
            return custom_response(
                success=True,
                message="Account updated successfully.",
                data=data,
                status_code=status.HTTP_200_OK
            )
            
        except Http404:
            logger.warning(f"Account not found for update: {kwargs.get('pk')}")
            return custom_response(
                success=False,
                message="Account not found.",
                data=None,
                status_code=status.HTTP_404_NOT_FOUND
            )
        except serializers.ValidationError as e:
            logger.warning(f"Account update validation error: {e.detail}")
            return custom_response(
                success=False,
                message="Validation Error",
                data=e.detail,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error updating account: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data={'error': str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def partial_update(self, request, *args, **kwargs):
        """
        Partial update of an account
        """
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            
            # Update the instance
            serializer.save()
            
            logger.info(f"Account partially updated: {instance.id}")
            
            # Return updated data
            updated_serializer = self.get_serializer(instance)
            data = self._process_account_data([updated_serializer.data])[0]
            
            return custom_response(
                success=True,
                message="Account updated successfully.",
                data=data,
                status_code=status.HTTP_200_OK
            )
            
        except Http404:
            logger.warning(f"Account not found for update: {kwargs.get('pk')}")
            return custom_response(
                success=False,
                message="Account not found.",
                data=None,
                status_code=status.HTTP_404_NOT_FOUND
            )
        except serializers.ValidationError as e:
            logger.warning(f"Account partial update validation error: {e.detail}")
            return custom_response(
                success=False,
                message="Validation Error",
                data=e.detail,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error partially updating account: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data={'error': str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """Toggle account active status"""
        try:
            instance = self.get_object()
            instance.is_active = not instance.is_active
            instance.save()
            
            status_text = "activated" if instance.is_active else "deactivated"
            
            logger.info(f"Account {instance.id} {status_text}")
            
            return custom_response(
                success=True,
                message=f"Account {status_text} successfully.",
                data={'id': instance.id, 'is_active': instance.is_active},
                status_code=status.HTTP_200_OK
            )
        except Http404:
            return custom_response(
                success=False,
                message="Account not found.",
                data=None,
                status_code=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error toggling account status: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data={'error': str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def destroy(self, request, *args, **kwargs):
        """
        FIX (গুরুতর): আগে সাধারণ delete ছিল — account মুছলে তার সব transaction ও (CASCADE) মুছে যেত,
        ফলে বিক্রি/কেনা/খরচের টাকার হিসাব হারিয়ে যেত। এখন লেনদেন থাকলে শুধু inactive হয়।
        """
        try:
            instance = self.get_object()
        except Http404:
            return custom_response(success=False, message="Account not found.", data=None,
                                   status_code=status.HTTP_404_NOT_FOUND)
        from transactions.models import Transaction
        used = Transaction.objects.filter(account=instance).count()
        if used or (instance.balance or 0) != 0:
            instance.is_active = False
            instance.save(update_fields=['is_active', 'updated_at'])
            reason = f"{used} transactions" if used else f"a balance of {instance.balance}"
            return custom_response(
                success=True,
                message=f"This account has {reason}, so it was marked inactive instead of deleted.",
                data={'id': instance.id, 'is_active': False, 'deletion_blocked': True},
                status_code=status.HTTP_200_OK)
        name = instance.name
        instance.delete()
        return custom_response(success=True, message=f"Account '{name}' deleted.", data=None,
                               status_code=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def statement(self, request, pk=None):
        """
        GET /api/accounts/<id>/statement/?start=YYYY-MM-DD&end=YYYY-MM-DD
        এই account এর সব টাকা আসা-যাওয়া, তারিখের ক্রমে, প্রতিটার পরে balance সহ।
        শুরুর আগের সব হিসাব "opening"। শেষে মিলিয়ে দেখা হয়: transaction গুলো যোগ করলে যা হয়, আসল
        balance তার সাথে মেলে কিনা — না মিললে "unexplained" (আগের কোনো bug এ হাতে বদলানো balance)।
        pending / failed লেনদেন balance বদলায় না, তাই বাদ।
        """
        from datetime import datetime as _dt
        from django.utils import timezone as _tz
        from transactions.models import Transaction
        try:
            account = self.get_object()
        except Http404:
            return custom_response(success=False, message="Account not found.", data=None,
                                   status_code=status.HTTP_404_NOT_FOUND)

        def _d(v):
            try:
                return _dt.strptime(v, '%Y-%m-%d').date() if v else None
            except ValueError:
                return None
        start, end = _d(request.query_params.get('start')), _d(request.query_params.get('end'))

        txns = (Transaction.objects.filter(account=account).exclude(status__in=['pending', 'failed'])
                .select_related('created_by').order_by('transaction_date', 'id'))
        opening = Decimal('0.00')
        total = Decimal('0.00')
        rows = []
        cin = cout = Decimal('0.00')
        for t in txns:
            effect = t.amount if t.transaction_type == 'credit' else -t.amount
            when = _tz.localtime(t.transaction_date) if _tz.is_aware(t.transaction_date) else t.transaction_date
            d = when.date()
            total += effect
            if start and d < start:
                opening += effect
                continue
            if end and d > end:
                continue
            if t.transaction_type == 'credit':
                cin += t.amount
            else:
                cout += t.amount
            rows.append({
                'id': t.id, 'no': t.transaction_no, 'date': when.isoformat(),
                'type': t.transaction_type, 'amount': float(t.amount),
                'description': t.description or '', 'method': t.payment_method,
                'reference': t.reference_no or '', 'status': t.status,
                'is_opening_balance': t.is_opening_balance,
                'by': t.created_by.username if t.created_by else '',
            })
        running = opening
        for r in rows:
            running += Decimal(str(r['amount'])) if r['type'] == 'credit' else -Decimal(str(r['amount']))
            r['balance'] = float(running)
        unexplained = (account.balance or Decimal('0.00')) - total
        return custom_response(success=True, message="Account statement.", data={
            'account': {'id': account.id, 'name': account.name, 'ac_type': account.ac_type,
                        'number': account.number, 'balance': float(account.balance or 0)},
            'start': start.isoformat() if start else None,
            'end': end.isoformat() if end else None,
            'opening_balance': float(opening),
            'money_in': float(cin), 'money_out': float(cout),
            'closing_balance': float(running),
            'unexplained': float(unexplained),
            'rows': rows,
        }, status_code=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def types(self, request):
        """Get available account types"""
        try:
            types_list = [
                {'value': Account.TYPE_BANK, 'label': 'Bank'},
                {'value': Account.TYPE_MOBILE, 'label': 'Mobile banking'},
                {'value': Account.TYPE_CASH, 'label': 'Cash'},
                {'value': Account.TYPE_OTHER, 'label': 'Other'}
            ]
            
            return custom_response(
                success=True,
                message="Account types fetched successfully.",
                data=types_list,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error fetching account types: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data={'error': str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get account summary statistics"""
        try:
            queryset = self.filter_queryset(self.get_queryset())
            
            total_accounts = queryset.count()
            total_balance = queryset.aggregate(total=Sum('balance'))['total'] or Decimal('0.00')
            
            # Count by account type
            type_count = queryset.values('ac_type').annotate(
                count=Count('id'),
                total_balance=Sum('balance')
            ).order_by('ac_type')
            
            # Count by status
            active_count = queryset.filter(is_active=True).count()
            inactive_count = total_accounts - active_count
            
            summary_data = {
                'total_accounts': total_accounts,
                'total_balance': float(total_balance),
                'account_type_breakdown': [
                    {
                        'ac_type': item['ac_type'],
                        'count': item['count'],
                        'total_balance': float(item['total_balance'] or Decimal('0.00'))
                    }
                    for item in type_count
                ],
                'status_breakdown': [
                    {'status': 'Active', 'count': active_count},
                    {'status': 'Inactive', 'count': inactive_count}
                ]
            }
            
            return custom_response(
                success=True,
                message="Account summary fetched successfully.",
                data=summary_data,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error fetching account summary: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data={'error': str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get only active accounts"""
        try:
            # Set is_active=true in query params
            request.GET = request.GET.copy()
            request.GET['is_active'] = 'true'
            
            # Reuse the list method
            return self.list(request)
        except Exception as e:
            logger.error(f"Error fetching active accounts: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data={'error': str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def inactive(self, request):
        """Get only inactive accounts"""
        try:
            # Set is_active=false in query params
            request.GET = request.GET.copy()
            request.GET['is_active'] = 'false'
            
            # Reuse the list method
            return self.list(request)
        except Exception as e:
            logger.error(f"Error fetching inactive accounts: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data={'error': str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )