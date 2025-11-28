# src/main_window.py
# Código para janela principal do programa
# Feito por Euler Torres - 22/10/2025

import sys
import os
import io
import time
import shutil
import json
import math
from string import Template
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QMessageBox, QSplitter, QGroupBox,
    QRadioButton, QTabWidget, QComboBox, QInputDialog,
    QLabel, QDialog, QProgressBar, QTextEdit,
    QCheckBox, QStackedWidget
)
from PyQt6.QtCore import Qt, QUrl, QThread, pyqtSignal, QIODevice, QBuffer, QTimer
from PyQt6.QtGui import QMovie
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
import pandas as pd
import numpy as np
import folium
from folium import CustomIcon
from geopy.distance import geodesic

# Importações da arquitetura modular
from src.data_parser import LogProcessingWorker
from src.widgets.standard_plots_widget import StandardPlotsWidget
from src.widgets.all_plots_widget import AllPlotsWidget
from src.widgets.custom_plot_widget import CustomPlotWidget
from src.utils.local_server import MapServer
from src.utils.pdf_reporter import PdfReportWorker
from src.utils.resource_paths import get_logs_directory, resource_path
from src.utils.sharepoint_downloader import SharePointClient, SharePointCredentialError
from src.widgets.log_download_dialog import LogDownloadDialog

AIRCRAFT_ICON_PATH = resource_path('aircraft.svg')
WIND_ICON_PATH = resource_path('seta.svg')
LOADING_GIF_PATH = resource_path('gato.gif')
DEFAULT_LOGS_DIR = get_logs_directory()

class LoadingDialog(QDialog):
    """Diálogo modal para exibir um GIF de carregamento."""

    def __init__(self, parent=None, animation_path=None):
        super().__init__(parent)
        
        # Remove a barra de título e deixa o fundo transparente
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True) # Impede interação com a janela principal

        # Label para conter o GIF
        self.label = QLabel(self)
        gif_path = str(animation_path) if animation_path else "gato.gif"
        self.movie = QMovie(gif_path)
        
        if not self.movie.isValid():
            print("AVISO: Não foi possível carregar o gato.gif!")
            self.label.setText("Carregando...")
        else:
            self.label.setMovie(self.movie)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.label)
        self.setLayout(layout)

    def start_animation(self):
        if self.movie.isValid():
            self.movie.start()

    def stop_animation(self):
        if self.movie.isValid():
            self.movie.stop()

class TelemetryApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.original_window_title = "SUPER VISUALIZADOR DE LOG DO EULER!! (～￣▽￣)～ - v0.2.3"
        self.setWindowTitle(self.original_window_title) 
        self.setGeometry(100, 100, 1600, 900)
        
        self.log_data = {}
        self.current_log_name = ""
        self.df = pd.DataFrame()
        self.thread = None
        self.worker = None

        self.default_logs_dir = DEFAULT_LOGS_DIR
        self.last_logs_root = DEFAULT_LOGS_DIR

        self.map_server = MapServer()
        self.map_server.start()
        self.temp_map_file_path = ""
        self.map_js_name = ""
        self.map_is_ready = False 
        self.aircraft_marker_js_name = ""
        self.wind_marker_js_name = ""
        self.standard_plots_tab = None

        self.loading_widget = LoadingDialog(self, animation_path=LOADING_GIF_PATH)

        self.view_toggle_checkbox = None
        self.map_stack = None
        self.cesiumWidget = None
        self.cesium_html_path = ""
        self.cesium_is_ready = False
        self.cesium_plane_asset = os.path.join('assets', 'cesium', 'plane.glb')
        self.cesium_controls_container = None
        self.cesium_center_button = None
        self.cesium_follow_checkbox = None
        self.cesium_imagery_combo = None
        self.cesium_play_button = None
        self.cesium_speed_combo = None
        self.timelineWidget = None
        self.timeline_html_path = ""
        self.timeline_is_ready = False
        self.cesium_sync_timer = QTimer(self)
        self.cesium_sync_timer.setInterval(120)
        self.cesium_sync_timer.timeout.connect(self._sync_cesium_timeline_into_app)
        self.cesium_imagery_presets = [
            {
                "key": "osm",
                "label": "OpenStreetMap (padrão)",
                "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                "credit": "© OpenStreetMap contributors",
                "tilingScheme": "webMercator",
                "maximumLevel": 19
            },
            {
                "key": "esriWorldImagery",
                "label": "Esri World Imagery (satélite)",
                "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                "credit": "Esri, Maxar, GeoEye, Earthstar Geographics",
                "tilingScheme": "webMercator",
                "maximumLevel": 19
            },
            {
                "key": "cartoDark",
                "label": "Carto Dark Matter",
                "url": "https://cartodb-basemaps-a.global.ssl.fastly.net/dark_all/{z}/{x}/{y}.png",
                "credit": "© CARTO",
                "tilingScheme": "webMercator",
                "maximumLevel": 19
            }
        ]
        self.current_cesium_imagery_key = self.cesium_imagery_presets[0]["key"] if self.cesium_imagery_presets else "osm"
        self.altitude_reference = 0.0
        self.current_timeline_index = 0
        self.last_plot_cursor_update_time = 0.0
        self.cesium_playing = False
        self.first_datalogger_df: pd.DataFrame | None = None

        self.aircraft_icon_filename = None
        self.wind_icon_filename = None

        self._register_static_assets()

        self.copy_assets_to_server(self.cesium_plane_asset)

        self.setup_ui()

        self.sharepoint_client: SharePointClient | None = None
        self.log_download_dialog: LogDownloadDialog | None = None

    def _register_static_assets(self):
        self.aircraft_icon_filename = self.copy_assets_to_server(AIRCRAFT_ICON_PATH)
        self.wind_icon_filename = self.copy_assets_to_server(WIND_ICON_PATH)

    def copy_assets_to_server(self, icon_path):
        """Copia arquivos estáticos necessários (ex: ícone) para o diretório do servidor."""

        try:
            if not icon_path:
                return None

            source_icon_path = Path(icon_path)
            if not source_icon_path.exists():
                print(f"AVISO: Arquivo '{source_icon_path}' não encontrado. O ícone pode não aparecer.")
                return None

            dest_dir = Path(self.map_server.get_temp_dir())
            if not dest_dir.exists():
                print(f"ERRO: Diretório do servidor '{dest_dir}' não encontrado.")
                return None

            dest_path = dest_dir / source_icon_path.name
            shutil.copy2(source_icon_path, dest_path)
            return source_icon_path.name

        except Exception as e:
            print(f"ERRO CRÍTICO ao copiar assets para o servidor: {e}")
            QMessageBox.warning(self, "Erro de Asset", f"Não foi possível copiar o ícone para o servidor:\n{e}")
            return None
        
    def setup_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget) # Layout principal vertical

        # --- Controles Superiores ---
        top_controls_layout = QHBoxLayout()
        self.btn_open = QPushButton("Selecionar Diretório Raiz dos Logs")
        self.btn_open.clicked.connect(self.open_log_directories)
        top_controls_layout.addWidget(self.btn_open)

        self.btn_download_sharepoint = QPushButton("Baixar Novos Logs")
        self.btn_download_sharepoint.setToolTip(
            "Abre o assistente para copiar voos da pasta '[00] PROGRAMAS' sincronizada"
        )
        self.btn_download_sharepoint.clicked.connect(self.open_sharepoint_downloader)
        top_controls_layout.addWidget(self.btn_download_sharepoint)

        top_controls_layout.addWidget(QLabel("Log Ativo para Visualização:"))
        self.log_selector_combo = QComboBox()
        self.log_selector_combo.currentTextChanged.connect(self._on_log_selected)
        self.log_selector_combo.setEnabled(False)
        top_controls_layout.addWidget(self.log_selector_combo, 1)
        self.btn_save_pdf = QPushButton("Salvar Relatório em PDF (do Log Ativo)")
        self.btn_save_pdf.clicked.connect(self.save_report_as_pdf)
        self.btn_save_pdf.setEnabled(False)
        top_controls_layout.addWidget(self.btn_save_pdf)

        self.view_toggle_checkbox = QCheckBox("Visualização 3D")
        self.view_toggle_checkbox.stateChanged.connect(self.on_view_toggle_changed)
        self.view_toggle_checkbox.setEnabled(True)
        top_controls_layout.addWidget(self.view_toggle_checkbox)

        # Adiciona controles superiores ao layout principal
        self.layout.addLayout(top_controls_layout)

        self.loading_status_widget = QWidget() # Container
        loading_layout = QVBoxLayout(self.loading_status_widget)
        loading_layout.setContentsMargins(5, 0, 5, 0) # Margens
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Processando diretórios... %p%")
        loading_layout.addWidget(self.progress_bar)
        
        self.status_log_output = QTextEdit()
        self.status_log_output.setReadOnly(True)
        self.status_log_output.setMaximumHeight(80) # Limita altura
        loading_layout.addWidget(self.status_log_output)
        
        self.layout.addWidget(self.loading_status_widget) # Adiciona ao layout principal
        self.loading_status_widget.hide() # Começa escondido

        # --- Painel Principal com Splitter ----------------------------------------------------------------------------------------------
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Abas (Painel Esquerdo do Splitter) ---
        self.tabs = QTabWidget()
        self.setup_tabs() # Cria e adiciona as abas ao QTabWidget
        self.splitter.addWidget(self.tabs) # Adiciona o QTabWidget ao splitter

        # --- Painel Direito (APENAS o Mapa) ---
        map_panel_widget = QWidget()
        map_panel_layout = QVBoxLayout(map_panel_widget)
        map_panel_layout.setContentsMargins(0, 0, 0, 0) # Sem margens internas
        self.mapWidget = QWebEngineView()
        self._configure_webview(self.mapWidget)
        self.mapWidget.loadFinished.connect(self.on_map_load_finished)
        self.cesiumWidget = QWebEngineView()

        self.cesiumWidget.loadFinished.connect(self.on_three_d_view_load_finished)

        self.cesium_controls_container = QWidget()
        cesium_controls_layout = QHBoxLayout(self.cesium_controls_container)
        cesium_controls_layout.setContentsMargins(8, 4, 8, 4)
        cesium_controls_layout.setSpacing(8)
        cesium_controls_layout.addWidget(QLabel("Base do globo:"))
        self.cesium_imagery_combo = QComboBox()
        self.cesium_imagery_combo.currentIndexChanged.connect(self.on_cesium_imagery_changed)
        cesium_controls_layout.addWidget(self.cesium_imagery_combo, 1)
        self.cesium_follow_checkbox = QCheckBox("Segue o drone")
        self.cesium_follow_checkbox.setChecked(True)
        self.cesium_follow_checkbox.stateChanged.connect(self.on_cesium_follow_changed)
        cesium_controls_layout.addWidget(self.cesium_follow_checkbox)
        self.cesium_center_button = QPushButton("Foca no drone")
        self.cesium_center_button.clicked.connect(self.center_cesium_camera)
        self.cesium_center_button.setEnabled(False)
        cesium_controls_layout.addWidget(self.cesium_center_button)

        self.cesium_play_button = QPushButton("Play ▶")
        self.cesium_play_button.clicked.connect(self.toggle_cesium_playback)
        cesium_controls_layout.addWidget(self.cesium_play_button)

        self.cesium_speed_combo = QComboBox()
        self.cesium_speed_combo.addItems(["0.5x", "1x", "2x", "4x"])
        self.cesium_speed_combo.setCurrentText("1x")
        self.cesium_speed_combo.currentTextChanged.connect(self.on_cesium_speed_changed)
        cesium_controls_layout.addWidget(QLabel("Velocidade:"))
        cesium_controls_layout.addWidget(self.cesium_speed_combo)
        cesium_controls_layout.addStretch(1)
        self.cesium_controls_container.hide()

        self.map_stack = QStackedWidget()
        self.map_stack.addWidget(self.mapWidget)
        self.map_stack.addWidget(self.cesiumWidget)
        map_panel_layout.addWidget(self.map_stack, 1)
        map_panel_layout.addWidget(self.cesium_controls_container)
        self.map_stack.setCurrentWidget(self.mapWidget)
        self.populate_cesium_imagery_combo()

        # Adiciona o painel do mapa ao splitter
        self.splitter.addWidget(map_panel_widget)

        # Adiciona o splitter ao layout principal, ocupando o espaço restante (stretch=1)
        self.layout.addWidget(self.splitter, 1) 

        # --- Controles da Timeline (Abaixo do Splitter, largura total) ---
        self.setup_timeline_controls(self.layout) 

        # Define os tamanhos iniciais do splitter
        self.splitter.setSizes([1000, 600])

    def _configure_webview(self, webview):
        if not webview:
            return
        settings = webview.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
            True,
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
            True,
        )

    def setup_tabs(self):
        self.standard_plots_tab = StandardPlotsWidget(self) # Cria o novo widget
        self.tabs.addTab(self.standard_plots_tab, "Gráficos Padrão")

        self.custom_plot_tab = CustomPlotWidget(self)
        self.tabs.addTab(self.custom_plot_tab, "Gráfico de Comparação")

        self.all_plots_tab = AllPlotsWidget(self)
        self.tabs.addTab(self.all_plots_tab, "Todos os Gráficos (Log Ativo)")

    def setup_timeline_controls(self, parent_layout):
        wrapper_layout = QHBoxLayout()
        #wrapper_layout.setContentsMargins(4, 4, 4, 4)
        #wrapper_layout.setSpacing(10)

        self.timelineWidget = QWebEngineView()
        self.timelineWidget.setFixedHeight(45)
        self.timelineWidget.loadFinished.connect(self.on_timeline_load_finished)

        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)
        self.timestamp_label = QLabel("Timestamp: --:--:--.---")
        self.timestamp_label.setFixedWidth(180)
        self.btn_set_timestamp = QPushButton("Definir 🕒")
        self.btn_set_timestamp.setToolTip("Definir timestamp manualmente")
        self.btn_set_timestamp.setFixedWidth(80)
        self.btn_set_timestamp.clicked.connect(self.set_timestamp_manually)
        self.btn_set_timestamp.setEnabled(False)

        controls_layout.addWidget(self.btn_set_timestamp)
        controls_layout.addWidget(self.timestamp_label)

        controls_container = QWidget()
        controls_container.setLayout(controls_layout)

        wrapper_layout.addWidget(self.timelineWidget, 1)
        wrapper_layout.addWidget(controls_container, 0)
        parent_layout.addLayout(wrapper_layout)
        self.refresh_timeline_html()

    def open_log_directories(self):
        start_dir = str(self.last_logs_root) if self.last_logs_root else ""
        root_path = QFileDialog.getExistingDirectory(
            self,
            "Seleciona a PASTA que tem as pastas dos .logs. É so isso mano, você consegue",
            start_dir,
        )
        if not root_path:
            return

        self._start_loading_from_path(root_path)

    def open_sharepoint_downloader(self):
        if self.sharepoint_client is None:
            try:
                self.sharepoint_client = SharePointClient()
            except SharePointCredentialError as exc:
                QMessageBox.warning(
                    self,
                    "Configuração necessária",
                    (
                        "Não foi possível localizar a pasta '[00] PROGRAMAS'.\n"
                        "Configure o caminho correto no assistente de cópia.\n"
                        f"{exc}"
                    ),
                )
                return
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Erro inesperado",
                    f"Falha ao abrir o assistente de cópia:\n{exc}",
                )
                return

        if self.log_download_dialog is None:
            self.log_download_dialog = LogDownloadDialog(self.sharepoint_client, self)
            self.log_download_dialog.logs_downloaded.connect(self.on_logs_downloaded_from_sharepoint)
            self.log_download_dialog.destroyed.connect(self._on_log_download_dialog_destroyed)

        self.log_download_dialog.show()
        self.log_download_dialog.raise_()
        self.log_download_dialog.activateWindow()

    def _on_log_download_dialog_destroyed(self, _obj=None):
        self.log_download_dialog = None

    def on_logs_downloaded_from_sharepoint(self, base_path: Path, local_paths: list[Path]):
        if not base_path:
            return

        self.last_logs_root = Path(base_path)
        count = len(local_paths)
        self.statusBar().showMessage(
            f"{count} novos voos foram copiados para {base_path}",
            8000,
        )

        if count == 0:
            return

        reply = QMessageBox.question(
            self,
            "Cópia concluída",
            (
                f"{count} voos foram salvos em:\n{base_path}\n\n"
                "Deseja carregar essa pasta agora?"
            ),
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._start_loading_from_path(str(base_path))

    def _start_loading_from_path(self, root_path):
        if not root_path:
            return

        self.last_logs_root = Path(root_path)
        self._clear_all_data()
        self.btn_open.setEnabled(False)

        self.setWindowTitle("Carregando Logs... (～￣▽￣)～")
        self.statusBar().showMessage(f"Carregando logs a partir de: {root_path}")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Dando uma olhada... %p%")
        self.status_log_output.clear()
        self.loading_status_widget.show()
        QApplication.processEvents()

        self.loading_widget.start_animation()
        self.loading_widget.open()

        self.thread = QThread()
        self.worker = LogProcessingWorker(root_path)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_loading_finished)
        self.worker.error.connect(self.on_loading_error)
        self.worker.progress.connect(self.on_loading_progress)
        self.worker.log_loaded.connect(self.on_log_item_loaded)

        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def on_log_item_loaded(self, log_name, log_type):
        """Atualiza a área de texto com o status de cada log."""
        message = f"INFO: Log '{log_name}' carregado (Tipo: {log_type})"
        self.status_log_output.append(message)
        print(message) # Mantém no console também, se desejar

    def on_loading_progress(self, value):
        """Atualiza a barra de progresso."""
        if isinstance(value, int):
            if value == -1: # Caso especial: erro ao contar diretórios
                 self.progress_bar.setFormat("Processando...")
                 self.progress_bar.setMaximum(0) # Modo indeterminado
                 self.progress_bar.setValue(0)
            elif self.progress_bar.maximum() == 0: # Se estava indeterminado, ajusta
                 self.progress_bar.setMaximum(100)
                 self.progress_bar.setFormat("Processando diretórios... %p%")
                 self.progress_bar.setValue(value)
            else:
                 self.progress_bar.setValue(value)
        # else: # Se ainda precisasse de mensagens de status aqui
        #    self.statusBar().showMessage(str(value))

    def on_loading_finished(self, loaded_logs):
        
        #self.loading_widget.stop_animation()
        #self.loading_widget.close()
        
        self.loading_status_widget.hide() # Esconde barra e texto
        self.setWindowTitle(self.original_window_title) # Restaura título
        self.btn_open.setEnabled(True) # Reabilita botão

        if not loaded_logs:
            self.loading_widget.stop_animation()
            self.loading_widget.close()
            QMessageBox.information(self, "NUM TEM Log", "Você que fez errado, lê direito vei, É a pasta que tem as pastas de .log")
            self.statusBar().showMessage("NAO TEM LOGGGGG AAAAAA", 5000)
            self.btn_open.setEnabled(True)
            return

        self.log_data = loaded_logs
        self.first_datalogger_df = self._find_first_datalogger_df()
        self.log_selector_combo.blockSignals(True); self.log_selector_combo.addItems(sorted(self.log_data.keys())); self.log_selector_combo.blockSignals(False)
        self.log_selector_combo.setEnabled(True)
        self._on_log_selected(self.log_selector_combo.currentText()) # Seleciona o primeiro
        self.custom_plot_tab.reload_data(self.log_data)
        self.statusBar().showMessage(f"{len(loaded_logs)} log(s) carregado(s)!!!", 5000)
        self.loading_widget.stop_animation()
        self.loading_widget.close()

    def on_loading_error(self, error_message):

        self.loading_status_widget.hide()
        self.setWindowTitle(self.original_window_title)
        self.btn_open.setEnabled(True)

        self.loading_widget.stop_animation()
        self.loading_widget.close()

        QMessageBox.critical(self, "Não consigo ler :( help", error_message)
        self.statusBar().showMessage("Etaporra deu ruim em carregar os logs", 5000)
        #self.btn_open.setEnabled(True)

    def _clear_all_data(self):
        self.map_is_ready = False
        self.log_data.clear()
        self.df = pd.DataFrame()
        self.current_log_name = ""
        self.first_datalogger_df = None
        self.log_selector_combo.blockSignals(True)
        self.log_selector_combo.clear()
        self.log_selector_combo.blockSignals(False)
        self.log_selector_combo.setEnabled(False)
        self.btn_save_pdf.setEnabled(False)

        if self.view_toggle_checkbox:
            self.view_toggle_checkbox.blockSignals(True)
            self.view_toggle_checkbox.setChecked(False)
            self.view_toggle_checkbox.blockSignals(False)

        if self.map_stack:
            self.map_stack.setCurrentWidget(self.mapWidget)

        self.cleanup_cesium_html()

        if self.standard_plots_tab: self.standard_plots_tab.load_dataframe(pd.DataFrame())
        if self.custom_plot_tab: self.custom_plot_tab.reload_data({})
        if self.all_plots_tab: self.all_plots_tab.load_dataframe(pd.DataFrame(), "")

        self.mapWidget.setHtml("")
        self.setup_timeline()

    def _find_first_datalogger_df(self):
        for _, df in self.log_data.items():
            if isinstance(df, pd.DataFrame) and 'ServoL_PWM_us' in df.columns and 'Timestamp' in df.columns:
                return df
        return None

    def _on_log_selected(self, log_name):
        if not log_name or log_name not in self.log_data: return
        self.current_log_name = log_name
        self.df = self.log_data[log_name]
        self._update_altitude_reference()
        self.cesium_playing = False

        self.loading_widget.start_animation()
        self.loading_widget.open()
        QApplication.processEvents()

        try:
            if self.standard_plots_tab: self.standard_plots_tab.load_dataframe(self.df, self.current_log_name)
            if self.all_plots_tab: self.all_plots_tab.load_dataframe(self.df, self.current_log_name, self.first_datalogger_df)
            # O custom_plot_tab já recebe todos os logs no on_loading_finished

            if self.tabs and self.standard_plots_tab:
                self.tabs.setCurrentWidget(self.standard_plots_tab)
                self.standard_plots_tab.show_position_plot()

            self.plot_map_route() # Recria o mapa
            self.setup_timeline()

            self.map_stack.setCurrentWidget(self.mapWidget)
            self.view_toggle_checkbox.blockSignals(True)
            self.view_toggle_checkbox.setChecked(False)
            self.view_toggle_checkbox.blockSignals(False)
            self.cesium_state = None
            self.cesium_ready = False
            self.cesium_start_timestamp = None
            self.cleanup_cesium_html()
            self._update_cesium_controls_state()

            cesium_state = self.build_cesium_state_from_dataframe()
            if cesium_state:
                self.cesium_state = cesium_state
                self.view_toggle_checkbox.setEnabled(True)
            else:
                self.view_toggle_checkbox.setEnabled(False)
        finally:
            self.loading_widget.stop_animation()
            self.loading_widget.close()

    # --- Funções do Mapa e Timeline ---
    
    def on_map_load_finished(self, ok):
        if ok:
            # ### ALTERAÇÃO SIMPLIFICADA ###
            # Define imediatamente como pronto. O JS cuidará da espera interna.
            self.map_is_ready = True
            #print("DEBUG: Carregamento HTML do mapa finalizado. JS cuidará da inicialização.")
            # Atualiza a posição inicial assim que possível
            self.update_views_from_timeline(self.current_timeline_index)
        else:
            self.map_is_ready = False
            print("ERRO: VISHII deu ruim o HTML do mapa, HEEELP aaaaaaaa")

    def on_three_d_view_load_finished(self, ok):
        if ok:
            self.statusBar().showMessage("Visualização 3D carregada!", 3000)
            self._wait_for_cesium_ready()
        else:
            self.cesium_is_ready = False
            self.statusBar().showMessage("Falha ao carregar visualização 3D.", 5000)

    def on_view_toggle_changed(self, state):
        if self.view_toggle_checkbox is None:
            return
        checked = Qt.CheckState(state) == Qt.CheckState.Checked
        if checked:
            if not self.show_cesium_3d_view():
                self.view_toggle_checkbox.blockSignals(True)
                self.view_toggle_checkbox.setChecked(False)
                self.view_toggle_checkbox.blockSignals(False)
                return
            self.map_stack.setCurrentWidget(self.cesiumWidget)
        else:
            self.map_stack.setCurrentWidget(self.mapWidget)
        self._update_cesium_controls_state()

    def plot_map_route(self):
        if 'Latitude' not in self.df.columns or 'Longitude' not in self.df.columns:
            self.mapWidget.setHtml("<html><body><h1>Mas num tem dado GPS meu filho!!.</h1></body></html>"); return
        coords = self.df[['Latitude', 'Longitude']].dropna().values.tolist()
        if not coords:
            self.mapWidget.setHtml("<html><body><h1>Mas num tem dado GPS meu filho!! kkkkk</h1></body></html>"); return

        # --- Cria o mapa base ---
        map_center = self.df[['Latitude', 'Longitude']].mean().values.tolist()
        m = folium.Map(location=map_center, zoom_start=15)
        self.map_js_name = m.get_name() # Guarda o nome JS do mapa principal

        # --- Rota e marcadores de início/fim ---
        folium.PolyLine(coords, color="blue", weight=3, opacity=0.8).add_to(m)
        folium.Marker(location=coords[0], popup="Início", icon=folium.Icon(color="green")).add_to(m)
        folium.Marker(location=coords[-1], popup="Fim", icon=folium.Icon(color="red")).add_to(m)

        # --- Ícone do aviaum  ---
        temp_dir = Path(self.map_server.get_temp_dir())
        icon_filename = self.aircraft_icon_filename
        icon_url = None
        if icon_filename:
            icon_path = temp_dir / icon_filename
            icon_url = QUrl.fromLocalFile(str(icon_path)).toString()
        
        icon_size = (60, 60)       # Tamanho desejado do ícone em pixels
        icon_aircraft_anchor = (30, 30)     # Ponto do ícone que corresponde à coordenada (centro)
        half_w, half_h = icon_size[0] // 2, icon_size[1] // 2
        half_w, half_h = icon_size[0] // 2, icon_size[1] // 2

        offset_x = 6    # + direita, - esquerda
        offset_y = 0   # + desce, -sobe

        aircraft_html = f"""
        <div id='aircraft-icon' style='
            width:{icon_size[0]}px;
            height:{icon_size[1]}px;
            //margin-left:-{half_w - offset_x}px;
            margin-left:0px;
            //margin-top:-{half_h - offset_y}px;
            margin-top:0px;
            transform-origin:center center;
            //position: relative;
            '>
            <img id='aircraft-img' src='{icon_url}'
                 style='width:{icon_size[0]}px;
                        height:{icon_size[1]}px;
                        transform-origin:center center;'>
        </div>
        """
        try:
            if icon_url:
                aircraft_icon = folium.DivIcon(html=aircraft_html, icon_anchor=icon_aircraft_anchor)
                aircraft_marker = folium.Marker(
                    location=coords[0],
                    icon=aircraft_icon,
                    popup='Aeronave'
                )
            else:
                raise FileNotFoundError('Ícone do avião indisponível')
            aircraft_marker.add_to(m)
            self.aircraft_marker_js_name = aircraft_marker.get_name()
            print(f"DEBUG: Marcador de avião criado com DivIcon. Nome JS: {self.aircraft_marker_js_name}")
        except Exception as e:
            print(f"ERRO ao criar ícone do avião: {e}")
            # Fallback simples
            aircraft_marker = folium.CircleMarker(
                location=coords[0],
                radius=6,
                color='red',
                fill=True,
                popup='Aeronave (Fallback)'
            )
            aircraft_marker.add_to(m)
            self.aircraft_marker_js_name = aircraft_marker.get_name()
            print("AVISO: Vish mano, vo usar o circulo pq num tem imagem do aviao.")

        # --- Ícone da Seta de Vento ---
        icon_wind_filename = self.wind_icon_filename
        icon_wind_url = None
        if icon_wind_filename:
            icon_wind_path = temp_dir / icon_wind_filename
            icon_wind_url = QUrl.fromLocalFile(str(icon_wind_path)).toString()
        icon_wind_size = (120, 120); icon_wind_anchor = (60, 60) # Centralizado
        # Posiciona a seta um pouco acima e à direita do avião via margens negativas
        # Ajuste 'margin-left' e 'margin-top' para mudar a posição relativa
        wind_html = f"""
        <div style='position: relative; width:{icon_wind_size[0]}px; height:{icon_wind_size[1]}px;
                    margin-left: 0px;  /* Ajuste para deslocar p/ direita */
                    margin-top: 0px; /* Ajuste para deslocar p/ cima */
                    transform-origin: center center;'>
            <img id='wind-arrow-img' src='{icon_wind_url}'
                 style='width:100%; height:100%; transform-origin: center center;'>
        </div>
        """
        try:
            if icon_wind_url:
                wind_icon = folium.DivIcon(html=wind_html, icon_size=icon_wind_size, icon_anchor=icon_wind_anchor)
                # Cria o marcador da seta NA MESMA POSIÇÃO INICIAL do avião (o offset é visual no HTML)
                wind_marker = folium.Marker(location=coords[0], icon=wind_icon, popup='Vento', interactive=False, keyboard=False)
                wind_marker.add_to(m)
                self.wind_marker_js_name = wind_marker.get_name()
                print(f"DEBUG: Marcador de vento criado. Nome JS: {self.wind_marker_js_name}")
            else:
                raise FileNotFoundError('Ícone de vento indisponível')
        except Exception as e:
            print(f"ERRO ao criar ícone de vento: {e}"); self.wind_marker_js_name = "" # Reseta

        # --- Função JS global para atualizar posição e rotação ---
        js_update_function = f"""
        <script>
            // Garante que só define uma vez
            if (typeof window.updateMarkers === 'undefined') {{
                window.updateMarkers = function(lat, lon, aircraft_yaw, wind_dir, wind_speed) {{
                    //console.log(`JS: updateMarkers called - Yaw: ${{aircraft_yaw}}, WindDir: ${{wind_dir}}`);
                    var aircraftMarker = window[{repr(self.aircraft_marker_js_name)}];
                    var windMarker = window[{repr(self.wind_marker_js_name)}];

                    if (aircraftMarker && typeof aircraftMarker.setLatLng === 'function') {{
                        var newLatLng = L.latLng(lat, lon);
                        aircraftMarker.setLatLng(newLatLng);
                        var aircraftImg = document.getElementById('aircraft-img');
                        if (aircraftImg) {{
                            // Assumindo SVG do avião aponta para CIMA
                            aircraftImg.style.transform = 'rotate(' + aircraft_yaw + 'deg)';
                        }}
                    }} else {{
                        //console.warn("JS: Marcador de avião não encontrado ou inválido.");
                    }}

                    if (windMarker && typeof windMarker.setLatLng === 'function') {{
                        var newLatLngWind = L.latLng(lat, lon); // Mantem na mesma posição do avião
                        windMarker.setLatLng(newLatLngWind);
                        var windImg = document.getElementById('wind-arrow-img');
                        if (windImg) {{
                            // Rotação: wind_dir é DE ONDE VEM (0=Norte). Seta aponta PARA ONDE VAI.
                            var windRotation = wind_dir;
                            // var windRotation = 90;
                            // windImg.style.transform = 'rotate(' + windRotation + 'deg)';

                            // Opcional: Escala/Opacidade baseada na velocidade (WSI)
                            // Exemplo simples de opacidade:
                            var opacity = 0.8 + (Math.min(wind_speed, 20) / 20) * 0.7; // Escala opacidade de 0.3 a 1.0 para 0-20 m/s
                            windImg.style.opacity = opacity.toFixed(2);

                            // Exemplo simples de escala (pode ficar estranho):
                            var scale = 0.7 + (Math.min(wind_speed, 15) / 15); // Escala tamanho de 70% a 120% para 0-15 m/s
                            windImg.style.transform = 'rotate(' + windRotation + 'deg) scale(' + scale.toFixed(2) + ')';

                        }} else {{
                             console.warn("JS: Imagem #wind-arrow-img não encontrada.");
                        }}
                    }} else {{
                        //console.warn("JS: Marcador de vento não encontrado ou inválido.");
                    }}
                }};
                console.log("DEBUG JS: Função global updateMarkers(lat, lon, yaw, wind_dir, wind_speed) definida.");
            }}
        </script>
        """
        m.get_root().html.add_child(folium.Element(js_update_function))

        temp_dir_str = self.map_server.get_temp_dir()
        self.temp_map_file_path = os.path.join(temp_dir_str, f"map_{time.time()}.html")
        m.save(self.temp_map_file_path)
        map_url = QUrl.fromLocalFile(self.temp_map_file_path)
        self.map_is_ready = False
        self.mapWidget.load(map_url)

    def cleanup_cesium_html(self):
        if self.cesium_html_path and os.path.exists(self.cesium_html_path):
            try:
                os.remove(self.cesium_html_path)
            except OSError:
                pass
        self.cesium_html_path = ""
        self.cesium_is_ready = False
        self.cesium_playing = False
        self.cesium_sync_timer.stop()

    def cleanup_timeline_html(self):
        if self.timeline_html_path and os.path.exists(self.timeline_html_path):
            try:
                os.remove(self.timeline_html_path)
            except OSError:
                pass
        self.timeline_html_path = ""
        self.timeline_is_ready = False

    def populate_cesium_imagery_combo(self):
        if self.cesium_imagery_combo is None:
            return
        self.cesium_imagery_combo.blockSignals(True)
        self.cesium_imagery_combo.clear()
        for preset in self.cesium_imagery_presets:
            self.cesium_imagery_combo.addItem(preset["label"], preset["key"])
        if self.cesium_imagery_presets:
            try:
                index = next(
                    idx for idx, preset in enumerate(self.cesium_imagery_presets)
                    if preset["key"] == self.current_cesium_imagery_key
                )
            except StopIteration:
                index = 0
                self.current_cesium_imagery_key = self.cesium_imagery_presets[0]["key"]
            self.cesium_imagery_combo.setCurrentIndex(index)
        self.cesium_imagery_combo.blockSignals(False)

    def on_cesium_imagery_changed(self, index):
        if not self.cesium_imagery_presets or index < 0 or index >= len(self.cesium_imagery_presets):
            return
        selected_key = self.cesium_imagery_presets[index]["key"]
        self.current_cesium_imagery_key = selected_key
        self.update_cesium_imagery_layer(selected_key)

    def update_cesium_imagery_layer(self, preset_key):
        if not self.cesium_is_ready or not self.cesiumWidget:
            return
        js_code = (
            "if (typeof setImageryLayer === 'function') {"
            f"setImageryLayer('{preset_key}');"
            "}"
        )
        self.cesiumWidget.page().runJavaScript(js_code)

    def center_cesium_camera(self):
        if not self.cesium_is_ready or not self.cesiumWidget:
            return
        js_code = (
            "if (typeof centerCameraOnAircraft === 'function') {"
            "centerCameraOnAircraft();"
            "}"
        )
        self.cesiumWidget.page().runJavaScript(js_code)

    def _current_cesium_speed_value(self):
        if not self.cesium_speed_combo:
            return 1.0
        text = self.cesium_speed_combo.currentText().lower().replace('x', '').strip()
        try:
            return float(text)
        except ValueError:
            return 1.0

    def on_cesium_speed_changed(self, _value):
        speed = self._current_cesium_speed_value()
        if self.cesium_is_ready and self.cesiumWidget:
            js_code = (
                "if (typeof setPlaybackSpeed === 'function') {"
                f"setPlaybackSpeed({speed});"
                "}"
            )
            self.cesiumWidget.page().runJavaScript(js_code)
        if self.timeline_is_ready and self.timelineWidget:
            js_code = (
                "if (typeof setTimelinePlaybackSpeed === 'function') {"
                f"setTimelinePlaybackSpeed({speed});"
                "}"
            )
            self.timelineWidget.page().runJavaScript(js_code)

    def toggle_cesium_playback(self):
        if not self.cesium_is_ready or not self.cesiumWidget:
            return
        if self.cesium_playing:
            self.pause_cesium_playback()
        else:
            self.start_cesium_playback()

    def start_cesium_playback(self):
        if not self.cesium_is_ready or not self.cesiumWidget:
            return
        speed = self._current_cesium_speed_value()
        js_code = (
            "if (typeof playTrajectory === 'function') {"
            f"playTrajectory({speed});"
            "}"
        )
        self.cesiumWidget.page().runJavaScript(js_code)
        if self.timeline_is_ready and self.timelineWidget:
            timeline_js = (
                "if (typeof playTimeline === 'function') {"
                f"playTimeline({speed});"
                "}"
            )
            self.timelineWidget.page().runJavaScript(timeline_js)
        self.cesium_playing = True
        self._update_cesium_play_button()
        if not self.cesium_sync_timer.isActive():
            self.cesium_sync_timer.start()

    def pause_cesium_playback(self):
        if not self.cesium_is_ready or not self.cesiumWidget:
            return
        js_code = "if (typeof pauseTrajectory === 'function') { pauseTrajectory(); }"
        self.cesiumWidget.page().runJavaScript(js_code)
        if self.timeline_is_ready and self.timelineWidget:
            self.timelineWidget.page().runJavaScript("if (typeof pauseTimeline === 'function') { pauseTimeline(); }")
        self.cesium_playing = False
        self._update_cesium_play_button()

    def _update_cesium_play_button(self):
        if not self.cesium_play_button:
            return
        self.cesium_play_button.setText("Pausar ⏸" if self.cesium_playing else "Play ▶")
        self.cesium_play_button.setEnabled(self.cesium_is_ready)

    def _update_cesium_controls_state(self):
        if not self.cesium_controls_container:
            return
        show_controls = self.view_toggle_checkbox and self.view_toggle_checkbox.isChecked()
        self.cesium_controls_container.setVisible(show_controls)
        if self.cesium_center_button:
            self.cesium_center_button.setEnabled(show_controls and self.cesium_is_ready)
        if self.cesium_imagery_combo:
            self.cesium_imagery_combo.setEnabled(show_controls)
        if self.cesium_follow_checkbox:
            self.cesium_follow_checkbox.setEnabled(show_controls and self.cesium_is_ready)
            if not show_controls:
                self.cesium_follow_checkbox.blockSignals(True)
                self.cesium_follow_checkbox.setChecked(True)
                self.cesium_follow_checkbox.blockSignals(False)
        if self.cesium_play_button:
            self.cesium_play_button.setEnabled(show_controls and self.cesium_is_ready)
            self._update_cesium_play_button()
        if self.cesium_speed_combo:
            self.cesium_speed_combo.setEnabled(show_controls and self.cesium_is_ready)

    def create_cesium_viewer_html(self):
        try:
            self.copy_assets_to_server(self.cesium_plane_asset)
            port = self.map_server.get_port()
            plane_url = f"http://127.0.0.1:{port}/{os.path.basename(self.cesium_plane_asset)}"
            plane_literal = json.dumps(plane_url)
            imagery_config_literal = json.dumps(self.cesium_imagery_presets)
            default_imagery_key = json.dumps(self.current_cesium_imagery_key)
            samples_literal = json.dumps(self._build_cesium_samples())
            html_template = Template("""<!DOCTYPE html>
<html lang='pt-BR'>
<head>
    <meta charset='utf-8'>
    <title>Visualização 3D - Cesium</title>
    <link rel='stylesheet' href='https://cdn.jsdelivr.net/npm/cesium@1.121.0/Build/Cesium/Widgets/widgets.css'>
    <style>
        html, body, #cesiumContainer {
            width: 100%;
            height: 100%;
            margin: 0;
            padding: 0;
            overflow: hidden;
            background: #01030a;
        }
        #hud {
            position: absolute;
            top: 12px;
            left: 12px;
            background: rgba(0, 0, 0, 0.55);
            border-radius: 10px;
            padding: 10px 14px;
            font-family: 'Segoe UI', Arial, sans-serif;
            color: #f8f9fa;
            font-size: 13px;
            line-height: 1.4;
            min-width: 160px;
        }
        #hud strong {
            color: #4dabf7;
        }
        #cesiumContainer .cesium-viewer-timelineContainer {
            bottom: 0;
        }
        #cesiumContainer .cesium-viewer-animationContainer {
            display: none !important;
        }
    </style>
</head>
<body>
    <div id='cesiumContainer'></div>
    <div id='hud'>
        <div><strong>Lat:</strong> <span id='hud-lat'>--</span></div>
        <div><strong>Lon:</strong> <span id='hud-lon'>--</span></div>
        <div><strong>Alt:</strong> <span id='hud-alt'>--</span> m</div>
        <div><strong>Pitch:</strong> <span id='hud-pitch'>--</span>°</div>
        <div><strong>Roll:</strong> <span id='hud-roll'>--</span>°</div>
    </div>
    <script src='https://cdn.jsdelivr.net/npm/cesium@1.121.0/Build/Cesium/Cesium.js'></script>
    <script>
        (function () {
            const terrainProvider = new Cesium.EllipsoidTerrainProvider();
            const viewer = new Cesium.Viewer('cesiumContainer', {
                animation: false,
                timeline: false,
                shouldAnimate: false,
                terrainProvider: terrainProvider,
                imageryProvider: undefined,
                baseLayerPicker: false,
                sceneModePicker: false,
                navigationHelpButton: false,
                geocoder: false,
                fullscreenButton: false,
                homeButton: false,
                infoBox: false,
                selectionIndicator: false
            });
            viewer.scene.globe.enableLighting = true;
            viewer.clock.shouldAnimate = false;
            const imageryConfigsArray = $IMAGERY_CONFIG_JSON;
            const imageryConfigs = imageryConfigsArray.reduce((acc, cfg) => {
                acc[cfg.key] = cfg;
                return acc;
            }, {});
            const defaultImageryKey = $DEFAULT_IMAGERY_KEY;
            const samples = $SAMPLES_JSON;
            const sampleTimes = Array.isArray(samples)
                ? samples.map(s => (s && Number.isFinite(s.timeMs)) ? s.timeMs : null)
                : [];
            const routePositions = Array.isArray(samples)
                ? samples.map(s => (s && Number.isFinite(s.lat) && Number.isFinite(s.lon))
                    ? { lat: s.lat, lon: s.lon, alt: Number.isFinite(s.alt) ? s.alt : 0.0 }
                    : null)
                : [];
            let startJulian = undefined;
            let stopJulian = undefined;
            function buildTilingScheme(cfg) {
                if (cfg.tilingScheme === 'geographic') {
                    return new Cesium.GeographicTilingScheme();
                }
                return new Cesium.WebMercatorTilingScheme();
            }
            function createImageryProvider(cfg) {
                return new Cesium.UrlTemplateImageryProvider({
                    url: cfg.url,
                    credit: cfg.credit || '',
                    tilingScheme: buildTilingScheme(cfg),
                    maximumLevel: Number.isFinite(cfg.maximumLevel) ? cfg.maximumLevel : undefined
                });
            }
            function applyImageryLayer(key) {
                const cfg = imageryConfigs[key] || imageryConfigs[defaultImageryKey];
                if (!cfg) {
                    return;
                }
                if (window.__currentBaseLayer) {
                    viewer.imageryLayers.remove(window.__currentBaseLayer, true);
                }
                window.__currentBaseLayer = viewer.imageryLayers.addImageryProvider(
                    createImageryProvider(cfg),
                    0
                );
                return cfg;
            }
            applyImageryLayer(defaultImageryKey);
            window.setImageryLayer = function(key) {
                return applyImageryLayer(key);
            };
            const scratchHPR = new Cesium.HeadingPitchRoll();
            const defaultPosition = Cesium.Cartesian3.fromDegrees(-47.9, -15.7, 1000.0);
            const aircraftEntity = viewer.entities.add({
                id: 'aircraft-model',
                name: 'Aeronave',
                position: defaultPosition,
                model: {
                    uri: $PLANE_LITERAL,
                    minimumPixelSize: 80,
                    maximumScale: 200,
                    runAnimations: true
                },
                orientation: Cesium.Transforms.headingPitchRollQuaternion(
                    defaultPosition,
                    new Cesium.HeadingPitchRoll()
                )
            });
            viewer.trackedEntity = aircraftEntity;
            const hudLat = document.getElementById('hud-lat');
            const hudLon = document.getElementById('hud-lon');
            const hudAlt = document.getElementById('hud-alt');
            const hudPitch = document.getElementById('hud-pitch');
            const hudRoll = document.getElementById('hud-roll');
            function updateHud(lat, lon, alt, pitchDeg, rollDeg) {
                hudLat.textContent = Number.isFinite(lat) ? lat.toFixed(6) : '--';
                hudLon.textContent = Number.isFinite(lon) ? lon.toFixed(6) : '--';
                hudAlt.textContent = Number.isFinite(alt) ? alt.toFixed(1) : '--';
                hudPitch.textContent = Number.isFinite(pitchDeg) ? pitchDeg.toFixed(1) : '--';
                hudRoll.textContent = Number.isFinite(rollDeg) ? rollDeg.toFixed(1) : '--';
            }
            function radiansOrZero(valueDeg) {
                return Cesium.Math.toRadians(Number.isFinite(valueDeg) ? valueDeg : 0.0);
            }
            const headingOffset = Cesium.Math.toRadians(-90.0);
            function applySample(sample) {
                if (!sample || !Number.isFinite(sample.lat) || !Number.isFinite(sample.lon)) {
                    return;
                }
                const safeAlt = Number.isFinite(sample.alt) ? sample.alt : 0.0;
                const position = Cesium.Cartesian3.fromDegrees(sample.lon, sample.lat, safeAlt);
                aircraftEntity.position = position;
                scratchHPR.heading = radiansOrZero(sample.heading) + headingOffset;
                scratchHPR.pitch = radiansOrZero(sample.pitch);
                scratchHPR.roll = radiansOrZero(sample.roll);
                aircraftEntity.orientation = Cesium.Transforms.headingPitchRollQuaternion(position, scratchHPR);
                updateHud(sample.lat, sample.lon, safeAlt, sample.pitch, sample.roll);
            }
            window.centerCameraOnAircraft = function() {
                if (!aircraftEntity) {
                    return;
                }
                if (window.__followEnabled !== false) {
                    viewer.trackedEntity = aircraftEntity;
                }
                viewer.flyTo(aircraftEntity, {
                    duration: 0.6,
                    offset: new Cesium.HeadingPitchRange(0.0, -0.5, 150.0)
                });
            };
            window.setFollowMode = function(enabled) {
                window.__followEnabled = !!enabled;
                viewer.trackedEntity = enabled ? aircraftEntity : undefined;
            };
            const completedPath = viewer.entities.add({
                polyline: {
                    positions: [],
                    width: 3,
                    material: new Cesium.PolylineGlowMaterialProperty({
                        glowPower: 0.08,
                        color: Cesium.Color.CYAN.withAlpha(0.85)
                    })
                }
            });
            const upcomingPath = viewer.entities.add({
                polyline: {
                    positions: [],
                    width: 3,
                    material: Cesium.Color.CYAN.withAlpha(0.18)
                }
            });
            function toCartesian(pts) {
                const arr = [];
                for (const p of pts) {
                    if (!p) continue;
                    arr.push(p.lon, p.lat, p.alt);
                }
                return arr.length ? Cesium.Cartesian3.fromDegreesArrayHeights(arr) : [];
            }
            function updateRouteProgress(index) {
                if (!Array.isArray(routePositions) || !routePositions.length) {
                    return;
                }
                const clamped = Math.max(0, Math.min(routePositions.length, index + 1));
                const done = routePositions.slice(0, clamped);
                const nextSegment = routePositions.slice(Math.max(0, clamped - 1));
                completedPath.polyline.positions = toCartesian(done);
                upcomingPath.polyline.positions = toCartesian(nextSegment);
            }
            function julianFromMs(ms) {
                return Cesium.JulianDate.fromDate(new Date(ms));
            }
            let playbackSpeed = 1.0;
            function applyPlaybackSpeed(speed) {
                const safe = Number.isFinite(speed) ? speed : 1.0;
                playbackSpeed = safe;
                viewer.clock.multiplier = playbackSpeed;
            }
            function findIndexForJulian(jd) {
                if (!sampleTimes.length) return 0;
                const currentMs = Cesium.JulianDate.toDate(jd).getTime();
                for (let i = 0; i < sampleTimes.length; i++) {
                    const t = sampleTimes[i];
                    if (t === null) continue;
                    const next = sampleTimes[Math.min(sampleTimes.length - 1, i + 1)];
                    if (currentMs <= (next ?? currentMs)) {
                        return i;
                    }
                }
                return sampleTimes.length - 1;
            }
            function clampIndex(idx) {
                return Math.max(0, Math.min(samples.length - 1, Number(idx) || 0));
            }
            let currentIndex = 0;
            function applyIndex(idx) {
                if (!Array.isArray(samples) || !samples.length) return;
                const clamped = clampIndex(idx);
                if (clamped === currentIndex && !viewer.clock.shouldAnimate) return;
                currentIndex = clamped;
                const sample = samples[clamped];
                if (sample) {
                    applySample(sample);
                    if (window.__followEnabled !== false) {
                        viewer.trackedEntity = aircraftEntity;
                    }
                }
                updateRouteProgress(clamped);
                window.__currentTimelineIndex = clamped;
            }
            window.setTimelineIndex = function(index) {
                if (!sampleTimes.length) return;
                const clamped = clampIndex(index);
                const t = sampleTimes[clamped];
                if (Number.isFinite(t)) {
                    viewer.clock.shouldAnimate = false;
                    viewer.clock.currentTime = julianFromMs(t);
                    applyIndex(clamped);
                }
            };
            window.setPlaybackSpeed = function(speed) {
                applyPlaybackSpeed(speed);
            };
            window.playTrajectory = function(speed) {
                if (Number.isFinite(speed)) {
                    applyPlaybackSpeed(speed);
                }
                if (startJulian) {
                    viewer.clock.currentTime = viewer.clock.currentTime || startJulian.clone();
                }
                viewer.clock.shouldAnimate = true;
            };
            window.pauseTrajectory = function() {
                viewer.clock.shouldAnimate = false;
            };
            if (Array.isArray(samples) && samples.length) {
                const firstValidTime = sampleTimes.find(t => t !== null);
                const lastValidTime = [...sampleTimes].reverse().find(t => t !== null);
                if (Number.isFinite(firstValidTime) && Number.isFinite(lastValidTime)) {
                    startJulian = julianFromMs(firstValidTime);
                    stopJulian = julianFromMs(lastValidTime);
                    viewer.clock.startTime = startJulian.clone();
                    viewer.clock.stopTime = stopJulian.clone();
                    viewer.clock.currentTime = startJulian.clone();
                    viewer.clock.clockRange = Cesium.ClockRange.CLAMPED;
                    viewer.clock.multiplier = playbackSpeed;
                    viewer.clock.shouldAnimate = false;
                }
                const initialSample = samples.find(s => !!s);
                if (initialSample) {
                    const startPosition = Cesium.Cartesian3.fromDegrees(initialSample.lon, initialSample.lat, initialSample.alt || 0.0);
                    aircraftEntity.position = startPosition;
                    aircraftEntity.orientation = Cesium.Transforms.headingPitchRollQuaternion(
                        startPosition,
                        new Cesium.HeadingPitchRoll()
                    );
                }
                viewer.trackedEntity = aircraftEntity;
                window.__followEnabled = true;
                viewer.clock.onTick.addEventListener(function(clock) {
                    if (!sampleTimes.length) return;
                    const idx = findIndexForJulian(clock.currentTime);
                    if (idx !== currentIndex || clock.shouldAnimate) {
                        applyIndex(idx);
                    }
                });
            } else {
                viewer.trackedEntity = aircraftEntity;
                window.__followEnabled = true;
            }
            window.__cesiumViewerReady = true;
        })();
    </script>
          </body>
          </html>
          """)
            html_content = html_template.substitute(
                PLANE_LITERAL=plane_literal,
                IMAGERY_CONFIG_JSON=imagery_config_literal,
                DEFAULT_IMAGERY_KEY=default_imagery_key,
                SAMPLES_JSON=samples_literal
            )
            output_name = f"cesium_view_{int(time.time()*1000)}.html"
            output_path = os.path.join(self.map_server.get_temp_dir(), output_name)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            return output_path
        except Exception as exc:
            QMessageBox.warning(self, "Visualização 3D", f"Não foi possível preparar o Cesium: {exc}")
            return ""

    def create_cesium_timeline_html(self):
        try:
            samples_literal = json.dumps(self._build_cesium_samples())
            html_template = Template("""<!DOCTYPE html>
    <html lang='pt-BR'>
    <head>
        <meta charset='utf-8'>
        <title>Timeline - Cesium</title>
        <link rel='stylesheet' href='https://cdn.jsdelivr.net/npm/cesium@1.121.0/Build/Cesium/Widgets/widgets.css'>
        <style>
            html, body, #timelineContainer {
                width: 100%;
                height: 100%;
                margin: 0;
                padding: 0;
                overflow: hidden;
                background: #01030a;
            }
            #timelineContainer .cesium-viewer-cesiumWidgetContainer,
            #timelineContainer .cesium-viewer-toolbar,
            #timelineContainer .cesium-viewer-fullscreenContainer,
            #timelineContainer .cesium-viewer-animationContainer {
                display: none !important;
            }
            #timelineContainer .cesium-viewer-timelineContainer {
                bottom: 0;
                height: 100%;
            }
            #timelineContainer .cesium-viewer-bottom {
                bottom: 0;
            }
        </style>
    </head>
    <body>
        <div id='timelineContainer'></div>
        <script src='https://cdn.jsdelivr.net/npm/cesium@1.121.0/Build/Cesium/Cesium.js'></script>
        <script>
            (function () {
                const samples = $SAMPLES_JSON;
                const sampleTimes = Array.isArray(samples)
                    ? samples.map(s => (s && Number.isFinite(s.timeMs)) ? s.timeMs : null)
                    : [];
                let playbackSpeed = 1.0;
                const viewer = new Cesium.Viewer('timelineContainer', {
                    animation: false,
                    timeline: true,
                    shouldAnimate: false,
                    imageryProvider: false,
                    baseLayerPicker: false,
                    geocoder: false,
                    sceneModePicker: false,
                    navigationHelpButton: false,
                    fullscreenButton: false,
                    homeButton: false,
                    infoBox: false,
                    selectionIndicator: false
                });
                viewer.scene.canvas.style.display = 'none';
                viewer.cesiumWidget.screenSpaceEventHandler.removeInputAction(Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);
                function julianFromMs(ms) { return Cesium.JulianDate.fromDate(new Date(ms)); }
                function clampIndex(idx) { return Math.max(0, Math.min(samples.length - 1, Number(idx) || 0)); }
                function findIndexForJulian(jd) {
                    if (!sampleTimes.length) return 0;
                    const currentMs = Cesium.JulianDate.toDate(jd).getTime();
                    for (let i = 0; i < sampleTimes.length; i++) {
                        const t = sampleTimes[i];
                        if (t === null) continue;
                        const next = sampleTimes[Math.min(sampleTimes.length - 1, i + 1)];
                        if (currentMs <= (next ?? currentMs)) { return i; }
                    }
                    return sampleTimes.length - 1;
                }
                function applyPlaybackSpeed(speed) {
                    const safe = Number.isFinite(speed) ? speed : 1.0;
                    playbackSpeed = safe;
                    viewer.clock.multiplier = playbackSpeed;
                }
                function configureClock() {
                    if (!sampleTimes.length) {
                        if (viewer.timeline) {
                            viewer.timeline.zoomTo(viewer.clock.startTime, viewer.clock.stopTime);
                        }
                        return;
                    }
                    const firstValidTime = sampleTimes.find(t => t !== null);
                    const lastValidTime = [...sampleTimes].reverse().find(t => t !== null);
                    if (Number.isFinite(firstValidTime) && Number.isFinite(lastValidTime)) {
                        const start = julianFromMs(firstValidTime);
                        const stop = julianFromMs(lastValidTime);
                        viewer.clock.startTime = start.clone();
                        viewer.clock.stopTime = stop.clone();
                        viewer.clock.currentTime = start.clone();
                        viewer.clock.multiplier = playbackSpeed;
                        viewer.clock.clockRange = Cesium.ClockRange.CLAMPED;
                        viewer.clock.shouldAnimate = false;
                        if (viewer.timeline) {
                            viewer.timeline.zoomTo(start, stop);
                        }
                    }
                }
                let currentIndex = 0;
                window.__currentTimelineIndex = 0;
                function applyIndex(idx) {
                    if (!Array.isArray(samples) || !samples.length) return;
                    const clamped = clampIndex(idx);
                    if (clamped === currentIndex && !viewer.clock.shouldAnimate) return;
                    currentIndex = clamped;
                    window.__currentTimelineIndex = clamped;
                }
                viewer.clock.onTick.addEventListener(function(clock) {
                    if (!sampleTimes.length) return;
                    const idx = findIndexForJulian(clock.currentTime);
                    if (idx !== currentIndex || clock.shouldAnimate) {
                        applyIndex(idx);
                    }
                });
                if (viewer.timeline) {
                    viewer.timeline.addEventListener('settime', function() {
                        const idx = findIndexForJulian(viewer.clock.currentTime);
                        applyIndex(idx);
                    });
                }
                window.setTimelineIndex = function(index) {
                    if (!sampleTimes.length) return;
                    const clamped = clampIndex(index);
                    const t = sampleTimes[clamped];
                    if (Number.isFinite(t)) {
                        viewer.clock.shouldAnimate = false;
                        viewer.clock.currentTime = julianFromMs(t);
                        applyIndex(clamped);
                    }
                };
                window.setTimelinePlaybackSpeed = function(speed) {
                    applyPlaybackSpeed(speed);
                };
                window.playTimeline = function(speed) {
                    if (Number.isFinite(speed)) {
                        applyPlaybackSpeed(speed);
                    }
                    viewer.clock.shouldAnimate = true;
                };
                window.pauseTimeline = function() {
                    viewer.clock.shouldAnimate = false;
                };
                configureClock();
                window.__timelineReady = true;
            })();
        </script>
    </body>
    </html>
    """)
            html_content = html_template.substitute(SAMPLES_JSON=samples_literal)
            output_name = f"cesium_timeline_{int(time.time()*1000)}.html"
            output_path = os.path.join(self.map_server.get_temp_dir(), output_name)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            return output_path
        except Exception as exc:
            QMessageBox.warning(self, "Timeline", f"Não foi possível preparar a timeline: {exc}")
            return ""

    def show_cesium_3d_view(self):
        self.cleanup_cesium_html()
        html_path = self.create_cesium_viewer_html()
        if not html_path:
            return False
        self.cesium_html_path = html_path
        port = self.map_server.get_port()
        self.cesium_is_ready = False
        url = QUrl(f"http://127.0.0.1:{port}/{os.path.basename(html_path)}")
        self.cesiumWidget.load(url)
        return True

    def refresh_timeline_html(self):
        if not self.timelineWidget:
            return
        self.cleanup_timeline_html()
        html_path = self.create_cesium_timeline_html()
        if not html_path:
            return
        self.timeline_html_path = html_path
        port = self.map_server.get_port()
        self.timeline_is_ready = False
        url = QUrl(f"http://127.0.0.1:{port}/{os.path.basename(html_path)}")
        self.timelineWidget.load(url)

    def on_timeline_load_finished(self, ok):
        if ok:
            self._wait_for_timeline_ready()
        else:
            self.timeline_is_ready = False

    def _wait_for_timeline_ready(self, retries=20):
        if not self.timelineWidget:
            return

        def _handle_ready(result):
            if result:
                self.timeline_is_ready = True
                self.statusBar().showMessage("Timeline pronta!", 2000)
                self.update_views_from_timeline(self.current_timeline_index, push_to_cesium=True, sync_timeline_widget=False, force_plot_update=True)
                if not self.cesium_sync_timer.isActive():
                    self.cesium_sync_timer.start()
            elif retries > 0:
                QTimer.singleShot(200, lambda: self._wait_for_timeline_ready(retries - 1))
            else:
                self.timeline_is_ready = False
                self.statusBar().showMessage("Não consegui sincronizar a timeline.", 4000)

        try:
            self.timelineWidget.page().runJavaScript("Boolean(window.__timelineReady)", _handle_ready)
        except RuntimeError:
            self.timeline_is_ready = False

    def _wait_for_cesium_ready(self, retries=20):
        if not self.cesiumWidget:
            return

        def _handle_ready(result):
            if result:
                self.cesium_is_ready = True
                self.statusBar().showMessage("Cesium pronto e timeline carregada!", 3000)
                self.update_cesium_imagery_layer(self.current_cesium_imagery_key)
                self._update_cesium_controls_state()
                self.update_views_from_timeline(self.current_timeline_index)
                self.update_cesium_index(self.current_timeline_index)
                if self.cesium_follow_checkbox:
                    self.cesium_follow_checkbox.blockSignals(True)
                    self.cesium_follow_checkbox.setChecked(True)
                    self.cesium_follow_checkbox.blockSignals(False)
                self.cesium_sync_timer.start()
            elif retries > 0:
                QTimer.singleShot(200, lambda: self._wait_for_cesium_ready(retries - 1))
            else:
                self.statusBar().showMessage("Não consegui sincronizar o Cesium.", 5000)
                self._update_cesium_controls_state()

        try:
            self.cesiumWidget.page().runJavaScript("Boolean(window.__cesiumViewerReady)", _handle_ready)
        except RuntimeError:
            self.cesium_is_ready = False
            self._update_cesium_controls_state()


    def setup_timeline(self):
        self.last_plot_cursor_update_time = 0.0
        self.refresh_timeline_html()
        if not self.df.empty:
            self.current_timeline_index = 0
            if 'Timestamp' in self.df.columns and not self.df['Timestamp'].empty:
                first_ts = self.df['Timestamp'].iloc[0]
                if pd.notna(first_ts):
                    self.timestamp_label.setText(f"Timestamp: {first_ts.strftime('%H:%M:%S.%f')[:-3]}")
            self.btn_set_timestamp.setEnabled(True)
            self.btn_save_pdf.setEnabled(True)
            # Mantém a timeline do Cesium como única fonte de playback
            if not self.cesium_html_path:
                self.show_cesium_3d_view()
        else:
            self.current_timeline_index = 0
            self.btn_set_timestamp.setEnabled(False)
            self.btn_save_pdf.setEnabled(False)
            self.timestamp_label.setText("Timestamp: --:--:--.---")
            
    def update_views_from_timeline(self, index, push_to_cesium=False, sync_timeline_widget=False, force_plot_update=False):
        if self.df.empty or index >= len(self.df):
            return
        self.current_timeline_index = index
        data_row = self.df.iloc[index]
        timestamp = data_row['Timestamp']

        self.timestamp_label.setText(f"Timestamp: {timestamp.strftime('%H:%M:%S.%f')[:-3]}")

        if 'Latitude' in data_row and 'Longitude' in data_row:

            yaw = self._extract_heading_deg(data_row)
            pitch = data_row.get('Pitch', 0)
            roll = data_row.get('Roll', 0)
            lat = data_row.get('Latitude')          # Pega a lat
            lon = data_row.get('Longitude')         # Pega a long
            alt_abs = data_row.get('AltitudeAbs', 0)    # Altitude absoluta
            win = data_row.get('WindDirection', 0)  # Pega o windD
            wsi = data_row.get('WSI', 0)            # Pega o vento
            if not pd.notna(yaw): yaw = 0 # Trata NaN
            if not pd.notna(pitch): pitch = 0
            if not pd.notna(roll): roll = 0
            if not pd.notna(alt_abs): alt_abs = 0
            if not pd.notna(win): win = 0 # Trata NaN
            if not pd.notna(wsi): wsi = 0 # Trata NaN

            alt_rel = self._compute_relative_altitude(alt_abs)

            self.update_aircraft_position(lat, lon, yaw, win, wsi)
            if push_to_cesium:
                self.update_cesium_index(index)
                if sync_timeline_widget:
                    self.update_timeline_index(index)

        now = time.monotonic()
        if force_plot_update or (now - self.last_plot_cursor_update_time) >= 1.0:
            self._update_plot_cursors(timestamp)
            self.last_plot_cursor_update_time = now

    def _update_plot_cursors(self, timestamp):
        if self.standard_plots_tab: self.standard_plots_tab.update_cursor(timestamp)
        if self.all_plots_tab: self.all_plots_tab.update_cursor(timestamp)
        if self.custom_plot_tab: self.custom_plot_tab.update_cursor(timestamp) # Ainda tem que ser implementado
            
    def update_aircraft_position(self, lat, lon, yaw, win, wsi):
        #print(f"DEBUG PY: Update Pos: Lat={lat:.6f}, Lon={lon:.6f}, Yaw={yaw:.1f}, WindDir={wind_dir:.1f}, WSI={wind_speed:.1f}, Ready={self.map_is_ready}")
        if not self.map_is_ready or not self.aircraft_marker_js_name or not self.wind_marker_js_name:
            #print("DEBUG PY: Mapa não pronto ou marcadores JS não definidos.")
            return
        if pd.notna(lat) and pd.notna(lon):
            # Passa todos os dados para a função JS unificada
            js_code = f"updateMarkers({lat}, {lon}, {yaw}, {win}, {wsi});"
            self.mapWidget.page().runJavaScript(js_code)

    def update_cesium_index(self, index):
        if not self.cesium_is_ready or self.cesiumWidget is None:
            return
        js_code = (
            "if (typeof setTimelineIndex === 'function') {"
            f"setTimelineIndex({int(index)});"
            "}"
        )
        self.cesiumWidget.page().runJavaScript(js_code)

    def update_timeline_index(self, index):
        if not self.timeline_is_ready or self.timelineWidget is None:
            return
        js_code = (
            "if (typeof setTimelineIndex === 'function') {"
            f"setTimelineIndex({int(index)});"
            "}"
        )
        self.timelineWidget.page().runJavaScript(js_code)

    def _sync_cesium_timeline_into_app(self):
        if self.df.empty:
            return

        target_widget = None
        push_to_cesium = True
        if self.cesium_playing and self.cesium_is_ready and self.cesiumWidget is not None:
            target_widget = self.cesiumWidget
            push_to_cesium = False
        elif self.timeline_is_ready and self.timelineWidget is not None:
            target_widget = self.timelineWidget
        elif self.cesium_is_ready and self.cesiumWidget is not None:
            target_widget = self.cesiumWidget
            push_to_cesium = False

        if not target_widget:
            return

        js_code = """
            (function() {
                return (typeof window.__currentTimelineIndex === 'number') ? window.__currentTimelineIndex : null;
            })();
        """
        target_widget.page().runJavaScript(js_code, lambda v: self._apply_timeline_snapshot(v, push_to_cesium))

    def _apply_timeline_snapshot(self, payload, push_to_cesium=True):
        idx_value = payload
        if isinstance(payload, dict):
            idx_value = payload.get('idx', payload.get('index'))
        self._apply_timeline_index(idx_value, push_to_cesium=push_to_cesium)

    def _apply_timeline_index(self, value, push_to_cesium=True):
        try:
            idx = int(value)
        except Exception:
            return
        if idx < 0:
            idx = 0
        if idx >= len(self.df):
            idx = len(self.df) - 1
        if idx != self.current_timeline_index:
            self.update_views_from_timeline(idx, push_to_cesium=push_to_cesium)

    def on_cesium_follow_changed(self, state):
        enabled = Qt.CheckState(state) == Qt.CheckState.Checked
        if not self.cesium_is_ready or self.cesiumWidget is None:
            return
        js_code = (
            "if (typeof setFollowMode === 'function') {"
            f"setFollowMode({str(enabled).lower()});"
            "}"
        )
        self.cesiumWidget.page().runJavaScript(js_code)

    def _compute_relative_altitude(self, alt_abs):
        if not pd.notna(alt_abs):
            return 0.0
        if self.altitude_reference is None:
            self.altitude_reference = float(alt_abs)
        return max(0.0, float(alt_abs) - float(self.altitude_reference))

    def _timestamp_to_epoch_ms(self, timestamp):
        if timestamp is None:
            return None
        try:
            ts = pd.to_datetime(timestamp)
            if hasattr(ts, 'tz_convert') and ts.tzinfo is not None:
                ts = ts.tz_convert(None)
            elif hasattr(ts, 'tz_localize'):
                try:
                    ts = ts.tz_localize(None)
                except Exception:
                    pass
            return int(ts.value // 1_000_000)
        except Exception:
            return None

    def _extract_heading_deg(self, row):
        yaw_candidates = [
            ('Yaw', False),
            ('Yaw_deg', False),
            ('yaw', False),
            ('Heading', False),
            ('AHRS_yaw', True),
            ('EKF_yaw', True),
            ('DCM_yaw', True),
            ('heading', False)
        ]
        for col, is_radians in yaw_candidates:
            if col in row and pd.notna(row[col]):
                value = float(row[col])
                if is_radians:
                    value = math.degrees(value)
                normalized = ((value + 180.0) % 360.0) - 180.0
                return normalized
        return 0.0

    def _update_altitude_reference(self):
        if self.df.empty or 'AltitudeAbs' not in self.df.columns:
            self.altitude_reference = 0.0
            return
        first_valid = self.df['AltitudeAbs'].dropna()
        self.altitude_reference = float(first_valid.iloc[0]) if not first_valid.empty else 0.0

    def _build_cesium_samples(self):
        samples = []
        if self.df.empty:
            return samples
        for _, row in self.df.iterrows():
            lat = row.get('Latitude') if 'Latitude' in row else None
            lon = row.get('Longitude') if 'Longitude' in row else None
            if pd.notna(lat) and pd.notna(lon):
                alt_abs = row.get('AltitudeAbs') if 'AltitudeAbs' in row else None
                alt_rel = self._compute_relative_altitude(alt_abs)
                timestamp = row.get('Timestamp') if 'Timestamp' in row else None
                time_ms = self._timestamp_to_epoch_ms(timestamp) if pd.notna(timestamp) else None
                samples.append({
                    'lat': float(lat),
                    'lon': float(lon),
                    'alt': float(alt_rel),
                    'heading': float(self._extract_heading_deg(row)),
                    'pitch': float(row.get('Pitch', 0) if pd.notna(row.get('Pitch', 0)) else 0),
                    'roll': float(row.get('Roll', 0) if pd.notna(row.get('Roll', 0)) else 0),
                    'timeMs': time_ms
                })
            else:
                samples.append(None)
        return samples

    def set_timestamp_manually(self):
        if self.df.empty: return
        current_ts_str = self.df['Timestamp'].iloc[self.current_timeline_index].strftime('%H:%M:%S.%f')[:-3]
        text, ok = QInputDialog.getText(self, "Definir Timestamp", "Digite (HH:MM:SS.mmm):", text=current_ts_str)
        if ok and text:
            try:
                date_part = self.df['Timestamp'].iloc[0].date()
                time_part = pd.to_datetime(text, format='%H:%M:%S.%f').time()
                target_timestamp = pd.Timestamp.combine(date_part, time_part)
                closest_index = (self.df['Timestamp'] - target_timestamp).abs().idxmin()

                self.update_views_from_timeline(int(closest_index), push_to_cesium=True, sync_timeline_widget=True, force_plot_update=True)

            except ValueError:
                QMessageBox.warning(self, "Erro de Formato", "Use HH:MM:SS.mmm.")

    def save_report_as_pdf(self):
        if self.df.empty:
            QMessageBox.warning(self, "Nenhum Dado", "Mano, tem que carregar um log pra mostrar o gráfico né kkkkkjk")
            return

        default_filename = self.current_log_name.replace(" ", "_") + "_Relatorio.pdf"
        file_path, _ = QFileDialog.getSaveFileName(self, "Salvar Relatório PDF", default_filename, "PDF Files (*.pdf)")

        if not file_path:
            return
        
        self.statusBar().showMessage("Capturando imagens para o relatório...")
        QApplication.processEvents()

        plot_images = self._capture_plot_images()
        map_images = self._capture_map_images()

        self.statusBar().showMessage("Escrevendo arquivo PDF em segundo plano...")
        self.btn_save_pdf.setEnabled(False)

        self.pdf_thread = QThread()
        self.pdf_worker = PdfReportWorker(file_path, self.current_log_name, plot_images, map_images)
        self.pdf_worker.moveToThread(self.pdf_thread)

        self.pdf_thread.started.connect(self.pdf_worker.run)
        self.pdf_worker.finished.connect(self.on_pdf_finished)
        self.pdf_worker.error.connect(self.on_pdf_error)
        
        self.pdf_worker.finished.connect(self.pdf_thread.quit)
        self.pdf_worker.finished.connect(self.pdf_worker.deleteLater)
        self.pdf_thread.finished.connect(self.pdf_thread.deleteLater)

        self.pdf_thread.start()

    def _capture_plot_images(self):
        images = []
        canvas_list = self.all_plots_tab.findChildren(FigureCanvas)
        for canvas in canvas_list:
            buf = io.BytesIO()
            canvas.figure.savefig(buf, format='png', dpi=150, bbox_inches='tight')
            buf.seek(0)
            images.append(buf)
        return images
        
    def _capture_map_images(self):
         # ### ALTERAÇÃO ### Usa o nome JS do mapa (self.map_js_name) em vez de window.map_instance
        images = []
        map_zooms = [17, 15, 12]
        if not self.map_js_name: # Verifica se temos o nome JS do mapa
             print("AVISO: Nome JS do mapa não definido. Pulando captura de mapas.")
             return images
        for zoom in map_zooms:
            if not self.map_is_ready: continue
            # Usa o nome correto da instância do mapa
            self.mapWidget.page().runJavaScript(f"{self.map_js_name}.setZoom({zoom});")
            start_time = time.time()
            while time.time() < start_time + 1.5: QApplication.processEvents()
            pixmap = self.mapWidget.grab(); buffer = QBuffer(); buffer.open(QIODevice.OpenModeFlag.ReadWrite)
            pixmap.save(buffer, "PNG"); img_bytes = io.BytesIO(buffer.data()); img_bytes.seek(0); images.append(img_bytes)
        # Usa o nome correto da instância do mapa
        self.mapWidget.page().runJavaScript(f"{self.map_js_name}.setZoom(15);")
        return images

    def on_pdf_finished(self, file_path):
        self.statusBar().showMessage(f"Relatório salvo em: {file_path}", 10000)
        QMessageBox.information(self, "Sucesso", f"Relatório salvo com sucesso em:\n{file_path}")
        self.btn_save_pdf.setEnabled(True)

    def on_pdf_error(self, error_msg):
        self.statusBar().showMessage("Erro ao gerar PDF.", 5000)
        QMessageBox.critical(self, "Erro", error_msg)
        self.btn_save_pdf.setEnabled(True)
    
    def closeEvent(self, event):
        print("Fechando aplicação...")
        self.map_server.stop()
        super().closeEvent(event)