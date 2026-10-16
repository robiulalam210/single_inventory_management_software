from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BranchViewSet, WarehouseViewSet

router = DefaultRouter()
router.register(r'branches', BranchViewSet)
router.register(r'warehouses', WarehouseViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
