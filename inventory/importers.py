"""
Servicios de importación masiva desde CSV/Excel.
Soporta: almacenes, proveedores, productos (con presentaciones).
"""
import csv
import io
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Tuple, Any

from django.db import transaction
from openpyxl import load_workbook, Workbook

from .models import Warehouse, Supplier, Product, ProductPresentation, ProductWarehouseStock
from configuration.models import Province, Municipality, Category, MeasureUnit


class ImportError(Exception):
    """Error específico de importación con detalle de fila"""
    def __init__(self, row: int, field: str, message: str):
        self.row = row
        self.field = field
        self.message = message
        super().__init__(f"Fila {row} ({field}): {message}")


class BaseImporter:
    """Clase base para todos los importadores"""
    EXPECTED_COLUMNS: List[str] = []
    REQUIRED_COLUMNS: List[str] = []

    def __init__(self, file_obj, filename: str):
        self.file_obj = file_obj
        self.filename = filename.lower()
        self.is_excel = filename.lower().endswith(('.xlsx', '.xls'))

    def read_rows(self) -> Tuple[List[str], List[Dict[str, str]]]:
        """Lee el archivo y retorna (headers, rows como dict)"""
        if self.is_excel:
            return self._read_excel()
        return self._read_csv()

    def _read_excel(self) -> Tuple[List[str], List[Dict[str, str]]]:
        self.file_obj.seek(0)
        wb = load_workbook(self.file_obj, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return [], []

        headers = [str(h).strip().lower() if h else f'col_{i}' for i, h in enumerate(rows[0])]
        data = []
        for row in rows[1:]:
            if not any(row):  # fila vacía
                continue
            data.append({
                headers[i]: (str(cell).strip() if cell is not None else '')
                for i, cell in enumerate(row)
                if i < len(headers)
            })
        return headers, data

    def _read_csv(self) -> Tuple[List[str], List[Dict[str, str]]]:
        self.file_obj.seek(0)
        # Intentar UTF-8, fallback a latin-1
        try:
            content = self.file_obj.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            self.file_obj.seek(0)
            content = self.file_obj.read().decode('latin-1')

        reader = csv.DictReader(io.StringIO(content))
        headers = [h.strip().lower() for h in (reader.fieldnames or [])]
        data = []
        for row in reader:
            cleaned = {k.strip().lower(): (v.strip() if v else '') for k, v in row.items()}
            if any(cleaned.values()):  # ignorar filas vacías
                data.append(cleaned)
        return headers, data

    def validate_headers(self, headers: List[str]) -> List[str]:
        """Valida que las columnas requeridas estén presentes"""
        missing = [c for c in self.REQUIRED_COLUMNS if c.lower() not in [h.lower() for h in headers]]
        return missing

    @staticmethod
    def generate_template(columns: List[str], example_rows: List[List[Any]] = None) -> bytes:
        """Genera una plantilla Excel con las columnas esperadas y filas de ejemplo"""
        wb = Workbook()
        ws = wb.active
        ws.title = "Plantilla"

        # Headers
        for col_idx, col_name in enumerate(columns, 1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.font = cell.font.copy(bold=True)

        # Filas de ejemplo
        if example_rows:
            for row_idx, row_data in enumerate(example_rows, 2):
                for col_idx, value in enumerate(row_data, 1):
                    ws.cell(row=row_idx, column=col_idx, value=value)

        # Ajustar ancho de columnas
        for col_idx, col_name in enumerate(columns, 1):
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = max(15, len(col_name) + 3)

        output = io.BytesIO()
        wb.save(output)
        return output.getvalue()


class WarehouseImporter(BaseImporter):
    """Importa almacenes desde CSV/Excel"""
    REQUIRED_COLUMNS = ['codigo', 'nombre', 'tipo']

    def import_all(self) -> Dict:
        headers, rows = self.read_rows()
        missing = self.validate_headers(headers)
        if missing:
            raise ImportError(0, 'headers', f'Faltan columnas requeridas: {", ".join(missing)}')

        created = []
        errors = []
        seen_codes = set()

        for row_num, row in enumerate(rows, start=2):
            code = (row.get('codigo') or '').strip().upper()
            name = (row.get('nombre') or '').strip()
            wh_type = (row.get('tipo') or '').strip().upper()
            address = (row.get('direccion') or '').strip()
            province_name = (row.get('provincia') or '').strip()

            # Validaciones
            if not code:
                errors.append({'row': row_num, 'field': 'codigo', 'error': 'Código requerido', 'data': row})
                continue
            if not name:
                errors.append({'row': row_num, 'field': 'nombre', 'error': 'Nombre requerido', 'data': row})
                continue
            if wh_type not in ['WAREHOUSE', 'POINT_OF_SALE', 'ALMACEN', 'PUNTO_DE_VENTA', 'PV', 'ALM']:
                errors.append({'row': row_num, 'field': 'tipo', 'error': f'Tipo inválido: {wh_type}. Use WAREHOUSE o POINT_OF_SALE', 'data': row})
                continue
            if code in seen_codes:
                errors.append({'row': row_num, 'field': 'codigo', 'error': f'Código duplicado en archivo: {code}', 'data': row})
                continue
            if Warehouse.objects.filter(code=code).exists():
                errors.append({'row': row_num, 'field': 'codigo', 'error': f'Código ya existe en BD: {code}', 'data': row})
                continue
            if Warehouse.objects.filter(name=name).exists():
                errors.append({'row': row_num, 'field': 'nombre', 'error': f'Nombre ya existe en BD: {name}', 'data': row})
                continue

            # Normalizar tipo
            type_map = {'ALMACEN': 'WAREHOUSE', 'ALM': 'WAREHOUSE', 'PUNTO_DE_VENTA': 'POINT_OF_SALE', 'PV': 'POINT_OF_SALE'}
            wh_type = type_map.get(wh_type, wh_type)

            # Buscar provincia
            province = None
            if province_name:
                province = Province.objects.filter(name__iexact=province_name).first()
                if not province:
                    errors.append({'row': row_num, 'field': 'provincia', 'error': f'Provincia no encontrada: {province_name}', 'data': row})
                    continue

            try:
                wh = Warehouse.objects.create(
                    code=code,
                    name=name,
                    warehouse_type=wh_type,
                    address=address,
                    province=province,
                )
                created.append({'row': row_num, 'code': code, 'name': name})
                seen_codes.add(code)
            except Exception as e:
                errors.append({'row': row_num, 'field': 'general', 'error': str(e), 'data': row})

        return {
            'total_rows': len(rows),
            'created_count': len(created),
            'error_count': len(errors),
            'created': created,
            'errors': errors,
        }


class SupplierImporter(BaseImporter):
    """Importa proveedores desde CSV/Excel"""
    REQUIRED_COLUMNS = ['nombre']

    def import_all(self) -> Dict:
        headers, rows = self.read_rows()
        missing = self.validate_headers(headers)
        if missing:
            raise ImportError(0, 'headers', f'Faltan columnas requeridas: {", ".join(missing)}')

        created = []
        errors = []
        seen_names = set()

        for row_num, row in enumerate(rows, start=2):
            name = (row.get('nombre') or '').strip()
            contact_person = (row.get('contacto') or '').strip()
            email = (row.get('email') or '').strip()
            phone = (row.get('telefono') or '').strip()
            address = (row.get('direccion') or '').strip()
            province_name = (row.get('provincia') or '').strip()
            notes = (row.get('notas') or '').strip()

            if not name:
                errors.append({'row': row_num, 'field': 'nombre', 'error': 'Nombre requerido', 'data': row})
                continue
            if name in seen_names:
                errors.append({'row': row_num, 'field': 'nombre', 'error': f'Nombre duplicado en archivo: {name}', 'data': row})
                continue
            if Supplier.objects.filter(name=name).exists():
                errors.append({'row': row_num, 'field': 'nombre', 'error': f'Proveedor ya existe en BD: {name}', 'data': row})
                continue

            # Email válido
            if email and '@' not in email:
                errors.append({'row': row_num, 'field': 'email', 'error': f'Email inválido: {email}', 'data': row})
                continue

            # Buscar provincia
            province = None
            if province_name:
                province = Province.objects.filter(name__iexact=province_name).first()
                if not province:
                    errors.append({'row': row_num, 'field': 'provincia', 'error': f'Provincia no encontrada: {province_name}', 'data': row})
                    continue

            try:
                supplier = Supplier.objects.create(
                    name=name,
                    contact_person=contact_person,
                    email=email,
                    phone=phone,
                    address=address,
                    province=province,
                    notes=notes,
                )
                created.append({'row': row_num, 'name': name})
                seen_names.add(name)
            except Exception as e:
                errors.append({'row': row_num, 'field': 'general', 'error': str(e), 'data': row})

        return {
            'total_rows': len(rows),
            'created_count': len(created),
            'error_count': len(errors),
            'created': created,
            'errors': errors,
        }


class ProductImporter(BaseImporter):
    """
    Importa productos con sus presentaciones desde CSV/Excel.
    Cada fila representa UNA presentación. Si un producto tiene varias
    presentaciones, aparecen varias filas con el mismo SKU.
    """
    REQUIRED_COLUMNS = ['sku', 'nombre', 'categoria', 'um_presentacion', 'factor', 'precio_venta']

    def import_all(self) -> Dict:
        headers, rows = self.read_rows()
        missing = self.validate_headers(headers)
        if missing:
            raise ImportError(0, 'headers', f'Faltan columnas requeridas: {", ".join(missing)}')

        created_products = []
        created_presentations = []
        errors = []

        # Agrupar filas por SKU
        sku_rows = {}
        for row_num, row in enumerate(rows, start=2):
            sku = (row.get('sku') or '').strip().upper()
            if not sku:
                errors.append({'row': row_num, 'field': 'sku', 'error': 'SKU requerido', 'data': row})
                continue
            if sku not in sku_rows:
                sku_rows[sku] = []
            sku_rows[sku].append((row_num, row))

        # Procesar cada producto
        with transaction.atomic():
            for sku, rows_list in sku_rows.items():
                first_row_num, first_row = rows_list[0]

                # Validar que no exista
                if Product.objects.filter(sku=sku).exists():
                    errors.append({
                        'row': first_row_num, 'field': 'sku',
                        'error': f'Producto con SKU {sku} ya existe en BD', 'data': first_row
                    })
                    continue

                # Datos del producto (de la primera fila)
                name = (first_row.get('nombre') or '').strip()
                barcode = (first_row.get('codigo_barras') or '').strip()
                category_name = (first_row.get('categoria') or '').strip()
                cost_price_str = (first_row.get('precio_costo') or '0').strip()
                sale_price_str = (first_row.get('precio_venta_base') or '').strip()
                min_stock_str = (first_row.get('stock_minimo') or '0').strip()
                is_service = (first_row.get('es_servicio') or '').strip().lower() in ('si', 'sí', 'true', '1', 'yes')
                description = (first_row.get('descripcion') or '').strip()

                if not name:
                    errors.append({'row': first_row_num, 'field': 'nombre', 'error': 'Nombre requerido', 'data': first_row})
                    continue
                if not category_name:
                    errors.append({'row': first_row_num, 'field': 'categoria', 'error': 'Categoría requerida', 'data': first_row})
                    continue

                # Buscar categoría
                category = Category.objects.filter(
                    name__iexact=category_name,
                    category_type='PRODUCT'
                ).first()
                if not category:
                    errors.append({'row': first_row_num, 'field': 'categoria', 'error': f'Categoría no encontrada: {category_name}', 'data': first_row})
                    continue

                # Parsear precios
                try:
                    cost_price = Decimal(cost_price_str) if cost_price_str else Decimal('0')
                except InvalidOperation:
                    errors.append({'row': first_row_num, 'field': 'precio_costo', 'error': f'Precio inválido: {cost_price_str}', 'data': first_row})
                    continue

                # Precio base: si está vacío, tomar el precio de venta de la primera presentación
                if sale_price_str:
                    try:
                        sale_price = Decimal(sale_price_str)
                    except InvalidOperation:
                        errors.append({'row': first_row_num, 'field': 'precio_venta_base', 'error': f'Precio inválido: {sale_price_str}', 'data': first_row})
                        continue
                else:
                    sale_price = None  # se calculará después

                try:
                    min_stock = Decimal(min_stock_str) if min_stock_str else Decimal('0')
                except InvalidOperation:
                    errors.append({'row': first_row_num, 'field': 'stock_minimo', 'error': f'Stock inválido: {min_stock_str}', 'data': first_row})
                    continue

                # Barcode único
                if barcode and Product.objects.filter(barcode=barcode).exists():
                    errors.append({'row': first_row_num, 'field': 'codigo_barras', 'error': f'Código de barras ya existe: {barcode}', 'data': first_row})
                    continue

                # Parsear presentaciones
                presentations_data = []
                has_error = False
                seen_ums = set()

                for row_num, row in rows_list:
                    um_name = (row.get('um_presentacion') or '').strip()
                    factor_str = (row.get('factor') or '1').strip()
                    pres_price_str = (row.get('precio_venta') or '0').strip()
                    is_default = (row.get('es_principal') or '').strip().lower() in ('si', 'sí', 'true', '1', 'yes')

                    if not um_name:
                        errors.append({'row': row_num, 'field': 'um_presentacion', 'error': 'UM requerida', 'data': row})
                        has_error = True
                        break

                    # Buscar unidad de medida
                    um = MeasureUnit.objects.filter(name__iexact=um_name).first()
                    if not um:
                        um = MeasureUnit.objects.filter(short_name__iexact=um_name).first()
                    if not um:
                        errors.append({'row': row_num, 'field': 'um_presentacion', 'error': f'UM no encontrada: {um_name}', 'data': row})
                        has_error = True
                        break

                    if um.id in seen_ums:
                        errors.append({'row': row_num, 'field': 'um_presentacion', 'error': f'UM duplicada para este producto: {um_name}', 'data': row})
                        has_error = True
                        break
                    seen_ums.add(um.id)

                    try:
                        factor = Decimal(factor_str) if factor_str else Decimal('1')
                        if factor <= 0:
                            raise InvalidOperation()
                    except InvalidOperation:
                        errors.append({'row': row_num, 'field': 'factor', 'error': f'Factor inválido: {factor_str}', 'data': row})
                        has_error = True
                        break

                    try:
                        pres_price = Decimal(pres_price_str) if pres_price_str else Decimal('0')
                    except InvalidOperation:
                        errors.append({'row': row_num, 'field': 'precio_venta', 'error': f'Precio inválido: {pres_price_str}', 'data': row})
                        has_error = True
                        break

                    presentations_data.append({
                        'um': um,
                        'factor': factor,
                        'price': pres_price,
                        'is_default': is_default,
                    })

                if has_error or not presentations_data:
                    continue

                # Si el precio base no se especificó, usar el de la presentación por defecto (o la primera)
                if sale_price is None:
                    default_pres = next((p for p in presentations_data if p['is_default']), presentations_data[0])
                    # precio base = precio presentación / factor
                    sale_price = default_pres['price'] / default_pres['factor'] if default_pres['factor'] > 0 else default_pres['price']

                # Asegurar que solo una presentación sea default
                default_count = sum(1 for p in presentations_data if p['is_default'])
                if default_count == 0:
                    presentations_data[0]['is_default'] = True
                elif default_count > 1:
                    # Solo la primera marcada como default
                    found_first = False
                    for p in presentations_data:
                        if p['is_default']:
                            if not found_first:
                                found_first = True
                            else:
                                p['is_default'] = False

                # Crear producto
                try:
                    product = Product.objects.create(
                        sku=sku,
                        name=name,
                        barcode=barcode,
                        category=category,
                        cost_price=cost_price,
                        sale_price=sale_price,
                        min_stock=min_stock,
                        is_service=is_service,
                        description=description,
                    )
                    created_products.append({'sku': sku, 'name': name})

                    # Crear presentaciones
                    for p_data in presentations_data:
                        ProductPresentation.objects.create(
                            product=product,
                            measure_unit=p_data['um'],
                            conversion_factor=p_data['factor'],
                            sale_price=p_data['price'],
                            is_default=p_data['is_default'],
                        )
                        created_presentations.append({
                            'sku': sku,
                            'um': p_data['um'].short_name,
                            'factor': str(p_data['factor']),
                        })

                except Exception as e:
                    errors.append({'row': first_row_num, 'field': 'general', 'error': str(e), 'data': first_row})

        return {
            'total_rows': len(rows),
            'products_created': len(created_products),
            'presentations_created': len(created_presentations),
            'error_count': len(errors),
            'created_products': created_products,
            'created_presentations': created_presentations,
            'errors': errors,
        }


# ===== Plantillas de ejemplo =====
def get_warehouse_template() -> bytes:
    return WarehouseImporter.generate_template(
        columns=['codigo', 'nombre', 'tipo', 'direccion', 'provincia'],
        example_rows=[
            ['WH-001', 'Almacén Central', 'WAREHOUSE', 'Calle 10 #45', 'La Habana'],
            ['PV-001', 'Punto de Venta Principal', 'POINT_OF_SALE', 'Calle 23 #12', 'La Habana'],
        ]
    )


def get_supplier_template() -> bytes:
    return SupplierImporter.generate_template(
        columns=['nombre', 'contacto', 'email', 'telefono', 'direccion', 'provincia', 'notas'],
        example_rows=[
            ['Proveedor ABC', 'Juan Pérez', 'juan@abc.com', '55551234', 'Calle 5 #10', 'La Habana', 'Entrega los lunes'],
            ['Distribuidora XYZ', 'María López', 'maria@xyz.com', '55554321', 'Avenida 3 #8', 'Santiago', ''],
        ]
    )


def get_product_template() -> bytes:
    return ProductImporter.generate_template(
        columns=['sku', 'nombre', 'codigo_barras', 'categoria', 'precio_costo', 'precio_venta_base',
                 'stock_minimo', 'es_servicio', 'descripcion',
                 'um_presentacion', 'factor', 'precio_venta', 'es_principal'],
        example_rows=[
            ['BEB-001', 'Cerveza Bucanero', '1234567890123', 'Bebidas', '200', '280', '50', 'no',
             'Cerveza nacional 330ml', 'Unidad', '1', '280', 'si'],
            ['BEB-001', 'Cerveza Bucanero', '1234567890123', 'Bebidas', '200', '280', '50', 'no',
             'Cerveza nacional 330ml', 'Caja', '24', '6000', 'no'],
            ['SRV-001', 'Servicio técnico', '', 'Servicios', '0', '500', '0', 'si',
             'Reparación de equipos', 'Unidad', '1', '500', 'si'],
        ]
    )