# core/base_viewsets.py
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework.response import Response
from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
import logging
from rest_framework import viewsets, serializers

from rest_framework import viewsets, status
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
import logging

logger = logging.getLogger(__name__)

class ReportPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000

class BaseReportView(APIView):
    permission_classes = [IsAuthenticated]
    filter_serializer_class = None
    cache_timeout = 300
    pagination_class = ReportPagination
    
    def get_filters(self, request):
        """Validate and return filters"""
        if self.filter_serializer_class:
            serializer = self.filter_serializer_class(data=request.GET)
            serializer.is_valid(raise_exception=True)
            return serializer.validated_data
        return {}
    
    def get_date_range(self, request):
        """Get date range with predefined range support"""
        from reports.utils import get_date_range, get_predefined_range
        
        # Check for predefined ranges first
        start, end = get_predefined_range(request)
        if start and end:
            return start, end
        
        # Fall back to custom date range
        return get_date_range(request)
    
    def paginate_data(self, data):
        """Paginate data if pagination class is set"""
        if self.pagination_class and isinstance(data, list):
            paginator = self.pagination_class()
            page = paginator.paginate_queryset(data, self.request)
            if page is not None:
                return paginator.get_paginated_response(page).data
        return data
    
    def handle_exception(self, exc):
        """Standard exception handling"""
        logger.error(f"Report error: {str(exc)}", exc_info=True)
        from reports.utils import custom_response
        return custom_response(False, str(exc), None, 400)
    

class BaseViewSet(viewsets.ModelViewSet):
    """লগইন করা ইউজার ছাড়া কিছু দেখায় না; তৈরির সময় created_by বসায়।"""

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.is_authenticated:
            return queryset.none()
        return queryset

    def perform_create(self, serializer):
        if not self.request.user.is_authenticated:
            raise serializers.ValidationError("User must be authenticated")
        serializer.save(created_by=self.request.user)


class BaseInventoryViewSet(viewsets.ModelViewSet):
    """
    Base ViewSet for all inventory models with common functionality
    """
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    ordering = ['-created_at']  # Default ordering
    
    def get_queryset(self):
        """
        Base queryset that handles active/inactive
        Override in child classes for specific needs
        """
        queryset = super().get_queryset()

        # Handle active/inactive filtering from URL parameters
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            if is_active.lower() in ['true', '1', 'yes']:
                queryset = queryset.filter(is_active=True)
            elif is_active.lower() in ['false', '0', 'no']:
                queryset = queryset.filter(is_active=False)
        
        return queryset

    def perform_create(self, serializer):
        """
        Automatically set created_by for new objects
        """
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        """
        Automatically set updated_by for modified objects
        """
        serializer.save(updated_by=self.request.user)
