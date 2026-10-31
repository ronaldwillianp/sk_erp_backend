from rest_framework import serializers
from configuration.models import Province, Municipality, Category, MeasureUnit
from configuration.serializers import ProvinceSerializer, MunicipalityLiteSerializer, CategoryLiteSerializer, MeasureUnitSerializer
from .models import StockDocument, StockDocumentLine, Warehouse, Supplier, Product, ProductPresentation, ProductWarehouseStock, StockMovement
from decimal import Decimal

# ============================================
# WAREHOUSE
# ============================================
class WarehouseSerializer(serializers.ModelSerializer):
    # === Lectura ===
    province = ProvinceSerializer(read_only=True)
    municipality = MunicipalityLiteSerializer(read_only=True)

    # === Escritura ===
    province_id = serializers.PrimaryKeyRelatedField(
        queryset=Province.objects.all(),
        source='province',
        write_only=True,
        required=False,
        allow_null=True
    )
    municipality_id = serializers.PrimaryKeyRelatedField(
        queryset=Municipality.objects.all(),
        source='municipality',
        write_only=True,
        required=False,
        allow_null=True
    )

    class Meta:
        model = Warehouse
        fields = [
            'id', 'name', 'code', 'warehouse_type', 'address',
            'province', 'province_id', 'municipality', 'municipality_id',
            'is_default', 'enabled'
        ]

    def save(self, **kwargs):
        """
        Si este almacén se marca como default,
        desmarca automáticamente los demás.
        """
        if self.validated_data.get('is_default'):
            qs = Warehouse.objects.filter(is_default=True)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            qs.update(is_default=False)
        return super().save(**kwargs)


class SupplierSerializer(serializers.ModelSerializer):
    # === Lectura ===
    province = ProvinceSerializer(read_only=True)

    # === Escritura ===
    province_id = serializers.PrimaryKeyRelatedField(
        queryset=Province.objects.all(),
        source='province',
        write_only=True,
        required=False,
        allow_null=True
    )

    class Meta:
        model = Supplier
        fields = [
            'id', 'name', 'contact_person', 'email', 'phone',
            'address', 'province', 'province_id', 'notes', 'enabled'
        ]

# ============================================
# PRODUCT PRESENTATION
# ============================================
class ProductPresentationSerializer(serializers.ModelSerializer):
    # El id es necesario para identificar presentaciones existentes al actualizar
    id = serializers.IntegerField(required=False, allow_null=True)

    # === Lectura ===
    measure_unit = MeasureUnitSerializer(read_only=True)

    # === Escritura ===
    measure_unit_id = serializers.PrimaryKeyRelatedField(
        queryset=MeasureUnit.objects.all(),
        source='measure_unit',
        write_only=True
    )

    class Meta:
        model = ProductPresentation
        fields = [
            'id', 'measure_unit', 'measure_unit_id',
            'conversion_factor', 'sale_price', 'is_default'
        ]

# ============================================
# PRODUCT (con presentaciones anidadas)
# ============================================
class ProductSerializer(serializers.ModelSerializer):
    # === Lectura ===
    category = CategoryLiteSerializer(read_only=True)
    presentations = ProductPresentationSerializer(many=True, required=False)
    
    # === NUEVO: Stock anotado desde el viewset (solo lectura) ===
    warehouse_stock = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        read_only=True, 
        required=False, 
        allow_null=True
    )

    # === Escritura ===
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        source='category',
        write_only=True
    )

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'sku', 'barcode',
            'category', 'category_id',
            'cost_price', 'sale_price', 'min_stock',
            'is_service', 'description', 'enabled',
            'presentations',
            'warehouse_stock',  # <--- Agregar aquí
        ]

    def create(self, validated_data):
        # warehouse_stock es read_only, así que no vendrá en validated_data
        validated_data.pop('warehouse_stock', None)
        
        presentations_data = validated_data.pop('presentations', [])
        product = Product.objects.create(**validated_data)

        for p_data in presentations_data:
            p_data.pop('id', None)
            ProductPresentation.objects.create(product=product, **p_data)

        return product

    def update(self, instance, validated_data):
        validated_data.pop('warehouse_stock', None)
        
        presentations_data = validated_data.pop('presentations', None)

        # Actualizar campos del producto
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Sincronizar presentaciones solo si vinieron en el payload
        if presentations_data is not None:
            self._sync_presentations(instance, presentations_data)

        return instance

    def _sync_presentations(self, product, presentations_data):
        """
        Sincroniza las presentaciones:
        - Si tiene id y existe → actualiza
        - Si tiene id pero no existe → crea
        - Si no tiene id → crea
        - Elimina las que no vinieron en el payload
        """
        existing_ids = set()

        for p_data in presentations_data:
            p_id = p_data.pop('id', None)

            if p_id:
                try:
                    presentation = ProductPresentation.objects.get(id=p_id, product=product)
                    for field, value in p_data.items():
                        setattr(presentation, field, value)
                    presentation.save()
                    existing_ids.add(p_id)
                except ProductPresentation.DoesNotExist:
                    new_p = ProductPresentation.objects.create(product=product, **p_data)
                    existing_ids.add(new_p.id)
            else:
                new_p = ProductPresentation.objects.create(product=product, **p_data)
                existing_ids.add(new_p.id)

        # Eliminar presentaciones que no vinieron en el payload
        if existing_ids:
            product.presentations.exclude(id__in=existing_ids).delete()
        else:
            product.presentations.all().delete()

