"""
Servicios de importación masiva desde CSV/Excel.
Soporta: almacenes, proveedores, productos (con presentaciones y stock inicial).
"""
import csv
import io
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Tuple, Any

from django.db import transaction
from openpyxl import load_workbook, Workbook

from .models import Warehouse, Supplier, Product, ProductPresentation, ProductWarehouseStock, StockMovement, StockDocument, StockDocumentLine
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
    Importa productos con sus presentaciones y stock inicial.
    
    - Cada fila representa UNA presentación.
    - Un producto con varias presentaciones aparece en varias filas con el mismo SKU.
    - Si una fila tiene 'cantidad' > 0, se genera una entrada de stock
      con referencia 'Carga inicial por importación'.
    - La columna 'almacen' es opcional; si se omite, usa el almacén por defecto.
    - Transacción global: si algún producto falla, no se importa nada.
    """
    REQUIRED_COLUMNS = ['sku', 'nombre', 'categoria', 'um_presentacion', 'factor', 'precio_venta']
    STOCK_REFERENCE = 'Carga inicial por importación'

    def __init__(self, file_obj, filename, user=None):
        super().__init__(file_obj, filename)
        self.user = user

    def import_all(self):
        headers, rows = self.read_rows()

        # Validar columnas requeridas
        missing = self.validate_headers(headers)
        if missing:
            raise ImportError(0, 'headers', f'Faltan columnas requeridas: {", ".join(missing)}')

        # Agrupar filas por SKU
        sku_rows = {}
        errors = []
        for row_num, row in enumerate(rows, start=2):
            sku = (row.get('sku') or '').strip().upper()
            if not sku:
                errors.append({'row': row_num, 'field': 'sku', 'error': 'SKU requerido', 'data': row})
                continue
            sku_rows.setdefault(sku, []).append((row_num, row))

        if errors:
            return self._build_result(len(rows), errors)

        # ============================================
        # FASE 1: VALIDACIÓN COMPLETA
        # ============================================
        valid_products = []

        for sku, rows_list in sku_rows.items():
            product_data, product_errors = self._validate_product(sku, rows_list)
            if product_errors:
                errors.extend(product_errors)
            else:
                valid_products.append(product_data)

        if errors:
            return self._build_result(len(rows), errors)

        # Contar cuántas líneas de stock habrá para saber si crear vale
        has_stock_entries = any(
            pres['quantity'] > 0
            for product_data in valid_products
            for pres in product_data['presentations']
        )

        # ============================================
        # FASE 2: CREACIÓN (transacción global)
        # ============================================
        try:
            with transaction.atomic():
                products_created = []
                presentations_created = []
                stock_entries_created = 0
                document = None

                # Si hay stock a cargar, crear un StockDocument (Vale de Entrada)
                if has_stock_entries:
                    document = StockDocument.objects.create(
                        document_type='ENTRY',
                        warehouse=self._get_default_warehouse(),  # Almacén por defecto del vale
                        reference='Importación masiva de productos',
                        notes=f'Generado automáticamente al importar {len(valid_products)} productos desde Excel/CSV',
                        created_by=self.user,
                    )

                for product_data in valid_products:
                    # Crear producto
                    product = Product.objects.create(
                        sku=product_data['sku'],
                        name=product_data['name'],
                        barcode=product_data['barcode'],
                        category=product_data['category'],
                        cost_price=product_data['cost_price'],
                        sale_price=product_data['sale_price'],
                        min_stock=product_data['min_stock'],
                        is_service=product_data['is_service'],
                        description=product_data['description'],
                    )
                    products_created.append({'sku': product.sku, 'name': product.name})

                    # Crear presentaciones + stock inicial
                    for pres_data in product_data['presentations']:
                        presentation = ProductPresentation.objects.create(
                            product=product,
                            measure_unit=pres_data['um'],
                            conversion_factor=pres_data['factor'],
                            sale_price=pres_data['price'],
                            is_default=pres_data['is_default'],
                        )
                        presentations_created.append({
                            'sku': product.sku,
                            'um': pres_data['um'].short_name,
                            'factor': str(pres_data['factor']),
                        })

                        # Generar entrada de stock si hay cantidad > 0
                        quantity = pres_data['quantity']
                        if quantity and quantity > 0:
                            warehouse = pres_data['warehouse']
                            self._create_initial_stock(
                                product, presentation, warehouse, quantity,
                                product_data['cost_price'], document
                            )
                            stock_entries_created += 1

                return {
                    'total_rows': len(rows),
                    'products_created': len(products_created),
                    'presentations_created': len(presentations_created),
                    'stock_entries_created': stock_entries_created,
                    'document_number': document.number if document else None,
                    'error_count': 0,
                    'created_products': products_created,
                    'created_presentations': presentations_created,
                    'errors': [],
                }

        except Exception as e:
            return {
                'total_rows': len(rows),
                'products_created': 0,
                'presentations_created': 0,
                'stock_entries_created': 0,
                'error_count': 1,
                'created_products': [],
                'created_presentations': [],
                'errors': [{
                    'row': 0,
                    'field': 'general',
                    'error': f'Error durante la creación (todo fue revertido): {str(e)}',
                }],
            }

    def _get_default_warehouse(self):
        """Obtiene el almacén por defecto para el vale padre."""
        warehouse = Warehouse.objects.filter(is_default=True, enabled=True).first()
        if not warehouse:
            warehouse = Warehouse.objects.filter(enabled=True).first()
        if not warehouse:
            raise Exception('No hay almacenes disponibles en el sistema')
        return warehouse
    
    def _validate_product(self, sku, rows_list):
        """Valida un producto completo (todas sus filas). Retorna (data, errors)."""
        errors = []
        first_row_num, first_row = rows_list[0]

        # SKU duplicado en BD
        if Product.objects.filter(sku=sku).exists():
            errors.append({
                'row': first_row_num, 'field': 'sku',
                'error': f'Producto con SKU {sku} ya existe en BD', 'data': first_row
            })
            return None, errors

        # Datos del producto (de la primera fila)
        name = (first_row.get('nombre') or '').strip()
        barcode = (first_row.get('codigo_barras') or '').strip()
        category_name = (first_row.get('categoria') or '').strip()
        cost_price_str = (first_row.get('precio_costo') or '0').strip() or '0'
        sale_price_str = (first_row.get('precio_venta_base') or '').strip()
        min_stock_str = (first_row.get('stock_minimo') or '0').strip() or '0'
        is_service = (first_row.get('es_servicio') or '').strip().lower() in ('si', 'sí', 'true', '1', 'yes')
        description = (first_row.get('descripcion') or '').strip()

        if not name:
            errors.append({'row': first_row_num, 'field': 'nombre', 'error': 'Nombre requerido', 'data': first_row})
            return None, errors
        if not category_name:
            errors.append({'row': first_row_num, 'field': 'categoria', 'error': 'Categoría requerida', 'data': first_row})
            return None, errors

        # Categoría
        category = Category.objects.filter(name__iexact=category_name, category_type='PRODUCT').first()
        if not category:
            errors.append({'row': first_row_num, 'field': 'categoria', 'error': f'Categoría no encontrada: {category_name}', 'data': first_row})
            return None, errors

        # Precio costo
        try:
            cost_price = Decimal(cost_price_str)
        except InvalidOperation:
            errors.append({'row': first_row_num, 'field': 'precio_costo', 'error': f'Precio inválido: {cost_price_str}', 'data': first_row})
            return None, errors

        # Precio base (puede ser vacío, se calcula después)
        sale_price = None
        if sale_price_str:
            try:
                sale_price = Decimal(sale_price_str)
            except InvalidOperation:
                errors.append({'row': first_row_num, 'field': 'precio_venta_base', 'error': f'Precio inválido: {sale_price_str}', 'data': first_row})
                return None, errors

        # Stock mínimo
        try:
            min_stock = Decimal(min_stock_str)
        except InvalidOperation:
            errors.append({'row': first_row_num, 'field': 'stock_minimo', 'error': f'Stock inválido: {min_stock_str}', 'data': first_row})
            return None, errors

        # Barcode único
        if barcode and Product.objects.filter(barcode=barcode).exists():
            errors.append({'row': first_row_num, 'field': 'codigo_barras', 'error': f'Código de barras ya existe: {barcode}', 'data': first_row})
            return None, errors

        # Validar cada presentación (fila)
        presentations_data = []
        seen_ums = set()

        for row_num, row in rows_list:
            pres_data, pres_errors = self._validate_presentation(row_num, row, seen_ums)
            if pres_errors:
                errors.extend(pres_errors)
                return None, errors
            seen_ums.add(pres_data['um'].id)
            presentations_data.append(pres_data)

        # Calcular precio base si no se especificó
        if sale_price is None:
            default_pres = next((p for p in presentations_data if p['is_default']), presentations_data[0])
            if default_pres['factor'] > 0:
                sale_price = default_pres['price'] / default_pres['factor']
            else:
                sale_price = default_pres['price']

        # Asegurar una sola presentación por defecto
        default_count = sum(1 for p in presentations_data if p['is_default'])
        if default_count == 0:
            presentations_data[0]['is_default'] = True
        elif default_count > 1:
            found_first = False
            for p in presentations_data:
                if p['is_default']:
                    if not found_first:
                        found_first = True
                    else:
                        p['is_default'] = False

        return {
            'sku': sku,
            'name': name,
            'barcode': barcode,
            'category': category,
            'cost_price': cost_price,
            'sale_price': sale_price,
            'min_stock': min_stock,
            'is_service': is_service,
            'description': description,
            'presentations': presentations_data,
        }, []

    def _validate_presentation(self, row_num, row, seen_ums):
        """Valida una presentación (fila). Retorna (data, errors)."""
        errors = []
        um_name = (row.get('um_presentacion') or '').strip()
        factor_str = (row.get('factor') or '1').strip() or '1'
        pres_price_str = (row.get('precio_venta') or '0').strip() or '0'
        is_default = (row.get('es_principal') or '').strip().lower() in ('si', 'sí', 'true', '1', 'yes')
        quantity_str = (row.get('cantidad') or '').strip()
        warehouse_code = (row.get('almacen') or '').strip().upper()

        # Unidad de medida
        if not um_name:
            errors.append({'row': row_num, 'field': 'um_presentacion', 'error': 'UM requerida', 'data': row})
            return None, errors
        um = MeasureUnit.objects.filter(name__iexact=um_name).first() or \
             MeasureUnit.objects.filter(short_name__iexact=um_name).first()
        if not um:
            errors.append({'row': row_num, 'field': 'um_presentacion', 'error': f'UM no encontrada: {um_name}', 'data': row})
            return None, errors
        if um.id in seen_ums:
            errors.append({'row': row_num, 'field': 'um_presentacion', 'error': f'UM duplicada para este producto: {um_name}', 'data': row})
            return None, errors

        # Factor
        try:
            factor = Decimal(factor_str)
            if factor <= 0:
                raise InvalidOperation()
        except InvalidOperation:
            errors.append({'row': row_num, 'field': 'factor', 'error': f'Factor inválido: {factor_str}', 'data': row})
            return None, errors

        # Precio
        try:
            pres_price = Decimal(pres_price_str)
        except InvalidOperation:
            errors.append({'row': row_num, 'field': 'precio_venta', 'error': f'Precio inválido: {pres_price_str}', 'data': row})
            return None, errors

        # Cantidad (opcional)
        quantity = Decimal('0')
        if quantity_str:
            try:
                quantity = Decimal(quantity_str)
                if quantity < 0:
                    errors.append({'row': row_num, 'field': 'cantidad', 'error': f'La cantidad no puede ser negativa: {quantity_str}', 'data': row})
                    return None, errors
            except InvalidOperation:
                errors.append({'row': row_num, 'field': 'cantidad', 'error': f'Cantidad inválida: {quantity_str}', 'data': row})
                return None, errors

        # Almacén (opcional, solo se valida si hay cantidad > 0)
        warehouse = None
        if quantity > 0:
            if warehouse_code:
                warehouse = Warehouse.objects.filter(code__iexact=warehouse_code, enabled=True).first()
                if not warehouse:
                    errors.append({'row': row_num, 'field': 'almacen', 'error': f'Almacén no encontrado o inactivo: {warehouse_code}', 'data': row})
                    return None, errors
            else:
                warehouse = Warehouse.objects.filter(is_default=True, enabled=True).first()
                if not warehouse:
                    errors.append({'row': row_num, 'field': 'almacen', 'error': 'No se especificó almacén y no hay almacén por defecto', 'data': row})
                    return None, errors

        return {
            'um': um,
            'factor': factor,
            'price': pres_price,
            'is_default': is_default,
            'quantity': quantity,
            'warehouse': warehouse,
        }, []

    def _create_initial_stock(self, product, presentation, warehouse, quantity, cost_price, document=None):
        """
        Crea el stock inicial y registra el movimiento de entrada.
        Si hay un documento padre (vale), también crea la línea del documento.
        """
        # Crear o actualizar stock
        stock, created = ProductWarehouseStock.objects.get_or_create(
            product=product,
            warehouse=warehouse,
            presentation=presentation,
            defaults={'quantity': Decimal('0'), 'total_value': Decimal('0')}
        )

        unit_cost = cost_price if cost_price else Decimal('0')
        stock.quantity += quantity
        stock.total_value += quantity * unit_cost
        stock.save()

        # Determinar la referencia del movimiento
        if document:
            reference = f"Vale {document.number}"
            notes = 'Generado por importación masiva de productos'
        else:
            reference = self.STOCK_REFERENCE
            notes = 'Generado automáticamente por importación masiva'

        # Registrar movimiento de entrada
        StockMovement.objects.create(
            movement_type='ENTRY',
            product=product,
            presentation=presentation,
            warehouse=warehouse,
            quantity=quantity,
            unit_cost=unit_cost,
            reference=reference,
            notes=notes,
            user=self.user,
        )

        # Si hay documento, crear la línea del documento
        if document:
            StockDocumentLine.objects.create(
                document=document,
                product=product,
                presentation=presentation,
                quantity=quantity,
                unit_cost=unit_cost,
            )

    def _build_result(self, total_rows, errors):
        """Construye un resultado de solo errores (sin creaciones)."""
        return {
            'total_rows': total_rows,
            'products_created': 0,
            'presentations_created': 0,
            'stock_entries_created': 0,
            'error_count': len(errors),
            'created_products': [],
            'created_presentations': [],
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
        columns=[
            'sku', 'nombre', 'codigo_barras', 'categoria', 'precio_costo',
            'precio_venta_base', 'stock_minimo', 'es_servicio', 'descripcion',
            'um_presentacion', 'factor', 'precio_venta', 'es_principal',
            'cantidad', 'almacen'
        ],
        example_rows=[
            ['BEB-001', 'Cerveza Bucanero', '1234567890123', 'Bebidas', '200', '280', '50', 'no',
             'Cerveza nacional 330ml', 'Unidad', '1', '280', 'si', '100', 'WH-001'],
            ['BEB-001', 'Cerveza Bucanero', '1234567890123', 'Bebidas', '200', '280', '50', 'no',
             'Cerveza nacional 330ml', 'Caja', '24', '6000', 'no', '5', 'WH-001'],
            ['SRV-001', 'Servicio técnico', '', 'Servicios', '0', '500', '0', 'si',
             'Reparación de equipos', 'Unidad', '1', '500', 'si', '', ''],
        ]
    )