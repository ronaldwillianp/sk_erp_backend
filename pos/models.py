# pos/models.py
from django.db import models
from django.conf import settings
from decimal import Decimal
from configuration.constants import CASH_REGISTER_STATUS_CHOICES

class WarehouseUser(models.Model):
    """
    Asigna usuarios a warehouses (principalmente PVs) con un rol específico.
    Un usuario puede trabajar en múltiples PVs con diferentes roles.
    Un PV puede tener múltiples usuarios asignados.
    
    Los roles se gestionan mediante los grupos de Django (auth.Group),
    lo que permite centralizar permisos y reutilizar la lógica existente.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='warehouse_assignments'
    )
    warehouse = models.ForeignKey(
        'inventory.Warehouse',
        on_delete=models.CASCADE,
        related_name='assigned_users'
    )
    group = models.ForeignKey(
        'auth.Group',
        on_delete=models.CASCADE,
        related_name='warehouse_assignments',
        help_text="Rol del usuario en este warehouse (ej: Cajero, Gerente PV, Administrador)"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, default='')
    
    class Meta:
        unique_together = ('user', 'warehouse')
        verbose_name = 'Asignación de Usuario a Almacén/PV'
        verbose_name_plural = 'Asignaciones de Usuarios a Almacenes/PVs'
        ordering = ['warehouse', 'user']
    
    def __str__(self):
        return f"{self.user.username} → {self.warehouse.code} ({self.group.name})"
    
class CashRegister(models.Model):
    """
    Control de sesión de caja diaria por almacén/PV.
    """

    warehouse = models.ForeignKey(
        'inventory.Warehouse', 
        on_delete=models.PROTECT,
        related_name='cash_registers',
        help_text="Almacén o Punto de Venta asociado a esta caja"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL,
        null=True, 
        related_name='opened_registers',
        help_text="Usuario que abrió la caja"
    )
    
    status = models.CharField(max_length=10, choices=CASH_REGISTER_STATUS_CHOICES, default='OPEN')
    
    # Apertura
    opening_date = models.DateTimeField(auto_now_add=True)
    opening_balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Efectivo inicial en caja (fondo de cambio)"
    )
    
    # Cierre
    closing_date = models.DateTimeField(null=True, blank=True)
    closed_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='closed_registers'
    )
    closing_balance = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Efectivo contado físicamente al cerrar"
    )
    expected_balance = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Efectivo que debería haber según el sistema"
    )
    difference = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Diferencia entre contado y esperado (Descuadre)"
    )
    
    notes = models.TextField(blank=True, default='')
    
    class Meta:
        ordering = ['-opening_date']
        verbose_name = 'Sesión de Caja'
        verbose_name_plural = 'Sesiones de Caja'

    def __str__(self):
        return f"Caja {self.warehouse.name} - {self.opening_date.strftime('%d/%m/%Y %H:%M')}"

class InvoicePayment(models.Model):
    """
    Permite registrar múltiples métodos de pago para una sola factura.
    Ej: Una venta de $100 pagada con $50 efectivo y $50 tarjeta.
    
    Usa los PaymentMethod configurados en el módulo de configuración.
    """
    invoice = models.ForeignKey(
        'sales.Invoice', 
        on_delete=models.CASCADE,
        related_name='payments',
        help_text="Factura asociada a este pago"
    )
    payment_method = models.ForeignKey(
        'configuration.PaymentMethod',
        on_delete=models.PROTECT,
        related_name='invoice_payments',
        help_text="Método de pago utilizado (Efectivo, Tarjeta, Transferencia, etc.)"
    )
    amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        help_text="Monto pagado con este método"
    )
    reference = models.CharField(
        max_length=100, 
        blank=True, 
        default='',
        help_text="Número de operación, último 4 dígitos de tarjeta, etc."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Pago de Factura'
        verbose_name_plural = 'Pagos de Facturas'

    def __str__(self):
        return f"{self.payment_method.name}: {self.amount} ({self.invoice.number})"