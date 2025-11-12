import io
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QPixmap

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader

class PdfReportWorker(QObject):
    """
    Gera o relatório PDF em uma thread separada para não congelar a UI.
    Recebe os dados e as imagens já capturadas da thread principal.
    """
    finished = pyqtSignal(str) # Emite o caminho do arquivo salvo ao terminar
    error = pyqtSignal(str)    # Emite mensagem de erro

    def __init__(self, file_path, log_name, plot_images, map_images):
        super().__init__()
        self.file_path = file_path
        self.log_name = log_name
        self.plot_images = plot_images  # Lista de buffers de imagem (BytesIO)
        self.map_images = map_images    # Lista de buffers de imagem (BytesIO)

    def run(self):
        """
        Executa a geração do PDF. Esta função não deve ter nenhuma interação com a UI.
        """
        try:
            c = canvas.Canvas(self.file_path, pagesize=landscape(A4))
            width, height = landscape(A4)

            # --- Página de Título ---
            self._create_title_page(c, width, height)

            # --- Páginas de Gráficos ---
            for img_buffer in self.plot_images:
                self._add_image_page(c, width, height, img_buffer)
            
            # --- Páginas do Mapa ---
            for i, img_buffer in enumerate(self.map_images):
                zoom_level = [17, 15, 12][i] # Assumindo 3 níveis de zoom
                title = f"Trajetória do Voo - Zoom: {zoom_level}"
                self._add_image_page(c, width, height, img_buffer, title)

            c.save()
            self.finished.emit(self.file_path)

        except Exception as e:
            self.error.emit(f"Ocorreu um erro ao gerar o PDF: {e}")

    def _create_title_page(self, c, width, height):
        c.setFont("Helvetica-Bold", 24)
        c.drawCentredString(width / 2, height - 2 * inch, "Relatório de Voo Detalhado")
        c.setFont("Helvetica", 14)
        c.drawCentredString(width / 2, height - 2.5 * inch, f"Arquivo de Log: {self.log_name}")
        c.setFont("Helvetica-Oblique", 12)
        c.drawCentredString(width / 2, 1 * inch, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        c.showPage()

    def _add_image_page(self, c, width, height, img_buffer, title=None):
        img_buffer.seek(0)
        image_reader = ImageReader(img_buffer)
        
        if title:
            c.setFont("Helvetica-Bold", 16)
            c.drawCentredString(width / 2, height - 1 * inch, title)
            margin_top = 1.5 * inch
        else:
            margin_top = 1 * inch

        img_w, img_h = image_reader.getSize()
        aspect = img_h / float(img_w)
        
        draw_width = width - 2 * inch
        draw_height = draw_width * aspect
        
        # Ajusta se a altura for excessiva
        max_height = height - margin_top - 1 * inch
        if draw_height > max_height:
            draw_height = max_height
            draw_width = draw_height / aspect

        x = (width - draw_width) / 2
        y = (height - draw_height - margin_top) / 2 + 1 * inch
        
        c.drawImage(image_reader, x, y, width=draw_width, height=draw_height, preserveAspectRatio=True)
        c.showPage()