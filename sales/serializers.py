from rest_framework import serializers
from .models import Customer, Invoice, InvoiceItem
from inventory.serializers import ProductSerializer, ProductPresentationSerializer, WarehouseSerializer


class CustomerSerializer(serializers.ModelSerializer):
    invoices_count = serializers.SerializerMethodField()
    total_spent = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = '__all__'

    def get_invoices_count(self, obj):
        return obj.invoices.count()

    def get_total_spent(self, obj):
        from django.db.models import Sum
        result = obj.invoices.filter(status__in=['PAID', 'PARTIAL']).aggregate(
            total=Sum('total')
        )
        return float(result['total'] or 0)


class InvoiceItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    presentation = ProductPresentationSerializer(read_only=True)
    warehouse = WarehouseSerializer(read_only=True)

    class Meta:
        model = InvoiceItem
        fields = [
            'id', 'product', 'presentation', 'warehouse',
            'quantity', 'unit_price', 'discount_percent', 'line_total'
        ]


class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)
    customer_detail = CustomerSerializer(source='customer', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True, default='—')

    class Meta:
        model = Invoice
        fields = '__all__'


class InvoiceCreateSerializer(serializers.Serializer):
    """Serializer para crear factura con líneas"""
    customer_id = serializers.IntegerField()
    due_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    items = serializers.ListField(child=serializers.DictField(), min_length=1)

    def validate_items(self, items):
        for i, item in enumerate(items):
            if not item.get('product_id'):
                raise serializers.ValidationError(f"Línea {i+1}: producto requerido")
            if not item.get('presentation_id'):
                raise serializers.ValidationError(f"Línea {i+1}: presentación requerida")
            if not item.get('warehouse_id'):
                raise serializers.ValidationError(f"Línea {i+1}: almacén requerido")
            qty = float(item.get('quantity', 0))
            if qty <= 0:
                raise serializers.ValidationError(f"Línea {i+1}: cantidad debe ser mayor a 0")
        return items