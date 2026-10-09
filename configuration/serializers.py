from rest_framework import serializers
from .models import Province, Municipality, MeasureUnit, Currency, PaymentMethod, Company, Category

# ============================================
# COMPANY (Singleton)
# ============================================
class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ['id', 'name', 'slogan', 'email', 'phone', 'address', 'logo']

# ============================================
# CATEGORY (Jerárquico)
# ============================================
class CategoryLiteSerializer(serializers.ModelSerializer):
    """Serializer ligero para representar el parent sin recursión"""
    class Meta:
        model = Category
        fields = ['id', 'name', 'category_type']


class CategorySerializer(serializers.ModelSerializer):
    # === Lectura ===
    parent = CategoryLiteSerializer(read_only=True)
    children_count = serializers.SerializerMethodField()

    # === Escritura ===
    parent_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        source='parent',
        write_only=True,
        required=False,
        allow_null=True
    )

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'category_type', 'parent', 'parent_id',
            'description', 'enabled', 'children_count'
        ]

    def get_children_count(self, obj):
        return obj.children.count()

    def validate(self, data):
        parent = data.get('parent', getattr(self.instance, 'parent', None))
        category_type = data.get(
            'category_type',
            getattr(self.instance, 'category_type', None)
        )

        if parent:
            # No puede ser su propio padre
            if self.instance and parent.id == self.instance.id:
                raise serializers.ValidationError({
                    'parent_id': 'Una categoría no puede ser su propio padre'
                })

            # El padre debe ser del mismo tipo
            if parent.category_type != category_type:
                raise serializers.ValidationError({
                    'parent_id': 'La categoría padre debe ser del mismo tipo'
                })

            # Evitar ciclos (el padre no puede ser un descendiente)
            if self.instance:
                current = parent
                while current:
                    if current.id == self.instance.id:
                        raise serializers.ValidationError({
                            'parent_id': 'Se detectó un ciclo en la jerarquía'
                        })
                    current = current.parent

        return data

class ProvinceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Province
        fields = ['id', 'name', 'short_name', 'enabled']


class MunicipalitySerializer(serializers.ModelSerializer):
    province_name = serializers.CharField(source='province.name', read_only=True)
    province_short_name = serializers.CharField(source='province.short_name', read_only=True)

    class Meta:
        model = Municipality
        fields = ['id', 'name', 'short_name', 'province', 'province_name', 'province_short_name']


class MunicipalityLiteSerializer(serializers.ModelSerializer):
    """Versión ligera para selects dependientes (provincia → municipio)"""
    class Meta:
        model = Municipality
        fields = ['id', 'name', 'short_name']


class MeasureUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeasureUnit
        fields = ['id', 'name', 'short_name', 'enabled']


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = ['id', 'name', 'short_name', 'default', 'enabled']

    def update(self, instance, validated_data):
        # Si se marca como default, desmarcar las demás
        if validated_data.get('default', False):
            Currency.objects.filter(default=True).exclude(pk=instance.pk).update(default=False)
        return super().update(instance, validated_data)

    def create(self, validated_data):
        if validated_data.get('default', False):
            Currency.objects.filter(default=True).update(default=False)
        return super().create(validated_data)


class PaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = ['id', 'name', 'description', 'enabled']