import json
from datetime import datetime
from itertools import cycle
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pprint

import numpy as np
import pandas as pd
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView


class DebugWebPage(QWebEnginePage):
    """WebEngine page that forwards console messages to Python debug logs."""

    def __init__(self, debug_cb, parent=None):
        super().__init__(parent)
        self._debug_cb = debug_cb

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        # Qt calls this virtual; we mirror the old signal-based logging.
        try:
            self._debug_cb(
                "webview console",
                level=int(level),
                line=int(line_number),
                source=str(source_id),
                message=str(message),
            )
        except Exception:
            pass
        super().javaScriptConsoleMessage(level, message, line_number, source_id)


class AllPlotsWidget(QWidget):
    """Plot stack powered by Plotly (mirrors UAVLogViewer behaviour)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.df = pd.DataFrame()
        self.datalogger_df: Optional[pd.DataFrame] = None
        self.current_log_name = ""
        self.datalogger_offset_sec: float = 0.0
        self.hidden_graph_titles: Set[str] = set()
        self._available_plot_titles: Set[str] = set()

        self._config_path = Path.home() / ".xmobots_log_viewer" / "config.json"
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_config()

        self.webview = QWebEngineView()
        self.webview.setPage(DebugWebPage(self._debug, self.webview))
        self.webview.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        self.webview.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        self.webview.loadFinished.connect(self._on_webview_ready)
        self.webview.loadFinished.connect(
            lambda ok: self._debug(
                "webview loadFinished",
                ok=ok,
                url=self.webview.url().toString(),
                last_path=getattr(self, "_last_html_path", None),
            )
        )
        self.webview.loadStarted.connect(
            lambda: self._debug(
                "webview loadStarted", url=self.webview.url().toString(), last_path=getattr(self, "_last_html_path", None)
            )
        )
        self._web_ready = False
        self._pending_js: List[str] = []
        self._last_cursor_ms: Optional[float] = None
        self._last_window: Optional[tuple[float, float]] = None
        self._last_html_path: Optional[Path] = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        controls = QHBoxLayout()
        controls.setContentsMargins(4, 0, 4, 0)
        controls.setSpacing(6)
        controls.addWidget(QLabel("Offset do Datalogger (s):"))
        self.datalogger_offset_spin = QDoubleSpinBox()
        self.datalogger_offset_spin.setRange(-600.0, 600.0)
        self.datalogger_offset_spin.setDecimals(3)
        self.datalogger_offset_spin.setSingleStep(0.1)
        self.datalogger_offset_spin.setValue(self.datalogger_offset_sec)
        self.datalogger_offset_spin.valueChanged.connect(self._on_datalogger_offset_changed)
        controls.addWidget(self.datalogger_offset_spin)

        self.graph_filter_button = QPushButton("Selecionar gráficos")
        self.graph_filter_button.clicked.connect(self._open_graph_filter_dialog)
        controls.addWidget(self.graph_filter_button)
        controls.addStretch(1)

        controls_widget = QWidget()
        controls_widget.setLayout(controls)
        main_layout.addWidget(controls_widget)
        main_layout.addWidget(self.webview, 1)

        self._render_empty()

    def _debug(self, message: str, **context: Any):
        """Lightweight debug helper to print reasons when plots fail to render."""
        payload = {"msg": message}
        if context:
            payload.update(context)
        try:
            print("[AllPlotsWidget]" + json.dumps(payload, ensure_ascii=False, default=str))
        except Exception:
            # Fallback if JSON serialization fails for a given payload
            print(f"[AllPlotsWidget]{message} | {pprint.pformat(context)}")

    # -------- public API --------
    def load_dataframe(
        self,
        df: pd.DataFrame,
        log_name: str = "",
        datalogger_df: Optional[pd.DataFrame] = None,
    ):
        self._debug(
            "load_dataframe called",
            log_name=log_name,
            df_empty=df.empty if isinstance(df, pd.DataFrame) else True,
            df_cols=list(df.columns) if isinstance(df, pd.DataFrame) else [],
            datalogger_present=isinstance(datalogger_df, pd.DataFrame) and not datalogger_df.empty,
        )
        self.df = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
        self.current_log_name = log_name or ""
        self.datalogger_df = datalogger_df if isinstance(datalogger_df, pd.DataFrame) else None
        self._update_datalogger_controls_visibility()
        self._render_plots()

    def update_cursor(self, timestamp):
        ts_ms = self._to_epoch_ms(timestamp)
        self._last_cursor_ms = ts_ms
        self._run_js(
            f"window.updateCursor && window.updateCursor({json.dumps(ts_ms)});"
        )

    def set_time_window(self, start_ts, end_ts):
        start_ms = self._to_epoch_ms(start_ts)
        end_ms = self._to_epoch_ms(end_ts)
        self._last_window = (start_ms, end_ms)
        self._run_js(
            (
                "if (window.setTimeWindow) {"
                f"setTimeWindow({json.dumps(start_ms)}, {json.dumps(end_ms)});"
                "}"
            )
        )

    def get_plot_images(self):
        # Plotly rendering happens in the webview; exporting is currently unsupported here.
        return []

    # -------- rendering --------
    def _render_empty(self, message: str | None = None):
        msg = message or "Carregue um arquivo de log para ver os gráficos."
        html = f"""
        <html><body style='font-family: sans-serif; background:#fafafa;'>
            <div style='padding:20px; color:#666;'>{msg}</div>
        </body></html>
        """
        self._web_ready = False
        self.webview.setHtml(html)

    def _render_plots(self):
        try:
            if self.df.empty:
                self._debug("render_plots aborted: df empty")
                self._render_empty()
                return

            # Alguns DataFrames chegam com o Timestamp apenas no índice; restaura a coluna
            # para evitar falha prematura que deixaria a mensagem "Carregue um arquivo...".
            if "Timestamp" not in self.df.columns and isinstance(self.df.index, pd.DatetimeIndex):
                self._debug("restoring Timestamp from index")
                self.df = self.df.reset_index().rename(columns={"index": "Timestamp"})

            if "Timestamp" not in self.df.columns:
                self._debug("render_plots aborted: missing Timestamp column", cols=list(self.df.columns))
                self._render_empty("Log sem coluna de Timestamp para plotar.")
                return

            df_plot = self.df.copy()
            df_plot["_ts_ms_"] = df_plot["Timestamp"].map(self._to_epoch_ms)
            self._debug(
                "timestamp mapped",
                rows=len(df_plot),
                timestamp_na=df_plot["Timestamp"].isna().sum(),
                ts_ms_na=df_plot["_ts_ms_"].isna().sum(),
                ts_ms_head=df_plot["_ts_ms_"].head(5).to_list(),
            )

            if df_plot["_ts_ms_"].dropna().empty:
                self._debug("render_plots aborted: no valid timestamp values")
                self._render_empty("Log sem timestamps válidos para plotar.")
                return

            overlay_df = None
            if self.datalogger_df is not None and not self.datalogger_df.empty and "Timestamp" in self.datalogger_df.columns:
                overlay_df = self.datalogger_df.copy()
                overlay_df["_ts_base_ms_"] = overlay_df["Timestamp"].map(self._to_epoch_ms)
                overlay_df["_ts_ms_"] = overlay_df["_ts_base_ms_"] + (self.datalogger_offset_sec * 1000.0)
                self._debug(
                    "datalogger overlay prepared",
                    rows=len(overlay_df),
                    ts_na=overlay_df["_ts_ms_"].isna().sum(),
                    head=overlay_df[["_ts_ms_", "_ts_base_ms_"]].head(3).to_dict(orient="list"),
                )

            plotting_config, aileron_styles = self._build_plotting_config(df_plot, overlay_df)

            self._available_plot_titles = {cfg["title"] for cfg in plotting_config}
            plots_payload = []
            plotted_cols: Set[str] = set()

            for config in plotting_config:
                if config["title"] in self.hidden_graph_titles:
                    continue
                spec, used_cols = self._config_to_plot_spec(config, df_plot, aileron_styles, overlay_df)
                if spec:
                    plots_payload.append(spec)
                    plotted_cols.update(used_cols)

            remaining_cols = [
                c
                for c in df_plot.select_dtypes(include=np.number).columns
                if c not in plotted_cols and c not in {"_ts_ms_"} and "Timestamp" not in c
            ]
            for config in self._build_remaining_configs(remaining_cols, df_plot):
                self._available_plot_titles.add(config["title"])
                if config["title"] in self.hidden_graph_titles:
                    continue
                spec, used_cols = self._config_to_plot_spec(config, df_plot, aileron_styles, overlay_df)
                if spec:
                    plots_payload.append(spec)

            if not plots_payload:
                self._debug("render_plots aborted: no plot payload built", plotted_cols=list(plotted_cols))
                self._render_empty("Nenhum dado numérico disponível para plotar.")
                return

            self._debug(
                "rendering plots",
                payload_count=len(plots_payload),
                plots=[p.get("title") for p in plots_payload],
            )
            payload = {
                "plots": plots_payload,
                "cursorMs": self._last_cursor_ms,
            }
            html = self._build_html(payload)
            self._debug("html built", html_chars=len(html))
            self._web_ready = False
            self._load_html_via_file(html)
        except Exception as exc:  # noqa: BLE001 - surfaced for troubleshooting
            self._debug("render_plots exception", error=str(exc))
            self._render_empty("Erro ao gerar gráficos. Consulte o log para detalhes.")

    def _load_html_via_file(self, html: str):
        try:
            tmp_dir = Path.home() / ".xmobots_log_viewer" / "tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_file = tmp_dir / f"all_plots_{int(datetime.now().timestamp()*1000)}.html"
            tmp_file.write_text(html, encoding="utf-8")
            if self._last_html_path and self._last_html_path.exists():
                try:
                    self._last_html_path.unlink()
                except Exception:
                    pass
            self._last_html_path = tmp_file
            self._debug("loading html file", path=str(tmp_file), size=tmp_file.stat().st_size)
            self.webview.setUrl(QUrl.fromLocalFile(str(tmp_file)))
        except Exception as exc:  # noqa: BLE001
            self._debug("load_html_via_file failed", error=str(exc))
            self._render_empty("Erro ao preparar HTML para os gráficos.")

    def _build_html(self, payload: Dict[str, Any]) -> str:
        data_json = json.dumps(payload, ensure_ascii=False, default=str)
        return f"""
