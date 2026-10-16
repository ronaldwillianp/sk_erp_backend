from django.db import transaction
from django.db.models import Sum
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import models as db_models
from django.db.models import Count, Sum
from decimal import Decimal
from django.db import transaction
from .models import Customer, Invoice, InvoiceItem
from .serializers import (
    CustomerSerializer, InvoiceSerializer, InvoiceCreateSerializer
)
from inventory.models import Product, ProductPresentation, ProductWarehouseStock, StockMovement


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [permissions.IsAuthenticated]
    search_fields = ['name', 'email', 'phone', 'nit']
    filterset_fields = ['enabled']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']


class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.select_related(
        'customer', 'created_by'
    ).prefetch_related('items__product', 'items__presentation', 'items__warehouse')
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['status', 'customer']
    search_fields = ['number', 'customer__name']
    ordering_fields = ['created_at', 'total', 'status']
    ordering = ['-created_at']

    @action(detail=False, methods=['post'], url_path='create-with-items')
    def create_with_items(self, request):
        """
        Crea una factura con sus líneas y descuenta stock automáticamente.
        """
        serializer = InvoiceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            customer = Customer.objects.get(id=data['customer_id'])
        except Customer.DoesNotExist:
            return Response({'error': 'Cliente no encontrado'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # Crear factura
            invoice = Invoice.objects.create(
                customer=customer,
                due_date=data.get('due_date'),
                notes=data.get('notes', ''),
                created_by=request.user,
                status='DRAFT',
            )

            subtotal = Decimal('0')

            # Crear líneas y descontar stock
            for item_data in data['items']:
                product = Product.objects.get(id=item_data['product_id'])
                presentation = ProductPresentation.objects.get(id=item_data['presentation_id'])
                warehouse_id = item_data['warehouse_id']

                # ✅ Convertir todo a Decimal
                quantity = Decimal(str(item_data['quantity']))
                unit_price = Decimal(str(item_data.get('unit_price', product.sale_price)))
                discount_pct = Decimal(str(item_data.get('discount_percent', 0)))

                # Verificar stock disponible
                stock_record = ProductWarehouseStock.objects.filter(
                    product=product,
                    warehouse_id=warehouse_id,
                    presentation=presentation,
                ).first()

                available = stock_record.quantity if stock_record else Decimal('0')
                if available < quantity:
                    return Response({
                        'error': f'Stock insuficiente para {product.name}. Disponible: {available}, solicitado: {quantity}'
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Crear línea de factura
                line = InvoiceItem.objects.create(
                    invoice=invoice,
                    product=product,
                    presentation=presentation,
                    warehouse_id=warehouse_id,
                    quantity=quantity,
                    unit_price=unit_price,
                    discount_percent=discount_pct,
                )
                subtotal += line.line_total  # line_total ya es Decimal (viene del modelo)

                # ✅ Descontar stock (Decimal -= Decimal)
                stock_record.quantity -= quantity
                if stock_record.quantity <= 0:
                    stock_record.delete()
                else:
                    stock_record.save()

                # Registrar movimiento de salida
                StockMovement.objects.create(
                    movement_type='EXIT',
                    product=product,
                    presentation=presentation,
                    warehouse_id=warehouse_id,
                    quantity=quantity,
                    unit_cost=Decimal(str(product.cost_price)),
                    reference=f"Venta {invoice.number}",
                    user=request.user,
                )

            # ✅ Actualizar totales de factura (Decimal)
            invoice.subtotal = subtotal
            invoice.tax_total = Decimal('0')  # TODO: calcular impuestos
            invoice.total = subtotal + invoice.tax_total
            invoice.save()

        return Response(
            InvoiceSerializer(invoice).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['post'], url_path='change-status')
    def change_status(self, request, pk=None):
        """Cambia el estado de la factura con validaciones y reversión de stock"""
        invoice = self.get_object()
        new_status = request.data.get('status')

        valid_statuses = [s[0] for s in Invoice.STATUS_CHOICES]
        if new_status not in valid_statuses:
            return Response(
                {'error': f'Estado inválido. Use: {", ".join(valid_statuses)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Definir transiciones válidas de estado
        VALID_TRANSITIONS = {
            'DRAFT': ['SENT', 'CANCELLED'],
            'SENT': ['PAID', 'PARTIAL', 'OVERDUE', 'CANCELLED'],
            'OVERDUE': ['PAID', 'PARTIAL', 'CANCELLED'],
            'PARTIAL': ['PAID', 'CANCELLED'],
            'PAID': [],  # No se puede cambiar después de pagar
            'CANCELLED': [],  # No se puede cambiar después de cancelar
        }

        if new_status not in VALID_TRANSITIONS.get(invoice.status, []):
            return Response(
                {'error': f'No se puede cambiar de {invoice.status} a {new_status}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            # Si se cancela, restaurar stock
            if new_status == 'CANCELLED':
                for item in invoice.items.all():
                    stock, created = ProductWarehouseStock.objects.get_or_create(
                        product=item.product,
                        warehouse=item.warehouse,
                        presentation=item.presentation,
                        defaults={
                            'quantity': Decimal('0'),
                            'total_value': Decimal('0')
                        }
                    )
                    
                    # Restaurar cantidad
                    stock.quantity += item.quantity
                    
                    # Recalcular valor total del stock
                    # Usar el costo promedio actual del producto si existe
                    if stock.quantity > Decimal('0'):
                        current_avg_cost = Decimal(str(item.product.cost_price))
                        stock.total_value = stock.quantity * current_avg_cost
                    
                    stock.save()

                    # Movimiento de entrada (reversión)
                    StockMovement.objects.create(
                        movement_type='ENTRY',
                        product=item.product,
                        presentation=item.presentation,
                        warehouse=item.warehouse,
                        quantity=item.quantity,
                        unit_cost=Decimal(str(item.product.cost_price)),
                        reference=f"Cancelación {invoice.number}",
                        user=request.user,
                    )

            invoice.status = new_status
            invoice.save()

        return Response(InvoiceSerializer(invoice).data)

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """Resumen de ventas"""
        qs = Invoice.objects.exclude(status='CANCELLED')
        totals = qs.aggregate(
            total_sales=Sum('total'),
            total_paid=Sum('paid_amount'),
            count=Count('id'),  # conteo aproximado
        )
        by_status = list(qs.values('status').annotate(count=Count('id'), total=Sum('total')))

        return Response({
            'total_sales': float(totals['total_sales'] or 0),
            'total_paid': float(totals['total_paid'] or 0),
            'pending': float(totals['total_sales'] or 0) - float(totals['total_paid'] or 0),
            'by_status': by_status,
        })