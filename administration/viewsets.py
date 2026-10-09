from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models import Count

from .serializers import UserSerializer, GroupSerializer, UserGroupsSerializer

User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    # queryset = User.objects.select_related('province', 'municipality').prefetch_related('groups')
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    # Búsqueda: ?search=juan  (busca en usuario, nombre, email, CI)
    search_fields = ['username', 'first_name', 'last_name', 'email', 'ci']

    # Ordenamiento: ?ordering=username  o  ?ordering=-first_name
    ordering_fields = ['username', 'first_name', 'last_name', 'email', 'is_active']
    ordering = ['username']

    # Filtros exactos: ?is_active=true  /  ?province=9  /  ?municipality=88
    filterset_fields = ['is_active', 'province', 'municipality']

    # Campos que un usuario puede editar de su propio perfil
    PROFILE_EDITABLE_FIELDS = [
        'first_name', 'last_name', 'email', 'ci',
        'contact', 'address', 'province_id', 'municipality_id',
    ]

    def get_queryset(self):
        """
        Excluye al usuario autenticado de la lista para evitar
        que pueda editarse o eliminarse a sí mismo desde esta vista.
        """
        return (
            User.objects
            .select_related('province', 'municipality')
            .prefetch_related('groups')
            .exclude(id=self.request.user.id)
        )

    @action(detail=False, methods=['get', 'put', 'patch'], url_path='me')
    def me(self, request):
        """
        GET  → Devuelve el perfil del usuario autenticado
        PUT/PATCH → Actualiza solo los campos permitidos del propio perfil
        """
        user = request.user

        if request.method == 'GET':
            serializer = UserSerializer(user)
            return Response(serializer.data)

        # Filtrar solo los campos permitidos para auto-edición (seguridad)
        filtered_data = {
            key: value
            for key, value in request.data.items()
            if key in self.PROFILE_EDITABLE_FIELDS
        }

        serializer = UserSerializer(user, data=filtered_data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(UserSerializer(user).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['put'], url_path='update_groups')
    def update_groups(self, request, pk=None):
        user = self.get_object()
        serializer = UserGroupsSerializer(data=request.data)

        if serializer.is_valid():
            serializer.update(user, serializer.validated_data)
            return Response(
                {"detail": "Grupos actualizados", "user": UserSerializer(user).data},
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.annotate(user_count=Count('user')).order_by('name')
    serializer_class = GroupSerializer
    permission_classes = [permissions.IsAuthenticated]

    # Búsqueda: ?search=admin
    search_fields = ['name']

    # Ordenamiento: ahora también por cantidad de usuarios
    ordering_fields = ['name', 'user_count']
    ordering = ['name']