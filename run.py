# /run.py
import sys
import os
from PyQt6.QtWidgets import QApplication
from src.main_window import TelemetryApp

if __name__ == '__main__':
    # Flag necessária para o QWebEngine em alguns sistemas
    #os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--single-process'
    
    app = QApplication(sys.argv)
    window = TelemetryApp()
    window.show()
    sys.exit(app.exec())