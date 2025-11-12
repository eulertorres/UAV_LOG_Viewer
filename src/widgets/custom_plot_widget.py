from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGroupBox,
    QComboBox, QInputDialog, QLabel, QListWidget, QSizePolicy
)
import pandas as pd
import numpy as np
from itertools import cycle
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

class CustomPlotWidget(QWidget):
    NEW_AXIS_OPTION = "<Novo Eixo>"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.log_data = {}
        
        self.plotted_data = []
        self.axis_names = []
        self.axes = []
        self.chart_title = "Gráfico de Comparação"
        self.vlines = []

        layout = QVBoxLayout(self)

        controls_group = QGroupBox("Controles do Gráfico de Comparação")
        controls_group.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        controls_layout = QVBoxLayout()
        add_data_layout = QHBoxLayout()
        
        self.log_source_combo = QComboBox()
        self.log_source_combo.currentTextChanged.connect(self._on_log_source_changed)
        
        self.column_combo = QComboBox()
        self.axis_combo = QComboBox()
        
        btn_add_plot = QPushButton("Adicionar ao Gráfico")
        btn_add_plot.clicked.connect(self.add_plot)
        
        add_data_layout.addWidget(QLabel("Fonte do Log:"))
        add_data_layout.addWidget(self.log_source_combo, 1)
        add_data_layout.addWidget(QLabel("Variável:"))
        add_data_layout.addWidget(self.column_combo, 1)
        add_data_layout.addWidget(QLabel("Eixo:"))
        add_data_layout.addWidget(self.axis_combo, 1)
        add_data_layout.addWidget(btn_add_plot)
        controls_layout.addLayout(add_data_layout)

        manage_layout = QHBoxLayout()
        btn_set_title = QPushButton("Definir Título")
        btn_set_title.clicked.connect(self.set_chart_title)
        btn_remove = QPushButton("Remover Selecionado(s)")
        btn_remove.clicked.connect(self.remove_selected)
        manage_layout.addStretch(1)
        manage_layout.addWidget(btn_set_title)
        manage_layout.addWidget(btn_remove)
        controls_layout.addLayout(manage_layout)
        controls_group.setLayout(controls_layout)
        layout.addWidget(controls_group)
        
        self.list_widget = QListWidget()
        self.list_widget.setMaximumHeight(120)
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self.list_widget)

        self.figure = Figure(figsize=(6, 4))
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        
        self._reset_axes()
        self.update_plot()

    def update_cursor(self, timestamp):
        pass

    def update_plot(self):
        self.figure.clear()
        self.axes.clear()
        self.figure.suptitle(self.chart_title, fontsize=14)

        if not self.log_data or not self.plotted_data:
            ax = self.figure.add_subplot(111)
            text = "Carregue diretórios e adicione variáveis para comparar"
            ax.text(0.5, 0.5, text, ha="center", va="center", transform=ax.transAxes)
            self.canvas.draw_idle()
            return

        host_ax = self.figure.add_subplot(111)
        self.axes = [host_ax] 

        axis_map = {0: host_ax}
        
        # --- ALTERAÇÃO CORRIGIDA E ROBUSTA ---
        # Usa np.linspace para pegar N cores perfeitamente espaçadas do colormap 'hsv'.
        # 'endpoint=False' é crucial para que a última cor não seja igual à primeira (vermelho).
        num_plots = len(self.plotted_data)
        if num_plots > 0:
            colors_list = [plt.cm.hsv(i) for i in np.linspace(0, 1, num_plots, endpoint=False)]
            colors = cycle(colors_list)
        else:
            colors = cycle(['blue'])
        
        handles, labels = [], []

        for plot_info in self.plotted_data:
            log_name, col, axis_idx = plot_info['log'], plot_info['col'], plot_info['axis_idx']
            
            if axis_idx not in axis_map:
                new_ax = host_ax.twinx()
                new_ax.spines['right'].set_position(('outward', 60 * (len(axis_map) - 1)))
                axis_map[axis_idx] = new_ax
                self.axes.append(new_ax)

            ax = axis_map[axis_idx]
            df_to_plot = self.log_data[log_name]
            color = next(colors)
            
            line_label = f"{col} ({log_name})"
            
            # Garante que seja uma linha sólida ('-') e sem marcadores de ponto.
            line, = ax.plot(df_to_plot.index.to_numpy(), df_to_plot[col].to_numpy(), 
                            label=line_label, color=color, linestyle='-', marker=None)
            
            handles.append(line)
            labels.append(line_label)
            ax.set_ylabel(self.axis_names[axis_idx])
            
        host_ax.set_xlabel("Índice da Amostra (Tempo Relativo)")
        host_ax.legend(handles, labels, loc='best')
        host_ax.grid(True, linestyle='--', alpha=0.6)
        
        self.figure.tight_layout(rect=[0, 0.03, 1, 0.95])
        self.canvas.draw_idle()

    def reload_data(self, all_log_data):
        self.log_data = all_log_data
        
        self.list_widget.clear()
        self.plotted_data = []
        self._reset_axes()
        
        self.log_source_combo.blockSignals(True)
        self.log_source_combo.clear()
        if self.log_data:
            log_names = sorted(list(self.log_data.keys()))
            self.log_source_combo.addItems(log_names)
        self.log_source_combo.blockSignals(False)
        self._on_log_source_changed(self.log_source_combo.currentText())
        
        self.update_plot()
        
    def _on_log_source_changed(self, log_name):
        self.column_combo.clear()
        if log_name and log_name in self.log_data:
            df = self.log_data[log_name]
            cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and "Timestamp" not in c]
            self.column_combo.addItems(sorted(cols))

    def _reset_axes(self):
        self.axis_combo.clear()
        self.axis_combo.addItem(self.NEW_AXIS_OPTION)
        self.axis_names = []

    def set_chart_title(self):
        new_title, ok = QInputDialog.getText(self, 'Título do Gráfico', 'Digite o título:', text=self.chart_title)
        if ok and new_title:
            self.chart_title = new_title
            self.update_plot()
    
    def add_plot(self):
        log_name = self.log_source_combo.currentText()
        col = self.column_combo.currentText()
        target_axis_name = self.axis_combo.currentText()

        if not log_name or not col: return
        if any(p['log'] == log_name and p['col'] == col for p in self.plotted_data): return

        axis_idx = -1
        if target_axis_name == self.NEW_AXIS_OPTION:
            axis_name = col 
            if axis_name in self.axis_names:
                axis_idx = self.axis_names.index(axis_name)
            else:
                self.axis_names.append(axis_name)
                self.axis_combo.addItem(axis_name)
                axis_idx = len(self.axis_names) - 1
        else:
            axis_name = target_axis_name
            axis_idx = self.axis_names.index(axis_name)

        plot_info = {'log': log_name, 'col': col, 'axis_idx': axis_idx}
        self.plotted_data.append(plot_info)
        
        item_text = f"'{col}' (de {log_name}) no eixo '{self.axis_names[axis_idx]}'"
        self.list_widget.addItem(item_text)
        
        self.update_plot()

    def remove_selected(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items: return

        indices_to_remove = sorted([self.list_widget.row(item) for item in selected_items], reverse=True)
        
        for index in indices_to_remove:
            self.list_widget.takeItem(index)
            del self.plotted_data[index]
            
        if self.plotted_data:
            active_axis_indices = {p['axis_idx'] for p in self.plotted_data}
            
            new_axis_names = []
            old_to_new_idx_map = {}
            current_new_idx = 0
            for i, name in enumerate(self.axis_names):
                if i in active_axis_indices:
                    new_axis_names.append(name)
                    old_to_new_idx_map[i] = current_new_idx
                    current_new_idx += 1
            
            for p in self.plotted_data:
                p['axis_idx'] = old_to_new_idx_map[p['axis_idx']]
            
            self.axis_names = new_axis_names
            self.axis_combo.clear()
            self.axis_combo.addItem(self.NEW_AXIS_OPTION)
            self.axis_combo.addItems(self.axis_names)
        else:
            self._reset_axes()

        self.update_plot()