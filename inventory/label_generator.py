"""
Generador de etiquetas PDF con códigos de barras.
Tamaño de etiqueta: 5 cm x 2.5 cm (formato para pistola de scanner)
"""
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import barcode
from barcode.writer import ImageWriter
from .models import Product

def generate_product_labels(product_ids: list[int]) -> BytesIO:
    """
    Genera un PDF con etiquetas compactas para los productos seleccionados.
    Cada etiqueta contiene: nombre (hasta 2 líneas), SKU y código de barras.
    Todo centrado horizontal y verticalmente.
    
    Formato: 3 columnas x 9 filas por página A4 (27 etiquetas por página)
    Tamaño de etiqueta: 5 cm x 2.5 cm
    """
    products = Product.objects.filter(id__in=product_ids).select_related('category')
    
    if not products.exists():
        raise ValueError("No se encontraron productos")
    
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # ============================================
    # CONFIGURACIÓN DE LAYOUT
    # ============================================
    cols = 4
    rows = 9
    label_width = 4 * cm    # Tamaño de etiqueta
    label_height = 2.5 * cm # Tamaño de etiqueta
    margin_x = 1 * cm     # Margen izquierdo y derecho de la página
    margin_y = 1.5 * cm     # Margen superior e inferior de la página
    spacing_x = 0.4 * cm    # Margen entre etiquetas horizontalmente
    spacing_y = 0.25 * cm   # Margen entre etiquetas verticalmente
    
    # ============================================
    # FUNCIÓN HELPER: Wrap de texto
    # ============================================
    def wrap_text(text, font_name, font_size, max_width, max_lines=2):
        """
        Divide un texto en líneas que caben en max_width.
        Retorna lista de líneas (máximo max_lines).
        Si hay más texto del que cabe, trunca la última línea con '...'
        """
        words = text.split()
        lines = []
        current_line = ""
        
        for word in words:
            test_line = f"{current_line} {word}".strip() if current_line else word
            test_width = c.stringWidth(test_line, font_name, font_size)
            
            if test_width <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
                
                # Si ya alcanzamos el máximo de líneas, truncar
                if len(lines) >= max_lines - 1:
                    break
        
        if current_line and len(lines) < max_lines:
            lines.append(current_line)
        elif current_line and len(lines) == max_lines - 1:
            # Última línea: verificar si cabe, si no truncar
            last_line = f"{lines[-1]} {current_line}".strip() if lines else current_line
            if c.stringWidth(last_line, font_name, font_size) <= max_width:
                if lines:
                    lines[-1] = last_line
                else:
                    lines.append(last_line)
            else:
                lines.append(current_line)
        
        # Truncar última línea si es demasiado larga
        if lines:
            last = lines[-1]
            while c.stringWidth(last, font_name, font_size) > max_width and len(last) > 3:
                last = last[:-1]
            if last != lines[-1]:
                lines[-1] = last + "..."
        
        return lines[:max_lines]
    
    # ============================================
    # GENERAR ETIQUETAS
    # ============================================
    for idx, product in enumerate(products):
        page_idx = idx % (cols * rows)
        
        if page_idx == 0 and idx > 0:
            c.showPage()
        
        col = page_idx % cols
        row = page_idx // cols
        
        x = margin_x + col * (label_width + spacing_x)
        y = height - margin_y - (row + 1) * label_height - row * spacing_y
        
        # Centro horizontal de la etiqueta
        center_x = x + label_width / 2
        
        # ----- Borde de la etiqueta -----
        c.setStrokeColorRGB(0.75, 0.75, 0.75)
        c.setLineWidth(1)
        c.rect(x, y, label_width, label_height)
        
        # ========================================
        # CÁLCULO DE ALTURAS PARA CENTRADO VERTICAL
        # ========================================
        # Espacio disponible para texto (arriba del barcode)
        text_max_width = label_width - 0.4 * cm  # margen interno 0.2cm cada lado
        
        # Nombre: wrap a máximo 2 líneas
        name_font = "Helvetica-Bold"
        name_size = 8
        name_lines = wrap_text(product.name, name_font, name_size, text_max_width, max_lines=2)
        name_line_height = name_size * 1  # interlineado aproximado en cm (puntos a cm)
        name_block_height = len(name_lines) * name_line_height
        
        # SKU: 1 línea
        sku_font = "Helvetica"
        sku_size = 6.5
        sku_text = f"SKU: {product.sku}"
        # Truncar SKU si es muy largo
        if c.stringWidth(sku_text, sku_font, sku_size) > text_max_width:
            sku_text = sku_text[:25] + "..."
        sku_line_height = sku_size * 0.45
        
        # Barcode
        barcode_height = 1.0 * cm
        barcode_bottom_margin = 0.35 * cm  # espacio debajo del barcode para el texto
        barcode_text_height = 0.25 * cm
        
        # Altura total del contenido
        gap_name_sku = 0.05 * cm
        gap_sku_barcode = 0.1 * cm
        
        total_content_height = (
            name_block_height +
            gap_name_sku +
            sku_line_height +
            gap_sku_barcode +
            barcode_height +
            barcode_bottom_margin +
            barcode_text_height
        )
        
        # Offset Y para centrar verticalmente todo el bloque
        vertical_offset = (label_height - total_content_height) / 2
        if vertical_offset < 0:
            vertical_offset = 0.1 * cm  # mínimo padding
        
        # Posición Y inicial (desde arriba de la etiqueta)
        current_y = y + label_height - vertical_offset - name_line_height
        
        # ----- Dibujar nombre (centrado, hasta 2 líneas) -----
        c.setFont(name_font, name_size)
        c.setFillColorRGB(0, 0, 0)
        
        for line in name_lines:
            c.drawCentredString(center_x, current_y, line)
            current_y -= name_line_height
        
        # ----- Dibujar SKU (centrado) -----
        current_y -= gap_name_sku
        c.setFont(sku_font, sku_size)
        c.setFillColorRGB(0.3, 0.3, 0.3)
        c.drawCentredString(center_x, current_y, sku_text)
        c.setFillColorRGB(0, 0, 0)
        
        # ----- Dibujar código de barras (centrado) -----
        current_y -= sku_line_height + gap_sku_barcode
        
        barcode_value = product.barcode or product.sku
        
        try:
            barcode_class = barcode.get_barcode_class('code128')
            code = barcode_class(barcode_value, writer=ImageWriter())
            
            barcode_buffer = BytesIO()
            code.write(barcode_buffer, options={
                'write_text': False,
                'module_height': 5,
                'quiet_zone': 1,
                'module_width': 0.25,
            })
            barcode_buffer.seek(0)
            
            barcode_img = ImageReader(barcode_buffer)
            barcode_width = label_width - 0.6 * cm
            barcode_x = x + (label_width - barcode_width) / 2
            barcode_y = current_y - barcode_height + 0.15 * cm
            
            c.drawImage(barcode_img, barcode_x, barcode_y,
                       width=barcode_width, height=barcode_height,
                       preserveAspectRatio=True)
            
            # Texto del código debajo del barcode (centrado)
            c.setFont("Helvetica", 6)
            c.setFillColorRGB(0.2, 0.2, 0.2)
            c.drawCentredString(center_x, barcode_y - barcode_bottom_margin + 0.1 * cm, barcode_value)
            c.setFillColorRGB(0, 0, 0)
            
        except Exception as e:
            c.setFont("Helvetica", 7)
            c.setFillColorRGB(0.8, 0, 0)
            c.drawCentredString(center_x, current_y - 0.5 * cm, f"Error: {str(e)[:25]}")
            c.setFillColorRGB(0, 0, 0)
    
    c.save()
    buffer.seek(0)
    return buffer