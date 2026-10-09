from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .viewsets import CustomerViewSet, InvoiceViewSet

router = SimpleRouter()
router.register(r'customers', CustomerViewSet, basename='customer')
router.register(r'invoices', InvoiceViewSet, basename='invoice')

urlpatterns = [
    path('', include(router.urls)),
]