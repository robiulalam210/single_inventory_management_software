from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError
from rest_framework import status, viewsets, serializers
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from core.utils import custom_response
from .models import Expense, ExpenseHead, ExpenseSubHead
from .serializers import ExpenseSerializer, ExpenseHeadSerializer, ExpenseSubHeadSerializer, ExpenseCreateSerializer, ExpenseUpdateSerializer   
from core.pagination import CustomPageNumberPagination
from django.db.models import Q 

from django.utils import timezone
from django.db import transaction
from django.conf import settings
import traceback    

 # Add this import

import logging

logger = logging.getLogger(__name__)


def _deny(request, action):
    """খরচের অনুমতি — আগে login থাকলেই যে কেউ খরচ লিখতে/মুছতে পারত"""
    u = request.user
    if getattr(u, 'role', '') == 'SUPER_ADMIN' or u.is_superuser or u.has_permission('expense', action):
        return None
    verb = {'view': 'see', 'create': 'add', 'edit': 'change', 'delete': 'delete'}[action]
    return custom_response(False, f"You don't have permission to {verb} expenses.", None, status.HTTP_403_FORBIDDEN)


class BaseViewSet(viewsets.ModelViewSet):
    """Base viewset: authenticated users only"""

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_authenticated:
            return queryset
        return queryset.none()


