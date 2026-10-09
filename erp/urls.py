"""
URL configuration for erp project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, re_path, include
from knox import views as knox_views
from .views import LoginView, index
from django.conf import settings
from  django.conf.urls.static import static

urlpatterns = [
    # Modulo administrativo de Django
    path('admin/', admin.site.urls),

    # Autenticación (Knox)
    path(r'api/auth/login/', LoginView.as_view(), name='knox_login'),
    path(r'api/auth/logout/', knox_views.LogoutView.as_view(), name='knox_logout'),
    path(r'api/auth/logoutall/', knox_views.LogoutAllView.as_view(), name='knox_logoutall'),

    # System Modules
    path('api/v1.0/administration/', include('administration.urls')),
    path('api/configuration/', include('configuration.urls')),
    path('api/inventory/', include('inventory.urls')),
    path('api/sales/', include('sales.urls')),

    re_path(r'^(?!admin/|api/|media/|assets/|.well-known/|auth/)', index),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)