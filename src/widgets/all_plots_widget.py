# all_plots_widget.py — Tema branco + legendas completas + sync X com debounce
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QCheckBox, QGridLayout, QHBoxLayout,
    QPushButton, QDialog, QDialogButtonBox, QToolButton
)
from PyQt6.QtCore import Qt, QTimer
import pandas as pd
import numpy as np
import io
from itertools import cycle
from datetime import datetime

import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter

from src.utils.config_manager import load_config, update_config_section
from src.utils.mode_utils import ModeSegment, compute_mode_segments

# ---- Compat/performance + TEMA BRANCO
pg.setConfigOptions(
    antialias=False,
    useOpenGL=False,
    background='w',   # fundo branco
    foreground='k'    # textos/linhas padrão pretos
)


class DateAxisItem(pg.AxisItem):
    """Eixo X que formata timestamps (segundos desde epoch) como HH:MM:SS."""
    def tickStrings(self, values, scale, spacing):
        out = []
        for v in values:
            try:
                out.append(datetime.fromtimestamp(float(v)).strftime('%H:%M:%S'))
            except Exception:
                out.append('')
        return out


class GraphMenuDialog(QDialog):
    def __init__(self, titles: list[str], current_state: dict[str, bool], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gráficos visíveis")
        self._titles = titles
        self._checkboxes: dict[str, QCheckBox] = {}
        grid_layout = QGridLayout()
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setHorizontalSpacing(12)
        grid_layout.setVerticalSpacing(6)
        columns = 10
        for idx, title in enumerate(titles):
            cb = QCheckBox(title)
            cb.setChecked(current_state.get(title, True))
            self._checkboxes[title] = cb
            row = idx // columns
            col = idx % columns
            grid_layout.addWidget(cb, row, col)

        root_layout = QVBoxLayout(self)
        root_layout.addLayout(grid_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root_layout.addWidget(buttons)

    def get_states(self) -> dict[str, bool]:
        return {title: cb.isChecked() for title, cb in self._checkboxes.items()}


class CollapsibleSection(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.toggle_button = QToolButton(checkable=True, checked=True)
        self.toggle_button.setArrowType(Qt.ArrowType.DownArrow)
        self.toggle_button.toggled.connect(self._on_toggled)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight: 600;")

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)
        header_layout.addWidget(self.toggle_button, 0, Qt.AlignmentFlag.AlignLeft)
        header_layout.addWidget(self.title_label, 1, Qt.AlignmentFlag.AlignVCenter)

        self.content_area = QWidget()
        self.content_area.setVisible(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(header_layout)
        layout.addWidget(self.content_area)

    def setContentLayout(self, content_layout: QVBoxLayout):
        self.content_area.setLayout(content_layout)

    def _on_toggled(self, checked: bool):
        self.toggle_button.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        self.content_area.setVisible(checked)

class AllPlotsWidget(QWidget):
    """
    Visualização rolável de múltiplos gráficos (PyQtGraph):
      - PlotDataItem com clipToView + autoDownsample('peak')
      - Degrau 'steps-post' sem stepMode (expand vetores)
      - Eixo secundário via ViewBox à direita
      - Cursor vertical (InfiniteLine)
      - Tema branco (background='w', foreground='k')
      - Sincronismo X apenas após soltar o mouse (debounce por QTimer)
      - Legendas completas (primário e secundário)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.df = pd.DataFrame()
        self.axes_list = []     # ViewBoxes para sync do eixo X
        self.vlines = []        # InfiniteLines (cursor) por gráfico
        self._syncing = False
        self._plot_widgets = []
        self.current_log_name = ""
        self.current_log_type = ""
        self._mode_segments: list[ModeSegment] = []
        self._config = load_config()
        self._legend_widget = None
        self._available_graph_titles: list[str] = []
        self._pending_df = pd.DataFrame()
        self._pending_log_name = ""
        self._pending_log_type = ""
        self._plots_dirty = False
        self._group_definitions: list[dict] = []
        self._sidebar_sections: dict[str, dict] = {}

        # Timer de debounce para sincronizar X
        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.setInterval(120)  # ms
        self._sync_timer.timeout.connect(self._sync_do_broadcast)
        self._pending_source_vb = None

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(10)

        # Painel lateral de seleção
        sidebar_container = QWidget()
        sidebar_container.setMinimumWidth(320)
        sidebar_container.setMaximumWidth(380)
        sidebar_layout = QVBoxLayout(sidebar_container)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(8)

        buttons_row = QHBoxLayout()
        self.btn_plot_all = QPushButton("Plotar todos")
        self.btn_plot_all.clicked.connect(self._plot_all_graphs)
        self.btn_clear_all = QPushButton("Remover todos")
        self.btn_clear_all.clicked.connect(self._clear_all_graphs)
        buttons_row.addWidget(self.btn_plot_all)
        buttons_row.addWidget(self.btn_clear_all)
        sidebar_layout.addLayout(buttons_row)

        self.groups_area = QScrollArea()
        self.groups_area.setWidgetResizable(True)
        self.groups_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        groups_content = QWidget()
        self.groups_layout = QVBoxLayout(groups_content)
        self.groups_layout.setContentsMargins(0, 0, 0, 0)
        self.groups_layout.setSpacing(8)
        self.groups_area.setWidget(groups_content)
        sidebar_layout.addWidget(self.groups_area, 1)

        main_layout.addWidget(sidebar_container, 0)

        # Área de gráficos
        plots_container = QWidget()
        plots_layout = QVBoxLayout(plots_container)
        plots_layout.setContentsMargins(0, 0, 0, 0)
        plots_layout.setSpacing(6)

        header_container = QWidget()
        header_container.setMaximumHeight(120)
        header_layout = QVBoxLayout(header_container)
        header_layout.setContentsMargins(0, 0, 0, 8)

        self.legend_holder = QVBoxLayout()
        self.legend_holder.setContentsMargins(0, 0, 0, 0)
        header_layout.addLayout(self.legend_holder)

        plots_layout.addWidget(header_container)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("background-color: white; border: none;")
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        plots_layout.addWidget(scroll_area)

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: white;")
        self.plots_layout = QVBoxLayout(scroll_content)
        scroll_area.setWidget(scroll_content)

        main_layout.addWidget(plots_container, 1)

    # ========== API pública ==========
    def load_dataframe(self, df: pd.DataFrame, log_name: str = "", log_type: str = ""):
        self._pending_df = df
        self._pending_log_name = log_name or ""
        self._pending_log_type = log_type or ""
        self._plots_dirty = True
        if self.isVisible():
            self._apply_pending_update()

    def ensure_ready(self):
        self._apply_pending_update()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_pending_update()

    def update_cursor(self, timestamp):
        if self.df.empty or not self.vlines:
            return
        ts = self._to_epoch_seconds(timestamp)
        for vline in self.vlines:
            vline.setValue(ts)
            vline.show()

    def set_time_window(self, start_ts, end_ts):
        if not self.axes_list:
            return
        start_val = self._to_epoch_seconds(start_ts)
        end_val = self._to_epoch_seconds(end_ts)
        if start_val is None or end_val is None:
            return
        self._sync_timer.stop()
        self._syncing = True
        try:
            for vb in self.axes_list:
                try:
                    vb.setXRange(start_val, end_val, padding=0)
                except Exception:
                    pass
        finally:
            self._syncing = False
        # reinicia o debounce para futuras interações do usuário
        self._sync_timer.start()

    def get_plot_images(self):
        images = []
        for plotw in self._plot_widgets:
            exporter = ImageExporter(plotw.plotItem)
            data = exporter.export(toBytes=True)
            buf = io.BytesIO()
            buf.write(data)
            buf.seek(0)
            images.append(buf)
        return images

    # ========== Internos ==========
    def _ensure_right_border(self, plot_item: pg.PlotItem, *,
                             has_secondary: bool,
                             right_label: str | None,
                             width_px: int = 64):
        """
        Garante uma 'borda' direita fixa (largura) para alinhar todos os gráficos.
        - Se has_secondary=True: mantém eixo direito normal (com label e ticks) e largura fixa
        - Se has_secondary=False: mostra eixo direito mas sem valores (apenas a borda), mantendo a largura
        """
        plot_item.showAxis('right')
        right_axis = plot_item.getAxis('right')

        # Largura fixa (padroniza a borda direita entre todos os gráficos)
        try:
            right_axis.setWidth(width_px)
        except Exception:
            # versões antigas: tenta pelo layout (fallback suave)
            try:
                # coluna 3 costuma ser o eixo direito no layout do PlotItem
                plot_item.layout.setColumnFixedWidth(3, width_px)
            except Exception:
                pass

        if has_secondary:
            # Eixo direito ativo (com label e valores)
            if right_label:
                right_axis.setLabel(right_label)
            right_axis.setStyle(showValues=True, tickLength=5)
        else:
            # Eixo direito “mudo”: desenha a linha, mas sem números/ticks
            right_axis.setStyle(showValues=False, tickLength=0)
            # um leve traço para a borda (opcional; com tema branco fica sutil)
            right_axis.setPen(pg.mkPen(150, 150, 150, 120))

    def _clear_plots(self):
        while self.plots_layout.count():
            item = self.plots_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.axes_list.clear()
        self.vlines.clear()
        self._plot_widgets.clear()
        self._mode_segments = []
        self._clear_legend()

    def _update_plots(self):
        self._clear_plots()

        df_plot = self.df.copy()
        if not df_plot.empty and 'Timestamp' in df_plot.columns:
            df_plot['_ts_'] = df_plot['Timestamp'].map(self._to_epoch_seconds)
        else:
            df_plot['_ts_'] = pd.Series(dtype=float)

        self._prepare_groups(df_plot)

        if self.df.empty:
            self._create_info_label("Carregue um arquivo de log para ver os gráficos.")
            return

        if 'Timestamp' not in self.df.columns:
            self._create_info_label("Coluna 'Timestamp' não encontrada no DataFrame.")
            return

        if self._should_render_mode_regions():
            self._mode_segments = compute_mode_segments(df_plot)
        else:
            self._mode_segments = []
        if self._mode_segments:
            self._add_mode_legend()
        else:
            self._clear_legend()

        graphs_added = False

        for group in self._group_definitions:
            plots = group.get('plots', [])
            if not plots:
                continue
            group_header_added = False
            for config in plots:
                if not self._is_graph_enabled(config['title']):
                    continue
                plotted = self._create_plot_from_config(config, df_plot)
                if plotted:
                    if not group_header_added:
                        self._add_group_header(group['title'])
                        group_header_added = True
                    graphs_added = True
            if group_header_added:
                self.plots_layout.addSpacing(4)

        if graphs_added:
            self.plots_layout.addStretch(1)
            self._sync_x_axes()
            self._add_vlines(df_plot)
        else:
            self._create_info_label("Nenhum dado numérico disponível para plotar.")

    def _create_info_label(self, text):
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: gray; font-size: 14px;")
        self.plots_layout.addWidget(label)

    def _add_group_header(self, title: str):
        header = QLabel(title)
        header.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        header.setStyleSheet("font-size: 14px; font-weight: 700; padding: 6px 0px 2px 0px;")
        self.plots_layout.addWidget(header)

    def _rebuild_sidebar(self):
        if not hasattr(self, 'groups_layout'):
            return
        while self.groups_layout.count():
            item = self.groups_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._sidebar_sections.clear()

        for group in self._group_definitions:
            plots = group.get('plots', [])
            if not plots:
                continue
            section = CollapsibleSection(group.get('title', ''))
            content_layout = QVBoxLayout()
            content_layout.setContentsMargins(4, 4, 4, 4)
            content_layout.setSpacing(6)

            actions_row = QHBoxLayout()
            plot_btn = QPushButton("Plotar grupo")
            plot_btn.setMinimumHeight(26)
            plot_btn.clicked.connect(lambda _, key=group.get('key'): self._plot_group(key))
            clear_btn = QPushButton("Limpar grupo")
            clear_btn.setMinimumHeight(26)
            clear_btn.clicked.connect(lambda _, key=group.get('key'): self._clear_group(key))
            actions_row.addWidget(plot_btn)
            actions_row.addWidget(clear_btn)
            content_layout.addLayout(actions_row)

            checkboxes = {}
            for cfg in plots:
                title = cfg['title']
                cb = QCheckBox(title)
                cb.setChecked(self._is_graph_enabled(title))
                cb.stateChanged.connect(lambda state, t=title: self._on_graph_checkbox_toggled(t, state))
                content_layout.addWidget(cb)
                checkboxes[title] = cb

            content_layout.addStretch(1)
            section.setContentLayout(content_layout)
            self.groups_layout.addWidget(section)
            self._sidebar_sections[group.get('key', group.get('title', ''))] = {
                'section': section,
                'checkboxes': checkboxes,
            }

        self.groups_layout.addStretch(1)

    def _apply_bulk_graph_state(self, updates: dict[str, bool]):
        if not updates:
            return
        states = self.get_graph_states()
        states.update(updates)
        self.apply_graph_visibility(states)
        self._sync_sidebar_states()

    def _on_graph_checkbox_toggled(self, title: str, state):
        enabled = Qt.CheckState(state) == Qt.CheckState.Checked
        self._apply_bulk_graph_state({title: enabled})

    def _plot_group(self, group_key: str | None):
        group = next((g for g in self._group_definitions if g.get('key') == group_key), None)
        if not group:
            return
        updates = {cfg['title']: True for cfg in group.get('plots', [])}
        self._apply_bulk_graph_state(updates)

    def _clear_group(self, group_key: str | None):
        group = next((g for g in self._group_definitions if g.get('key') == group_key), None)
        if not group:
            return
        updates = {cfg['title']: False for cfg in group.get('plots', [])}
        self._apply_bulk_graph_state(updates)

    def _plot_all_graphs(self):
        updates = {cfg['title']: True for grp in self._group_definitions for cfg in grp.get('plots', [])}
        self._apply_bulk_graph_state(updates)

    def _clear_all_graphs(self):
        updates = {cfg['title']: False for grp in self._group_definitions for cfg in grp.get('plots', [])}
        self._apply_bulk_graph_state(updates)

    def _sync_sidebar_states(self):
        states = self.get_graph_states()
        for section in self._sidebar_sections.values():
            for title, cb in section.get('checkboxes', {}).items():
                desired = states.get(title, True)
                if cb.isChecked() != desired:
                    cb.blockSignals(True)
                    cb.setChecked(desired)
                    cb.blockSignals(False)

    # ---------- Configuração de gráficos ----------
    def _register_graph_titles(self, titles: list[str]):
        graph_cfg = self._config.get('graphs', {}) if isinstance(self._config, dict) else {}
        changed = False
        for title in titles:
            if title not in graph_cfg:
                graph_cfg[title] = True
                changed = True
        self._available_graph_titles = sorted(set(self._available_graph_titles + titles))
        if changed:
            self._config = update_config_section('graphs', graph_cfg)

    def _is_graph_enabled(self, title: str) -> bool:
        graphs = self._config.get('graphs', {}) if isinstance(self._config, dict) else {}
        if title not in graphs:
            self._register_graph_titles([title])
        return graphs.get(title, True)

    def get_available_graph_titles(self) -> list[str]:
        return list(self._available_graph_titles)

    def get_graph_states(self) -> dict[str, bool]:
        graphs = self._config.get('graphs', {}) if isinstance(self._config, dict) else {}
        return graphs if isinstance(graphs, dict) else {}

    def apply_graph_visibility(self, states: dict[str, bool]):
        if not isinstance(states, dict):
            return
        self._config = update_config_section('graphs', states)
        if self._pending_df is None or self._pending_df.empty:
            self._pending_df = self.df
            self._pending_log_name = self.current_log_name
            self._pending_log_type = self.current_log_type
        self._plots_dirty = True
        if self.isVisible():
            self._apply_pending_update()
        self._sync_sidebar_states()

    def _create_placeholder_plot(self, title):
        plotw = pg.PlotWidget(axisItems={'bottom': DateAxisItem(orientation='bottom')})
        plotw.setMinimumHeight(150)
        plotw.setTitle(self._format_plot_title(title))
        txt = pg.TextItem(f"Dados para '{title}' não disponíveis.", anchor=(0.5, 0.5), color=(120, 120, 120))
        plotw.addItem(txt)
        vb = plotw.getPlotItem().getViewBox()
        vb.setRange(xRange=(0, 1), yRange=(0, 1), disableAutoRange=True)
        txt.setPos(0.5, 0.5)
        self.plots_layout.addWidget(plotw)

    def _apply_pending_update(self):
        if not self._plots_dirty:
            return
        self.df = self._pending_df
        self.current_log_name = self._pending_log_name
        self.current_log_type = self._pending_log_type
        self._plots_dirty = False
        self._update_plots()

    def _build_remaining_configs(self, columns, df_plot):
        grouped = {}
        friendly_titles = {}

        for col in columns:
            key, friendly = self._normalize_axis_group(col)
            grouped.setdefault(key, []).append(col)
            friendly_titles.setdefault(key, friendly)

        configs = []
        for key, cols in grouped.items():
            valid_cols = [c for c in cols if c in df_plot.columns and not df_plot[c].isnull().all()]
            if not valid_cols:
                continue

            if len(valid_cols) == 1:
                title = valid_cols[0]
            else:
                title = friendly_titles.get(key, key)

            configs.append({
                'title': title,
                'primary_y': {
                    'cols': valid_cols,
                    'label': title
                }
            })

        return configs

    def _prepare_groups(self, df_plot: pd.DataFrame):
        base_groups = [
            {
                'key': 'navegacao',
                'title': 'Navegação',
                'plots': [
                    {'title': 'Atitude da Aeronave', 'primary_y': {'cols': ['Roll', 'Pitch', 'Yaw'], 'label': 'Graus (°)'}},
                    {'title': 'Altitude e Velocidade Vertical', 'primary_y': {'cols': ['AltitudeAbs', 'QNE'], 'label': 'Altitude (m)'},
                     'secondary_y': {'cols': ['VSI'], 'label': 'Vel. Vertical (m/s)'}},
                    {'title': 'Dados de Voo (Air Data)', 'primary_y': {'cols': ['ASI', 'WSI'], 'label': 'Velocidade (m/s)'},
                     'secondary_y': {'cols': ['WindDirection'], 'label': 'Direção do Vento (°)'}},
                ]
            },
            {
                'key': 'gnss',
                'title': 'GNSS',
                'plots': [
                    {'title': 'Status do Receptor GNSS', 'primary_y': {'cols': ['Satellites', 'Sat_use'], 'label': 'Contagem'},
                     'secondary_y': {'cols': ['RTK_Status'], 'label': 'Status RTK'}}
                ]
            },
            {
                'key': 'sistema',
                'title': 'Sistema',
                'plots': [
                    {'title': 'Status e Alertas do Sistema',
                     'primary_y': {'cols': ['IsFlying', 'isVTOL', 'ModoVoo', 'Spoofing', 'Jamming'], 'label': 'Estado (On/Off)', 'style': 'steps-post'}},
                    {'title': 'Energia do Sistema', 'primary_y': {'cols': ['Voltage', 'VTOL_vbat', 'Filt_VDC'], 'label': 'Tensão (V)'},
                     'secondary_y': {'cols': ['Porcent_bat'], 'label': 'Bateria (%)'}},
                ]
            },
            {
                'key': 'atuadores',
                'title': 'Atuadores',
                'plots': [
                    {'title': 'Comandos dos Atuadores', 'primary_y': {'cols': ['Elevator', 'Aileron', 'AileronR', 'AileronL'], 'label': 'Comando'}},
                ]
            },
            {
                'key': 'motor',
                'title': 'Motor',
                'plots': [
                    {'title': 'Motor', 'primary_y': {'cols': ['RPM'], 'label': 'RPM'},
                     'secondary_y': {'cols': ['CHT'], 'label': 'Temperatura (°C)'}},
                ]
            },
        ]

        used_cols = self._collect_used_columns(base_groups)
        numeric_cols = []
        if not df_plot.empty:
            numeric_cols = [c for c in df_plot.select_dtypes(include=np.number).columns
                            if c not in ('_ts_',) and 'Timestamp' not in c]

        remaining_cols = [c for c in numeric_cols if c not in used_cols]
        grouped_configs = self._build_remaining_configs(remaining_cols, df_plot)
        if grouped_configs:
            base_groups.append({
                'key': 'outros',
                'title': 'Outros dados',
                'plots': grouped_configs
            })

        self._group_definitions = base_groups
        all_titles = [cfg['title'] for grp in self._group_definitions for cfg in grp.get('plots', [])]
        self._available_graph_titles = sorted(set(all_titles))
        self._register_graph_titles(all_titles)
        self._rebuild_sidebar()

    @staticmethod
    def _collect_used_columns(groups: list[dict]) -> set[str]:
        used = set()
        for group in groups:
            for config in group.get('plots', []):
                if 'primary_y' in config:
                    used.update(config['primary_y'].get('cols', []))
                if 'secondary_y' in config:
                    used.update(config['secondary_y'].get('cols', []))
        return used

    @staticmethod
    def _normalize_axis_group(column_name: str):
        tokens = ['_x_', '_y_', '_z_', '_X_', '_Y_', '_Z_']
        suffixes = ['_x', '_y', '_z', '_X', '_Y', '_Z']
        normalized = column_name
        replaced = False

        for token in tokens:
            if token in column_name:
                normalized = column_name.replace(token, '_axis_')
                replaced = True
                break

        if not replaced:
            for suffix in suffixes:
                if column_name.endswith(suffix):
                    normalized = column_name[: -len(suffix)] + '_axis'
                    replaced = True
                    break

        if replaced:
            friendly = normalized.replace('_axis_', '_XYZ_').replace('_axis', '_XYZ')
        else:
            friendly = column_name

        return normalized, friendly

    def _create_plot_from_config(self, config, df_plot):
        primary_series = []
        secondary_series = []
        plotted_cols = set()

        if 'primary_y' in config:
            pconf = config['primary_y']
            step_mode_flag = True if pconf.get('style', '') == 'steps-post' else False
            for col in pconf['cols']:
                if col in df_plot.columns and not df_plot[col].isnull().all():
                    valid = df_plot[['_ts_', col]].dropna()
                    if not valid.empty:
                        primary_series.append((col, valid, step_mode_flag))
                        plotted_cols.add(col)

        if 'secondary_y' in config:
            sconf = config['secondary_y']
            step_mode_sec_flag = True if sconf.get('style', '') == 'steps-post' else False
            for col in sconf['cols']:
                if col in df_plot.columns and not df_plot[col].isnull().all():
                    valid = df_plot[['_ts_', col]].dropna()
                    if not valid.empty:
                        secondary_series.append((col, valid, step_mode_sec_flag))
                        plotted_cols.add(col)

        if not primary_series and not secondary_series:
            return set()

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 10)

        plotw = pg.PlotWidget(axisItems={'bottom': DateAxisItem(orientation='bottom')})
        plotw.setMinimumHeight(216)
        plot_item = plotw.getPlotItem()
        plotw.setTitle(self._format_plot_title(config['title']))
        plot_item.showGrid(x=True, y=True, alpha=0.3)
        plot_item.enableAutoRange(x=True, y=True)

        has_secondary = bool(secondary_series)
        right_label = config.get('secondary_y', {}).get('label') if has_secondary else None
        self._ensure_right_border(plot_item, has_secondary=has_secondary, right_label=right_label, width_px=64)

        colors = cycle([
            ( 33, 150, 243),
            (244,  67,  54),
            ( 76, 175,  80),
            (255, 193,   7),
            (156,  39, 176),
            (  0, 188, 212),
            (255,  87,  34),
            ( 96, 125, 139),
            (139, 195,  74),
            (121,  85,  72),
        ])

        legend_items = []

        if primary_series:
            pconf = config['primary_y']
            for col, valid, step_flag in primary_series:
                pen = pg.mkPen(color=next(colors), width=1.8)
                item = self._plot_series(
                    plot_item,
                    valid['_ts_'].to_numpy(),
                    valid[col].to_numpy(),
                    name=col,
                    pen=pen,
                    step_mode_flag=step_flag
                )
                legend_items.append((item, col))
            if pconf.get('label'):
                plot_item.getAxis('left').setLabel(pconf['label'])

        right_vb = None
        if secondary_series:
            right_vb = pg.ViewBox()
            plot_item.showAxis('right')
            plot_item.scene().addItem(right_vb)
            plot_item.getAxis('right').linkToView(right_vb)
            right_vb.setXLink(plot_item.vb)

            def update_right_vb():
                right_vb.setGeometry(plot_item.vb.sceneBoundingRect())
                right_vb.linkedViewChanged(plot_item.vb, right_vb.XAxis)

            plot_item.vb.sigResized.connect(update_right_vb)
            update_right_vb()

            for col, valid, step_flag in secondary_series:
                pen = pg.mkPen(color=next(colors), width=1.8)
                c = self._plot_series(
                    right_vb,
                    valid['_ts_'].to_numpy(),
                    valid[col].to_numpy(),
                    name=col,
                    pen=pen,
                    step_mode_flag=step_flag
                )
                legend_items.append((c, col))

            sconf = config['secondary_y']
            if sconf.get('label'):
                plot_item.getAxis('right').setLabel(sconf['label'])

        self._ensure_legend(plot_item, legend_items)

        self.axes_list.append(plot_item.vb)
        if right_vb:
            self.axes_list.append(right_vb)

        plot_item.getViewBox().setMouseEnabled(x=True, y=False)

        container_layout.addWidget(plotw)
        self._add_toggle_controls(container_layout, legend_items)
        self.plots_layout.addWidget(container)
        self._plot_widgets.append(plotw)

        self._add_mode_regions(plot_item)

        return plotted_cols

    def _format_plot_title(self, base_title: str) -> str:
        parts = [base_title]
        if self.current_log_name:
            parts.append(self.current_log_name)
        full_title = " - ".join(parts)
        return f"<span style='font-size:13px; font-weight:600;'>{full_title}</span>"

    # ---------- Legenda ----------
    def _ensure_legend(self, plot_item: pg.PlotItem, items):
        """
        Garante que haja uma legenda e registra todos os items (mesmo se já plotados).
        'items' é lista de tuplas (PlotDataItem, name).
        """
        if plot_item.legend is None:
            plot_item.addLegend()  # usa foreground/background globais (preto/branco)

        # limpa entradas duplicadas (opcional: mantém simples)
        # Re-adiciona explicitamente para garantir presença mesmo do eixo secundário
        for it, name in items:
            try:
                plot_item.legend.addItem(it, name)
            except Exception:
                pass  # se já estiver, ignora

    def _add_toggle_controls(self, container_layout, legend_items):
        """Cria checkboxes para mostrar/ocultar séries individualmente."""
        if not legend_items:
            return

        toggles_widget = QWidget()
        grid = QGridLayout(toggles_widget)
        grid.setContentsMargins(8, 0, 8, 8)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)

        added = 0
        for item, name in legend_items:
            if item is None or name is None:
                continue
            checkbox = QCheckBox(name)
            checkbox.setChecked(True)

            def _toggle(state, target=item):
                target.setVisible(Qt.CheckState(state) == Qt.CheckState.Checked)

            checkbox.stateChanged.connect(_toggle)
            grid.addWidget(checkbox, added // 3, added % 3)
            added += 1

        if added == 0:
            toggles_widget.deleteLater()
            return

        container_layout.addWidget(toggles_widget)

    # ---------- Sincronismo X com debounce ----------
    def _sync_x_axes(self):
        if not self.axes_list:
            return
        for vb in self.axes_list:
            vb.sigXRangeChanged.connect(self._on_xlim_changed_debounced)

    def _on_xlim_changed_debounced(self, vb, _=None):
        self._pending_source_vb = vb
        self._sync_timer.start()  # reinicia (debounce)

    def _sync_do_broadcast(self):
        if self._syncing or self._pending_source_vb is None:
            return
        src = self._pending_source_vb
        self._pending_source_vb = None

        self._syncing = True
        try:
            xmin, xmax = src.viewRange()[0]
            for other in self.axes_list:
                if other is src:
                    continue
                oxmin, oxmax = other.viewRange()[0]
                if (oxmin != xmin) or (oxmax != xmax):
                    other.setXRange(xmin, xmax, padding=0)
        finally:
            self._syncing = False

    def _add_vlines(self, df_plot):
        if df_plot.empty:
            return
        initial_ts = float(df_plot['_ts_'].iloc[0])
        for plotw in self._plot_widgets:
            line = pg.InfiniteLine(pos=initial_ts, angle=90, movable=False,
                                   pen=pg.mkPen((255, 0, 0), width=1))
            line.hide()
            plotw.addItem(line)
            self.vlines.append(line)

    # ---------- Faixas de modo de voo ----------
    def _should_render_mode_regions(self) -> bool:
        return 'xcockpit' not in (self.current_log_type or '').lower()

    def _add_mode_legend(self):
        if not self._mode_segments:
            self._clear_legend()
            return

        seen = set()
        unique_segments: list[ModeSegment] = []
        for seg in self._mode_segments:
            if seg.mode_value in seen:
                continue
            seen.add(seg.mode_value)
            unique_segments.append(seg)

        if not unique_segments:
            self._clear_legend()
            return

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(2, 0, 2, 4)
        layout.setSpacing(6)

        for seg in unique_segments:
            swatch = QLabel()
            swatch.setFixedSize(14, 14)
            swatch.setStyleSheet(
                f"background-color: rgb({seg.color[0]}, {seg.color[1]}, {seg.color[2]});"
                "border: 1px solid #666; border-radius: 2px;"
            )
            text = QLabel(seg.label)
            text.setStyleSheet("font-size: 11px; color: #333;")
            item = QWidget()
            item_layout = QHBoxLayout(item)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(4)
            item_layout.addWidget(swatch)
            item_layout.addWidget(text)
            layout.addWidget(item)

        layout.addStretch(1)
        self._set_legend_widget(container)

    def _add_mode_regions(self, plot_item: pg.PlotItem):
        if not self._mode_segments:
            return

        for seg in self._mode_segments:
            region = pg.LinearRegionItem(values=(seg.start, seg.end), brush=pg.mkBrush(*seg.color, 45), movable=False)
            region.setZValue(-10)
            plot_item.addItem(region)

    def _set_legend_widget(self, widget: QWidget):
        self._clear_legend()
        self._legend_widget = widget
        self.legend_holder.addWidget(widget)

    def _clear_legend(self):
        if self._legend_widget:
            self.legend_holder.removeWidget(self._legend_widget)
            self._legend_widget.deleteLater()
            self._legend_widget = None

    # ---------- Utilidades ----------
    @staticmethod
    def _to_epoch_seconds(ts):
        if isinstance(ts, (int, float, np.integer, np.floating)):
            return float(ts)
        try:
            if isinstance(ts, pd.Timestamp):
                return ts.to_datetime64().astype('datetime64[ns]').astype(np.int64) / 1e9
            return pd.Timestamp(ts).to_datetime64().astype('datetime64[ns]').astype(np.int64) / 1e9
        except Exception:
            return 0.0

    def _as_step_post_arrays(self, x: np.ndarray, y: np.ndarray):
        """Gera 'degrau' (steps-post) sem stepMode: len(xs)=len(ys)=2*N-1."""
        if x.size < 2 or y.size < 2:
            return x, y
        xs = np.empty(2 * x.size - 1, dtype=float)
        ys = np.empty(2 * y.size - 1, dtype=float)
        xs[0::2] = x
        xs[1::2] = x[1:]
        ys[0::2] = y
        ys[1::2] = y[:-1]
        return xs, ys

    def _plot_series(self, target, x, y, name, pen, step_mode_flag: bool):
        """
        target: PlotItem (primário) ou ViewBox (secundário).
        Adiciona o item ao alvo ANTES de setData() (evita autoRangeEnabled error).
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        if step_mode_flag:
            x, y = self._as_step_post_arrays(x, y)

        item = pg.PlotDataItem()  # sem dados ainda
        if isinstance(target, pg.PlotItem):
            target.addItem(item)
        else:
            target.addItem(item)  # ViewBox

        # configura dados + cor + otimizações
        item.setData(
            x=x, y=y,
            pen=pen,
            connect='all',
            clipToView=True,
            autoDownsample=True,
            downsampleMethod='peak',
            antialias=False,
            name=name
        )
        return item
