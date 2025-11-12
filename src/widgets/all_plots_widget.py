# all_plots_widget.py — Tema branco + legendas completas + sync X com debounce
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea
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

        # Timer de debounce para sincronizar X
        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.setInterval(120)  # ms
        self._sync_timer.timeout.connect(self._sync_do_broadcast)
        self._pending_source_vb = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)

        scroll_content = QWidget()
        self.plots_layout = QVBoxLayout(scroll_content)
        scroll_area.setWidget(scroll_content)

    # ========== API pública ==========
    def load_dataframe(self, df: pd.DataFrame):
        self.df = df
        self._update_plots()

    def update_cursor(self, timestamp):
        if self.df.empty or not self.vlines:
            return
        ts = self._to_epoch_seconds(timestamp)
        for vline in self.vlines:
            vline.setValue(ts)
            vline.show()

    def get_plot_images(self):
        images = []
        for i in range(self.plots_layout.count()):
            widget = self.plots_layout.itemAt(i).widget()
            if isinstance(widget, pg.PlotWidget):
                exporter = ImageExporter(widget.plotItem)
                data = exporter.export(toBytes=True)  # bytes PNG
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
        for i in reversed(range(self.plots_layout.count())):
            w = self.plots_layout.itemAt(i).widget()
            if w:
                w.deleteLater()
        self.axes_list.clear()
        self.vlines.clear()

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
            {'title': 'Comandos dos Atuadores', 'primary_y': {'cols': ['Elevator', 'Aileron'], 'label': 'Comando'}},
            {'title': 'Motor', 'primary_y': {'cols': ['RPM'], 'label': 'RPM'},
             'secondary_y': {'cols': ['CHT'], 'label': 'Temperatura (°C)'}},
        ]

        plotted_cols = set()

        for config in plotting_config:
            config_cols = []
            if 'primary_y' in config:  config_cols.extend(config['primary_y']['cols'])
            if 'secondary_y' in config: config_cols.extend(config['secondary_y']['cols'])

            has_data = any((c in df_plot.columns) and (not df_plot[c].dropna().empty) for c in config_cols)
            if has_data:
                self._create_plot_from_config(config, df_plot)
                plotted_cols.update(config_cols)
            else:
                self._create_placeholder_plot(config['title'])

        remaining_cols = [c for c in df_plot.select_dtypes(include=np.number).columns
                          if c not in plotted_cols and c not in ('_ts_',) and 'Timestamp' not in c]
        for col_name in remaining_cols:
            if not df_plot[col_name].isnull().all():
                self._create_plot_from_config({'title': col_name,
                                               'primary_y': {'cols': [col_name], 'label': col_name}}, df_plot)

        self.plots_layout.addStretch(1)
        self._sync_x_axes()
        self._add_vlines(df_plot)

    def _create_info_label(self, text):
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: gray; font-size: 14px;")
        self.plots_layout.addWidget(label)

    def _create_placeholder_plot(self, title):
        plotw = pg.PlotWidget(axisItems={'bottom': DateAxisItem(orientation='bottom')})
        plotw.setMinimumHeight(150)
        plotw.setTitle(title)
        txt = pg.TextItem(f"Dados para '{title}' não disponíveis.", anchor=(0.5, 0.5), color=(120, 120, 120))
        plotw.addItem(txt)
        vb = plotw.getPlotItem().getViewBox()
        vb.setRange(xRange=(0, 1), yRange=(0, 1), disableAutoRange=True)
        txt.setPos(0.5, 0.5)
        self.plots_layout.addWidget(plotw)

    def _create_plot_from_config(self, config, df_plot):
        plotw = pg.PlotWidget(axisItems={'bottom': DateAxisItem(orientation='bottom')})
        plotw.setMinimumHeight(360)
        plot_item = plotw.getPlotItem()
        plotw.setTitle(config['title'])
        plot_item.showGrid(x=True, y=True, alpha=0.3)  # grade discreta no tema branco
        plot_item.enableAutoRange(x=True, y=True)

        has_secondary = 'secondary_y' in config
        right_label = config.get('secondary_y', {}).get('label') if has_secondary else None
        self._ensure_right_border(plot_item, has_secondary=has_secondary, right_label=right_label, width_px=64)

        colors = cycle([
            ( 33, 150, 243),  # azul
            (244,  67,  54),  # vermelho
            ( 76, 175,  80),  # verde
            (255, 193,   7),  # âmbar
            (156,  39, 176),  # roxo
            (  0, 188, 212),  # ciano
            (255,  87,  34),  # laranja
            ( 96, 125, 139),  # cinza-azulado
            (139, 195,  74),  # verde claro
            (121,  85,  72),  # marrom
        ])

        legend_items = []  # guardamos para garantir inclusão na legenda

        # ---- Eixo primário
        if 'primary_y' in config:
            pconf = config['primary_y']
            step_mode_flag = True if pconf.get('style', '') == 'steps-post' else False
            for col in pconf['cols']:
                if col in df_plot.columns and not df_plot[col].isnull().all():
                    valid = df_plot[['_ts_', col]].dropna()
                    pen = pg.mkPen(color=next(colors), width=1.8)
                    item = self._plot_series(
                        plot_item,                              # alvo primário
                        valid['_ts_'].to_numpy(),
                        valid[col].to_numpy(),
                        name=col,
                        pen=pen,
                        step_mode_flag=step_mode_flag
                    )
                    legend_items.append((item, col))
            if pconf.get('label'):
                plot_item.getAxis('left').setLabel(pconf['label'])

        # ---- Eixo secundário (direito) com ViewBox
        right_vb = None
        if 'secondary_y' in config:
            sconf = config['secondary_y']

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

            step_mode_sec_flag = True if sconf.get('style', '') == 'steps-post' else False
            for col in sconf['cols']:
                if col in df_plot.columns and not df_plot[col].isnull().all():
                    valid = df_plot[['_ts_', col]].dropna()
                    pen = pg.mkPen(color=next(colors), width=1.8)
                    c = self._plot_series(
                        right_vb,                               # alvo secundário
                        valid['_ts_'].to_numpy(),
                        valid[col].to_numpy(),
                        name=col,
                        pen=pen,
                        step_mode_flag=step_mode_sec_flag
                    )
                    legend_items.append((c, col))

            if sconf.get('label'):
                plot_item.getAxis('right').setLabel(sconf['label'])

        # ---- Legenda (garantimos inclusão dos itens, inclusive do eixo direito)
        self._ensure_legend(plot_item, legend_items)

        # Guarda para sincronismo de X
        self.axes_list.append(plot_item.vb)
        if right_vb:
            self.axes_list.append(right_vb)

        # Zoom só em X (mais leve)
        plot_item.getViewBox().setMouseEnabled(x=True, y=False)

        self.plots_layout.addWidget(plotw)

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
        for i in range(self.plots_layout.count()):
            widget = self.plots_layout.itemAt(i).widget()
            if isinstance(widget, pg.PlotWidget):
                line = pg.InfiniteLine(pos=initial_ts, angle=90, movable=False,
                                       pen=pg.mkPen((255, 0, 0), width=1))
                line.hide()
                widget.addItem(line)
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
