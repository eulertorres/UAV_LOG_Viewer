# src/main_window.py
# Código para janela principal do programa
# Feito por Euler Torres - 22/10/2025

import sys
import os
import io
import time
import json
import math
import shutil
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QMessageBox, QSplitter, QGroupBox,
    QRadioButton, QTabWidget, QComboBox, QInputDialog,
    QSlider, QLabel, QDialog, QProgressBar, QTextEdit,
    QCheckBox, QStackedWidget
)
from PyQt6.QtCore import Qt, QUrl, QThread, pyqtSignal, QIODevice, QBuffer, QTimer
from PyQt6.QtGui import QMovie
from PyQt6.QtWebEngineWidgets import QWebEngineView
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

icone_aviao = 'aircraft.svg'
icone_seta = 'seta.svg'

class LoadingDialog(QDialog):
    """
    Um diálogo modal simples, sem bordas e transparente
    para mostrar um GIF de carregamento.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Remove a barra de título e deixa o fundo transparente
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True) # Impede interação com a janela principal

        # Label para conter o GIF
        self.label = QLabel(self)
        self.movie = QMovie("gato.gif")
        
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
        self.original_window_title = "SUPER VISUALIZADOR DE LOG DO EULERRRR!!! (～￣▽￣)～"
        self.setWindowTitle(self.original_window_title) 
        self.setGeometry(100, 100, 1600, 900)
        
        self.log_data = {}
        self.current_log_name = ""
        self.df = pd.DataFrame()
        self.thread = None
        self.worker = None

        self.map_server = MapServer()
        self.map_server.start()
        self.temp_map_file_path = ""
        self.map_js_name = ""
        self.map_is_ready = False 
        self.aircraft_marker_js_name = ""
        self.wind_marker_js_name = ""
        self.standard_plots_tab = None

        self.loading_widget = LoadingDialog(self)

        self.view_toggle_checkbox = None
        self.map_stack = None
        self.cesiumWidget = None
        self.cesium_state = None
        self.cesium_start_timestamp = None
        self.cesium_assets_ready = False
        self.cesium_dist_path = ""
        self.cesium_current_html = ""
        self.cesium_ready = False

        self.copy_assets_to_server(icone_aviao)
        self.copy_assets_to_server(icone_seta)

        self.setup_ui()

    def copy_assets_to_server(self, icon):
        """Copia arquivos estáticos necessários (ex: ícone) para o diretório do servidor."""
        try:
            # O arquivo SVG deve estar na raiz do projeto (onde run.py está)
            source_icon_path = icon
            if not os.path.exists(source_icon_path):
                print(f"AVISO: Arquivo '{source_icon_path}' não encontrado na raiz do projeto. O ícone do avião pode não aparecer.")
                return # Não faz nada se o arquivo não existir

            dest_dir = self.map_server.get_temp_dir()
            # Verifica se o diretório de destino existe (deve existir se o servidor iniciou)
            if not os.path.isdir(dest_dir):
                 print(f"ERRO: Diretório do servidor '{dest_dir}' não encontrado.")
                 return

            dest_path = os.path.join(dest_dir, os.path.basename(source_icon_path))

            # Copia o arquivo
            shutil.copy2(source_icon_path, dest_path) # copy2 preserva metadados
            #print(f"DEBUG: Ícone '{source_icon_path}' copiado para '{dest_path}'.")

        except Exception as e:
            print(f"ERRO CRÍTICO ao copiar assets para o servidor: {e}")
            QMessageBox.warning(self, "Erro de Asset", f"Não foi possível copiar o ícone do avião para o servidor:\n{e}")
        
    def setup_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget) # Layout principal vertical

        # --- Controles Superiores ---
        top_controls_layout = QHBoxLayout()
        self.btn_open = QPushButton("Selecionar Diretório Raiz dos Logs")
        self.btn_open.clicked.connect(self.open_log_directories)
        top_controls_layout.addWidget(self.btn_open)
        top_controls_layout.addWidget(QLabel("Log Ativo para Visualização:"))
        self.log_selector_combo = QComboBox()
        self.log_selector_combo.currentTextChanged.connect(self._on_log_selected)
        self.log_selector_combo.setEnabled(False)
        top_controls_layout.addWidget(self.log_selector_combo, 1)
        self.btn_save_pdf = QPushButton("Salvar Relatório em PDF (do Log Ativo)")
        self.btn_save_pdf.clicked.connect(self.save_report_as_pdf)
        self.btn_save_pdf.setEnabled(False)
        top_controls_layout.addWidget(self.btn_save_pdf)

        self.view_toggle_checkbox = QCheckBox("Visualização 3D (Cesium)")
        self.view_toggle_checkbox.stateChanged.connect(self.on_view_toggle_changed)
        self.view_toggle_checkbox.setEnabled(False)
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

        # --- Painel Principal com Splitter ---
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
        self.mapWidget.loadFinished.connect(self.on_map_load_finished)
        self.cesiumWidget = QWebEngineView()
        self.cesiumWidget.loadFinished.connect(self.on_cesium_load_finished)

        self.map_stack = QStackedWidget()
        self.map_stack.addWidget(self.mapWidget)
        self.map_stack.addWidget(self.cesiumWidget)
        map_panel_layout.addWidget(self.map_stack)
        self.map_stack.setCurrentWidget(self.mapWidget)

        # Adiciona o painel do mapa ao splitter
        self.splitter.addWidget(map_panel_widget)

        # Adiciona o splitter ao layout principal, ocupando o espaço restante (stretch=1)
        self.layout.addWidget(self.splitter, 1) 

        # --- Controles da Timeline (Abaixo do Splitter, largura total) ---
        self.setup_timeline_controls(self.layout) 

        # Define os tamanhos iniciais do splitter
        self.splitter.setSizes([800, 800]) # Ajuste inicial, pode ser [1000, 600] ou outro

    def setup_tabs(self):
        self.standard_plots_tab = StandardPlotsWidget(self) # Cria o novo widget
        self.tabs.addTab(self.standard_plots_tab, "Gráficos Padrão")

        self.custom_plot_tab = CustomPlotWidget(self)
        self.tabs.addTab(self.custom_plot_tab, "Gráfico de Comparação")

        self.all_plots_tab = AllPlotsWidget(self)
        self.tabs.addTab(self.all_plots_tab, "Todos os Gráficos (Log Ativo)")

    def setup_timeline_controls(self, parent_layout):
        timeline_layout = QHBoxLayout() # Cria o layout horizontal para a timeline
        self.timeline_slider = QSlider(Qt.Orientation.Horizontal)
        self.timeline_slider.setEnabled(False)
        self.timeline_slider.valueChanged.connect(self.update_views_from_timeline) 
        self.timeline_slider.sliderReleased.connect(self.update_plot_cursors_on_release) 

        self.timestamp_label = QLabel("Timestamp: --:--:--.---"); self.timestamp_label.setFixedWidth(180)
        self.btn_set_timestamp = QPushButton("Definir 🕒")
        self.btn_set_timestamp.setToolTip("Definir timestamp manualmente"); self.btn_set_timestamp.setFixedWidth(80)
        self.btn_set_timestamp.clicked.connect(self.set_timestamp_manually)
        self.btn_set_timestamp.setEnabled(False)

        # Adiciona os widgets ao layout da timeline
        timeline_layout.addWidget(self.timeline_slider) # Slider ocupa a maior parte
        timeline_layout.addWidget(self.btn_set_timestamp)
        timeline_layout.addWidget(self.timestamp_label)

        # Adiciona o layout da timeline ao layout principal (vertical) que foi passado
        parent_layout.addLayout(timeline_layout)

    def open_log_directories(self):
        root_path = QFileDialog.getExistingDirectory(
            self, "Seleciona a PASTA que tem as pastas dos .logs. É so isso mano, você consegue"
        )
        if not root_path:
            return

        self._clear_all_data()
        self.btn_open.setEnabled(False)

        self.setWindowTitle("Carregando Logs... (～￣▽￣)～") # Muda título
        self.statusBar().showMessage("Calma ai deixa eu ver se tem log mesmo aqui na pasta..")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Dando uma olhada... %p%")
        self.status_log_output.clear()
        self.loading_status_widget.show() # Mostra barra e área de texto
        QApplication.processEvents() # Força a UI a atualizar

        self.loading_widget.start_animation()
        self.loading_widget.open()        

        self.thread = QThread(); self.worker = LogProcessingWorker(root_path)
        self.worker.moveToThread(self.thread); self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_loading_finished); self.worker.error.connect(self.on_loading_error)
        
        self.worker.progress.connect(self.on_loading_progress) 
        self.worker.log_loaded.connect(self.on_log_item_loaded) # Conecta ao novo slot
        
        self.worker.finished.connect(self.thread.quit); self.worker.finished.connect(self.worker.deleteLater); self.thread.finished.connect(self.thread.deleteLater)
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
            QMessageBox.information(self, "NUM TEM Log", "Você que fez errado, lê direito vei, É a pasta que tem as pastas de .log")
            self.statusBar().showMessage("NAO TEM LOGGGGG AAAAAA", 5000)
            self.btn_open.setEnabled(True)
            return

        self.log_data = loaded_logs
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
        
        QMessageBox.critical(self, "Não consigo ler :( help", error_message)
        self.statusBar().showMessage("Etaporra deu ruim em carregar os logs", 5000)
        #self.btn_open.setEnabled(True)

    def _clear_all_data(self):
        self.map_is_ready = False
        self.log_data.clear()
        self.df = pd.DataFrame()
        self.current_log_name = ""
        self.log_selector_combo.blockSignals(True)
        self.log_selector_combo.clear()
        self.log_selector_combo.blockSignals(False)
        self.log_selector_combo.setEnabled(False)
        self.btn_save_pdf.setEnabled(False)

        if self.view_toggle_checkbox:
            self.view_toggle_checkbox.blockSignals(True)
            self.view_toggle_checkbox.setChecked(False)
            self.view_toggle_checkbox.setEnabled(False)
            self.view_toggle_checkbox.blockSignals(False)

        if self.map_stack:
            self.map_stack.setCurrentWidget(self.mapWidget)

        self.cleanup_cesium_html()
        self.cesium_state = None
        self.cesium_ready = False
        self.cesium_start_timestamp = None

        if self.standard_plots_tab: self.standard_plots_tab.load_dataframe(pd.DataFrame())
        if self.custom_plot_tab: self.custom_plot_tab.reload_data({})
        if self.all_plots_tab: self.all_plots_tab.load_dataframe(pd.DataFrame())

        self.mapWidget.setHtml("")
        self.setup_timeline()

    def _on_log_selected(self, log_name):
        if not log_name or log_name not in self.log_data: return
        self.current_log_name = log_name
        self.df = self.log_data[log_name]

        if self.standard_plots_tab: self.standard_plots_tab.load_dataframe(self.df, self.current_log_name)
        if self.all_plots_tab: self.all_plots_tab.load_dataframe(self.df)
        # O custom_plot_tab já recebe todos os logs no on_loading_finished

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

        cesium_state = self.build_cesium_state_from_dataframe()
        if cesium_state:
            self.cesium_state = cesium_state
            self.view_toggle_checkbox.setEnabled(True)
        else:
            self.view_toggle_checkbox.setEnabled(False)

    # --- Funções do Mapa e Timeline ---
    
    def on_map_load_finished(self, ok):
        if ok:
            # ### ALTERAÇÃO SIMPLIFICADA ###
            # Define imediatamente como pronto. O JS cuidará da espera interna.
            self.map_is_ready = True
            #print("DEBUG: Carregamento HTML do mapa finalizado. JS cuidará da inicialização.")
            # Atualiza a posição inicial assim que possível
            self.update_views_from_timeline(self.timeline_slider.value())
        else:
            self.map_is_ready = False
            print("ERRO: VISHII deu ruim o HTML do mapa, HEEELP aaaaaaaa")

    def on_cesium_load_finished(self, ok):
        self.cesium_ready = bool(ok)
        if ok and not self.df.empty and self.cesium_start_timestamp is not None:
            try:
                current_ts = self.df['Timestamp'].iloc[self.timeline_slider.value()]
                self.sync_cesium_time(current_ts)
            except Exception:
                pass

    def on_view_toggle_changed(self, state):
        if self.view_toggle_checkbox is None:
            return
        checked = Qt.CheckState(state) == Qt.CheckState.Checked
        if checked:
            if not self.cesium_state:
                cesium_state = self.build_cesium_state_from_dataframe()
                if not cesium_state:
                    self.view_toggle_checkbox.blockSignals(True)
                    self.view_toggle_checkbox.setChecked(False)
                    self.view_toggle_checkbox.blockSignals(False)
                    QMessageBox.warning(self, "Viewer 3D", "Não foi possível preparar os dados para o viewer 3D.")
                    return
                self.cesium_state = cesium_state
            if not self.show_cesium_view():
                self.view_toggle_checkbox.blockSignals(True)
                self.view_toggle_checkbox.setChecked(False)
                self.view_toggle_checkbox.blockSignals(False)
                return
            self.map_stack.setCurrentWidget(self.cesiumWidget)
        else:
            self.map_stack.setCurrentWidget(self.mapWidget)

    def plot_map_route(self):
        if 'Latitude' not in self.df.columns or 'Longitude' not in self.df.columns:
            self.mapWidget.setHtml("<html><body><h1>Mas num tem dado GPS meu filho!!.</h1></body></html>"); return
        coords = self.df[['Latitude', 'Longitude']].dropna().values.tolist()
        if not coords:
            self.mapWidget.setHtml("<html><body><h1>WTF e essas Coordenadas GPS?? kkkkk</h1></body></html>"); return

        # --- Cria o mapa base ---
        map_center = self.df[['Latitude', 'Longitude']].mean().values.tolist()
        m = folium.Map(location=map_center, zoom_start=15)
        self.map_js_name = m.get_name() # Guarda o nome JS do mapa principal

        # --- Rota e marcadores de início/fim ---
        folium.PolyLine(coords, color="blue", weight=3, opacity=0.8).add_to(m)
        folium.Marker(location=coords[0], popup="Início", icon=folium.Icon(color="green")).add_to(m)
        folium.Marker(location=coords[-1], popup="Fim", icon=folium.Icon(color="red")).add_to(m)

        # --- Ícone do aviaum  ---
        icon_filename = 'aircraft.svg'
        port = self.map_server.get_port()
        icon_url = f"http://127.0.0.1:{port}/{icon_filename}"
        
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
            aircraft_icon = folium.DivIcon(html=aircraft_html, icon_anchor=icon_aircraft_anchor)
            aircraft_marker = folium.Marker(
                location=coords[0],
                icon=aircraft_icon,
                popup='Aeronave'
            )
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
        icon_wind_filename = 'seta.svg'
        icon_wind_url = f"http://127.0.0.1:{port}/{icon_wind_filename}"
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
            wind_icon = folium.DivIcon(html=wind_html, icon_size=icon_wind_size, icon_anchor=icon_wind_anchor)
            # Cria o marcador da seta NA MESMA POSIÇÃO INICIAL do avião (o offset é visual no HTML)
            wind_marker = folium.Marker(location=coords[0], icon=wind_icon, popup='Vento', interactive=False, keyboard=False)
            wind_marker.add_to(m); self.wind_marker_js_name = wind_marker.get_name()
            print(f"DEBUG: Marcador de vento criado. Nome JS: {self.wind_marker_js_name}")
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

        temp_dir = self.map_server.get_temp_dir()
        self.temp_map_file_path = os.path.join(temp_dir, f"map_{time.time()}.html")
        m.save(self.temp_map_file_path)
        map_filename = os.path.basename(self.temp_map_file_path)
        # port = self.map_server.get_port() # Já pegamos antes
        url_map_html = f"http://127.0.0.1:{port}/{map_filename}"
        self.map_is_ready = False
        self.mapWidget.load(QUrl(url_map_html))

    def cleanup_cesium_html(self):
        if self.cesium_current_html and os.path.exists(self.cesium_current_html):
            try:
                os.remove(self.cesium_current_html)
            except OSError:
                pass
        self.cesium_current_html = ""

    def ensure_cesium_assets(self):
        if self.cesium_assets_ready and os.path.isdir(self.cesium_dist_path):
            return True
        project_root = os.path.dirname(os.path.abspath(__file__))
        dist_dir = os.path.join(os.path.dirname(project_root), 'UAVLogViewer', 'dist')
        if not os.path.isdir(dist_dir):
            QMessageBox.warning(self, "Viewer 3D", "Build do UAVLogViewer não encontrado. Execute npm run build em UAVLogViewer.")
            return False
        dest_dir = os.path.join(self.map_server.get_temp_dir(), 'cesium_dist')
        try:
            if os.path.isdir(dest_dir):
                shutil.rmtree(dest_dir)
            shutil.copytree(dist_dir, dest_dir)
        except Exception as exc:
            QMessageBox.warning(self, "Viewer 3D", f"Erro ao preparar assets do Cesium: {exc}")
            return False
        self.cesium_dist_path = dest_dir
        self.cesium_assets_ready = True
        return True

    def render_cesium_html(self, state_data):
        if not self.ensure_cesium_assets():
            return ""
        index_path = os.path.join(self.cesium_dist_path, 'index.html')
        if not os.path.exists(index_path):
            return ""
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                html = f.read()
            payload = json.dumps(state_data)
            injection = f"<script>window.__UAVLOGVIEWER_PRELOADED_STATE__ = {payload};</script>"
            insert_at = html.find('<script')
            if insert_at != -1:
                html = html[:insert_at] + injection + '\n' + html[insert_at:]
            else:
                html = html + injection
            output_name = f"cesium_view_{int(time.time()*1000)}.html"
            output_path = os.path.join(self.map_server.get_temp_dir(), output_name)
            with open(output_path, 'w', encoding='utf-8') as out:
                out.write(html)
            return output_path
        except Exception as exc:
            QMessageBox.warning(self, "Viewer 3D", f"Erro ao gerar HTML do Cesium: {exc}")
            return ""

    def show_cesium_view(self):
        if not self.cesium_state:
            return False
        html_path = self.render_cesium_html(self.cesium_state)
        if not html_path:
            return False
        self.cleanup_cesium_html()
        self.cesium_current_html = html_path
        port = self.map_server.get_port()
        url = QUrl(f"http://127.0.0.1:{port}/{os.path.basename(html_path)}")
        self.cesium_ready = False
        self.cesiumWidget.load(url)
        return True

    def build_cesium_state_from_dataframe(self):
        if self.df.empty:
            return None
        required_cols = {'Timestamp', 'Latitude', 'Longitude'}
        if not required_cols.issubset(set(self.df.columns)):
            return None
        altitude_column = 'AltitudeAbs' if 'AltitudeAbs' in self.df.columns else 'Altitude'
        if altitude_column not in self.df.columns:
            return None

        columns = ['Timestamp', 'Latitude', 'Longitude', altitude_column]
        for axis in ['Roll', 'Pitch', 'Yaw']:
            if axis in self.df.columns:
                columns.append(axis)

        df = self.df[columns].dropna(subset=['Timestamp', 'Latitude', 'Longitude', altitude_column]).copy()
        if df.empty:
            return None

        df.sort_values('Timestamp', inplace=True)
        self.cesium_start_timestamp = None
        try:
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        except Exception:
            return None

        start_row = df.iloc[0]
        self.cesium_start_timestamp = start_row['Timestamp']
        start_altitude = float(start_row[altitude_column])

        trajectory = []
        time_trajectory = {}
        time_attitude = {}

        roll_available = 'Roll' in df.columns
        pitch_available = 'Pitch' in df.columns
        yaw_available = 'Yaw' in df.columns

        for _, row in df.iterrows():
            timestamp = row['Timestamp']
            lat = float(row['Latitude'])
            lon = float(row['Longitude'])
            alt = float(row[altitude_column])
            delta_ms = int((timestamp - self.cesium_start_timestamp).total_seconds() * 1000)
            altitude_rel = alt - start_altitude
            trajectory.append([lon, lat, altitude_rel, delta_ms])
            time_trajectory[delta_ms] = [lon, lat, altitude_rel / 1000.0, delta_ms]

            if roll_available and pitch_available and yaw_available:
                roll = row.get('Roll', None)
                pitch = row.get('Pitch', None)
                yaw = row.get('Yaw', None)
                if pd.notna(roll) and pd.notna(pitch) and pd.notna(yaw):
                    time_attitude[delta_ms] = [
                        math.radians(float(roll)),
                        math.radians(float(pitch)),
                        math.radians(float(yaw))
                    ]

        if not trajectory:
            return None

        max_time = trajectory[-1][3]
        start_time_iso = self.cesium_start_timestamp.to_pydatetime().isoformat()

        state = {
            'externalDataInjected': True,
            'mapAvailable': True,
            'showMap': True,
            'mapLoading': False,
            'trajectorySources': ['python'],
            'trajectorySource': 'python',
            'trajectories': {
                'python': {
                    'trajectory': trajectory,
                    'timeTrajectory': time_trajectory
                }
            },
            'currentTrajectory': trajectory,
            'timeTrajectory': time_trajectory,
            'timeAttitude': time_attitude,
            'timeAttitudeQ': {},
            'attitudeSources': {'eulers': ['python'], 'quaternions': []},
            'attitudeSource': 'python',
            'vehicle': 'plane',
            'metadata': {'startTime': start_time_iso},
            'flightModeChanges': [],
            'mission': [],
            'fences': [],
            'processDone': True,
            'processStatus': 'Processed!',
            'plotOn': False,
            'messageTypes': {},
            'messages': {},
            'events': [],
            'showTrajectory': True,
            'showClickableTrajectory': False,
            'showWaypoints': False,
            'heightOffset': 0.0,
            'modelScale': 10,
            'cameraType': 'follow',
            'isOnline': False,
            'timeRange': [0, max_time],
            'currentTime': 0,
            'namedFloats': []
        }
        return state

    def sync_cesium_time(self, timestamp):
        if not self.cesium_ready or self.cesium_start_timestamp is None:
            return
        try:
            ts = pd.to_datetime(timestamp)
        except Exception:
            return
        delta_ms = int((ts - self.cesium_start_timestamp).total_seconds() * 1000)
        if delta_ms < 0:
            delta_ms = 0
        js_code = f"if (window.__setExternalCesiumTime__) {{ window.__setExternalCesiumTime__({delta_ms}); }}"
        self.cesiumWidget.page().runJavaScript(js_code)


    def setup_timeline(self):
        if not self.df.empty:
            self.timeline_slider.setRange(0, len(self.df) - 1)
            self.timeline_slider.setValue(0)
            self.timeline_slider.setEnabled(True)
            self.btn_set_timestamp.setEnabled(True)
            self.btn_save_pdf.setEnabled(True)
        else:
            self.timeline_slider.setEnabled(False)
            self.btn_set_timestamp.setEnabled(False)
            self.btn_save_pdf.setEnabled(False)
            self.timestamp_label.setText("Timestamp: --:--:--.---")
            
    def update_views_from_timeline(self, index):
        if self.df.empty or index >= len(self.df): return
        data_row = self.df.iloc[index]
        timestamp = data_row['Timestamp']
        
        self.timestamp_label.setText(f"Timestamp: {timestamp.strftime('%H:%M:%S.%f')[:-3]}")
        
        if 'Latitude' in data_row and 'Longitude' in data_row:
            yaw = data_row.get('Yaw', 0)            # Pega Yaw, default 0
            lat = data_row.get('Latitude')          # Pega a lat
            lon = data_row.get('Longitude')         # Pega a long
            win = data_row.get('WindDirection', 0)  # Pega o windD
            wsi = data_row.get('WSI', 0)            # Pega o vento
            if not pd.notna(yaw): yaw = 0 # Trata NaN
            if not pd.notna(win): win = 0 # Trata NaN
            if not pd.notna(wsi): wsi = 0 # Trata NaN

            #print(f"DEBUG do YAW: {yaw}")

            self.update_aircraft_position(lat, lon, yaw, win, wsi)

        self.sync_cesium_time(timestamp)


    def update_plot_cursors_on_release(self):
        """Chamado quando o slider é SOLTO. Atualiza os cursores dos gráficos."""
        if self.df.empty: return
        
        index = self.timeline_slider.value()
        if index >= len(self.df): return # Segurança extra
            
        timestamp = self.df['Timestamp'].iloc[index]
        #print(f"DEBUG: Slider solto. Atualizando cursores dos gráficos para {timestamp}")

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

    def set_timestamp_manually(self):
        if self.df.empty: return
        current_ts_str = self.df['Timestamp'].iloc[self.timeline_slider.value()].strftime('%H:%M:%S.%f')[:-3]
        text, ok = QInputDialog.getText(self, "Definir Timestamp", "Digite (HH:MM:SS.mmm):", text=current_ts_str)
        if ok and text:
            try:
                date_part = self.df['Timestamp'].iloc[0].date()
                time_part = pd.to_datetime(text, format='%H:%M:%S.%f').time()
                target_timestamp = pd.Timestamp.combine(date_part, time_part)
                closest_index = (self.df['Timestamp'] - target_timestamp).abs().idxmin()
                
                # Move o slider (isso vai disparar update_views_from_timeline para label e mapa)
                self.timeline_slider.setValue(closest_index) 
                
                # ### ALTERADO ### Chama explicitamente a função de atualizar os gráficos
                # Precisamos disso aqui porque setValue não dispara sliderReleased
                self.update_plot_cursors_on_release() 
                
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