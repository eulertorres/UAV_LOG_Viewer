from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox, QSpinBox

from src.utils.config_manager import load_config, update_config_section


class OptionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Opções do Programa")
        self.setModal(True)

        self.sync_spin = QSpinBox(self)
        self.sync_spin.setRange(30, 5000)
        self.sync_spin.setSuffix(" ms")
        self.sync_spin.setSingleStep(10)

        self._load_values()

        form = QFormLayout(self)
        form.addRow("Frequência de sincronização (2D/3D ↔ gráficos)", self.sync_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _load_values(self):
        cfg = load_config()
        sync_cfg = cfg.get("sync", {}) if isinstance(cfg, dict) else {}
        value = sync_cfg.get("timeline_frequency_ms", 120) if isinstance(sync_cfg, dict) else 120
        self.sync_spin.setValue(int(value))

    def accept(self):
        update_config_section("sync", {"timeline_frequency_ms": int(self.sync_spin.value())})
        super().accept()