# ============================================
# PRODUCT WAREHOUSE STOCK
# ============================================
class ProductWarehouseStockSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    warehouse = WarehouseSerializer(read_only=True)
    presentation = ProductPresentationSerializer(read_only=True)
    presentations_count = serializers.SerializerMethodField()

    class Meta:
        model = ProductWarehouseStock
        fields = [
            'id', 'product', 'warehouse', 'presentation',
            'quantity', 'total_value', 'average_cost', 'presentations_count'
        ]

    def get_presentations_count(self, obj):
        return obj.product.presentations.count()

# ============================================
# CONVERSION (entrada de datos)
# ============================================
class ConversionSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    warehouse_id = serializers.IntegerField()
    from_presentation_id = serializers.IntegerField()
    to_presentation_id = serializers.IntegerField()
    quantity = serializers.DecimalField(
        max_digits=10, decimal_places=2,
        min_value=Decimal('0.01')
    )

# ============================================
# STOCK MOVEMENT
# ============================================
class StockMovementSerializer(serializers.ModelSerializer):
    # === Lectura ===
    product = ProductSerializer(read_only=True)
    warehouse = WarehouseSerializer(read_only=True)
    destination_warehouse = WarehouseSerializer(read_only=True)
    presentation = ProductPresentationSerializer(read_only=True)
    destination_presentation = ProductPresentationSerializer(read_only=True)
    user = serializers.StringRelatedField(read_only=True)

    # === Escritura ===
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), source='product', write_only=True
    )
    warehouse_id = serializers.PrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), source='warehouse', write_only=True
    )
    destination_warehouse_id = serializers.PrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), source='destination_warehouse',
        write_only=True, required=False, allow_null=True
    )
    presentation_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductPresentation.objects.all(), source='presentation', write_only=True
    )
    destination_presentation_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductPresentation.objects.all(), source='destination_presentation',
        write_only=True, required=False, allow_null=True
    )

    class Meta:
        model = StockMovement
        fields = [
            'id', 'movement_type', 'quantity', 'unit_cost', 'reference', 'notes',
            'created_at',
            # Lectura
            'product', 'warehouse', 'destination_warehouse',
            'presentation', 'destination_presentation', 'user',
            'product_name_snapshot',           # <-- NUEVO: Snapshot del nombre del producto
            'presentation_name_snapshot',      # <-- NUEVO: Snapshot del nombre de la presentación
            # Escritura
            'product_id', 'warehouse_id', 'destination_warehouse_id',
            'presentation_id', 'destination_presentation_id',
            'source',  # <-- NUEVO: Origen del movimiento
        ]
        read_only_fields = ['user', 'created_at', 'product_name_snapshot', 'presentation_name_snapshot', 'source']

    def validate(self, data):
        movement_type = data.get('movement_type')
        product = data.get('product')
        presentation = data.get('presentation')

        # Validar que la presentación pertenece al producto
        if presentation and product and presentation.product_id != product.id:
            raise serializers.ValidationError({
                'presentation_id': 'La presentación no pertenece a este producto'
            })

        # Validaciones por tipo de movimiento
        if movement_type == 'TRANSFER':
            dest_wh = data.get('destination_warehouse')
            if not dest_wh:
                raise serializers.ValidationError({
                    'destination_warehouse_id': 'El almacén destino es requerido para traslados'
                })
            if dest_wh.id == data.get('warehouse').id:
                raise serializers.ValidationError({
                    'destination_warehouse_id': 'El almacén destino debe ser diferente al origen'
                })

        if movement_type == 'ENTRY' and not data.get('unit_cost'):
            raise serializers.ValidationError({
                'unit_cost': 'El costo unitario es requerido para entradas'
            })

        return data

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        validated_data['source'] = 'MANUAL'
        
        # === NUEVO: Generar snapshots automáticamente si no vienen en validated_data ===
        # Esto es un fallback por si algún flujo crea movimientos vía serializer sin pasar snapshots
        if 'product' in validated_data and 'product_name_snapshot' not in validated_data:
            product = validated_data['product']
            validated_data['product_name_snapshot'] = product.name
            
        if 'presentation' in validated_data and 'presentation_name_snapshot' not in validated_data:
            presentation = validated_data['presentation']
            validated_data['presentation_name_snapshot'] = f"{presentation.measure_unit.name} (x{presentation.conversion_factor})"
        
        movement = super().create(validated_data)
        self._update_stock(movement)
        return movement

    def _update_stock(self, movement):
        """Actualiza el stock según el tipo de movimiento"""
        mt = movement.movement_type

        if mt == 'ENTRY':
            self._handle_entry(movement)
        elif mt == 'EXIT':
            self._handle_exit(movement)
        elif mt == 'TRANSFER':
            self._handle_transfer(movement)
        elif mt == 'ADJUSTMENT':
            self._handle_adjustment(movement)
        # CONVERSION ya se maneja en ConversionViewSet

    def _get_or_create_stock(self, product, warehouse, presentation):
        stock, created = ProductWarehouseStock.objects.get_or_create(
            product=product,
            warehouse=warehouse,
            presentation=presentation,
            defaults={'quantity': 0, 'total_value': 0}
        )
        return stock

    def _handle_entry(self, movement):
        """Entrada: aumenta stock y recalcula costo promedio"""
        stock = self._get_or_create_stock(
            movement.product, movement.warehouse, movement.presentation
        )
        quantity = movement.quantity
        cost = movement.unit_cost

        # Recalcular costo promedio ponderado
        new_total_value = stock.total_value + (quantity * cost)
        new_quantity = stock.quantity + quantity

        stock.quantity = new_quantity
        stock.total_value = new_total_value
        stock.save()

    def _handle_exit(self, movement):
        """Salida: disminuye stock"""
        stock = self._get_or_create_stock(
            movement.product, movement.warehouse, movement.presentation
        )
        if stock.quantity < movement.quantity:
            raise serializers.ValidationError({
                'quantity': f'Stock insuficiente. Disponible: {stock.quantity}'
            })

        # Mantener proporción del valor
        if stock.quantity > 0:
            cost_per_unit = stock.total_value / stock.quantity
        else:
            cost_per_unit = 0

        stock.quantity -= movement.quantity
        stock.total_value -= movement.quantity * cost_per_unit
        stock.save()

    def _handle_transfer(self, movement):
        """Traslado: sale de origen, entra a destino"""
        # Salida del origen
        from_stock = self._get_or_create_stock(
            movement.product, movement.warehouse, movement.presentation
        )
        if from_stock.quantity < movement.quantity:
            raise serializers.ValidationError({
                'quantity': f'Stock insuficiente en origen. Disponible: {from_stock.quantity}'
            })

        if from_stock.quantity > 0:
            cost_per_unit = from_stock.total_value / from_stock.quantity
        else:
            cost_per_unit = 0

        value_transferred = movement.quantity * cost_per_unit

        from_stock.quantity -= movement.quantity
        from_stock.total_value -= value_transferred
        from_stock.save()

        # Entrada al destino (misma presentación)
        to_stock = self._get_or_create_stock(
            movement.product, movement.destination_warehouse, movement.presentation
        )
        to_stock.quantity += movement.quantity
        to_stock.total_value += value_transferred
        to_stock.save()

    def _handle_adjustment(self, movement):
        """Ajuste: puede ser positivo o negativo"""
        stock = self._get_or_create_stock(
            movement.product, movement.warehouse, movement.presentation
        )
        quantity = movement.quantity  # Positivo = agregar, negativo = quitar

        if quantity < 0 and stock.quantity < abs(quantity):
            raise serializers.ValidationError({
                'quantity': f'Stock insuficiente para ajuste negativo. Disponible: {stock.quantity}'
            })

        stock.quantity += quantity
        # Para ajustes, no modificamos el valor total proporcionalmente
        # El usuario puede ajustar manualmente después si necesita
        if quantity > 0 and movement.unit_cost:
            stock.total_value += quantity * movement.unit_cost
        elif quantity < 0 and stock.quantity + abs(quantity) > 0:
            cost_per_unit = stock.total_value / (stock.quantity + abs(quantity))
            stock.total_value += quantity * cost_per_unit
        stock.save()

