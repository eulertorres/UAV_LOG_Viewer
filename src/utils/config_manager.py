from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

DEFAULT_CONFIG: Dict[str, Any] = {
    "graphs": {},
    "sync": {
        "timeline_frequency_ms": 120,
    },
    "gpu": {
        "preferred_index": None,
    },
}

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def _ensure_defaults(config: Dict[str, Any]) -> Dict[str, Any]:
    merged = DEFAULT_CONFIG.copy()
    graphs = config.get("graphs", {}) if isinstance(config, dict) else {}
    merged["graphs"] = graphs if isinstance(graphs, dict) else {}

    sync_cfg = DEFAULT_CONFIG["sync"].copy()
    user_sync = config.get("sync", {}) if isinstance(config, dict) else {}
    if isinstance(user_sync, dict):
        sync_cfg.update({k: v for k, v in user_sync.items() if v is not None})
    merged["sync"] = sync_cfg

    gpu_cfg = DEFAULT_CONFIG["gpu"].copy()
    user_gpu = config.get("gpu", {}) if isinstance(config, dict) else {}
    if isinstance(user_gpu, dict):
        gpu_cfg.update({k: v for k, v in user_gpu.items() if v is not None})
    merged["gpu"] = gpu_cfg
    return merged


def load_config() -> Dict[str, Any]:
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return _ensure_defaults(data)
    except Exception:
        pass
    return _ensure_defaults({})


def save_config(config: Dict[str, Any]) -> None:
    cfg = _ensure_defaults(config)
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def update_config_section(section: str, values: Dict[str, Any]) -> Dict[str, Any]:
    cfg = load_config()
    if section == "graphs":
        graph_cfg = cfg.get("graphs", {})
        if not isinstance(graph_cfg, dict):
            graph_cfg = {}
        graph_cfg.update(values)
        cfg["graphs"] = graph_cfg
    else:
        sec_cfg = cfg.get(section, {}) if isinstance(cfg.get(section), dict) else {}
        sec_cfg.update(values)
        cfg[section] = sec_cfg
    save_config(cfg)
    return cfg
