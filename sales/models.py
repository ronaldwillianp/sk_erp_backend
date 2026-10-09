from django.db import models
from django.conf import settings


class Customer(models.Model):
    """Cliente para facturación"""
    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    address = models.TextField(blank=True, default='')
    nit = models.CharField('NIT / CI', max_length=30, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Invoice(models.Model):
    """Factura de venta"""
    STATUS_CHOICES = [
        ('DRAFT', 'Borrador'),
        ('SENT', 'Enviada'),
        ('PAID', 'Pagada'),
        ('PARTIAL', 'Parcialmente Pagada'),
        ('OVERDUE', 'Vencida'),
        ('CANCELLED', 'Cancelada'),
    ]

    number = models.CharField(max_length=20, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='invoices')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='DRAFT')
    issue_date = models.DateField(auto_now_add=True)
    due_date = models.DateField(null=True, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='created_invoices'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Factura {self.number}"

    def save(self, *args, **kwargs):
        if not self.number:
            last = Invoice.objects.order_by('-id').first()
            next_num = (int(last.number.replace('FAC-', '')) + 1) if last and last.number.startswith('FAC-') else 1
            self.number = f"FAC-{next_num:05d}"
        super().save(*args, **kwargs)


class InvoiceItem(models.Model):
    """Línea de factura"""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('inventory.Product', on_delete=models.PROTECT)
    presentation = models.ForeignKey('inventory.ProductPresentation', on_delete=models.PROTECT)
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        # Calcular total de línea con descuento
        gross = self.quantity * self.unit_price
        discount_amount = gross * (self.discount_percent / 100)
        self.line_total = gross - discount_amount
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"