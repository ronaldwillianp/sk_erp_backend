from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from .importers import (
    WarehouseImporter, SupplierImporter, ProductImporter,
    get_warehouse_template, get_supplier_template, get_product_template,
    ImportError as ImportErrorException,
)


IMPORTER_MAP = {
    'warehouses': (WarehouseImporter, get_warehouse_template, 'plantilla_almacenes.xlsx'),
    'suppliers': (SupplierImporter, get_supplier_template, 'plantilla_proveedores.xlsx'),
    'products': (ProductImporter, get_product_template, 'plantilla_productos.xlsx'),
}


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_template(request, import_type: str):
    """Descarga la plantilla Excel para el tipo de importación"""
    if import_type not in IMPORTER_MAP:
        return Response(
            {'error': f'Tipo de importación inválido: {import_type}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    _, template_func, filename = IMPORTER_MAP[import_type]
    file_bytes = template_func()

    response = HttpResponse(
        file_bytes,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser])
def import_data(request, import_type: str):
    """Importa datos desde un archivo CSV o Excel"""
    if import_type not in IMPORTER_MAP:
        return Response(
            {'error': f'Tipo de importación inválido: {import_type}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    file_obj = request.FILES.get('file')
    if not file_obj:
        return Response(
            {'error': 'No se proporcionó archivo'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Validar extensión
    filename = file_obj.name.lower()
    if not filename.endswith(('.csv', '.xlsx', '.xls')):
        return Response(
            {'error': 'El archivo debe ser CSV (.csv) o Excel (.xlsx, .xls)'},
            status=status.HTTP_400_BAD_REQUEST
        )

    importer_class, _, _ = IMPORTER_MAP[import_type]

    try:
        importer = importer_class(file_obj, file_obj.name)
        result = importer.import_all()
        return Response(result, status=status.HTTP_200_OK)
    except ImportErrorException as e:
        return Response(
            {'error': str(e), 'row': e.row, 'field': e.field},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        return Response(
            {'error': f'Error inesperado al procesar el archivo: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )