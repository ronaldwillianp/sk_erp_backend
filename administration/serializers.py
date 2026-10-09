# administration/serializers.py

from rest_framework import serializers
from .models import User
from django.contrib.auth.models import Group
from configuration.models import Province, Municipality
from configuration.serializers import ProvinceSerializer, MunicipalitySerializer

class GroupSerializer(serializers.ModelSerializer):
    user_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Group
        fields = ['id', 'name', 'user_count']
        
class UserSerializer(serializers.ModelSerializer):
    # === CAMPOS PARA LECTURA (objetos completos) ===
    groups = GroupSerializer(many=True, read_only=True)
    province = ProvinceSerializer(read_only=True)
    municipality = MunicipalitySerializer(read_only=True)
    
    # === CAMPOS PARA ESCRITURA (solo IDs) ===
    group_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Group.objects.all(),
        source='groups',
        write_only=True,
        required=False
    )
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
        model = User
        fields = [
            'id', 'username', 'password', 'first_name', 'last_name', 'email', 
            'ci', 'contact', 'address', 
            'province', 'municipality', 'groups',
            'province_id', 'municipality_id', 'group_ids',
            'is_active'
        ]
        extra_kwargs = {
            'password': {'write_only': True, 'required': False} # Importante: required=False
        }

    def create(self, validated_data):
        groups_data = validated_data.pop('groups', [])
        password = validated_data.pop('password')
        
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        
        if groups_data:
            user.groups.set(groups_data)
        return user

    def update(self, instance, validated_data):
        # Extraer datos especiales antes de actualizar campos simples
        groups_data = validated_data.pop('groups', None)
        password = validated_data.pop('password', None)
        
        # Actualizar campos básicos (nombre, email, ci, etc.)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
            
        # Actualizar contraseña solo si se proporcionó
        if password:
            instance.set_password(password)
            
        instance.save()
        
        # Actualizar grupos solo si se proporcionaron
        if groups_data is not None:
            instance.groups.set(groups_data)
            
        return instance

class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, required=True, min_length=8)

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("La contraseña actual es incorrecta")
        return value

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({
                "confirm_password": "Las contraseñas nuevas no coinciden"
            })
        if data['current_password'] == data['new_password']:
            raise serializers.ValidationError({
                "new_password": "La nueva contraseña debe ser diferente a la actual"
            })
        return data

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user    

class PasswordInitializeSerializer(serializers.Serializer):
    new_password = serializers.CharField(required=True, min_length=8)
    confirm_password = serializers.CharField(required=True, min_length=8)

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError("Las contraseñas no coinciden")
        return data

    def save(self, user, **kwargs):
        """
        Recibe el usuario objetivo y actualiza su password.
        Útil para que el Admin reinicie passwords.
        """
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user

class UserGroupsSerializer(serializers.Serializer):
    group_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Group.objects.all(),
        required=True
    )

    def validate_group_ids(self, value):
        if not value:
            raise serializers.ValidationError("Debe asignar al menos un grupo")
        return value

    def update(self, instance, validated_data):
        instance.groups.set(validated_data['group_ids'])
        return instance