# ------------------------------
# Expense Head
# ------------------------------
class ExpenseHeadListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            from django.db.models import Count, Sum
            heads = ExpenseHead.objects.filter().annotate(
                expense_count=Count('expense', distinct=True), expense_total=Sum('expense__amount'),
                subhead_count=Count('subheads', distinct=True),
            ).order_by('name')
            data = ExpenseHeadSerializer(heads, many=True).data
            for row, h in zip(data, heads):
                row['expense_count'] = h.expense_count
                row['expense_total'] = str(h.expense_total or 0)
                row['subhead_count'] = h.subhead_count
            return custom_response(True, "Expense heads fetched successfully.", data, status.HTTP_200_OK)
        except Exception as e:
            return custom_response(False, f"Server Error: {str(e)}", None, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        denied = _deny(request, 'create')
        if denied:
            return denied
        try:
            data = request.data.copy()
            data['name'] = (data.get('name') or '').strip()
            if data['name'] and ExpenseHead.objects.filter(name__iexact=data['name']).exists():
                return custom_response(False, "Validation error.", {'name': ['This expense head already exists.']}, status.HTTP_400_BAD_REQUEST)
            serializer = ExpenseHeadSerializer(data=data)

            if serializer.is_valid():
                serializer.save(created_by=request.user)  # SUCCESS: Set created_by
                return custom_response(True, "Expense head created successfully.", serializer.data, status.HTTP_201_CREATED)
            return custom_response(False, "Validation error.", serializer.errors, status.HTTP_400_BAD_REQUEST)

        except IntegrityError as e:
            return custom_response(False, f"Database integrity error: {str(e)}", None, status.HTTP_400_BAD_REQUEST)
        except ValidationError as e:
            return custom_response(False, f"Validation error: {e.message}", None, status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return custom_response(False, f"Unexpected error: {str(e)}", None, status.HTTP_500_INTERNAL_SERVER_ERROR)


class ExpenseHeadDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            head = ExpenseHead.objects.filter(id=pk).first()
            if not head:
                return custom_response(False, "Expense head not found.", None, status.HTTP_404_NOT_FOUND)
            
            serializer = ExpenseHeadSerializer(head)
            return custom_response(True, "Expense head fetched successfully.", serializer.data, status.HTTP_200_OK)
        except Exception as e:
            return custom_response(False, f"Server Error: {str(e)}", None, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def patch(self, request, pk):
        try:
            head = ExpenseHead.objects.filter(id=pk).first()
            if not head:
                return custom_response(False, "Expense head not found.", None, status.HTTP_404_NOT_FOUND)
            denied = _deny(request, 'edit')
            if denied:
                return denied
            # company আগে বদলানো যেত (অন্য কোম্পানিতে head সরিয়ে দেওয়া) — এখন শুধু নাম আর চালু/বন্ধ
            data = {k: v for k, v in request.data.items() if k in ('name', 'is_active')}
            if 'name' in data:
                data['name'] = (data['name'] or '').strip()
                if ExpenseHead.objects.filter(name__iexact=data['name']).exclude(pk=head.pk).exists():
                    return custom_response(False, "Validation error.", {'name': ['This expense head already exists.']}, status.HTTP_400_BAD_REQUEST)
            serializer = ExpenseHeadSerializer(head, data=data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return custom_response(True, "Expense head updated successfully.", serializer.data, status.HTTP_200_OK)
            return custom_response(False, "Validation error.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return custom_response(False, f"Update failed: {str(e)}", None, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, pk):
        try:
            head = ExpenseHead.objects.filter(id=pk).first()
            if not head:
                return custom_response(False, "Expense head not found.", None, status.HTTP_404_NOT_FOUND)
                
            denied = _deny(request, 'delete')
            if denied:
                return denied
            # খরচ বা sub head থাকলে মুছি না, বন্ধ করি — মুছলে সেই খরচগুলোর head হারিয়ে যেত
            if head.expense_set.exists() or head.subheads.exists():
                head.is_active = False
                head.save(update_fields=['is_active'])
                return custom_response(True, f"{head.name} is in use, so it was turned off instead of deleted.", None, status.HTTP_200_OK)
            head.delete()
            return custom_response(True, "Expense head deleted successfully.", None, status.HTTP_204_NO_CONTENT)
        except IntegrityError as e:
            return custom_response(False, f"Cannot delete: {str(e)}", None, status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return custom_response(False, f"Delete failed: {str(e)}", None, status.HTTP_500_INTERNAL_SERVER_ERROR)


# ------------------------------
# Expense SubHead
# ------------------------------
class ExpenseSubHeadListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            subheads = ExpenseSubHead.objects.filter().select_related('head')
            serializer = ExpenseSubHeadSerializer(subheads, many=True)
            return custom_response(True, "Expense SubHeads fetched successfully.", serializer.data, status.HTTP_200_OK)
        except Exception as e:
            return custom_response(False, f"Server Error: {str(e)}", None, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        denied = _deny(request, 'create')
        if denied:
            return denied
        try:
            data = request.data.copy()
            data['name'] = (data.get('name') or '').strip()
            if data.get('head') and ExpenseSubHead.objects.filter(head_id=data.get('head'), name__iexact=data['name']).exists():
                return custom_response(False, "Validation Error.", {'name': ['This sub head already exists under that head.']}, status.HTTP_400_BAD_REQUEST)
            
            # Validate that head exists and belongs to company
            head_id = data.get('head')
            if head_id:
                head_exists = ExpenseHead.objects.filter(id=head_id).exists()
                if not head_exists:
                    return custom_response(False, "Expense Head not found or .", None, status.HTTP_400_BAD_REQUEST)
            
            serializer = ExpenseSubHeadSerializer(data=data)
            if serializer.is_valid():
                serializer.save(created_by=request.user)  # SUCCESS: Set created_by
                return custom_response(True, "Expense SubHead created successfully.", serializer.data, status.HTTP_201_CREATED)
            return custom_response(False, "Validation Error.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        except IntegrityError as e:
            return custom_response(False, f"Database integrity error: {str(e)}", None, status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return custom_response(False, f"Unexpected error: {str(e)}", None, status.HTTP_500_INTERNAL_SERVER_ERROR)


class ExpenseSubHeadDetailView(APIView):
    permission_classes = [IsAuthenticated]


    def get(self, request, pk):
        try:
            subhead = ExpenseSubHead.objects.filter(id=pk).first()
            if not subhead:
                return custom_response(False, "Expense SubHead not found.", None, status.HTTP_404_NOT_FOUND)
            
            serializer = ExpenseSubHeadSerializer(subhead)
            return custom_response(True, "Expense SubHead fetched successfully.", serializer.data, status.HTTP_200_OK)
        except Exception as e:
            return custom_response(False, f"Server Error: {str(e)}", None, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def patch(self, request, pk):
        try:
            subhead = ExpenseSubHead.objects.filter(id=pk).first()
            if not subhead:
                return custom_response(False, "Expense SubHead not found.", None, status.HTTP_404_NOT_FOUND)
            denied = _deny(request, 'edit')
            if denied:
                return denied
            
            # Validate head if provided in update
            head_id = request.data.get('head')
            if head_id:
                head_exists = ExpenseHead.objects.filter(id=head_id).exists()
                if not head_exists:
                    return custom_response(False, "Expense Head not found or .", None, status.HTTP_400_BAD_REQUEST)
            
            data = {k: v for k, v in request.data.items() if k in ('name', 'head', 'is_active')}
            if 'name' in data:
                data['name'] = (data['name'] or '').strip()
                if ExpenseSubHead.objects.filter(head_id=data.get('head', subhead.head_id), name__iexact=data['name']).exclude(pk=subhead.pk).exists():
                    return custom_response(False, "Validation Error.", {'name': ['This sub head already exists under that head.']}, status.HTTP_400_BAD_REQUEST)
            serializer = ExpenseSubHeadSerializer(subhead, data=data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return custom_response(True, "Expense SubHead updated successfully.", serializer.data, status.HTTP_200_OK)
            return custom_response(False, "Validation Error.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return custom_response(False, f"Update failed: {str(e)}", None, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, pk):
        try:
            subhead = ExpenseSubHead.objects.filter(id=pk).first()
            if not subhead:
                return custom_response(False, "Expense SubHead not found.", None, status.HTTP_404_NOT_FOUND)
            
            denied = _deny(request, 'delete')
            if denied:
                return denied
            if subhead.expense_set.exists():
                subhead.is_active = False
                subhead.save(update_fields=['is_active'])
                return custom_response(True, f"{subhead.name} has expenses, so it was turned off instead of deleted.", None, status.HTTP_200_OK)
                
            subhead.delete()
            return custom_response(True, "Expense SubHead deleted successfully.", None, status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return custom_response(False, f"Delete failed: {str(e)}", None, status.HTTP_500_INTERNAL_SERVER_ERROR)


# ------------------------------
# Expense
# ------------------------------


class ExpenseListView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPageNumberPagination

    def get(self, request):
        denied = _deny(request, 'view')
        if denied:
            return denied
        try:
            # Get query parameters
            page = request.GET.get('page', 1)
            page_size = request.GET.get('page_size', 10)
            search = request.GET.get('search', '')
            start_date = request.GET.get('start_date')
            end_date = request.GET.get('end_date')
            head_id = request.GET.get('head_id')
            subhead_id = request.GET.get('subhead_id')
            payment_method = request.GET.get('payment_method')
            sort_by = request.GET.get('sort_by', 'date_created')
            sort_order = request.GET.get('sort_order', 'desc')

            # Base queryset
            expenses = Expense.objects.filter().select_related('head', 'subhead', 'account')

            # Apply search filter
            if search:
                q = (Q(note__icontains=search) | Q(invoice_number__icontains=search) | Q(head__name__icontains=search)
                     | Q(subhead__name__icontains=search) | Q(payment_method__icontains=search))
                # সংখ্যা হলে টাকার পরিমাণও মেলাই — আগে AND ছিল, তাই "1001" লিখলে EXP-1001 আসত না
                try:
                    q |= Q(amount=float(search.replace(',', '')))
                except (ValueError, TypeError):
                    pass
                expenses = expenses.filter(q)
            account_id = request.GET.get('account_id')
            if account_id:
                expenses = expenses.filter(account_id=account_id)

            # Date range filter
            if start_date and end_date:
                expenses = expenses.filter(expense_date__range=[start_date, end_date])
            elif start_date:
                expenses = expenses.filter(expense_date__gte=start_date)
            elif end_date:
                expenses = expenses.filter(expense_date__lte=end_date)

            # Head and subhead filters
            if head_id:
                expenses = expenses.filter(head_id=head_id)
            if subhead_id:
                expenses = expenses.filter(subhead_id=subhead_id)

            # Payment method filter
            if payment_method:
                expenses = expenses.filter(payment_method__iexact=payment_method)

            # Handle sorting
            valid_sort_fields = [
                'id', 'date_created', 'expense_date', 'amount', 'invoice_number',
                'head__name', 'subhead__name', 'payment_method'
            ]
            
            # Default sorting
            order_by_field = '-date_created'
            
            if sort_by:
                clean_sort_by = sort_by.lstrip('-')
                if clean_sort_by in valid_sort_fields:
                    if sort_order.lower() == 'desc':
                        order_by_field = f'-{clean_sort_by}'
                    else:
                        order_by_field = clean_sort_by
                else:
                    order_by_field = '-date_created'

            expenses = expenses.order_by(order_by_field)

            # Paginate results
            paginator = self.pagination_class()
            paginator.page_size = page_size
            
            try:
                page_number = int(page)
                if page_number < 1:
                    page_number = 1
            except (ValueError, TypeError):
                page_number = 1

            paginated_expenses = paginator.paginate_queryset(expenses, request, view=self)
            
            serializer = ExpenseSerializer(paginated_expenses, many=True)
            
            return paginator.get_paginated_response(serializer.data, "Expenses fetched successfully.")
            
        except Exception as e:
            logger.error(f"Error in ExpenseListView GET: {str(e)}", exc_info=True)
            return custom_response(False, f"Server Error: {str(e)}", None, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        """Handle expense creation - FIXED: Use ExpenseCreateSerializer"""
        denied = _deny(request, 'create')
        if denied:
            return denied
        try:
            data = request.data.copy()
            
            # Validate head and subhead
            head_id = data.get('head')
            if head_id:
                head_exists = ExpenseHead.objects.filter(id=head_id).exists()
                if not head_exists:
                    return custom_response(False, "Expense Head not found.", None, status.HTTP_400_BAD_REQUEST)
            
            subhead_id = data.get('subhead')
            if subhead_id:
                subhead_exists = ExpenseSubHead.objects.filter(id=subhead_id, **({'head_id': head_id} if head_id else {})).exists()
                if not subhead_exists:
                    return custom_response(False, "Pick a sub head that belongs to the chosen head.", {'subhead': ['Pick a sub head under the chosen head.']}, status.HTTP_400_BAD_REQUEST)
            
            # Validate account if provided
            account_id = data.get('account')
            if account_id:
                from accounts.models import Account
                account_exists = Account.objects.filter(id=account_id).exists()
                if not account_exists:
                    return custom_response(False, "Account not found.", None, status.HTTP_400_BAD_REQUEST)
            
            # Use ExpenseCreateSerializer for POST
            serializer = ExpenseCreateSerializer(data=data, context={'request': request})
            if serializer.is_valid():
                expense = serializer.save()
                # Return the full expense data using ExpenseSerializer
                response_serializer = ExpenseSerializer(expense)
                return custom_response(True, "Expense created successfully.", response_serializer.data, status.HTTP_201_CREATED)
            
            return custom_response(False, "Validation Error.", serializer.errors, status.HTTP_400_BAD_REQUEST)
            
        except serializers.ValidationError as e:
            return custom_response(False, "Validation Error.", e.detail, status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error in ExpenseListView POST: {str(e)}", exc_info=True)
            return custom_response(False, f"Unexpected error: {str(e)}", None, status.HTTP_500_INTERNAL_SERVER_ERROR)


class ExpenseDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        denied = _deny(request, 'view')
        if denied:
            return denied
        try:
            expense = Expense.objects.filter(pk=pk).first()
            if not expense:
                return custom_response(False, "Expense not found.", None, status.HTTP_404_NOT_FOUND)
            
            serializer = ExpenseSerializer(expense)
            return custom_response(True, "Expense fetched successfully.", serializer.data, status.HTTP_200_OK)
        except Exception as e:
            return custom_response(False, f"Server Error: {str(e)}", None, status.HTTP_500_INTERNAL_SERVER_ERROR)
    def patch(self, request, pk):
        denied = _deny(request, 'edit')
        if denied:
            return denied
        try:
            expense = Expense.objects.filter(pk=pk).first()
            if not expense:
                return custom_response(False, "Expense not found.", None, status.HTTP_404_NOT_FOUND)

            # Get the data from request
            data = request.data.copy()
            
            # Check if subhead is being sent as string 'null' and convert it to None
            if 'subhead' in data and data['subhead'] == 'null':
                data['subhead'] = None
            
            # Validate head if provided
            head_id = data.get('head')
            if head_id:
                head_exists = ExpenseHead.objects.filter(id=head_id).exists()
                if not head_exists:
                    return custom_response(False, "Expense Head not found.", None, status.HTTP_400_BAD_REQUEST)
            
            # Validate subhead if provided (and not None)
            subhead_id = data.get('subhead')
            if subhead_id:  # This will be False for None, empty string, or 0
                try:
                    # Ensure it's a valid integer
                    subhead_id_int = int(subhead_id)
                    subhead_exists = ExpenseSubHead.objects.filter(id=subhead_id_int).exists()
                    if not subhead_exists:
                        return custom_response(False, "Expense SubHead not found.", None, status.HTTP_400_BAD_REQUEST)
                except (ValueError, TypeError):
                    # If subhead_id is not a valid integer, treat it as null
                    data['subhead'] = None
            
            # Use ExpenseUpdateSerializer for PATCH
            hid = data.get('head', expense.head_id)
            sid = data.get('subhead') if 'subhead' in data else expense.subhead_id
            if sid and hid and not ExpenseSubHead.objects.filter(id=sid, head_id=hid).exists():
                return custom_response(False, "Pick a sub head that belongs to the chosen head.", {'subhead': ['Pick a sub head under the chosen head.']}, status.HTTP_400_BAD_REQUEST)
            acc = data.get('account')
            if acc not in (None, '', 'null'):
                from accounts.models import Account
                if not Account.objects.filter(id=acc).exists():
                    return custom_response(False, "Account not found.", None, status.HTTP_400_BAD_REQUEST)
            serializer = ExpenseUpdateSerializer(expense, data=data, partial=True, context={'request': request})
            if serializer.is_valid():
                try:
                    updated_expense = serializer.save()
                except ValidationError as e:
                    return custom_response(False, ' '.join(e.messages), None, status.HTTP_400_BAD_REQUEST)
                # Return the full updated expense data
                response_serializer = ExpenseSerializer(updated_expense)
                return custom_response(True, "Expense updated successfully.", response_serializer.data, status.HTTP_200_OK)
            return custom_response(False, "Validation Error.", serializer.errors, status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error in ExpenseDetailView PATCH: {str(e)}", exc_info=True)
            return custom_response(False, f"Update failed: {str(e)}", None, status.HTTP_500_INTERNAL_SERVER_ERROR)
    
  
    # def delete(self, request, pk):
    #     try:
    #         company = getattr(request.user, None)
    #         expense = Expense.objects.filter(pk=pk).first()
    #         if not expense:
    #             return custom_response(False, "Expense not found.", None, status.HTTP_404_NOT_FOUND)
            
    #         # Store expense info for logging before deletion
    #         expense_info = f"{expense.invoice_number} - {expense.amount}"
    #         expense.delete()
            
    #         logger.info(f"Expense deleted: {expense_info}")
    #         return custom_response(True, "Expense deleted successfully.", None, status.HTTP_204_NO_CONTENT)
    #     except Exception as e:
    #         logger.error(f"Error in ExpenseDetailView DELETE: {str(e)}", exc_info=True)
    #         return custom_response(False, f"Delete failed: {str(e)}", None, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, pk):
        denied = _deny(request, 'delete')
        if denied:
            return denied
        try:
            expense = Expense.objects.filter(pk=pk).first()
            
            if not expense:
                return custom_response(False, "Expense not found.", None, status.HTTP_404_NOT_FOUND)
            
            # Store info for logging
            expense_info = f"{expense.invoice_number} - {expense.amount}"
            
            # Log before deletion
            logger.info(f"📱 API DELETE Request: Expense {expense_info}")
            
            # THIS IS THE KEY: Just call expense.delete() - let the MODEL handle the logic
            expense.delete()
            
            logger.info(f"✅ Expense deleted successfully: {expense_info}")
            return custom_response(True, f"{expense_info.split(' - ')[0]} deleted. The money went back to the account.", None, status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"❌ Error in ExpenseDetailView DELETE: {str(e)}", exc_info=True)
            return custom_response(False, f"Delete failed: {str(e)}", None, status.HTTP_500_INTERNAL_SERVER_ERROR)


class ExpenseSummaryView(APIView):
    """খরচের মোট আর head/account অনুযায়ী ভাগ — list এর একই filter মেনে"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        denied = _deny(request, 'view')
        if denied:
            return denied
        from django.db.models import Count, Sum
        qs = Expense.objects.filter()
        p = request.GET
        search = (p.get('search') or '').strip()
        if search:
            q = Q(note__icontains=search) | Q(invoice_number__icontains=search) | Q(head__name__icontains=search) | Q(subhead__name__icontains=search)
            try:
                q |= Q(amount=float(search.replace(',', '')))
            except ValueError:
                pass
            qs = qs.filter(q)
        if p.get('start_date'):
            qs = qs.filter(expense_date__gte=p['start_date'])
        if p.get('end_date'):
            qs = qs.filter(expense_date__lte=p['end_date'])
        if p.get('head_id'):
            qs = qs.filter(head_id=p['head_id'])
        if p.get('subhead_id'):
            qs = qs.filter(subhead_id=p['subhead_id'])
        if p.get('account_id'):
            qs = qs.filter(account_id=p['account_id'])
        tot = qs.aggregate(total=Sum('amount'), count=Count('id'))
        by_head = qs.values('head_id', 'head__name').annotate(total=Sum('amount'), count=Count('id')).order_by('-total')
        by_account = qs.values('account_id', 'account__name').annotate(total=Sum('amount')).order_by('-total')
        return custom_response(True, "Expense summary", {
            'total': str(tot['total'] or 0), 'count': tot['count'],
            'by_head': [{'id': r['head_id'], 'name': r['head__name'] or 'No head', 'total': str(r['total']), 'count': r['count']} for r in by_head],
            'by_account': [{'id': r['account_id'], 'name': r['account__name'] or 'No account', 'total': str(r['total'])} for r in by_account],
        }, status.HTTP_200_OK)
