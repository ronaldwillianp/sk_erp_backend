from django.db import transaction
from django.db.models import Sum, Count
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from decimal import Decimal
from django.utils import timezone
from .models import Customer, Invoice, InvoiceItem
from .serializers import (
    CustomerSerializer, InvoiceSerializer, InvoiceCreateSerializer
)
from inventory.models import (
    Product, ProductPresentation, ProductWarehouseStock, StockMovement, 
    StockDocument, StockDocumentLine
)


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
        Crea una factura, su vale asociado, procesa pagos y descuenta stock.
        Todo dentro de una transacción atómica.
        """
        serializer = InvoiceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            customer = Customer.objects.get(id=data['customer_id'])
        except Customer.DoesNotExist:
            return Response({'error': 'Cliente no encontrado'}, status=status.HTTP_400_BAD_REQUEST)

        # Determinar estado inicial
        initial_status = data.get('status', 'DRAFT')
        valid_statuses = [s[0] for s in Invoice.STATUS_CHOICES]
        if initial_status not in valid_statuses:
            initial_status = 'DRAFT'

        # Validar Cash Register si se proporciona
        cash_register = None
        if data.get('cash_register_id'):
            from pos.models import CashRegister
            try:
                cash_register = CashRegister.objects.get(
                    id=data['cash_register_id'],
                    status='OPEN'
                )
            except CashRegister.DoesNotExist:
                return Response(
                    {'error': 'La caja seleccionada no existe o está cerrada'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        issue_date = data.get('issue_date') or timezone.now().date()

        with transaction.atomic():
            # 1. Crear Factura
            invoice = Invoice.objects.create(
                customer=customer,
                issue_date=issue_date,
                due_date=data.get('due_date'),
                notes=data.get('notes', ''),
                created_by=request.user,
                status=initial_status,
                cash_register=cash_register,  # <-- NUEVO: Vincular con la caja
            )

            subtotal = Decimal('0')
            items_created = []

            # 2. Procesar líneas y validar stock
            for item_data in data['items']:
                product = Product.objects.get(id=item_data['product_id'])
                presentation = ProductPresentation.objects.get(id=item_data['presentation_id'])
                warehouse_id = item_data['warehouse_id']

                quantity = Decimal(str(item_data['quantity']))
                unit_price = Decimal(str(item_data.get('unit_price', product.sale_price)))
                
                # Verificar stock
                stock_record = ProductWarehouseStock.objects.filter(
                    product=product,
                    warehouse_id=warehouse_id,
                    presentation=presentation,
                ).first()

                available = stock_record.quantity if stock_record else Decimal('0')
                if available < quantity:
                    raise Exception(f'Stock insuficiente para {product.name}. Disponible: {available}, solicitado: {quantity}')

                # Crear línea de factura
                line = InvoiceItem.objects.create(
                    invoice=invoice,
                    product=product,
                    presentation=presentation,
                    warehouse_id=warehouse_id,
                    quantity=quantity,
                    unit_price=unit_price,
                    discount_percent=Decimal(str(item_data.get('discount_percent', 0))),
                )
                subtotal += line.line_total
                items_created.append({
                    'product': product,
                    'presentation': presentation,
                    'warehouse_id': warehouse_id,
                    'quantity': quantity,
                    'unit_cost': Decimal(str(product.cost_price)),
                })

            # Actualizar totales básicos
            invoice.subtotal = subtotal
            invoice.tax_total = Decimal('0')
            invoice.total = subtotal
            
            # 3. Procesar Pagos (si el estado inicial es PAID o hay pagos definidos)
            payments_data = data.get('payments', [])
            total_paid = Decimal('0')
            
            if payments_data:
                from pos.models import InvoicePayment
                
                for payment_data in payments_data:
                    InvoicePayment.objects.create(
                        invoice=invoice,
                        payment_method_id=payment_data['payment_method_id'],
                        amount=Decimal(str(payment_data['amount'])),
                        reference=payment_data.get('reference', ''),
                    )
                    total_paid += Decimal(str(payment_data['amount']))
                
                invoice.paid_amount = total_paid
                
                # Ajustar estado final según lo pagado
                if total_paid >= invoice.total:
                    invoice.status = 'PAID'
                elif total_paid > 0:
                    invoice.status = 'PARTIAL'
                # Si total_paid es 0, se mantiene el status inicial (ej. DRAFT o SENT)
            
            invoice.save()

            # 4. Generar Vale de Salida (StockDocument) asociado a la factura
            doc_ref = f"Factura {invoice.number}"
            
            stock_doc = StockDocument.objects.create(
                document_type='EXIT',
                warehouse_id=data['items'][0]['warehouse_id'],
                reference=doc_ref,
                notes=f"Generado automáticamente por factura {invoice.number}",
                created_by=request.user,
            )

            # 5. Aplicar movimientos de stock y líneas del vale
            for item_info in items_created:
                product = item_info['product']
                presentation = item_info['presentation']
                warehouse_id = item_info['warehouse_id']
                quantity = item_info['quantity']
                unit_cost = item_info['unit_cost']

                # A. Crear línea del vale
                StockDocumentLine.objects.create(
                    document=stock_doc,
                    product=product,
                    presentation=presentation,
                    quantity=quantity,
                    unit_cost=unit_cost,
                )

                # B. Descontar stock físicamente
                stock_record = ProductWarehouseStock.objects.get(
                    product=product,
                    warehouse_id=warehouse_id,
                    presentation=presentation,
                )
                stock_record.quantity -= quantity
                if stock_record.quantity <= 0:
                    stock_record.delete()
                else:
                    stock_record.save()

                # C. Registrar movimiento individual
                StockMovement.objects.create(
                    movement_type='EXIT',
                    product=product,
                    presentation=presentation,
                    warehouse_id=warehouse_id,
                    quantity=quantity,
                    unit_cost=unit_cost,
                    reference=doc_ref,
                    user=request.user,
                )

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

        VALID_TRANSITIONS = {
            'DRAFT': ['SENT', 'CANCELLED', 'PAID'],
            'SENT': ['PAID', 'PARTIAL', 'OVERDUE', 'CANCELLED'],
            'OVERDUE': ['PAID', 'PARTIAL', 'CANCELLED'],
            'PARTIAL': ['PAID', 'CANCELLED'],
            'PAID': [],
            'CANCELLED': [],
        }

        if new_status not in VALID_TRANSITIONS.get(invoice.status, []):
            return Response(
                {'error': f'No se puede cambiar de {invoice.status} a {new_status}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            if new_status == 'CANCELLED':
                # 1. Restaurar stock
                for item in invoice.items.all():
                    stock, created = ProductWarehouseStock.objects.get_or_create(
                        product=item.product,
                        warehouse=item.warehouse,
                        presentation=item.presentation,
                        defaults={'quantity': Decimal('0'), 'total_value': Decimal('0')}
                    )
                    stock.quantity += item.quantity
                    if stock.quantity > Decimal('0'):
                        current_avg_cost = Decimal(str(item.product.cost_price))
                        stock.total_value = stock.quantity * current_avg_cost
                    stock.save()

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
                
                # 2. Eliminar el vale de salida asociado (si existe)
                from inventory.models import StockDocument
                related_doc = StockDocument.objects.filter(
                    reference=f"Factura {invoice.number}",
                    document_type='EXIT'
                ).first()
                
                if related_doc:
                    related_doc.delete()
            
            # Si se marca como PAGADA, podríamos generar la transacción financiera aquí (futuro)
            
            invoice.status = new_status
            invoice.save()

        return Response(InvoiceSerializer(invoice).data)

    def destroy(self, request, *args, **kwargs):
        """
        Elimina físicamente una factura y TODOS sus registros asociados:
        - Movimientos de stock generados por la factura
        - Vale (StockDocument) asociado
        - Restaura el stock al inventario
        
        ⚠️ ACCIÓN DE ADMINISTRADOR - No deja rastro histórico
        """
        invoice = self.get_object()

        # Validaciones de seguridad
        if invoice.status == 'PAID':
            return Response(
                {'error': 'No se puede eliminar una factura pagada. Cancélela primero.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verificar consecutivos
        try:
            current_seq = int(invoice.number.split('-')[1])
            next_invoices = Invoice.objects.filter(number__regex=r'^FAC-\d+$').exclude(pk=invoice.pk)
            has_later_invoices = False
            for inv in next_invoices:
                try:
                    seq = int(inv.number.split('-')[1])
                    if seq > current_seq:
                        has_later_invoices = True
                        break
                except:
                    continue
            
            if has_later_invoices:
                return Response({
                    'error': 'No se puede eliminar esta factura porque existen facturas con números posteriores.'
                }, status=status.HTTP_400_BAD_REQUEST)
        except:
            pass

        with transaction.atomic():
            # 1. Borrar movimientos de stock asociados a esta factura
            # ⚠️ IMPORTANTE: La referencia debe coincidir con la que se usa en create_with_items
            # En create_with_items se usa: doc_ref = f"Factura {invoice.number}"
            movements_deleted, _ = StockMovement.objects.filter(
                reference=f"Factura {invoice.number}"  # ✅ Cambiado de "Venta" a "Factura"
            ).delete()

            # 2. Borrar vale (StockDocument) asociado
            documents_deleted, _ = StockDocument.objects.filter(
                reference=f"Factura {invoice.number}"
            ).delete()

            # 3. Restaurar stock físicamente (sin crear movimientos de reversión)
            for item in invoice.items.all():
                stock, created = ProductWarehouseStock.objects.get_or_create(
                    product=item.product,
                    warehouse=item.warehouse,
                    presentation=item.presentation,
                    defaults={'quantity': Decimal('0'), 'total_value': Decimal('0')}
                )
                stock.quantity += item.quantity
                if stock.quantity > Decimal('0'):
                    stock.total_value = stock.quantity * Decimal(str(item.product.cost_price))
                stock.save()

            # 4. Eliminar factura (las líneas se borran en cascada)
            invoice.delete()

        return Response(
            {
                'message': f'Factura {invoice.number} eliminada. Stock restaurado. '
                           f'Se borraron {movements_deleted} movimientos y {documents_deleted} vales asociados.',
            },
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        qs = Invoice.objects.exclude(status='CANCELLED')
        totals = qs.aggregate(
            total_sales=Sum('total'),
            total_paid=Sum('paid_amount'),
            count=Count('id'),
        )
        by_status = list(qs.values('status').annotate(count=Count('id'), total=Sum('total')))

        return Response({
            'total_sales': float(totals['total_sales'] or 0),
            'total_paid': float(totals['total_paid'] or 0),
            'pending': float(totals['total_sales'] or 0) - float(totals['total_paid'] or 0),
            'by_status': by_status,
        })