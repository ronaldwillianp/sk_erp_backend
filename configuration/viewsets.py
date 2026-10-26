from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import Http404

from .models import Province, Municipality, MeasureUnit, Currency, PaymentMethod, Company, Category
from .serializers import (
    ProvinceSerializer,
    MunicipalitySerializer,
    MunicipalityLiteSerializer,
    MeasureUnitSerializer,
    CurrencySerializer,
    PaymentMethodSerializer,
    CompanySerializer,
    CategorySerializer
)


class CompanyViewSet(viewsets.ModelViewSet):
    """
    ViewSet singleton para la empresa.
    Solo puede existir una empresa en el sistema.

    El truco del singleton está en get_object(): siempre devuelve la única
    empresa sin importar el pk de la URL, así PUT/PATCH funcionan con
    cualquier /company/{id}/.
    """
    serializer_class = CompanySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Company.objects.all()

    def get_object(self):
        """
        Sobrescrito para el singleton: ignora el pk de la URL
        y siempre devuelve la única empresa existente.
        """
        company = self.get_queryset().first()
        if company is None:
            raise Http404("No hay empresa configurada")
        return company

    def list(self, request, *args, **kwargs):
        """GET /company/ - Devuelve la única empresa"""
        company = self.get_queryset().first()
        if company is None:
            return Response(
                {'detail': 'No hay empresa configurada'},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = self.get_serializer(company)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        """GET /company/{pk}/ - Ignora el pk, devuelve la única empresa"""
        return self.list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        """POST /company/ - Crea la empresa solo si no existe"""
        if Company.objects.exists():
            return Response(
                {'detail': 'Ya existe una empresa configurada. Use PUT/PATCH para actualizar.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """DELETE - No permitido para el singleton"""
        return Response(
            {'detail': 'No se puede eliminar la empresa del sistema'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

class ProvinceViewSet(viewsets.ModelViewSet):
    queryset = Province.objects.all().order_by('name')
    serializer_class = ProvinceSerializer
    permission_classes = [permissions.IsAuthenticated]

    # Búsqueda: ?search=ciego
    search_fields = ['name', 'short_name']

    # Ordenamiento: ?ordering=name  o  ?ordering=-name
    ordering_fields = ['name', 'short_name', 'enabled']
    ordering = ['name']

    # Filtros exactos: ?enabled=true
    filterset_fields = ['enabled']

    @action(detail=True, methods=['get'], url_path='municipalities')
    def municipalities(self, request, pk=None):
        """Municipios de una provincia específica"""
        province = self.get_object()
        municipalities = province.municipalities.all().order_by('name')
        serializer = MunicipalityLiteSerializer(municipalities, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='enabled')
    def enabled(self, request):
        """Solo provincias habilitadas"""
        provinces = self.get_queryset().filter(enabled=True)
        serializer = self.get_serializer(provinces, many=True)
        return Response(serializer.data)


class MunicipalityViewSet(viewsets.ModelViewSet):
    serializer_class = MunicipalitySerializer
    permission_classes = [permissions.IsAuthenticated]

    # Búsqueda: incluye el nombre de la provincia para búsquedas más amplias
    search_fields = ['name', 'short_name', 'province__name']

    # Ordenamiento
    ordering_fields = ['name', 'short_name', 'province__name']
    ordering = ['name']

    # Filtros exactos: ?province=9  (nota: usa 'province', no 'province_id')
    filterset_fields = ['province']

    def get_queryset(self):
        """
        Filtra por provincia si se envía ?province_id=
        GET /api/configuration/municipalities/?province_id=9
        """
        queryset = Municipality.objects.select_related('province').order_by('name')
        province_id = self.request.query_params.get('province_id', None)
        if province_id:
            queryset = queryset.filter(province_id=province_id)
        return queryset


class MeasureUnitViewSet(viewsets.ModelViewSet):
    queryset = MeasureUnit.objects.all()
    serializer_class = MeasureUnitSerializer
    permission_classes = [permissions.IsAuthenticated]

    search_fields = ['name', 'short_name']
    ordering_fields = ['name', 'short_name', 'enabled']
    ordering = ['name']
    filterset_fields = ['enabled']

    @action(detail=False, methods=['get'], url_path='enabled')
    def enabled(self, request):
        """Unidades de medida habilitadas (sin paginar)"""
        queryset = self.get_queryset().filter(enabled=True)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class CurrencyViewSet(viewsets.ModelViewSet):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer
    permission_classes = [permissions.IsAuthenticated]

    search_fields = ['name', 'short_name']
    ordering_fields = ['name', 'short_name', 'default', 'enabled']
    ordering = ['name']
    filterset_fields = ['enabled', 'default']

    @action(detail=False, methods=['get'], url_path='default')
    def default_currency(self, request):
        """Devuelve la moneda configurada por defecto"""
        currency = Currency.objects.filter(default=True, enabled=True).first()
        if currency:
            serializer = self.get_serializer(currency)
            return Response(serializer.data)
        return Response({"detail": "No hay moneda por defecto"}, status=status.HTTP_404_NOT_FOUND)


class PaymentMethodViewSet(viewsets.ModelViewSet):
    queryset = PaymentMethod.objects.all()
    serializer_class = PaymentMethodSerializer
    permission_classes = [permissions.IsAuthenticated]

    search_fields = ['name', 'description']
    ordering_fields = ['name', 'enabled']
    ordering = ['name']
    filterset_fields = ['enabled']
    
    @action(detail=False, methods=['get'], url_path='enabled')
    def enabled(self, request):
        """Devuelve solo los métodos de pago habilitados"""
        queryset = self.get_queryset().filter(enabled=True)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.select_related('parent').order_by('category_type', 'name')
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated]

    # Búsqueda y filtros
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'category_type', 'enabled']
    ordering = ['name']
    filterset_fields = ['category_type', 'enabled', 'parent']

    @action(detail=False, methods=['get'], url_path='enabled')
    def enabled(self, request):
        """
        Categorías habilitadas, opcionalmente filtradas por tipo.
        Útil para selects en otros módulos.
        Ej: /categories/enabled/?category_type=EXPENSE
        """
        queryset = self.get_queryset().filter(enabled=True)
        category_type = request.query_params.get('category_type', None)
        if category_type:
            queryset = queryset.filter(category_type=category_type)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='children')
    def children(self, request, pk=None):
        """Subcategorías de una categoría específica"""
        category = self.get_object()
        children_qs = category.children.select_related('parent').order_by('name')
        serializer = self.get_serializer(children_qs, many=True)
        return Response(serializer.data)