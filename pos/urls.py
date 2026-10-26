# pos/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .viewsets import CashRegisterViewSet, WarehouseUserViewSet, MyWarehousesViewSet

router = DefaultRouter()
router.register(r'cash-registers', CashRegisterViewSet, basename='cash-register')
router.register(r'warehouse-users', WarehouseUserViewSet, basename='warehouse-user')
router.register(r'my-warehouses', MyWarehousesViewSet, basename='my-warehouse')

urlpatterns = [
    path('', include(router.urls)),
]