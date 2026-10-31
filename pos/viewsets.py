# pos/viewsets.py
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from decimal import Decimal
from django.contrib.auth.models import Group
from administration.permissions import IsDeveloper

from .models import CashRegister, InvoicePayment, WarehouseUser
from .serializers import (
    CashRegisterSerializer,
    CashRegisterOpenSerializer,
    CashRegisterCloseSerializer,
    InvoicePaymentSerializer,
    WarehouseUserSerializer,
)
from inventory.models import Warehouse


class CashRegisterViewSet(viewsets.ModelViewSet):
    """
    Gestión de sesiones de caja (apertura/cierre/reportes).
    """
    queryset = CashRegister.objects.select_related(
        'warehouse', 'user', 'closed_by_user'
    ).prefetch_related('invoices')
    serializer_class = CashRegisterSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    filterset_fields = ['warehouse', 'status', 'user']
    search_fields = ['warehouse__name', 'user__username']
    ordering = ['-opening_date']

    @action(detail=False, methods=['post'], url_path='open')
    def open_register(self, request):
        """
        Abre una nueva sesión de caja para un almacén/PV.
        Solo puede haber UNA caja abierta por almacén a la vez.
        """
        serializer = CashRegisterOpenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        try:
            cash_register = CashRegister.objects.create(
                warehouse_id=data['warehouse_id'],
                user=request.user,
                status='OPEN',
                opening_balance=data['opening_balance'],
            )
            
            return Response(
                CashRegisterSerializer(cash_register).data,
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response(
                {'error': f'Error al abrir caja: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'], url_path='close')
    def close_register(self, request, pk=None):
        """
        Cierra una sesión de caja.
        Calcula automáticamente:
        - expected_balance = opening_balance + ventas en efectivo
        - difference = closing_balance - expected_balance
        """
        cash_register = self.get_object()
        
        if cash_register.status == 'CLOSED':
            return Response(
                {'error': 'Esta caja ya está cerrada'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = CashRegisterCloseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        # Calcular ventas en efectivo de esta sesión
        cash_sales = cash_register.invoices.filter(
            status__in=['PAID', 'PARTIAL'],
            payments__payment_method__name__icontains='efectivo'
        ).aggregate(
            total=Sum('payments__amount')
        )['total'] or Decimal('0')
        
        # Calcular saldo esperado
        expected_balance = cash_register.opening_balance + cash_sales
        
        # Calcular diferencia
        closing_balance = data['closing_balance']
        difference = closing_balance - expected_balance
        
        # Cerrar la caja
        cash_register.status = 'CLOSED'
        cash_register.closing_date = timezone.now()
        cash_register.closed_by_user = request.user
        cash_register.closing_balance = closing_balance
        cash_register.expected_balance = expected_balance
        cash_register.difference = difference
        cash_register.notes = data.get('notes', '')
        cash_register.save()
        
        return Response(
            CashRegisterSerializer(cash_register).data,
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['delete'], url_path='purge', permission_classes=[IsDeveloper])
    def purge_registers(self, request):
        """
        Elimina TODOS los registros de caja y reinicia los IDs.
        ⚠️ ACCIÓN DE DESARROLLO/ADMINISTRADOR. 
        """
        try:
            with transaction.atomic():
                count = CashRegister.objects.count()
                CashRegister.objects.all().delete()

                # Reiniciar auto-increment de la tabla
                from django.db import connection  # <--- IMPORTANTE: Importar aquí
                with connection.cursor() as cursor:
                    try:
                        # PostgreSQL
                        cursor.execute(
                            "SELECT setval(pg_get_serial_sequence('pos_cashregister', 'id'), 1, false)"
                        )
                    except Exception:
                        # Fallback para SQLite u otros motores
                        pass

                return Response({
                    'message': f'{count} registros de caja eliminados e IDs reiniciados correctamente.',
                    'deleted_count': count,
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            return Response(
                {'error': f'Error al purgar cierres de caja: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], url_path='current')
    def current_register(self, request):
        """
        Obtiene la caja abierta actual para un almacén.
        Query param: warehouse_id
        """
        warehouse_id = request.query_params.get('warehouse_id')
        
        if not warehouse_id:
            return Response(
                {'error': 'Debe proporcionar warehouse_id'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        cash_register = CashRegister.objects.filter(
            warehouse_id=warehouse_id,
            status='OPEN'
        ).first()
        
        if not cash_register:
            return Response(
                {'message': 'No hay caja abierta para este almacén'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response(
            CashRegisterSerializer(cash_register).data,
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['get'], url_path='report')
    def register_report(self, request, pk=None):
        """
        Reporte detallado de una sesión de caja cerrada.
        """
        cash_register = self.get_object()
        
        # Ventas de la sesión
        invoices = cash_register.invoices.filter(
            status__in=['PAID', 'PARTIAL']
        ).select_related('customer')
        
        # Desglose por método de pago
        payments_by_method = []
        for payment in InvoicePayment.objects.filter(
            invoice__cash_register=cash_register,
            invoice__status__in=['PAID', 'PARTIAL']
        ).values('payment_method__name').annotate(
            total=Sum('amount')
        ).order_by('-total'):
            payments_by_method.append({
                'method': payment['payment_method__name'],
                'total': float(payment['total'] or 0),
            })
        
        # Total vendido
        total_sales = invoices.aggregate(total=Sum('total'))['total'] or 0
        
        return Response({
            'register': CashRegisterSerializer(cash_register).data,
            'invoices_count': invoices.count(),
            'total_sales': float(total_sales),
            'payments_by_method': payments_by_method,
        })


class WarehouseUserViewSet(viewsets.ModelViewSet):
    """
    Gestión de asignaciones de usuarios a Puntos de Venta.
    """
    queryset = WarehouseUser.objects.select_related(
        'user', 'warehouse', 'group'
    )
    serializer_class = WarehouseUserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    filterset_fields = ['warehouse', 'group', 'user', 'is_active']
    search_fields = ['user__username', 'warehouse__name']
    ordering = ['warehouse', 'user']
    
    def get_queryset(self):
        """
        Los administradores ven todas las asignaciones.
        Los demás usuarios solo ven las suyas.
        """
        user = self.request.user
        if user.is_superuser or user.groups.filter(name='Administrador').exists():
            return self.queryset
        return self.queryset.filter(user=user)


class MyWarehousesViewSet(viewsets.ViewSet):
    """
    Endpoint especial: devuelve los PVs donde el usuario actual está asignado.
    Incluye información sobre si hay caja abierta en cada PV.
    
    GET /api/pos/my-warehouses/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def list(self, request):
        user = request.user
        
        # Si es admin/superuser, tiene acceso a todos los PVs
        if user.is_superuser or user.groups.filter(name='Administrador').exists():
            warehouses = Warehouse.objects.filter(
                warehouse_type='POINT_OF_SALE',
                enabled=True
            )
        else:
            # Obtener IDs de warehouses donde el usuario está asignado
            warehouse_ids = WarehouseUser.objects.filter(
                user=user,
                is_active=True,
                warehouse__warehouse_type='POINT_OF_SALE'
            ).values_list('warehouse_id', flat=True)
            
            warehouses = Warehouse.objects.filter(
                id__in=warehouse_ids,
                enabled=True
            )
        
        # Para cada PV, verificar si hay caja abierta
        result = []
        for wh in warehouses:
            open_register = CashRegister.objects.filter(
                warehouse=wh,
                status='OPEN'
            ).first()
            
            # Obtener el rol del usuario en este PV
            assignment = WarehouseUser.objects.filter(
                user=user,
                warehouse=wh,
                is_active=True
            ).first()
            
            result.append({
                'id': wh.id,
                'name': wh.name,
                'code': wh.code,
                'address': wh.address,
                'has_open_register': open_register is not None,
                'current_register_id': open_register.id if open_register else None,
                'current_register_opening': open_register.opening_date if open_register else None,
                'user_role': assignment.group.name if assignment else (
                    'Administrador' if (user.is_superuser or user.groups.filter(name='Administrador').exists()) else None
                ),
            })
        
        return Response(result)