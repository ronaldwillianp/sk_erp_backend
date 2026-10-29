from django.db import models
from django.conf import settings
from configuration.constants import WAREHOUSE_TYPE_CHOICES, MOVEMENT_TYPE_CHOICES

class Warehouse(models.Model):
    name = models.CharField(max_length=50, unique=True)
    code = models.CharField(max_length=10, unique=True)
    warehouse_type = models.CharField(max_length=15, choices=WAREHOUSE_TYPE_CHOICES)
    address = models.CharField(max_length=100, blank=True)
    province = models.ForeignKey(
        'configuration.Province',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='warehouses'
    )
    municipality = models.ForeignKey(
        'configuration.Municipality',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='warehouses'
    )
    is_default = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} | {self.name}"

    class Meta:
        ordering = ['name']

class Product(models.Model):
    name = models.CharField(max_length=100)
    sku = models.CharField(max_length=20, unique=True)
    barcode = models.CharField(max_length=50, blank=True)
    category = models.ForeignKey(
        'configuration.Category',
        on_delete=models.PROTECT,
        related_name='products'
    )
    sale_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Precio de venta base (referencia)"
    )
    cost_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Precio de costo de referencia. El costo real se calcula por movimiento."
    )
    min_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_service = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.sku} | {self.name}"

    class Meta:
        ordering = ['name']

class ProductPresentation(models.Model):
    """
    Define las unidades de medida disponibles para un producto,
    con su factor de conversión y precio de venta específico.
    
    Ejemplo: Cigarro → Unidad (factor 1), Caja (factor 20), Rueda (factor 400)
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='presentations')
    measure_unit = models.ForeignKey(
        'configuration.MeasureUnit',
        on_delete=models.PROTECT,
        related_name='product_presentations'
    )
    conversion_factor = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Cuántas unidades base equivale esta UM. Ej: Caja=20, Rueda=400"
    )
    sale_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Precio de venta en esta unidad de medida"
    )
    is_default = models.BooleanField(default=False)

    class Meta:
        unique_together = ('product', 'measure_unit')
        ordering = ['-conversion_factor']

    def __str__(self):
        return f"{self.product.sku} - {self.measure_unit.name} (x{self.conversion_factor})"

class Supplier(models.Model):
    name = models.CharField(max_length=100)
    contact_person = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=15, blank=True)
    address = models.CharField(max_length=100, blank=True)
    province = models.ForeignKey(
        'configuration.Province',
        on_delete=models.PROTECT,
        null=True, blank=True
    )
    notes = models.TextField(blank=True)
    enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']

class StockMovement(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='movements')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='movements')
    presentation = models.ForeignKey(
        ProductPresentation,
        on_delete=models.PROTECT,
        related_name='movements',
        help_text="Unidad de medida en la que se registra este movimiento"
    )
    destination_warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT,
        null=True, blank=True, related_name='incoming_transfers'
    )
    destination_presentation = models.ForeignKey(
        ProductPresentation,
        on_delete=models.PROTECT,
        null=True, blank=True, related_name='incoming_conversions',
        help_text="UM destino en conversiones (ej: de Caja a Unidad)"
    )
    
    # === NUEVO: Snapshots de los nombres en el momento del movimiento ===
    product_name_snapshot = models.CharField(
        max_length=150, 
        help_text="Nombre del producto al momento del movimiento (inmutable)"
    )
    presentation_name_snapshot = models.CharField(
        max_length=100, 
        blank=True, 
        default='',
        help_text="Nombre de la presentación al momento del movimiento"
    )
    
    movement_type = models.CharField(max_length=15, choices=MOVEMENT_TYPE_CHOICES)
    quantity = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Cantidad EN LA PRESENTACIÓN del movimiento (no en unidad base)"
    )
    unit_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Costo por unidad EN LA PRESENTACIÓN (solo para entradas)"
    )
    reference = models.CharField(max_length=50, blank=True)
    notes = models.CharField(max_length=200, blank=True)
    user = models.ForeignKey(
        'administration.User',
        on_delete=models.PROTECT,
        null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.movement_type} | {self.product_name_snapshot} x{self.quantity} {self.presentation_name_snapshot}"

    class Meta:
        ordering = ['-created_at']

class ProductWarehouseStock(models.Model):
    """
    Stock independiente por producto + almacén + presentación.
    Refleja la realidad física del almacén (enfoque Versat).
    
    Ejemplo:
      Cigarro | Almacén Central | Caja   | 20
      Cigarro | Almacén Central | Unidad | 10
      Cigarro | Almacén Central | Rueda  | 0
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_records')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='stock_records')
    presentation = models.ForeignKey(ProductPresentation, on_delete=models.CASCADE, related_name='stock_records')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_value = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Valor total del stock en esta presentación (cantidad × costo promedio)"
    )

    @property
    def average_cost(self):
        """Costo promedio por unidad EN ESTA PRESENTACIÓN"""
        if self.quantity == 0:
            return 0
        return self.total_value / self.quantity

    class Meta:
        unique_together = ('product', 'warehouse', 'presentation')
        verbose_name = 'Stock por presentación'
        verbose_name_plural = 'Stock por presentación'

    def __str__(self):
        return f"{self.product.sku} | {self.warehouse.code} | {self.presentation.measure_unit.short_name}: {self.quantity}"

class StockDocument(models.Model):
    """Documento padre para entradas/salidas/traslados/ajustes multi-producto"""
       
    number = models.CharField(max_length=20, unique=True, editable=False)
    document_type = models.CharField(max_length=10, choices=MOVEMENT_TYPE_CHOICES)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='stock_documents_origin')
    destination_warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, 
        related_name='stock_documents_destination',
        null=True, blank=True
    )
    supplier = models.ForeignKey(
        'Supplier', on_delete=models.SET_NULL, 
        null=True, blank=True, related_name='stock_documents'
    )
    reference = models.CharField(max_length=100, blank=True, default='', help_text='Referencia externa')
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, 
        null=True, related_name='stock_documents_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_document_type_display()} {self.number}"

    def save(self, *args, **kwargs):
        if not self.number:
            prefixes = {'ENTRY': 'ENT', 'EXIT': 'SAL', 'TRANSFER': 'TRA', 'ADJUSTMENT': 'AJU'}
            prefix = prefixes.get(self.document_type, 'DOC')
            last = StockDocument.objects.filter(document_type=self.document_type).order_by('-id').first()
            next_num = 1
            if last and last.number:
                try:
                    next_num = int(last.number.split('-')[1]) + 1
                except (IndexError, ValueError):
                    next_num = 1
            self.number = f"{prefix}-{next_num:05d}"
        super().save(*args, **kwargs)

class StockDocumentLine(models.Model):
    """Línea de un documento de stock"""
    document = models.ForeignKey(StockDocument, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey('Product', on_delete=models.PROTECT)
    presentation = models.ForeignKey('ProductPresentation', on_delete=models.PROTECT)
    
    # === NUEVO: Snapshots de los nombres en el momento del vale ===
    product_name_snapshot = models.CharField(
        max_length=150, 
        help_text="Nombre del producto al momento del vale (inmutable)"
    )
    presentation_name_snapshot = models.CharField(
        max_length=100, 
        blank=True, 
        default='',
        help_text="Nombre de la presentación al momento del vale"
    )
    
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.product_name_snapshot} x{self.quantity}"