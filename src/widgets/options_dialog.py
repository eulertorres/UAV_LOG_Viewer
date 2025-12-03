from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QDialogButtonBox,
    QSpinBox,
    QPushButton,
    QMessageBox,
)

from src.utils.config_manager import load_config, update_config_section
from src.widgets.all_plots_widget import GraphMenuDialog


class OptionsDialog(QDialog):
    def __init__(self, parent=None, *,
                 graph_titles: list[str] | None = None,
                 graph_states: dict | None = None,
                 apply_graphs_callback=None):
        super().__init__(parent)
        self.setWindowTitle("Opções do Programa")
        self.setModal(True)

        self._graph_titles = graph_titles or []
        self._graph_states = graph_states or {}
        self._apply_graphs_callback = apply_graphs_callback

        self.sync_spin = QSpinBox(self)
        self.sync_spin.setRange(30, 5000)
        self.sync_spin.setSuffix(" ms")
        self.sync_spin.setSingleStep(10)

        self._load_values()

        form = QFormLayout(self)
        form.addRow("Frequência de sincronização (2D/3D ↔ gráficos)", self.sync_spin)

        self.graphs_btn = QPushButton("Configurar gráficos visíveis", self)
        self.graphs_btn.setEnabled(bool(self._graph_titles))
        self.graphs_btn.clicked.connect(self._open_graph_menu)
        form.addRow(self.graphs_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _load_values(self):
        cfg = load_config()
        sync_cfg = cfg.get("sync", {}) if isinstance(cfg, dict) else {}
        value = sync_cfg.get("timeline_frequency_ms", 120) if isinstance(sync_cfg, dict) else 120
        self.sync_spin.setValue(int(value))

    def _open_graph_menu(self):
        if not self._graph_titles:
            QMessageBox.information(self, "Configuração", "Nenhum gráfico disponível para configurar ainda.")
            return
        dialog = GraphMenuDialog(self._graph_titles, self._graph_states, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._graph_states = dialog.get_states()
            update_config_section("graphs", self._graph_states)
            if callable(self._apply_graphs_callback):
                self._apply_graphs_callback(self._graph_states)

    def accept(self):
        update_config_section("sync", {"timeline_frequency_ms": int(self.sync_spin.value())})
        super().accept()
