from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .viewsets import (
    WarehouseViewSet, SupplierViewSet, ProductViewSet,
    StockViewSet, ConversionViewSet, StockMovementViewSet
)
from .views import download_template, import_data

router = SimpleRouter()
router.register(r'warehouses', WarehouseViewSet, basename='warehouse')
router.register(r'suppliers', SupplierViewSet, basename='supplier')
router.register(r'products', ProductViewSet, basename='product')
router.register(r'stock', StockViewSet, basename='stock')
router.register(r'conversions', ConversionViewSet, basename='conversion')
router.register(r'movements', StockMovementViewSet, basename='movement')

urlpatterns = [
    path('', include(router.urls)),
    path('import/template/<str:import_type>/', download_template, name='import-template'),
    path('import/<str:import_type>/', import_data, name='import-data'),
]