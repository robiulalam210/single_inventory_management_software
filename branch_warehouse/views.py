from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from .model import Branch, Warehouse
from .serializers import (
    BranchSerializer, WarehouseSerializer
   
)

# Branch & Warehouse
class BranchViewSet(viewsets.ModelViewSet):
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'code', 'address']
    ordering_fields = ['name', 'code']


class WarehouseViewSet(viewsets.ModelViewSet):
    queryset = Warehouse.objects.select_related('branch').all()
    serializer_class = WarehouseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'location', 'branch__name']
    ordering_fields = ['name']

