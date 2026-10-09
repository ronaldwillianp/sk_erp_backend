from django.shortcuts import render
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from knox.models import AuthToken
from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model

from administration.serializers import UserSerializer

User = get_user_model()


def index(request):
    return render(request, 'index.html', locals())


class LoginView(APIView):
    """
    Login personalizado: recibe JSON con username/password,
    devuelve token de Knox + datos del usuario.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, format=None):
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return Response(
                {"detail": "Se requiere usuario y contraseña"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Autenticar con Django
        user = authenticate(username=username, password=password)

        if user is None:
            return Response(
                {"detail": "Credenciales inválidas"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not user.is_active:
            return Response(
                {"detail": "La cuenta está desactivada"},
                status=status.HTTP_403_FORBIDDEN
            )

        # Crear token con Knox
        instance, token = AuthToken.objects.create(user)

        # Serializar datos del usuario
        user_data = UserSerializer(user).data

        return Response({
            'token': token,
            'expiry': instance.expiry,
            'user': user_data
        }, status=status.HTTP_200_OK)