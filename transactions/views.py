from django.shortcuts import render
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, Q, Count
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers
from .models import Transaction
from accounts.models import Account
from .serializers import (
    TransactionSerializer, 
    TransactionCreateSerializer,
    AccountBalanceSerializer,
    TransactionSummarySerializer
)
import logging

from core.utils import custom_response

logger = logging.getLogger(__name__)

class TransactionViewSet(viewsets.ModelViewSet):
    serializer_class = TransactionSerializer
    queryset = Transaction.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['transaction_no', 'description', 'account__name']
    ordering_fields = ['transaction_date', 'amount', 'created_at', 'transaction_no']
    ordering = ['-transaction_no'] 
    # FIX (নিরাপত্তা): আগে PUT/PATCH/DELETE খোলা ছিল — যে কেউ লেনদেনের টাকা বদলাতে বা মুছতে পারত,
    # অথচ account balance বদলাত না। লেনদেন বদলানো হয় শুধু উৎস (sale/receipt/purchase …) বাতিল করে।
    http_method_names = ['get', 'post', 'head', 'options']

    # এই debug endpoint গুলো শুধু superuser এর জন্য — debug_all_companies সব company র লেনদেন দেখাত,
    # আর test_create_transaction যেকোনো account এ ৳100 যোগ করে দিত।
    DEBUG_ACTIONS = {'debug_all_companies', 'check_company_data', 'test_create_transaction',
                     'check_company_accounts', 'transaction_creation_debug', 'debug_sql'}

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if self.action in self.DEBUG_ACTIONS and not getattr(request.user, 'is_superuser', False):
            from rest_framework.exceptions import NotFound
            raise NotFound()
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Apply filters
        account_id = self.request.query_params.get('account_id')
        transaction_type = self.request.query_params.get('transaction_type')
        status_filter = self.request.query_params.get('status')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')

        user = self.request.user
        if user.is_authenticated:
            queryset = queryset.filter()
            logger.info(f"🔍 TRANSACTION FILTER DEBUG:")
            logger.info(f"  - User: {user.username}")
            logger.info(f"  - Transactions before filter: {super().get_queryset().count()}")
        else:
            return Transaction.objects.none()
        
        if account_id:
            queryset = queryset.filter(account_id=account_id)
            logger.info(f"  - After account filter: {queryset.count()}")
        
        if transaction_type:
            queryset = queryset.filter(transaction_type=transaction_type)
            logger.info(f"  - After type filter: {queryset.count()}")
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
            logger.info(f"  - After status filter: {queryset.count()}")
        
        # Date range filter (FIX: শুধু একটা তারিখ দিলেও কাজ করে; দিন হিসাব local তারিখে)
        try:
            if start_date:
                queryset = queryset.filter(transaction_date__date__gte=datetime.strptime(start_date, '%Y-%m-%d').date())
            if end_date:
                queryset = queryset.filter(transaction_date__date__lte=datetime.strptime(end_date, '%Y-%m-%d').date())
        except ValueError:
            pass
        
        # FIXED: Use only essential select_related to avoid problematic joins
        queryset = queryset.select_related(
            'account', 'created_by'
        )
        # Remove problematic relationships: 'sale', 'money_receipt', 'expense', 'purchase'
        # Add them back when the database schema is fixed
        
        logger.info(f"  - Final transaction count: {queryset.count()}")
        logger.info(f"🔍 END DEBUG")
        
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'create':
            return TransactionCreateSerializer
        return TransactionSerializer

    def create(self, request, *args, **kwargs):
        """Create a new transaction with proper company and account validation"""
        try:
            # Use the create serializer
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            
            # Get user and company
            user = request.user
            # Log creation attempt
            logger.info(f"🔄 TRANSACTION CREATION ATTEMPT:")
            logger.info(f"  - User: {user.username}")
            logger.info(f"  - Data: {request.data}")
            
            # Check if account belongs to user's company
            account_id = request.data.get('account')
            if not account_id:
                return custom_response(
                    success=False,
                    message="Account is required",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                account = Account.objects.get(id=account_id)
                logger.info(f"  - Account verified: {account.name} (Balance: {account.balance})")
            except Account.DoesNotExist:
                return custom_response(
                    success=False,
                    message="Account not found or not found",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            # Create the transaction with company and user
            transaction = serializer.save(
                created_by=user
            )
            
            logger.info(f"SUCCESS: TRANSACTION CREATED SUCCESSFULLY:")
            logger.info(f"  - Transaction ID: {transaction.id}")
            logger.info(f"  - Transaction No: {transaction.transaction_no}")
            logger.info(f"  - Amount: {transaction.amount}")
            logger.info(f"  - Account: {transaction.account.name}")
            logger.info(f"  - Account Balance After: {transaction.account.balance}")
            
            # Return the created transaction using the detail serializer
            detail_serializer = TransactionSerializer(transaction)
            
            return custom_response(
                success=True,
                message="Transaction created successfully",
                data=detail_serializer.data,
                status_code=status.HTTP_201_CREATED
            )
            
        except serializers.ValidationError as e:
            logger.error(f"ERROR:Transaction validation error: {e.detail}")
            return custom_response(
                success=False,
                message="Validation error",
                data=e.detail,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"ERROR:Transaction creation error: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message="Internal server error",
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def list(self, request, *args, **kwargs):
        """Get transactions list with custom response"""
        try:
            queryset = self.filter_queryset(self.get_queryset())
            
            # Handle pagination
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                paginated_response = self.get_paginated_response(serializer.data)
                
                return custom_response(
                    success=True,
                    message=f"Transactions fetched successfully. Total: {paginated_response.data.get('count', 0)}",
                    data={
                        'results': paginated_response.data.get('results', []),
                        'count': paginated_response.data.get('count', 0),
                        'total_pages': paginated_response.data.get('total_pages', 1),
                        'current_page': paginated_response.data.get('current_page', 1),
                        'page_size': paginated_response.data.get('page_size', 10),
                        'next': paginated_response.data.get('next'),
                        'previous': paginated_response.data.get('previous'),
                    },
                    status_code=status.HTTP_200_OK
                )
            
            # Non-paginated response
            serializer = self.get_serializer(queryset, many=True)
            return custom_response(
                success=True,
                message="Transaction list fetched successfully.",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Error fetching transaction list: {str(e)}")
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # DEBUG ENDPOINT TO CHECK ALL TRANSACTIONS
    @action(detail=False, methods=['get'])
    def debug_all_companies(self, request):
        """Debug endpoint to see transactions across all companies (admin only)"""
        try:
            user = request.user
            all_transactions = Transaction.objects.all().select_related('account')
            
            transactions_by_account = {}
            for transaction in all_transactions:
                key = transaction.account.name if transaction.account else "No Account"
                transactions_by_account.setdefault(key, []).append({
                    'id': transaction.id,
                    'transaction_no': transaction.transaction_no,
                    'amount': float(transaction.amount),
                    'type': transaction.transaction_type,
                    'date': transaction.transaction_date,
                    'created_by': transaction.created_by.username if transaction.created_by else "Unknown"
                })

            return custom_response(
                success=True,
                message="All transactions",
                data={
                    'current_user': user.username,
                    
                    'transactions_by_account': transactions_by_account,
                    'total_transactions': all_transactions.count()
                },
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def check_company_data(self, request):
        """Check what data exists for current user's company"""
        try:
            user = request.user
            # Get counts for current company
            transaction_count = Transaction.objects.filter().count()
            account_count = Account.objects.filter().count()
            
            # Get recent transactions
            recent_transactions = Transaction.objects.filter().order_by('-id')[:10].values(
                'id', 'transaction_no', 'amount', 'transaction_type', 'account__name', 'transaction_date'
            )
            
            # Get accounts
            accounts = Account.objects.filter().values('id', 'name', 'balance', 'ac_type')
            
            return custom_response(
                success=True,
                message="System data",
                data={
                    'counts': {
                        'transactions': transaction_count,
                        'accounts': account_count
                    },
                    'recent_transactions': list(recent_transactions),
                    'accounts': list(accounts)
                },
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def test_create_transaction(self, request):
        """Test endpoint to create a transaction for current company"""
        try:
            user = request.user
            # Get first active account from user's company
            test_account = Account.objects.filter(is_active=True).first()
            if not test_account:
                return custom_response(
                    success=False,
                    message="No active accounts found ",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            # Create test transaction data
            test_data = {
                'transaction_type': 'credit',
                'amount': '100.00',
                'account': test_account.id,
                'payment_method': 'cash',
                'description': f'Test transaction',
                'status': 'completed'
            }
            
            # Use the same create logic
            serializer = self.get_serializer(data=test_data)
            serializer.is_valid(raise_exception=True)
            
            transaction = serializer.save(
                created_by=user
            )
            
            # Refresh account to get updated balance
            test_account.refresh_from_db()
            
            return custom_response(
                success=True,
                message="Test transaction created successfully",
                data={
                    'transaction_id': transaction.id,
                    'transaction_no': transaction.transaction_no,
                    'amount': float(transaction.amount),
                    'account': transaction.account.name,
                    'account_balance_after': float(test_account.balance)
                },
                status_code=status.HTTP_201_CREATED
            )
            
        except Exception as e:
            logger.error(f"Test transaction creation failed: {str(e)}", exc_info=True)
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def check_company_accounts(self, request):
        """Check available accounts for current company"""
        try:
            user = request.user
            accounts = Account.objects.filter(is_active=True).values(
                'id', 'name', 'ac_type', 'balance', 'ac_no'
            )
            
            return custom_response(
                success=True,
                message=f"Accounts",
                data={
                    'total_accounts': len(accounts),
                    'accounts': list(accounts)
                },
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def transaction_creation_debug(self, request):
        """Debug transaction creation issues"""
        try:
            user = request.user
            # Check if there are any transactions for this company
            company_transactions = Transaction.objects.filter()
            
            # Check accounts
            company_accounts = Account.objects.filter(is_active=True)
            
            debug_info = {
                'user': {
                    'username': user.username
                },
                'shop_data': {
                    'total_transactions': company_transactions.count(),
                    'total_accounts': company_accounts.count(),
                    'recent_transactions': list(company_transactions.order_by('-id')[:5].values(
                        'id', 'transaction_no', 'amount', 'transaction_type', 'account__name'
                    )),
                    'available_accounts': list(company_accounts.values('id', 'name', 'ac_type', 'balance'))
                },
                'system_status': {
                    'total_transactions_in_system': Transaction.objects.count(),
                    'total_accounts_in_system': Account.objects.count()
                }
            }
            
            return custom_response(
                success=True,
                message="Transaction creation debug info",
                data=debug_info,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def account_balances(self, request):
        """Get account balances with transaction summaries"""
        try:
            user = request.user
            accounts = Account.objects.filter(is_active=True)
            
            # Annotate with transaction totals
            accounts = accounts.annotate(
                total_credits=Sum(
                    'transactions__amount',
                    filter=Q(transactions__transaction_type='credit', 
                            transactions__status='completed')
                ),
                total_debits=Sum(
                    'transactions__amount',
                    filter=Q(transactions__transaction_type='debit', 
                            transactions__status='completed')
                ),
                transaction_count=Count(
                    'transactions',
                    filter=Q(transactions__status='completed')
                )
            )
            
            for account in accounts:
                account.current_balance = (account.total_credits or 0) - (account.total_debits or 0)
            
            serializer = AccountBalanceSerializer(accounts, many=True)
            
            return custom_response(
                success=True,
                message="Account balances fetched successfully",
                data={
                    'accounts': serializer.data
                },
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get transaction summary for dashboard"""
        try:
            user = request.user
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            
            # Build base queryset for user's company
            transactions = Transaction.objects.filter(
                status='completed'
            )
            
            # Apply date filters
            if start_date:
                try:
                    start_date = datetime.strptime(start_date, '%Y-%m-%d')
                    transactions = transactions.filter(transaction_date__gte=start_date)
                except ValueError:
                    pass
            
            if end_date:
                try:
                    end_date = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                    transactions = transactions.filter(transaction_date__lte=end_date)
                except ValueError:
                    pass
            
            # Calculate totals
            total_transactions = transactions.count()
            total_credits = transactions.filter(transaction_type='credit').aggregate(
                total=Sum('amount')
            )['total'] or 0
            total_debits = transactions.filter(transaction_type='debit').aggregate(
                total=Sum('amount')
            )['total'] or 0
            net_flow = total_credits - total_debits
            
            summary_data = {
                'total_transactions': total_transactions,
                'total_credits': float(total_credits),
                'total_debits': float(total_debits),
                'net_flow': float(net_flow)
            }
            
            serializer = TransactionSummarySerializer(summary_data)
            
            return custom_response(
                success=True,
                message="Transaction summary fetched successfully",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def daily_summary(self, request):
        """Get today's and this month's transaction summary"""
        try:
            user = request.user
            # Today's transactions
            today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)
            
            today_transactions = Transaction.objects.filter(
                transaction_date__range=[today_start, today_end],
                status='completed'
            )
            
            # This month's transactions
            month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            next_month = month_start.replace(month=month_start.month+1) if month_start.month < 12 else month_start.replace(year=month_start.year+1, month=1)
            
            month_transactions = Transaction.objects.filter(
                transaction_date__range=[month_start, next_month],
                status='completed'
            )
            
            summary = {
                'today': {
                    'total_transactions': today_transactions.count(),
                    'total_credits': float(today_transactions.filter(transaction_type='credit').aggregate(Sum('amount'))['amount__sum'] or 0),
                    'total_debits': float(today_transactions.filter(transaction_type='debit').aggregate(Sum('amount'))['amount__sum'] or 0),
                },
                'this_month': {
                    'total_transactions': month_transactions.count(),
                    'total_credits': float(month_transactions.filter(transaction_type='credit').aggregate(Sum('amount'))['amount__sum'] or 0),
                    'total_debits': float(month_transactions.filter(transaction_type='debit').aggregate(Sum('amount'))['amount__sum'] or 0),
                }
            }
            
            return custom_response(
                success=True,
                message="Daily summary fetched successfully",
                data=summary,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def by_account(self, request):
        """Get transactions for a specific account"""
        try:
            account_id = request.query_params.get('account_id')
            if not account_id:
                return custom_response(
                    success=False,
                    message="account_id is required",
                    data=None,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            user = request.user
            # Ensure account belongs to user's company
            account = Account.objects.get(id=account_id)
            transactions = Transaction.objects.filter(account=account).order_by('-transaction_date')
            serializer = self.get_serializer(transactions, many=True)
            
            return custom_response(
                success=True,
                message=f"Transactions for account {account.name} fetched successfully",
                data={
                    'account': account.name,
                    'transactions': serializer.data
                },
                status_code=status.HTTP_200_OK
            )
        except Account.DoesNotExist:
            return custom_response(
                success=False,
                message="Account not found or not found",
                data=None,
                status_code=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def recent(self, request):
        """Get recent transactions (last 50)"""
        try:
            user = request.user
            transactions = Transaction.objects.filter(
                status='completed'
            ).order_by('-transaction_date')[:50]
            
            serializer = self.get_serializer(transactions, many=True)
            
            return custom_response(
                success=True,
                message="Recent transactions fetched successfully",
                data={
                    'transactions': serializer.data
                },
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def debug_sql(self, request):
        """Debug SQL queries and database schema"""
        try:
            from django.db import connection
            
            # Get a queryset
            queryset = self.get_queryset()
            
            # Get SQL for the query
            sql_query = str(queryset.query)
            
            # Try to get information about the money_receipts table
            money_receipt_columns = []
            try:
                with connection.cursor() as cursor:
                    # Try MySQL syntax first
                    cursor.execute("DESCRIBE money_receipts_moneyreceipt;")
                    money_receipt_columns = cursor.fetchall()
            except:
                try:
                    # Try SQLite syntax
                    with connection.cursor() as cursor:
                        cursor.execute("PRAGMA table_info(money_receipts_moneyreceipt);")
                        money_receipt_columns = cursor.fetchall()
                except:
                    money_receipt_columns = ["Could not fetch table info"]
            
            # Check if sale_invoice_no column exists
            sale_invoice_no_exists = any('sale_invoice_no' in str(col).lower() for col in money_receipt_columns)
            
            return custom_response(
                success=True,
                message="SQL Debug Info",
                data={
                    'sql_query': sql_query,
                    'money_receipt_columns': money_receipt_columns,
                    'sale_invoice_no_exists': sale_invoice_no_exists,
                    'problem_detected': not sale_invoice_no_exists and 'sale_invoice_no' in sql_query.lower()
                },
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            return custom_response(
                success=False,
                message=str(e),
                data=None,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )