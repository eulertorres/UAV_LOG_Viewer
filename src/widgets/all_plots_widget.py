# all_plots_widget.py — Tema branco + legendas completas + sync X com debounce
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea, QCheckBox, QGridLayout, QHBoxLayout, QDoubleSpinBox
from PyQt6.QtCore import Qt, QTimer
import pandas as pd
import numpy as np
import io
from itertools import cycle
from datetime import datetime

import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter

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
        self.datalogger_df: pd.DataFrame | None = None
        self.current_log_name = ""
        self.datalogger_offset_sec: float = 0.0

        # Timer de debounce para sincronizar X
        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.setInterval(120)  # ms
        self._sync_timer.timeout.connect(self._sync_do_broadcast)
        self._pending_source_vb = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Controles superiores (offset do datalogger)
        self.datalogger_controls = QWidget()
        controls_layout = QHBoxLayout(self.datalogger_controls)
        controls_layout.setContentsMargins(4, 0, 4, 0)
        controls_layout.setSpacing(6)
        controls_layout.addWidget(QLabel("Offset do Datalogger (s):"))
        self.datalogger_offset_spin = QDoubleSpinBox()
        self.datalogger_offset_spin.setRange(-600.0, 600.0)
        self.datalogger_offset_spin.setDecimals(3)
        self.datalogger_offset_spin.setSingleStep(0.1)
        self.datalogger_offset_spin.setValue(self.datalogger_offset_sec)
        self.datalogger_offset_spin.valueChanged.connect(self._on_datalogger_offset_changed)
        controls_layout.addWidget(self.datalogger_offset_spin)
        controls_layout.addStretch(1)
        self.datalogger_controls.hide()
        main_layout.addWidget(self.datalogger_controls)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("background-color: white; border: none;")
        main_layout.addWidget(scroll_area)

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: white;")
        self.plots_layout = QVBoxLayout(scroll_content)
        scroll_area.setWidget(scroll_content)

    # ========== API pública ==========
    def load_dataframe(self, df: pd.DataFrame, log_name: str = "", datalogger_df: pd.DataFrame | None = None):
        self.df = df
        self.datalogger_df = datalogger_df if isinstance(datalogger_df, pd.DataFrame) else None
        self.current_log_name = log_name or ""
        self._update_datalogger_controls_visibility()
        self._update_plots()

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

    def _update_datalogger_controls_visibility(self):
        has_overlay = self.datalogger_df is not None and not self.datalogger_df.empty
        self.datalogger_controls.setVisible(bool(has_overlay))
        if not has_overlay:
            self.datalogger_offset_sec = 0.0
            self.datalogger_offset_spin.blockSignals(True)
            self.datalogger_offset_spin.setValue(self.datalogger_offset_sec)
            self.datalogger_offset_spin.blockSignals(False)

    def _on_datalogger_offset_changed(self, value: float):
        self.datalogger_offset_sec = float(value)
        # Recalcula gráficos com o deslocamento aplicado
        self._update_plots()

    def _update_plots(self):
        self._clear_plots()

        if self.df.empty:
            self._create_info_label("Carregue um arquivo de log para ver os gráficos.")
            return

        if 'Timestamp' not in self.df.columns:
            self._create_info_label("Coluna 'Timestamp' não encontrada no DataFrame.")
            return

        ts_epoch = self.df['Timestamp'].map(self._to_epoch_seconds)
        df_plot = self.df.copy()
        df_plot['_ts_'] = ts_epoch

        overlay_plot_df = None
        if self.datalogger_df is not None and not self.datalogger_df.empty and 'Timestamp' in self.datalogger_df.columns:
            overlay_plot_df = self.datalogger_df.copy()
            overlay_plot_df['_ts_'] = overlay_plot_df['Timestamp'].map(self._to_epoch_seconds) + self.datalogger_offset_sec

        aileron_overlays = []
        aileron_styles = {}
        aileron_secondary_label = None
        if overlay_plot_df is not None:
            if 'ServoL_PWM_us' in overlay_plot_df.columns:
                aileron_overlays.append({
                    'cols': ['ServoL_PWM_us'],
                    'df': overlay_plot_df,
                    'axis': 'secondary',
                    'pen': {'color': (33, 150, 243), 'width': 2.4},
                    'legend_prefix': 'Datalogger '
                })
                aileron_styles['AileronL'] = {'style': Qt.PenStyle.DashLine, 'width': 2.0, 'color': (33, 150, 243)}
                aileron_secondary_label = "PWM (µs)"
            if 'ServoR_PWM_us' in overlay_plot_df.columns:
                aileron_overlays.append({
                    'cols': ['ServoR_PWM_us'],
                    'df': overlay_plot_df,
                    'axis': 'secondary',
                    'pen': {'color': (244, 67, 54), 'width': 2.4},
                    'legend_prefix': 'Datalogger '
                })
                aileron_styles['AileronR'] = {'style': Qt.PenStyle.DashLine, 'width': 2.0, 'color': (244, 67, 54)}
                aileron_secondary_label = "PWM (µs)"
            if 'Aileron' in df_plot.columns:
                aileron_styles.setdefault('Aileron', {'style': Qt.PenStyle.DashLine, 'width': 2.0, 'color': (76, 175, 80)})
        else:
            # sem datalogger: ainda usamos estilos consistentes para os comandos
            aileron_styles.setdefault('AileronL', {'style': Qt.PenStyle.DashLine, 'width': 2.0, 'color': (33, 150, 243)})
            aileron_styles.setdefault('AileronR', {'style': Qt.PenStyle.DashLine, 'width': 2.0, 'color': (244, 67, 54)})
            aileron_styles.setdefault('Aileron', {'style': Qt.PenStyle.DashLine, 'width': 2.0, 'color': (76, 175, 80)})

        plotting_config = [
            {'title': 'Atitude da Aeronave', 'primary_y': {'cols': ['Roll', 'Pitch', 'Yaw'], 'label': 'Graus (°)'}},
            {'title': 'Altitude e Velocidade Vertical', 'primary_y': {'cols': ['AltitudeAbs', 'QNE'], 'label': 'Altitude (m)'},
             'secondary_y': {'cols': ['VSI'], 'label': 'Vel. Vertical (m/s)'}},
            {'title': 'Status e Alertas do Sistema',
             'primary_y': {'cols': ['IsFlying', 'isVTOL', 'ModoVoo', 'Spoofing', 'Jamming'], 'label': 'Estado (On/Off)', 'style': 'steps-post'}},
            {'title': 'Status do Receptor GNSS', 'primary_y': {'cols': ['Satellites', 'Sat_use'], 'label': 'Contagem'},
             'secondary_y': {'cols': ['RTK_Status'], 'label': 'Status RTK'}},
            {'title': 'Energia do Sistema', 'primary_y': {'cols': ['Voltage', 'VTOL_vbat', 'Filt_VDC'], 'label': 'Tensão (V)'},
             'secondary_y': {'cols': ['Porcent_bat'], 'label': 'Bateria (%)'}},
            {'title': 'Dados de Voo (Air Data)', 'primary_y': {'cols': ['ASI', 'WSI'], 'label': 'Velocidade (m/s)'},
             'secondary_y': {'cols': ['WindDirection'], 'label': 'Direção do Vento (°)'}},
            {'title': 'Comandos dos Atuadores',
             'primary_y': {'cols': ['Elevator', 'Aileron', 'AileronL', 'AileronR'], 'label': 'Comando'},
             'secondary_y': {'cols': [], 'label': aileron_secondary_label} if aileron_secondary_label else None,
             'overlays': aileron_overlays,
             'col_styles': aileron_styles},
            {'title': 'Motor', 'primary_y': {'cols': ['RPM'], 'label': 'RPM'},
             'secondary_y': {'cols': ['CHT'], 'label': 'Temperatura (°C)'}},
        ]

        plotted_cols = set()
        graphs_added = False

        for config in plotting_config:
            config_cols = []
            if 'primary_y' in config:
                config_cols.extend(config['primary_y']['cols'])
            if config.get('secondary_y'):
                config_cols.extend(config['secondary_y'].get('cols', []))

            plotted = self._create_plot_from_config(config, df_plot)
            if plotted:
                plotted_cols.update(plotted)
                graphs_added = True

        remaining_cols = [c for c in df_plot.select_dtypes(include=np.number).columns
                          if c not in plotted_cols and c not in ('_ts_',) and 'Timestamp' not in c]

        grouped_configs = self._build_remaining_configs(remaining_cols, df_plot)
        for config in grouped_configs:
            plotted = self._create_plot_from_config(config, df_plot)
            if plotted:
                graphs_added = True

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
        col_styles = config.get('col_styles', {}) if isinstance(config.get('col_styles'), dict) else {}

        def _append_series(target_list, column, source_df, step_flag, display_name=None, pen_override=None):
            if column in source_df.columns and not source_df[column].isnull().all():
                valid = source_df[['_ts_', column]].dropna()
                if not valid.empty:
                    target_list.append((display_name or column, valid, step_flag, pen_override, column))
                    plotted_cols.add(column)

        if 'primary_y' in config:
            pconf = config['primary_y']
            step_mode_flag = True if pconf.get('style', '') == 'steps-post' else False
            for col in pconf['cols']:
                _append_series(primary_series, col, df_plot, step_mode_flag)

        if 'secondary_y' in config:
            sconf = config['secondary_y']
            step_mode_sec_flag = True if sconf.get('style', '') == 'steps-post' else False
            for col in sconf['cols']:
                _append_series(secondary_series, col, df_plot, step_mode_sec_flag)

        overlays = config.get('overlays', []) if isinstance(config.get('overlays'), list) else []
        for overlay in overlays:
            if not overlay:
                continue
            source_df = overlay.get('df', df_plot)
            if source_df is None or source_df.empty:
                continue
            axis_target = overlay.get('axis', 'primary')
            cols = overlay.get('cols', [])
            pen_override = overlay.get('pen') or {}
            legend_prefix = overlay.get('legend_prefix', '') or ''
            step_flag = True if overlay.get('style', '') == 'steps-post' else False
            for col in cols:
                if col not in source_df.columns or source_df[col].isnull().all():
                    continue
                display = f"{legend_prefix}{col}" if legend_prefix else col
                _append_series(
                    secondary_series if axis_target == 'secondary' else primary_series,
                    col,
                    source_df,
                    step_flag,
                    display_name=display,
                    pen_override=pen_override
                )

        if not primary_series and not secondary_series:
            return set()

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 10)

        plotw = pg.PlotWidget(axisItems={'bottom': DateAxisItem(orientation='bottom')})
        plotw.setMinimumHeight(360)
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
            for series_entry in primary_series:
                col, valid, step_flag, pen_override, data_col = series_entry
                style = dict(col_styles.get(col, {})) if isinstance(col_styles, dict) else {}
                base_color = style.pop('color', next(colors))
                pen_kwargs = {'color': base_color, 'width': 1.8}
                if style:
                    pen_kwargs.update(style)
                if pen_override:
                    pen_kwargs.update(pen_override)
                pen = pg.mkPen(**pen_kwargs)
                item = self._plot_series(
                    plot_item,
                    valid['_ts_'].to_numpy(),
                    valid[data_col].to_numpy(),
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

            for series_entry in secondary_series:
                col, valid, step_flag, pen_override, data_col = series_entry
                style = dict(col_styles.get(col, {})) if isinstance(col_styles, dict) else {}
                base_color = style.pop('color', next(colors))
                pen_kwargs = {'color': base_color, 'width': 1.8}
                if style:
                    pen_kwargs.update(style)
                if pen_override:
                    pen_kwargs.update(pen_override)
                pen = pg.mkPen(**pen_kwargs)
                c = self._plot_series(
                    right_vb,
                    valid['_ts_'].to_numpy(),
                    valid[data_col].to_numpy(),
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
