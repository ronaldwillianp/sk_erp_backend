# pos/serializers.py
from rest_framework import serializers
from django.utils import timezone
from decimal import Decimal
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model

from .models import CashRegister, InvoicePayment, WarehouseUser
from configuration.models import PaymentMethod
from configuration.serializers import PaymentMethodSerializer
from inventory.models import Warehouse
from administration.serializers import UserSerializer, GroupSerializer

User = get_user_model()


# ============================================
# WAREHOUSE USER (Asignaciones a PVs)
# ============================================
class WarehouseUserSerializer(serializers.ModelSerializer):
    """
    Asignación de usuarios a Puntos de Venta con un rol específico.
    Usa los serializers completos de User y Group (sin versiones Lite).
    """
    # === Lectura (objetos completos) ===
    user_detail = UserSerializer(source='user', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    warehouse_code = serializers.CharField(source='warehouse.code', read_only=True)
    warehouse_type = serializers.CharField(source='warehouse.warehouse_type', read_only=True)
    group_detail = GroupSerializer(source='group', read_only=True)
    
    # === Escritura (solo IDs) ===
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source='user',
        write_only=True
    )
    warehouse_id = serializers.PrimaryKeyRelatedField(
        queryset=Warehouse.objects.filter(warehouse_type='POINT_OF_SALE', enabled=True),
        source='warehouse',
        write_only=True,
        help_text="Solo se permiten Puntos de Venta habilitados"
    )
    group_id = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(),
        source='group',
        write_only=True
    )
    
    class Meta:
        model = WarehouseUser
        fields = [
            'id',
            # Lectura
            'user_detail', 'warehouse_name', 'warehouse_code', 
            'warehouse_type', 'group_detail',
            # Escritura
            'user_id', 'warehouse_id', 'group_id',
            # Campos propios
            'is_active', 'notes', 'created_at',
        ]
        read_only_fields = ['created_at']
    
    def validate_warehouse_id(self, value):
        """Doble validación: solo PVs habilitados"""
        if value.warehouse_type != 'POINT_OF_SALE':
            raise serializers.ValidationError(
                'Solo se pueden asignar usuarios a Puntos de Venta'
            )
        if not value.enabled:
            raise serializers.ValidationError(
                'El Punto de Venta está deshabilitado'
            )
        return value


# ============================================
# CASH REGISTER (Apertura/Cierre de Caja)
# ============================================
class CashRegisterSerializer(serializers.ModelSerializer):
    """Serializer para leer sesiones de caja"""
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    warehouse_code = serializers.CharField(source='warehouse.code', read_only=True)
    user_name = serializers.CharField(source='user.username', read_only=True)
    closed_by_user_name = serializers.CharField(
        source='closed_by_user.username', 
        read_only=True, 
        default='—'
    )
    invoices_count = serializers.SerializerMethodField()
    total_sales = serializers.SerializerMethodField()
    
    class Meta:
        model = CashRegister
        fields = [
            'id', 'warehouse', 'warehouse_name', 'warehouse_code',
            'user', 'user_name', 'status',
            'opening_date', 'opening_balance',
            'closing_date', 'closed_by_user', 'closed_by_user_name',
            'closing_balance', 'expected_balance', 'difference',
            'notes',
            'invoices_count', 'total_sales',
        ]
        read_only_fields = [
            'closing_date', 'closed_by_user', 'closing_balance',
            'expected_balance', 'difference', 'invoices_count', 'total_sales'
        ]
    
    def get_invoices_count(self, obj):
        """Cantidad de facturas vendidas en esta sesión"""
        return obj.invoices.filter(status__in=['PAID', 'PARTIAL']).count()
    
    def get_total_sales(self, obj):
        """Total vendido en esta sesión"""
        from django.db.models import Sum
        result = obj.invoices.filter(status__in=['PAID', 'PARTIAL']).aggregate(
            total=Sum('total')
        )
        return float(result['total'] or 0)


class CashRegisterOpenSerializer(serializers.Serializer):
    """Serializer para abrir una caja"""
    warehouse_id = serializers.IntegerField()
    opening_balance = serializers.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    
    def validate_warehouse_id(self, value):
        """Verificar que sea un PV y que no haya caja abierta"""
        try:
            warehouse = Warehouse.objects.get(id=value, enabled=True)
        except Warehouse.DoesNotExist:
            raise serializers.ValidationError("Almacén no encontrado o inactivo")
        
        if warehouse.warehouse_type != 'POINT_OF_SALE':
            raise serializers.ValidationError(
                "Solo se pueden abrir cajas en Puntos de Venta"
            )
        
        open_register = CashRegister.objects.filter(
            warehouse_id=value,
            status='OPEN'
        ).exists()
        
        if open_register:
            raise serializers.ValidationError(
                "Ya existe una caja abierta para este Punto de Venta. Ciérrela primero."
            )
        
        return value


class CashRegisterCloseSerializer(serializers.Serializer):
    """Serializer para cerrar una caja"""
    closing_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    
    def validate_closing_balance(self, value):
        if value < 0:
            raise serializers.ValidationError("El saldo de cierre no puede ser negativo")
        return value


# ============================================
# INVOICE PAYMENT (Métodos de pago)
# ============================================
class InvoicePaymentSerializer(serializers.ModelSerializer):
    """Serializer para leer pagos de facturas"""
    payment_method_detail = PaymentMethodSerializer(source='payment_method', read_only=True)
    
    class Meta:
        model = InvoicePayment
        fields = [
            'id', 'invoice', 'payment_method', 'payment_method_detail',
            'amount', 'reference', 'created_at'
        ]
        read_only_fields = ['created_at']


class InvoicePaymentInputSerializer(serializers.Serializer):
    """Serializer para recibir pagos al crear una factura"""
    payment_method_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    reference = serializers.CharField(required=False, allow_blank=True, default='')
    
    def validate_payment_method_id(self, value):
        """Verificar que el método de pago exista y esté habilitado"""
        try:
            pm = PaymentMethod.objects.get(id=value, enabled=True)
        except PaymentMethod.DoesNotExist:
            raise serializers.ValidationError("Método de pago no encontrado o inactivo")
        return value
    
    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("El monto debe ser mayor a 0")
        return value