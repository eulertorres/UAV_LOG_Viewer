from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple
import numpy as np
import pandas as pd


@dataclass
class ModeSegment:
    start: float
    end: float
    label: str
    color: Tuple[int, int, int]
    mode_value: int


def _resolve_mode_palette(df: pd.DataFrame) -> Dict[int, Tuple[str, Tuple[int, int, int]]]:
    fw_modes = {
        -1: ("RC Mode", (96, 125, 139)),
        0: ("Subir", (156, 39, 176)),
        1: ("Manual (FW150)", (33, 150, 243)),
        2: ("SEMI", (0, 188, 212)),
        3: ("Survey", (76, 175, 80)),
        4: ("Tracking", (255, 202, 40)),
        5: ("Orbit", (255, 112, 67)),
        8: ("Landing", (244, 67, 54)),
        9: ("TakeOff", (141, 110, 99)),
        255: ("RC manual", (121, 85, 72)),
    }
    rw_modes = {
        0: ("Stabilize", (3, 169, 244)),
        1: ("IDLE", (120, 144, 156)),
        2: ("AUTO", (76, 175, 80)),
        3: ("Forced Land", (244, 67, 54)),
    }
    is_rw = False
    if 'isVTOL' in df.columns:
        try:
            is_rw = bool(df['isVTOL'].dropna().astype(float).mean() >= 0.5)
        except Exception:
            is_rw = False
    return rw_modes if is_rw else fw_modes


def compute_mode_segments(df: pd.DataFrame, *, timestamp_column: str = 'Timestamp', mode_column: str = 'ModoVoo') -> List[ModeSegment]:
    if timestamp_column not in df.columns or mode_column not in df.columns or df.empty:
        return []

    try:
        ts_series = df[timestamp_column].map(_to_epoch_seconds)
        mode_data = pd.DataFrame({
            '_ts_': ts_series,
            'mode': df[mode_column]
        }).dropna().sort_values('_ts_')
    except Exception:
        return []

    if mode_data.empty:
        return []

    palette = _resolve_mode_palette(df)
    segments: List[ModeSegment] = []

    ts_values = mode_data['_ts_'].to_numpy(dtype=float)
    mode_values = mode_data['mode'].to_numpy(dtype=int)

    current_mode = mode_values[0]
    start_ts = ts_values[0]

    def _append_segment(seg_start: float, seg_end: float, mode_value: int):
        if seg_end <= seg_start:
            return
        label, color = palette.get(mode_value, (f"Modo {mode_value}", (160, 160, 160)))
        segments.append(ModeSegment(seg_start, seg_end, label, color, int(mode_value)))

    for idx in range(1, len(ts_values)):
        ts = ts_values[idx]
        mode_val = mode_values[idx]
        if mode_val != current_mode:
            _append_segment(start_ts, ts, current_mode)
            start_ts = ts
            current_mode = mode_val

    last_ts = float(np.nanmax(ts_values)) if len(ts_values) else start_ts
    _append_segment(start_ts, last_ts, current_mode)
    return segments


def build_mode_path_segments(df: pd.DataFrame, segments: Iterable[ModeSegment], *, lat_col: str = 'Latitude', lon_col: str = 'Longitude', alt_col: str | None = 'AltitudeAbs') -> List[dict]:
    if df.empty or lat_col not in df.columns or lon_col not in df.columns:
        return []
    ts_series = df['Timestamp'].map(_to_epoch_seconds) if 'Timestamp' in df.columns else pd.Series(dtype=float)
    lat = df[lat_col]
    lon = df[lon_col]
    alt = df[alt_col] if alt_col and alt_col in df.columns else None

    results: List[dict] = []
    for seg in segments:
        mask = (ts_series >= seg.start) & (ts_series <= seg.end)
        seg_lat = lat[mask].dropna()
        seg_lon = lon[mask].dropna()
        if seg_lat.empty or seg_lon.empty:
            continue
        coords = list(zip(seg_lat.to_numpy(dtype=float), seg_lon.to_numpy(dtype=float)))
        if alt is not None:
            seg_alt = alt[mask].reindex(seg_lat.index)
            coords_with_alt = [
                (lat_v, lon_v, float(a)) if pd.notna(a) else (lat_v, lon_v, None)
                for (lat_v, lon_v), a in zip(coords, seg_alt)
            ]
        else:
            coords_with_alt = [(lat_v, lon_v, None) for lat_v, lon_v in coords]
        results.append({
            'mode': seg.mode_value,
            'label': seg.label,
            'color': seg.color,
            'points': coords_with_alt,
        })
    return results


def _to_epoch_seconds(ts):
    if isinstance(ts, (int, float, np.integer, np.floating)):
        return float(ts)
    try:
        if isinstance(ts, pd.Timestamp):
            return ts.to_datetime64().astype('datetime64[ns]').astype(np.int64) / 1e9
        return pd.Timestamp(ts).to_datetime64().astype('datetime64[ns]').astype(np.int64) / 1e9
    except Exception:
        return 0.0
