from rest_framework.permissions import BasePermission


class IsDeveloper(BasePermission):
    """
    Solo permite acceso a usuarios del grupo 'Desarrollador'.
    Usado para acciones destructivas masivas (purge).
    """
    message = 'Se requiere rol de Desarrollador para realizar esta acción.'

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return user.groups.filter(name='Desarrollador').exists()


class IsDeveloperOrAdmin(BasePermission):
    """
    Permite acceso a usuarios del grupo 'Desarrollador' o 'Administrador'.
    Usado para eliminación de registros individuales.
    """
    message = 'Se requiere rol de Desarrollador o Administrador para realizar esta acción.'

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return (
            user.groups.filter(name__in=['Desarrollador', 'Administrador']).exists()
        )