<!DOCTYPE html>
<html lang='pt-BR'>
<head>
  <meta charset='utf-8'>
  <title>Todos os Gráficos</title>
  <script src='https://cdn.plot.ly/plotly-2.31.1.min.js'></script>
  <style>
    body {{ margin:0; padding:0; background:#fafafa; font-family:'Segoe UI', Arial, sans-serif; }}
    .plot-container {{ padding: 10px 12px 6px 12px; }}
    .plot-box {{ background:white; border:1px solid #e5e5e5; border-radius:8px; box-shadow: 0 1px 2px rgba(0,0,0,0.04); margin-bottom:12px; }}
  </style>
</head>
<body>
  <div id='plotsRoot'></div>
  <script>
    const payload = {data_json};
    const plotRegistry = {{}};

    function createLayout(plot) {{
      const layout = {{
        title: {{ text: plot.title, font: {{ size: 15 }} }},
        margin: {{ l: 60, r: 60, t: 40, b: 40 }},
        hovermode: 'x unified',
        legend: {{ orientation: 'h', x: 0, y: 1.12 }},
        xaxis: {{
          type: 'date',
          rangeslider: {{ visible: false }},
          showspikes: true,
          spikemode: 'across',
          spikecolor: '#d32f2f',
          spikethickness: 1,
        }},
        yaxis: {{ title: plot.yLabel || '' }},
      }};
      if (plot.y2Label) {{
        layout.yaxis2 = {{ title: plot.y2Label, overlaying: 'y', side: 'right', showgrid: false }};
      }}
      if (plot.initialRange && plot.initialRange.length === 2) {{
        layout.xaxis.range = plot.initialRange;
      }}
      return layout;
    }}

    function renderAll() {{
      const root = document.getElementById('plotsRoot');
      root.innerHTML = '';
      payload.plots.forEach((plot, idx) => {{
        const wrap = document.createElement('div');
        wrap.className = 'plot-container';
        const box = document.createElement('div');
        box.className = 'plot-box';
        box.id = plot.id || ('plot_' + idx);
        wrap.appendChild(box);
        root.appendChild(wrap);

        const traces = (plot.traces || []).map(tr => {{
          const copy = Object.assign({{}}, tr);
          if (Array.isArray(tr.baseX)) {{
            const offsetMs = (plot.offsetMs || 0);
            copy.x = tr.baseX.map(v => v + offsetMs);
          }}
          return copy;
        }});
        const layout = createLayout(plot);
        Plotly.newPlot(box, traces, layout, {{ displayModeBar: false, responsive: true }}).then(() => {{
          const reg = {{ id: box.id, el: box, datalogger: [] }};
          (plot.traces || []).forEach((tr, tIdx) => {{
            if (Array.isArray(tr.baseX)) {{
              reg.datalogger.push({{ index: tIdx, baseX: tr.baseX }});
            }}
          }});
          plotRegistry[box.id] = reg;
          if (payload.cursorMs) {{
            updateCursor(payload.cursorMs);
          }}
        }});
      }});
    }}

    window.updateCursor = function(tsMs) {{
      Object.values(plotRegistry).forEach(reg => {{
        const line = {{
          type: 'line', x0: tsMs, x1: tsMs, yref: 'paper', y0: 0, y1: 1,
          line: {{ color: 'red', width: 1 }}
        }};
        Plotly.relayout(reg.el, {{ shapes: [line] }});
      }});
    }};

    window.setTimeWindow = function(startMs, endMs) {{
      Object.values(plotRegistry).forEach(reg => {{
        Plotly.relayout(reg.el, {{ 'xaxis.range': [startMs, endMs] }});
      }});
    }};

    window.applyDataloggerOffset = function(offsetSec) {{
      const offsetMs = Number(offsetSec || 0) * 1000;
      Object.values(plotRegistry).forEach(reg => {{
        if (!reg.datalogger) return;
        reg.datalogger.forEach(entry => {{
          const newX = entry.baseX.map(v => v + offsetMs);
          Plotly.restyle(reg.el, {{ x: [newX] }}, entry.index);
        }});
      }});
    }};

    renderAll();
  </script>
</body>
</html>
        """

    def _build_plotting_config(self, df_plot: pd.DataFrame, overlay_df: Optional[pd.DataFrame]):
        aileron_overlays = []
        aileron_styles: Dict[str, Dict[str, Any]] = {}
        aileron_secondary_label = None

        if overlay_df is not None:
            if "ServoL_PWM_us" in overlay_df.columns:
                aileron_overlays.append({
                    "name": "ServoL_PWM_us",
                    "color": "rgb(33,150,243)",
                    "yaxis": "y2",
                })
                aileron_styles["AileronL"] = {"dash": "dash", "color": "rgb(33,150,243)"}
                aileron_secondary_label = "PWM (µs)"
            if "ServoR_PWM_us" in overlay_df.columns:
                aileron_overlays.append({
                    "name": "ServoR_PWM_us",
                    "color": "rgb(244,67,54)",
                    "yaxis": "y2",
                })
                aileron_styles["AileronR"] = {"dash": "dash", "color": "rgb(244,67,54)"}
                aileron_secondary_label = "PWM (µs)"
            if "Aileron" in df_plot.columns:
                aileron_styles.setdefault("Aileron", {"dash": "dash", "color": "rgb(76,175,80)"})
        else:
            aileron_styles.setdefault("AileronL", {"dash": "dash", "color": "rgb(33,150,243)"})
            aileron_styles.setdefault("AileronR", {"dash": "dash", "color": "rgb(244,67,54)"})
            aileron_styles.setdefault("Aileron", {"dash": "dash", "color": "rgb(76,175,80)"})

        plotting_config = [
            {"title": "Atitude da Aeronave", "primary_y": {"cols": ["Roll", "Pitch", "Yaw"], "label": "Graus (°)"}},
            {
                "title": "Altitude e Velocidade Vertical",
                "primary_y": {"cols": ["AltitudeAbs", "QNE"], "label": "Altitude (m)"},
                "secondary_y": {"cols": ["VSI"], "label": "Vel. Vertical (m/s)"},
            },
            {
                "title": "Status e Alertas do Sistema",
                "primary_y": {"cols": ["IsFlying", "isVTOL", "ModoVoo", "Spoofing", "Jamming"], "label": "Estado (On/Off)", "style": "steps-post"},
            },
            {
                "title": "Status do Receptor GNSS",
                "primary_y": {"cols": ["Satellites", "Sat_use"], "label": "Contagem"},
                "secondary_y": {"cols": ["RTK_Status"], "label": "Status RTK"},
            },
            {
                "title": "Energia do Sistema",
                "primary_y": {"cols": ["Voltage", "VTOL_vbat", "Filt_VDC"], "label": "Tensão (V)"},
                "secondary_y": {"cols": ["Porcent_bat"], "label": "Bateria (%)"},
            },
            {
                "title": "Dados de Voo (Air Data)",
                "primary_y": {"cols": ["ASI", "WSI"], "label": "Velocidade (m/s)"},
                "secondary_y": {"cols": ["WindDirection"], "label": "Direção do Vento (°)"},
            },
            {
                "title": "Comandos dos Atuadores",
                "primary_y": {"cols": ["Elevator", "Aileron", "AileronL", "AileronR"], "label": "Comando"},
                "secondary_y": {"cols": [], "label": aileron_secondary_label} if aileron_secondary_label else None,
                "overlays": aileron_overlays,
                "col_styles": aileron_styles,
            },
            {
                "title": "Motor",
                "primary_y": {"cols": ["RPM"], "label": "RPM"},
                "secondary_y": {"cols": ["CHT"], "label": "Temperatura (°C)"},
            },
        ]
        return plotting_config, aileron_styles

    def _config_to_plot_spec(
        self,
        config: Dict[str, Any],
        df_plot: pd.DataFrame,
        col_styles: Dict[str, Dict[str, Any]],
        overlay_df: Optional[pd.DataFrame],
    ):
        traces = []
        used_cols: Set[str] = set()
        colors = cycle(
            [
                "rgb(33,150,243)",
                "rgb(244,67,54)",
                "rgb(76,175,80)",
                "rgb(255,193,7)",
                "rgb(156,39,176)",
                "rgb(0,188,212)",
                "rgb(255,87,34)",
                "rgb(96,125,139)",
                "rgb(139,195,74)",
                "rgb(121,85,72)",
            ]
        )

        def append_trace(column: str, target_df: pd.DataFrame, axis: str, style_override: Optional[Dict[str, Any]] = None, legend_name: Optional[str] = None):
            nonlocal traces
            if column not in target_df.columns:
                return
            series = target_df[["_ts_ms_", column]].dropna()
            if series.empty:
                return
            x_vals = series["_ts_ms_"].to_list()
            y_vals = series[column].to_list()
            base_style = {"color": next(colors), "width": 2}
            if style_override:
                base_style.update(style_override)
            trace = {
                "name": legend_name or column,
                "x": x_vals,
                "y": y_vals,
                "mode": "lines",
                "line": {"color": base_style.get("color"), "width": base_style.get("width", 2)},
            }
            if axis == "secondary":
                trace["yaxis"] = "y2"
            if base_style.get("dash"):
                trace["line"]["dash"] = base_style["dash"]
            if base_style.get("shape"):
                trace["line"]["shape"] = base_style["shape"]
            used_cols.add(column)
            traces.append(trace)

        pconf = config.get("primary_y", {}) or {}
        step_primary = pconf.get("style") == "steps-post"
        for col in pconf.get("cols", []):
            style = dict(col_styles.get(col, {})) if isinstance(col_styles, dict) else {}
            if step_primary:
                style.setdefault("shape", "hv")
            append_trace(col, df_plot, "primary", style)

        sconf = config.get("secondary_y")
        if isinstance(sconf, dict):
            step_secondary = sconf.get("style") == "steps-post"
            for col in sconf.get("cols", []):
                style = dict(col_styles.get(col, {})) if isinstance(col_styles, dict) else {}
                if step_secondary:
                    style.setdefault("shape", "hv")
                append_trace(col, df_plot, "secondary", style)

        overlays = config.get("overlays", []) if isinstance(config.get("overlays"), list) else []
        for overlay in overlays:
            col_name = overlay.get("name") or overlay.get("cols", [None])[0]
            if not col_name or overlay_df is None:
                continue
            if col_name not in overlay_df.columns:
                continue
            series = overlay_df[["_ts_ms_", "_ts_base_ms_", col_name]].dropna()
            if series.empty:
                continue
            x_vals = series["_ts_ms_"].to_list()
            base_x = series["_ts_base_ms_"].to_list()
            y_vals = series[col_name].to_list()
            trace = {
                "name": overlay.get("legend_prefix", "") + col_name,
                "x": x_vals,
                "y": y_vals,
                "mode": "lines",
                "line": {"color": overlay.get("color", overlay.get("pen", {}).get("color", "rgb(33,150,243)")), "width": 2.4},
                "baseX": base_x,
            }
            if overlay.get("yaxis") == "y2":
                trace["yaxis"] = "y2"
            traces.append(trace)

        if not traces:
            self._debug("no traces built for config", title=config.get("title"), available_cols=list(df_plot.columns))
            return None, used_cols

        valid_ts = df_plot["_ts_ms_"].dropna()
        if valid_ts.empty:
            self._debug("no valid timestamps for config", title=config.get("title"))
            return None, used_cols

        first_ts = valid_ts.iloc[0]
        last_ts = valid_ts.iloc[-1]
        spec = {
            "id": f"plot_{hash(config['title']) & 0xfffff}",
            "title": config["title"],
            "yLabel": pconf.get("label", ""),
            "y2Label": sconf.get("label") if isinstance(sconf, dict) else None,
            "traces": traces,
            "initialRange": [first_ts, last_ts],
            "offsetMs": self.datalogger_offset_sec * 1000.0,
        }
        return spec, used_cols

    def _normalize_axis_group(self, column_name: str):
        tokens = ["_x_", "_y_", "_z_", "_X_", "_Y_", "_Z_"]
        suffixes = ["_x", "_y", "_z", "_X", "_Y", "_Z"]
        normalized = column_name
        replaced = False

        for token in tokens:
            if token in column_name:
                normalized = column_name.replace(token, "_axis_")
                replaced = True
                break

        if not replaced:
            for suffix in suffixes:
                if column_name.endswith(suffix):
                    normalized = column_name[: -len(suffix)] + "_axis"
                    replaced = True
                    break

        if replaced:
            friendly = normalized.replace("_axis_", "_XYZ_").replace("_axis", "_XYZ")
        else:
            friendly = column_name

        return normalized, friendly

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

            title = valid_cols[0] if len(valid_cols) == 1 else friendly_titles.get(key, key)
            configs.append(
                {
                    "title": title,
                    "primary_y": {"cols": valid_cols, "label": title},
                }
            )

        return configs

    # -------- controls & config --------
    def _update_datalogger_controls_visibility(self):
        has_overlay = self.datalogger_df is not None and not self.datalogger_df.empty
        self.datalogger_offset_spin.setEnabled(has_overlay)
        self.datalogger_offset_spin.blockSignals(True)
        self.datalogger_offset_spin.setValue(self.datalogger_offset_sec)
        self.datalogger_offset_spin.blockSignals(False)

    def _on_datalogger_offset_changed(self, value: float):
        self.datalogger_offset_sec = float(value)
        self._save_config()
        self._run_js(f"window.applyDataloggerOffset && window.applyDataloggerOffset({self.datalogger_offset_sec});")

    def _open_graph_filter_dialog(self):
        if not self._available_plot_titles:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Selecionar gráficos")
        layout = QVBoxLayout(dialog)
        grid = QGridLayout()

        checkboxes = []
        titles_sorted = sorted(self._available_plot_titles)
        columns = 6
        for idx, title in enumerate(titles_sorted):
            cb = QCheckBox(title)
            cb.setChecked(title not in self.hidden_graph_titles)
            row = idx // columns
            col = idx % columns
            grid.addWidget(cb, row, col)
            checkboxes.append(cb)

        layout.addLayout(grid)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_hidden = set()
            for cb in checkboxes:
                if not cb.isChecked():
                    new_hidden.add(cb.text())
            self.hidden_graph_titles = new_hidden
            self._save_config()
            self._render_plots()

    def _load_config(self):
        try:
            if self._config_path.exists():
                with self._config_path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self.datalogger_offset_sec = float(data.get("datalogger_offset_sec", 0.0))
                hidden = data.get("hidden_graph_titles", [])
                if isinstance(hidden, list):
                    self.hidden_graph_titles = set(hidden)
        except Exception:
            self.datalogger_offset_sec = 0.0
            self.hidden_graph_titles = set()

    def _save_config(self):
        payload = {
            "datalogger_offset_sec": self.datalogger_offset_sec,
            "hidden_graph_titles": sorted(self.hidden_graph_titles),
        }
        try:
            with self._config_path.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # -------- helpers --------
    def _on_webview_ready(self, ok: bool):
        self._web_ready = ok
        self._debug("_on_webview_ready", ok=ok)
        if not ok:
            self._render_empty("Erro ao carregar os gráficos no navegador embutido. Consulte o log para detalhes.")
            return
        if ok:
            if self._last_cursor_ms is not None:
                self.update_cursor(self._last_cursor_ms)
            if self._last_window is not None:
                self.set_time_window(*self._last_window)
            while self._pending_js:
                js = self._pending_js.pop(0)
                try:
                    self.webview.page().runJavaScript(js)
                except RuntimeError:
                    break

    def _run_js(self, script: str):
        if not self.webview:
            return
        if self._web_ready:
            try:
                self.webview.page().runJavaScript(script)
            except RuntimeError:
                pass
        else:
            self._pending_js.append(script)

    @staticmethod
    def _to_epoch_ms(ts) -> float:
        if isinstance(ts, (int, float, np.integer, np.floating)):
            return float(ts) * 1000.0 if float(ts) < 1e12 else float(ts)
        try:
            if isinstance(ts, pd.Timestamp):
                return ts.to_datetime64().astype("datetime64[ns]").astype(np.int64) / 1e6
            return pd.Timestamp(ts).to_datetime64().astype("datetime64[ns]").astype(np.int64) / 1e6
        except Exception:
            try:
                return datetime.fromtimestamp(0).timestamp() * 1000.0
            except Exception:
                return 0.0

