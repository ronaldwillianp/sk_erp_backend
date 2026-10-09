from django.urls import path, include
from rest_framework.routers import SimpleRouter

# Importar desde viewsets.py en vez de views.py
from .viewsets import UserViewSet, GroupViewSet

# Las APIViews siguen en views.py
from .views import ChangePasswordView, InitializePasswordView

router = SimpleRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'groups', GroupViewSet, basename='group')

urlpatterns = [
    path('', include(router.urls)),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('initialize-password/<int:user_id>/', InitializePasswordView.as_view(), name='initialize-password'),
]

# ============================================
# ENDPOINTS DISPONIBLES
# ============================================
#
# --- USUARIOS ---
# GET    /api/administration/users/                    → Listar todos los usuarios
# POST   /api/administration/users/                    → Crear un nuevo usuario
# GET    /api/administration/users/{id}/               → Obtener detalle de un usuario
# PUT    /api/administration/users/{id}/               → Actualizar usuario completo
# PATCH  /api/administration/users/{id}/               → Actualizar usuario parcial
# DELETE /api/administration/users/{id}/               → Eliminar un usuario
# PUT    /api/administration/users/{id}/update_groups/ → Cambiar grupos de un usuario
#
# --- GRUPOS ---
# GET    /api/administration/groups/                   → Listar todos los grupos
# POST   /api/administration/groups/                   → Crear un nuevo grupo
# GET    /api/administration/groups/{id}/              → Obtener detalle de un grupo
# PUT    /api/administration/groups/{id}/              → Actualizar grupo
# PATCH  /api/administration/groups/{id}/              → Actualizar grupo parcial
# DELETE /api/administration/groups/{id}/              → Eliminar un grupo
#
# --- CONTRASEÑAS ---
# POST   /api/administration/change-password/                    → Cambiar contraseña propia
# POST   /api/administration/initialize-password/{user_id}/      → Admin reinicia contraseña de otro
#