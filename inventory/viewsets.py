from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from decimal import Decimal
from django.db import transaction
from django.utils.dateparse import parse_date
from .utils import reset_sequence
from django.db.models import Sum, Count, F, ExpressionWrapper, DecimalField, Case, When, Value, CharField, F, Sum, Exists, OuterRef, Q
from django.db.models.functions import Coalesce
from .label_generator import generate_product_labels
from django.http import HttpResponse
from rest_framework.exceptions import ValidationError

from .models import (
    Product, Warehouse, Supplier, ProductPresentation, ProductWarehouseStock, StockMovement, StockDocument, StockDocumentLine
)

from .serializers import (
    ProductSerializer, WarehouseSerializer, SupplierSerializer,
    ProductWarehouseStockSerializer, ConversionSerializer, StockMovementSerializer, StockDocumentSerializer, StockDocumentCreateSerializer
)

class WarehouseViewSet(viewsets.ModelViewSet):
    queryset = Warehouse.objects.select_related('province', 'municipality').order_by('name')
    serializer_class = WarehouseSerializer
    permission_classes = [permissions.IsAuthenticated]

    # Búsqueda y filtros
    search_fields = ['name', 'code', 'address']
    ordering_fields = ['name', 'code', 'warehouse_type', 'enabled']
    ordering = ['name']
    filterset_fields = ['warehouse_type', 'enabled', 'province', 'municipality']

    @action(detail=False, methods=['get'], url_path='enabled')
    def enabled(self, request):
        """
        Almacenes habilitados, opcionalmente filtrados por tipo.
        Útil para selects en otros módulos.
        Ej: /warehouses/enabled/?warehouse_type=POINT_OF_SALE
        """
        queryset = self.get_queryset().filter(enabled=True)
        warehouse_type = request.query_params.get('warehouse_type', None)
        if warehouse_type:
            queryset = queryset.filter(warehouse_type=warehouse_type)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='default')
    def default_warehouse(self, request):
        """Devuelve el almacén por defecto"""
        warehouse = self.get_queryset().filter(is_default=True).first()
        if not warehouse:
            return Response(
                {'detail': 'No hay almacén por defecto'},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = self.get_serializer(warehouse)
        return Response(serializer.data)

    @action(detail=True, methods=['put'], url_path='set-default')
    def set_default(self, request, pk=None):
        """Marcar un almacén como default (desmarca los demás)"""
        warehouse = self.get_object()
        Warehouse.objects.filter(is_default=True).exclude(pk=warehouse.pk).update(is_default=False)
        warehouse.is_default = True
        warehouse.save()
        serializer = self.get_serializer(warehouse)
        return Response(serializer.data)

class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.select_related('province').order_by('name')
    serializer_class = SupplierSerializer
    permission_classes = [permissions.IsAuthenticated]

    # Búsqueda y filtros
    search_fields = ['name', 'contact_person', 'email', 'phone', 'address']
    ordering_fields = ['name', 'enabled']
    ordering = ['name']
    filterset_fields = ['enabled', 'province']

    @action(detail=False, methods=['get'], url_path='enabled')
    def enabled(self, request):
        """
        Proveedores habilitados.
        Útil para selects en otros módulos (Compras).
        """
        queryset = self.get_queryset().filter(enabled=True)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.select_related('category').prefetch_related(
        'presentations__measure_unit'
    ).order_by('name')
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    # Búsqueda y filtros
    search_fields = ['name', 'sku', 'barcode']
    ordering_fields = ['name', 'sku', 'sale_price', 'enabled']
    ordering = ['name']
    filterset_fields = ['category', 'enabled', 'is_service']

    @action(detail=False, methods=['get'], url_path='enabled')
    def enabled(self, request):
        """
        Productos habilitados, opcionalmente filtrados.
        Útil para selects en Ventas.
        """
        queryset = self.get_queryset().filter(enabled=True)
        is_service = request.query_params.get('is_service', None)
        if is_service is not None:
            queryset = queryset.filter(is_service=(is_service == 'true'))
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['delete'], url_path='purge')
    def purge(self, request):
        """
        Elimina TODOS los productos, presentaciones, stock, movimientos y vales.
        Reinicia los IDs desde 1. Acción destructiva total.
        """
        from .models import (
            StockDocumentLine, StockDocument, StockMovement,
            ProductWarehouseStock, ProductPresentation, Product
        )
        
        try:
            with transaction.atomic():
                # 1. Eliminar líneas de documentos de stock (dependen de Product)
                StockDocumentLine.objects.all().delete()
                
                # 2. Eliminar documentos de stock (vales)
                StockDocument.objects.all().delete()
                
                # 3. Eliminar movimientos de inventario
                StockMovement.objects.all().delete()
                
                # 4. Eliminar stock por almacén
                ProductWarehouseStock.objects.all().delete()
                
                # 5. Eliminar presentaciones (dependen de Product)
                ProductPresentation.objects.all().delete()
                
                # 6. Eliminar productos
                Product.objects.all().delete()
                
                # 7. Reiniciar secuencias de IDs (PostgreSQL)
                from django.db import connection
                with connection.cursor() as cursor:
                    tables_to_reset = [
                        'inventory_product',
                        'inventory_productpresentation',
                        'inventory_productwarehousestock',
                        'inventory_stockmovement',
                        'inventory_stockdocument',
                        'inventory_stockdocumentline',
                    ]
                    for table in tables_to_reset:
                        try:
                            cursor.execute(
                                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), 1, false)"
                            )
                        except Exception:
                            pass  # Ignorar si la tabla no existe o no es PostgreSQL
                
                return Response({
                    'message': 'Todos los productos, presentaciones, stock, movimientos y vales han sido eliminados. IDs reiniciados desde 1.',
                    'status': 'success'
                })
                
        except Exception as e:
            return Response(
                {'error': f'Error al purgar productos: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'], url_path='generate-labels')
    def generate_labels(self, request):
        """
        Genera un PDF con etiquetas de productos seleccionados.
        Body: { "product_ids": [1, 2, 3] }
        """
        product_ids = request.data.get('product_ids', [])
        
        if not product_ids or not isinstance(product_ids, list):
            return Response(
                {'error': 'Debe proporcionar una lista de product_ids'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            pdf_buffer = generate_product_labels(product_ids)
            
            response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="etiquetas_productos.pdf"'
            return response
            
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {'error': f'Error generando etiquetas: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], url_path='with-stock')
    def with_stock(self, request):
        """
        Devuelve productos que tienen stock > 0 en un almacén específico.
        Query params:
        - warehouse: ID del almacén (requerido)
        - is_service: filtrar por tipo (opcional)
        """
        warehouse_id = request.query_params.get('warehouse')
        is_service = request.query_params.get('is_service')
        
        if not warehouse_id:
            return Response(
                {'error': 'El parámetro warehouse es requerido'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Subquery para verificar si existe stock > 0 en ese almacén
        stock_exists = ProductWarehouseStock.objects.filter(
            product=OuterRef('pk'),
            warehouse_id=warehouse_id,
            quantity__gt=0
        )
        
        # Filtrar productos que tienen stock en ese almacén
        queryset = Product.objects.filter(
            Exists(stock_exists),
            enabled=True
        )
        
        # Filtrar por tipo si se especifica
        if is_service is not None:
            is_service_bool = is_service.lower() in ('true', '1', 'yes')
            queryset = queryset.filter(is_service=is_service_bool)
        
        # Aplicar búsqueda y ordenamiento estándar
        search = request.query_params.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(sku__icontains=search) | Q(barcode__icontains=search)
            )
        
        # Paginación
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ProductSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = ProductSerializer(queryset, many=True)
        return Response(serializer.data)

class StockViewSet(viewsets.ReadOnlyModelViewSet):
    """Consulta de stock actual por producto/almacén/presentación"""
    queryset = ProductWarehouseStock.objects.select_related(
        'product', 'warehouse', 'presentation__measure_unit'
    ).filter(quantity__gt=0).order_by('product__name', 'warehouse__name', '-presentation__conversion_factor')
    serializer_class = ProductWarehouseStockSerializer
    permission_classes = [permissions.IsAuthenticated]

    filterset_fields = ['product', 'warehouse', 'presentation']
    search_fields = ['product__name', 'product__sku']
    ordering_fields = ['warehouse__name', 'product__name', 'quantity', 'total_value', 'average_cost']
    ordering = ['warehouse__name', 'product__name']

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """
        Resumen del inventario: totales generales y por almacén.
        """
        stock_qs = ProductWarehouseStock.objects.filter(quantity__gt=0).select_related(
            'warehouse', 'product'
        )

        # Totales generales
        totals = stock_qs.aggregate(
            total_value=Sum('total_value'),
            total_quantity=Sum('quantity'),
            unique_products=Count('product', distinct=True),
            unique_warehouses=Count('warehouse', distinct=True),
        )

        # Totales por almacén
        by_warehouse = list(
            stock_qs.values(
                'warehouse__id', 'warehouse__name', 'warehouse__code',
                'warehouse__warehouse_type'
            ).annotate(
                total_value=Sum('total_value'),
                total_quantity=Sum('quantity'),
                products_count=Count('product', distinct=True),
            ).order_by('warehouse__name')
        )

        return Response({
            'totals': {
                'total_value': totals['total_value'] or 0,
                'total_quantity': totals['total_quantity'] or 0,
                'unique_products': totals['unique_products'] or 0,
                'unique_warehouses': totals['unique_warehouses'] or 0,
            },
            'by_warehouse': by_warehouse,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='alerts')
    def alerts(self, request):
        """
        Retorna productos con stock por debajo del mínimo definido.
        
        Severidad:
        - CRITICAL: stock = 0
        - WARNING: stock > 0 pero < min_stock
        """
        # Anotar el stock total en unidad base (sum de quantity * conversion_factor)
        products_with_stock = Product.objects.filter(
            enabled=True, is_service=False
        ).annotate(
            total_stock_base=Coalesce(
                Sum(
                    ExpressionWrapper(
                        F('stock_records__quantity') * F('stock_records__presentation__conversion_factor'),
                        output_field=DecimalField(max_digits=10, decimal_places=2)
                    )
                ),
                Value(0),
                output_field=DecimalField(max_digits=10, decimal_places=2)
            )
        ).filter(
            total_stock_base__lt=F('min_stock')
        ).order_by('total_stock_base', 'name')

        # Aplicar filtro por severidad si viene en query params
        severity = request.query_params.get('severity', None)

        alerts_list = []
        for product in products_with_stock:
            stock_base = float(product.total_stock_base or 0)
            min_stock = float(product.min_stock or 0)
            deficit = max(0, min_stock - stock_base)

            # Determinar severidad
            if stock_base == 0:
                sev = 'CRITICAL'
            else:
                sev = 'WARNING'

            # Filtrar por severidad si se solicitó
            if severity and sev != severity:
                continue

            # Obtener detalle de stock por almacén
            stock_details = list(
                ProductWarehouseStock.objects.filter(
                    product=product, quantity__gt=0
                ).select_related('warehouse', 'presentation__measure_unit').values(
                    'warehouse__name', 'warehouse__code',
                    'presentation__measure_unit__short_name',
                    'quantity'
                )
            )

            alerts_list.append({
                'product_id': product.id,
                'product_name': product.name,
                'sku': product.sku,
                'min_stock': min_stock,
                'current_stock': stock_base,
                'deficit': deficit,
                'severity': sev,
                'stock_by_warehouse': stock_details,
            })

        # Resumen de alertas
        summary = {
            'total_alerts': len(alerts_list),
            'critical_count': sum(1 for a in alerts_list if a['severity'] == 'CRITICAL'),
            'warning_count': sum(1 for a in alerts_list if a['severity'] == 'WARNING'),
        }

        return Response({
            'summary': summary,
            'alerts': alerts_list,
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['delete'], url_path='delete')
    def delete_stock(self, request, pk=None):
        """
        Elimina un registro de stock individual.
        ⚠️ NO crea movimiento inverso. Solo borra el registro.
        """
        try:
            stock = ProductWarehouseStock.objects.get(pk=pk)
            product_name = stock.product.name
            warehouse_name = stock.warehouse.name
            unit_name = stock.presentation.measure_unit.short_name
            quantity = stock.quantity
            stock.delete()
            return Response({
                'message': f'Stock eliminado: {quantity} {unit_name} de {product_name} en {warehouse_name}',
            }, status=status.HTTP_200_OK)
        except ProductWarehouseStock.DoesNotExist:
            return Response({'error': 'Registro de stock no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['delete'], url_path='purge')
    def purge(self, request):
        """
        Elimina TODOS los registros de stock. No reinicia IDs.
        ⚠️ NO restaura ni crea movimientos. Solo vacía el inventario.
        """
        count = ProductWarehouseStock.objects.count()
        ProductWarehouseStock.objects.all().delete()
        return Response({
            'message': f'{count} registros de stock eliminados correctamente',
            'deleted_count': count,
        }, status=status.HTTP_200_OK)

class ConversionViewSet(viewsets.ViewSet):
    """Conversiones manuales entre presentaciones (enfoque Versat)"""
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request):
        serializer = ConversionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Validar que existan los objetos
        try:
            product = Product.objects.get(id=data['product_id'])
        except Product.DoesNotExist:
            return Response({'error': 'Producto no encontrado'}, status=status.HTTP_404_NOT_FOUND)

        try:
            warehouse = Warehouse.objects.get(id=data['warehouse_id'])
        except Warehouse.DoesNotExist:
            return Response({'error': 'Almacén no encontrado'}, status=status.HTTP_404_NOT_FOUND)

        try:
            from_presentation = ProductPresentation.objects.get(
                id=data['from_presentation_id'], product=product
            )
        except ProductPresentation.DoesNotExist:
            return Response({'error': 'Presentación origen no válida para este producto'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            to_presentation = ProductPresentation.objects.get(
                id=data['to_presentation_id'], product=product
            )
        except ProductPresentation.DoesNotExist:
            return Response({'error': 'Presentación destino no válida para este producto'}, status=status.HTTP_400_BAD_REQUEST)

        if from_presentation.id == to_presentation.id:
            return Response(
                {'error': 'La presentación origen y destino no pueden ser iguales'},
                status=status.HTTP_400_BAD_REQUEST
            )

        quantity = data['quantity']

        # Calcular la equivalencia
        quantity_in_base = quantity * from_presentation.conversion_factor
        quantity_destination = quantity_in_base / to_presentation.conversion_factor

        with transaction.atomic():
            # Obtener stock de origen con bloqueo
            from_stock, _ = ProductWarehouseStock.objects.select_for_update().get_or_create(
                product=product,
                warehouse=warehouse,
                presentation=from_presentation,
                defaults={'quantity': 0, 'total_value': 0}
            )

            # Verificar stock suficiente
            if from_stock.quantity < quantity:
                return Response(
                    {'error': f'Stock insuficiente. Disponible: {from_stock.quantity}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Calcular el valor a transferir (mantiene el costo promedio)
            if from_stock.quantity > 0:
                cost_per_source_unit = from_stock.total_value / from_stock.quantity
            else:
                cost_per_source_unit = Decimal('0')

            value_to_transfer = quantity * cost_per_source_unit

            # Descontar del origen
            from_stock.quantity -= quantity
            from_stock.total_value -= value_to_transfer
            from_stock.save()

            # Sumar al destino
            to_stock, _ = ProductWarehouseStock.objects.select_for_update().get_or_create(
                product=product,
                warehouse=warehouse,
                presentation=to_presentation,
                defaults={'quantity': 0, 'total_value': 0}
            )
            to_stock.quantity += quantity_destination
            to_stock.total_value += value_to_transfer
            to_stock.save()

            # Registrar el movimiento de conversión
            movement = StockMovement.objects.create(
                product=product,
                warehouse=warehouse,
                presentation=from_presentation,
                destination_presentation=to_presentation,
                movement_type='CONVERSION',
                quantity=quantity,
                unit_cost=cost_per_source_unit,
                user=request.user,
                notes=f'{quantity} {from_presentation.measure_unit.short_name} → {quantity_destination} {to_presentation.measure_unit.short_name}',
            )

        return Response({
            'message': 'Conversión realizada correctamente',
            'movement_id': movement.id,
            'from_presentation': from_presentation.measure_unit.short_name,
            'to_presentation': to_presentation.measure_unit.short_name,
            'converted_quantity': str(quantity_destination),
            'remaining_from': str(from_stock.quantity),
            'remaining_to': str(to_stock.quantity),
        }, status=status.HTTP_200_OK)

class StockMovementViewSet(viewsets.ModelViewSet):
    """CRUD de movimientos de inventario con actualización automática de stock"""
    queryset = StockMovement.objects.select_related(
        'product', 'warehouse', 'destination_warehouse',
        'presentation__measure_unit', 'destination_presentation__measure_unit',
        'user'
    ).order_by('-created_at')
    serializer_class = StockMovementSerializer
    permission_classes = [permissions.IsAuthenticated]

    filterset_fields = ['movement_type', 'product', 'warehouse', 'presentation']
    search_fields = ['product__name', 'product__sku', 'reference', 'notes']
    ordering_fields = ['created_at', 'quantity', 'movement_type']
    ordering = ['-created_at']

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """Resumen de movimientos por tipo en un rango de fechas"""

        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        queryset = self.get_queryset()
        if date_from:
            queryset = queryset.filter(created_at__date__gte=parse_date(date_from))
        if date_to:
            queryset = queryset.filter(created_at__date__lte=parse_date(date_to))

        summary = queryset.values('movement_type').annotate(
            count=models.Count('id'),
            total_quantity=models.Sum('quantity'),
        ).order_by('movement_type')

        return Response(list(summary))
    @action(detail=False, methods=['delete'], url_path='purge')
    def purge(self, request):
        """
        Elimina TODOS los movimientos y reinicia los IDs.
        ⚠️ NO restaura el stock. Solo borra el historial.
        """
        count = StockMovement.objects.count()
        StockMovement.objects.all().delete()

        # Reiniciar auto-increment 
        reset_sequence('inventory_stockmovement')

        return Response({
            'message': f'{count} movimientos eliminados correctamente',
            'deleted_count': count,
        }, status=status.HTTP_200_OK)   

class StockDocumentViewSet(viewsets.ModelViewSet):
    queryset = StockDocument.objects.select_related(
        'warehouse', 'destination_warehouse', 'supplier', 'created_by'
    ).prefetch_related('lines__product', 'lines__presentation')
    serializer_class = StockDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['document_type', 'warehouse', 'supplier']
    search_fields = ['number', 'reference', 'notes']
    ordering = ['-created_at']

    @action(detail=False, methods=['post'], url_path='create-with-lines')
    def create_with_lines(self, request):
        """Crea un vale con múltiples líneas y genera los movimientos correspondientes."""
        serializer = StockDocumentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        doc_type = data['document_type']
        
        # Validar almacén origen
        try:
            warehouse = Warehouse.objects.get(id=data['warehouse_id'])
        except Warehouse.DoesNotExist:
            return Response({'error': 'Almacén origen no encontrado'}, status=status.HTTP_400_BAD_REQUEST)

        # Validar almacén destino (solo para traslados)
        destination_warehouse = None
        if doc_type == 'TRANSFER':
            try:
                destination_warehouse = Warehouse.objects.get(id=data['destination_warehouse_id'])
            except Warehouse.DoesNotExist:
                return Response({'error': 'Almacén destino no encontrado'}, status=status.HTTP_400_BAD_REQUEST)

        # Validar proveedor (opcional, solo entradas)
        supplier = None
        if data.get('supplier_id'):
            try:
                supplier = Supplier.objects.get(id=data['supplier_id'])
            except Supplier.DoesNotExist:
                return Response({'error': 'Proveedor no encontrado'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # Crear documento padre
            document = StockDocument.objects.create(
                document_type=doc_type,
                warehouse=warehouse,
                destination_warehouse=destination_warehouse,
                supplier=supplier,
                reference=data.get('reference', ''),
                notes=data.get('notes', ''),
                created_by=request.user,
            )

            # Procesar cada línea
            for item_data in data['items']:
                product = Product.objects.get(id=item_data['product_id'])
                presentation = ProductPresentation.objects.get(id=item_data['presentation_id'])
                quantity = Decimal(str(item_data['quantity']))
                unit_cost = Decimal(str(item_data.get('unit_cost', 0)))

                # Verificar stock para salidas y traslados
                if doc_type in ['EXIT', 'TRANSFER']:
                    stock_record = ProductWarehouseStock.objects.filter(
                        product=product,
                        warehouse=warehouse,
                        presentation=presentation,
                    ).first()
                    available = stock_record.quantity if stock_record else Decimal('0')
                    needed = abs(quantity) if quantity < 0 else quantity
                    if available < needed:
                        raise ValidationError(
                            f'Stock insuficiente para {product.name}. Disponible: {available}, solicitado: {needed}'
                        )

                # Para ajustes negativos, verificar stock también
                if doc_type == 'ADJUSTMENT' and quantity < 0:
                    stock_record = ProductWarehouseStock.objects.filter(
                        product=product,
                        warehouse=warehouse,
                        presentation=presentation,
                    ).first()
                    available = stock_record.quantity if stock_record else Decimal('0')
                    if available < abs(quantity):
                        raise ValidationError(
                            f'Stock insuficiente para ajuste de {product.name}. Disponible: {available}'
                        )

                # Crear línea del documento
                StockDocumentLine.objects.create(
                    document=document,
                    product=product,
                    presentation=presentation,
                    quantity=quantity,
                    unit_cost=unit_cost,
                )

                # Generar movimiento(s)
                if doc_type == 'TRANSFER':
                    # Traslado: genera movimiento de tipo TRANSFER
                    movement = StockMovement.objects.create(
                        movement_type='TRANSFER',
                        product=product,
                        presentation=presentation,
                        warehouse=warehouse,
                        destination_warehouse=destination_warehouse,
                        destination_presentation=presentation,
                        quantity=abs(quantity),
                        unit_cost=unit_cost,
                        reference=f"Vale {document.number}",
                        notes=data.get('notes', ''),
                        user=request.user,
                    )
                    # Actualizar stock manualmente (salida de origen + entrada en destino)
                    self._apply_transfer(movement)
                else:
                    # ENTRY, EXIT, ADJUSTMENT
                    movement = StockMovement.objects.create(
                        movement_type=doc_type,
                        product=product,
                        presentation=presentation,
                        warehouse=warehouse,
                        quantity=quantity,
                        unit_cost=unit_cost,
                        reference=f"Vale {document.number}",
                        notes=data.get('notes', ''),
                        user=request.user,
                    )
                    self._apply_movement(movement)

        return Response(
            StockDocumentSerializer(document).data,
            status=status.HTTP_201_CREATED
        )

    def _apply_movement(self, movement):
        """Aplica un movimiento simple (ENTRY, EXIT, ADJUSTMENT) al stock."""
        stock, created = ProductWarehouseStock.objects.get_or_create(
            product=movement.product,
            warehouse=movement.warehouse,
            presentation=movement.presentation,
            defaults={'quantity': Decimal('0'), 'total_value': Decimal('0')}
        )

        if movement.movement_type == 'ENTRY':
            stock.quantity += movement.quantity
            stock.total_value += movement.quantity * movement.unit_cost
        elif movement.movement_type == 'EXIT':
            if stock.quantity > 0:
                cost_per_unit = stock.total_value / stock.quantity
            else:
                cost_per_unit = Decimal('0')
            stock.quantity -= movement.quantity
            stock.total_value -= movement.quantity * cost_per_unit
        elif movement.movement_type == 'ADJUSTMENT':
            stock.quantity += movement.quantity
            if movement.quantity > 0 and movement.unit_cost:
                stock.total_value += movement.quantity * movement.unit_cost

        # Eliminar si queda en 0
        if stock.quantity <= 0:
            stock.delete()
        else:
            stock.save()

    def _apply_transfer(self, movement):
        """Aplica un traslado: salida del origen + entrada al destino."""
        # Salida del origen
        from_stock = ProductWarehouseStock.objects.filter(
            product=movement.product,
            warehouse=movement.warehouse,
            presentation=movement.presentation,
        ).first()

        if from_stock:
            if from_stock.quantity > 0:
                cost_per_unit = from_stock.total_value / from_stock.quantity
            else:
                cost_per_unit = Decimal('0')
            value_transferred = movement.quantity * cost_per_unit

            from_stock.quantity -= movement.quantity
            from_stock.total_value -= value_transferred
            if from_stock.quantity <= 0:
                from_stock.delete()
            else:
                from_stock.save()
        else:
            value_transferred = Decimal('0')

        # Entrada al destino
        to_stock, _ = ProductWarehouseStock.objects.get_or_create(
            product=movement.product,
            warehouse=movement.destination_warehouse,
            presentation=movement.destination_presentation or movement.presentation,
            defaults={'quantity': Decimal('0'), 'total_value': Decimal('0')}
        )
        to_stock.quantity += movement.quantity
        to_stock.total_value += value_transferred
        to_stock.save()