# ============================================
# STOCK DOCUMENT (Vales multi-producto)
# ============================================
class StockDocumentLineSerializer(serializers.ModelSerializer):
    product_detail = ProductSerializer(source='product', read_only=True)
    presentation_detail = ProductPresentationSerializer(source='presentation', read_only=True)

    class Meta:
        model = StockDocumentLine
        fields = [
            'id', 'document', 
            'product', 'product_detail',
            'product_name_snapshot',  # <-- NUEVO
            'presentation', 'presentation_detail',
            'presentation_name_snapshot',  # <-- NUEVO
            'quantity', 'unit_cost'
        ]

class StockDocumentSerializer(serializers.ModelSerializer):
    lines = StockDocumentLineSerializer(many=True, read_only=True)
    warehouse_detail = WarehouseSerializer(source='warehouse', read_only=True)
    destination_warehouse_detail = WarehouseSerializer(source='destination_warehouse', read_only=True)
    supplier_detail = SupplierSerializer(source='supplier', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True, default='—')

    class Meta:
        model = StockDocument
        fields = '__all__'

class StockDocumentCreateSerializer(serializers.Serializer):
    """Serializer para crear vale con múltiples líneas"""
    document_type = serializers.ChoiceField(choices=['ENTRY', 'EXIT', 'TRANSFER', 'ADJUSTMENT'])
    warehouse_id = serializers.IntegerField()
    destination_warehouse_id = serializers.IntegerField(required=False, allow_null=True)
    supplier_id = serializers.IntegerField(required=False, allow_null=True)
    reference = serializers.CharField(required=False, allow_blank=True, default='')
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    items = serializers.ListField(child=serializers.DictField(), min_length=1)

    def validate(self, data):
        doc_type = data.get('document_type')
        
        # Validar almacén destino para traslados
        if doc_type == 'TRANSFER':
            if not data.get('destination_warehouse_id'):
                raise serializers.ValidationError({'destination_warehouse_id': 'Requerido para traslados'})
            if data['warehouse_id'] == data['destination_warehouse_id']:
                raise serializers.ValidationError({'destination_warehouse_id': 'El destino debe ser diferente al origen'})
        
        # Validar proveedor opcional solo para entradas
        if doc_type == 'ENTRY' and data.get('supplier_id'):
            if not Supplier.objects.filter(id=data['supplier_id']).exists():
                raise serializers.ValidationError({'supplier_id': 'Proveedor no encontrado'})
        
        # Validar líneas
        items = data.get('items', [])
        for i, item in enumerate(items):
            if not item.get('product_id'):
                raise serializers.ValidationError({'items': f"Línea {i+1}: producto requerido"})
            if not item.get('presentation_id'):
                raise serializers.ValidationError({'items': f"Línea {i+1}: presentación requerida"})
            try:
                qty = float(item.get('quantity', 0))
                if qty == 0:
                    raise serializers.ValidationError({'items': f"Línea {i+1}: cantidad no puede ser 0"})
                if doc_type in ['ENTRY', 'EXIT', 'TRANSFER'] and qty < 0:
                    raise serializers.ValidationError({'items': f"Línea {i+1}: cantidad no puede ser negativa"})
            except (ValueError, TypeError):
                raise serializers.ValidationError({'items': f"Línea {i+1}: cantidad inválida"})
            
            # Costo requerido para entradas
            if doc_type == 'ENTRY':
                try:
                    cost = float(item.get('unit_cost', 0))
                    if cost < 0:
                        raise serializers.ValidationError({'items': f"Línea {i+1}: costo no puede ser negativo"})
                except (ValueError, TypeError):
                    raise serializers.ValidationError({'items': f"Línea {i+1}: costo inválido"})
        
        return data