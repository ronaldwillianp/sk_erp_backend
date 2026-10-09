from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .viewsets import (
    ProvinceViewSet,
    MunicipalityViewSet,
    MeasureUnitViewSet,
    CurrencyViewSet,
    PaymentMethodViewSet,
    CategoryViewSet,
    CompanyViewSet
)

router = SimpleRouter()
router.register(r'provinces', ProvinceViewSet, basename='province')
router.register(r'municipalities', MunicipalityViewSet, basename='municipality')
router.register(r'measure-units', MeasureUnitViewSet, basename='measure-unit')
router.register(r'currencies', CurrencyViewSet, basename='currency')
router.register(r'payment-methods', PaymentMethodViewSet, basename='payment-method')
router.register(r'company', CompanyViewSet, basename='company')
router.register(r'categories', CategoryViewSet, basename='category')

urlpatterns = [
    path('', include(router.urls)),
]

# ============================================
# ENDPOINTS DISPONIBLES
# ============================================
#
# --- PROVINCIAS ---
# GET    /api/configuration/provinces/                        → Listar todas
# GET    /api/configuration/provinces/enabled/                → Solo habilitadas
# POST   /api/configuration/provinces/                        → Crear
# GET    /api/configuration/provinces/{id}/                   → Detalle
# PUT    /api/configuration/provinces/{id}/                   → Actualizar completa
# PATCH  /api/configuration/provinces/{id}/                   → Actualizar parcial
# DELETE /api/configuration/provinces/{id}/                   → Eliminar
# GET    /api/configuration/provinces/{id}/municipalities/    → Municipios de la provincia
#
# --- MUNICIPIOS ---
# GET    /api/configuration/municipalities/                   → Listar todos
# GET    /api/configuration/municipalities/?province_id=9     → Filtrar por provincia
# POST   /api/configuration/municipalities/                   → Crear
# GET    /api/configuration/municipalities/{id}/              → Detalle
# PUT    /api/configuration/municipalities/{id}/              → Actualizar completo
# PATCH  /api/configuration/municipalities/{id}/              → Actualizar parcial
# DELETE /api/configuration/municipalities/{id}/              → Eliminar
#
# --- UNIDADES DE MEDIDA ---
# GET    /api/configuration/measure-units/                    → Listar todas
# POST   /api/configuration/measure-units/                    → Crear
# GET    /api/configuration/measure-units/{id}/               → Detalle
# PUT    /api/configuration/measure-units/{id}/               → Actualizar completa
# PATCH  /api/configuration/measure-units/{id}/               → Actualizar parcial
# DELETE /api/configuration/measure-units/{id}/               → Eliminar
#
# --- MONEDAS ---
# GET    /api/configuration/currencies/                       → Listar todas
# GET    /api/configuration/currencies/default/               → Moneda por defecto
# POST   /api/configuration/currencies/                       → Crear
# GET    /api/configuration/currencies/{id}/                  → Detalle
# PUT    /api/configuration/currencies/{id}/                  → Actualizar completa
# PATCH  /api/configuration/currencies/{id}/                  → Actualizar parcial
# DELETE /api/configuration/currencies/{id}/                  → Eliminar
#
# --- MÉTODOS DE PAGO ---
# GET    /api/configuration/payment-methods/                  → Listar todos
# POST   /api/configuration/payment-methods/                  → Crear
# GET    /api/configuration/payment-methods/{id}/             → Detalle
# PUT    /api/configuration/payment-methods/{id}/             → Actualizar completo
# PATCH  /api/configuration/payment-methods/{id}/             → Actualizar parcial
# DELETE /api/configuration/payment-methods/{id}/             → Eliminar
#