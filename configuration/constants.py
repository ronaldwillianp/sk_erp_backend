# Configuration Module

# Source / Origen de documentos y movimientos
SOURCE_CHOICES = [
    ('POS', 'Punto de Venta'),
    ('BILLING', 'Módulo de Facturación'),
    ('MANUAL', 'Manual'),
]

SYSTEM_MODULES_CHOICES = [
    ('CONF','Configuración'),
    ('ADMIN','Administración'),
    ('INV','Inventario'),
    ('SALES','Ventas'),
    ('POS','Punto de Venta'),
]

CATEGORY_TYPE_CHOICES = [
        ('INCOME', 'Ingreso'),
        ('EXPENSE', 'Gasto'),
        ('PRODUCT', 'Producto'),
    ]

# Inventory Module
WAREHOUSE_TYPE_CHOICES = [
        ('WAREHOUSE', 'Almacén'),
        ('POINT_OF_SALE', 'Punto de venta'),
    ]

MOVEMENT_TYPE_CHOICES = [
        ('ENTRY', 'Entrada'),
        ('EXIT', 'Salida'),
        ('TRANSFER', 'Traslado'),
        ('ADJUSTMENT', 'Ajuste'),
        ('CONVERSION', 'Conversión'),
    ]

# SALES Module
INVOICE_STATUS_CHOICES = [
        ('DRAFT', 'Borrador'),
        ('SENT', 'Enviada'),
        ('PAID', 'Pagada'),
        ('PARTIAL', 'Parcialmente Pagada'),
        ('OVERDUE', 'Vencida'),
        ('CANCELLED', 'Cancelada'),
    ]

# POS Module

CASH_REGISTER_STATUS_CHOICES = [        # Estado de Caja
        ('OPEN', 'Abierta'),
        ('CLOSED', 'Cerrada'),
    ]