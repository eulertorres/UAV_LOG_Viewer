"""Ferramentas para listar e copiar logs a partir da pasta local do SharePoint."""
from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Sequence

SHAREPOINT_ENSAIOS_FOLDER = "[01] Ensaios"
FLIGHT_FOLDER_RE = re.compile(
    r"^(?P<class>[A-Z]{2})(?P<program>[A-Z0-9]{2})-(?P<date>\d{8})-(?P<flight>\d+)-(?P<serial>[A-Za-z0-9_.-]+)$"
)
SUPPORTED_LOG_EXTS = {".mat", ".log", ".csv"}
CONFIG_DIR = Path.home() / ".config" / "xmobots"
PROGRAMS_ROOT_FILE = CONFIG_DIR / "programs_root.json"
PROGRAMS_ROOT_KEY = "programs_root"


class SharePointCredentialError(RuntimeError):
    """Erro disparado quando a pasta sincronizada não está configurada."""


@dataclass(slots=True)
class SharePointProgram:
    code: str
    name: str
    folder_name: str
    icon_name: str | None = None


@dataclass(slots=True)
class SharePointFlight:
    program: SharePointProgram
    name: str
    relative_path: Path
    serial_folder: str | None
    date: datetime | None
    log_types: tuple[str, ...] = ()

    def local_subpath(self) -> Path:
        parts = [self.program.code]
        if self.serial_folder:
            parts.append(self.serial_folder)
        parts.append(self.name)
        return Path(*parts)

    def human_label(self) -> str:
        date_text = self.date.strftime("%d/%m/%Y") if self.date else "Data desconhecida"
        serial = self.serial_folder or "Serial não identificado"
        log_text = ", ".join(self.log_types) if self.log_types else "Nenhum log reconhecido"
        return f"{self.name} — {serial} — {date_text} — Logs: {log_text}"


DEFAULT_PROGRAMS: Sequence[SharePointProgram] = (
    SharePointProgram(code="FW1000", name="FW1000", folder_name="[00] FW1000", icon_name="fw1000.png"),
    SharePointProgram(code="FW150", name="FW150", folder_name="[01] FW150", icon_name="fw150.png"),
    SharePointProgram(code="FW25", name="FW25", folder_name="[02] FW25", icon_name="fw25.png"),
    SharePointProgram(code="FW7", name="FW7", folder_name="[03] FW7", icon_name="fw7.png"),
    SharePointProgram(code="DJI", name="DJI", folder_name="[04] DJI", icon_name="dji.png"),
    SharePointProgram(code="RW25", name="RW25", folder_name="[06] RW25", icon_name="rw25.png"),
    SharePointProgram(code="SAGRO", name="SAGRO", folder_name="[07] SAGRO", icon_name="sagro.png"),
    SharePointProgram(code="SAMA", name="SAMA", folder_name="[08] SAMA", icon_name="sama.png"),
    SharePointProgram(code="SAMB", name="SAMB", folder_name="[09] SAMB", icon_name="samb.png"),
)


def _dedupe_paths(paths: List[Path]) -> List[Path]:
    seen = set()
    unique: List[Path] = []
    for path in paths:
        resolved = Path(path).expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def _load_saved_programs_root() -> Path | None:
    if PROGRAMS_ROOT_FILE.exists():
        try:
            payload = json.loads(PROGRAMS_ROOT_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        saved = payload.get(PROGRAMS_ROOT_KEY)
        if saved:
            candidate = Path(saved).expanduser()
            if candidate.exists():
                return candidate
    return None


def _default_programs_root_candidates() -> List[Path]:
    candidates: List[Path] = []
    env_dir = os.environ.get("XMOBOTS_PROGRAMS_DIR")
    if env_dir:
        candidates.append(Path(env_dir))

    saved = _load_saved_programs_root()
    if saved:
        candidates.append(saved)

    home = Path.home()
    onedrive_hints = [
        "OneDrive - XMOBOTS AEROESPACIAL E DEFESA LTDA",
        "OneDrive - XMOBOTS AEROSPACIAL E DEFESA LTDA",
        "OneDrive - XMOBOTS AEROSPACEIAL E DEFESA LTDA",
    ]
    for hint in onedrive_hints:
        base = home / hint
        candidates.append(base / "Departamento de Ensaios em voo" / "[00] PROGRAMAS")
        candidates.append(base / "[00] PROGRAMAS")

    for folder in home.glob("OneDrive*XMOBOTS*"):
        candidates.append(folder / "Departamento de Ensaios em voo" / "[00] PROGRAMAS")
        candidates.append(folder / "[00] PROGRAMAS")

    candidates.append(home / "Departamento de Ensaios em voo" / "[00] PROGRAMAS")
    candidates.append(home / "[00] PROGRAMAS")

    deduped = _dedupe_paths([c for c in candidates if c])
    print("[debug][programs_root] Candidatos detectados:")
    for candidate in deduped:
        print(f"  - {candidate}")
    return deduped


def _save_programs_root(path: Path) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {PROGRAMS_ROOT_KEY: str(path)}
    PROGRAMS_ROOT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class SharePointClient:
    """Cliente simples que trabalha sobre a pasta local sincronizada."""

    def __init__(self, programs_root: Path | None = None):
        self.programs_root: Path | None = None
        if programs_root:
            self.set_programs_root(programs_root, persist=False)
        else:
            for candidate in _default_programs_root_candidates():
                if candidate.exists():
                    self.programs_root = candidate
                    print(f"[debug][init] Usando pasta sincronizada detectada: {candidate}")
                    break

    def has_valid_programs_root(self) -> bool:
        return self.programs_root is not None and self.programs_root.exists()

    def require_programs_root(self) -> Path:
        if not self.has_valid_programs_root():
            raise SharePointCredentialError(
                "Selecione a pasta '[00] PROGRAMAS' sincronizada com o SharePoint no OneDrive."
            )
        return Path(self.programs_root)

    def set_programs_root(self, path: Path, persist: bool = True) -> None:
        resolved = Path(path).expanduser()
        if not resolved.exists() or not resolved.is_dir():
            raise FileNotFoundError(f"Pasta inválida: {resolved}")
        print(f"[debug][set_programs_root] Configurando pasta raiz para {resolved}")
        self.programs_root = resolved
        if persist:
            _save_programs_root(resolved)

    def list_flights(self, program: SharePointProgram) -> List[SharePointFlight]:
        root = self.require_programs_root()
        ensaios_path = root / program.folder_name / SHAREPOINT_ENSAIOS_FOLDER
        print(f"[debug][list_flights] Programa: {program.code}")
        print(f"[debug][list_flights] Raiz dos programas: {root}")
        print(f"[debug][list_flights] Pasta de ensaios esperada: {ensaios_path}")
        flights: List[SharePointFlight] = []
        if not ensaios_path.exists():
            print("[debug][list_flights] Pasta de ensaios inexistente ou inacessível")
            return flights
        self._walk_program(program, root, ensaios_path, None, flights, ensaios_path)
        print(f"[debug][list_flights] Total de voos encontrados: {len(flights)}")
        flights.sort(key=lambda flight: (flight.date or datetime.min), reverse=True)
        return flights

    def _walk_program(
        self,
        program: SharePointProgram,
        root: Path,
        folder_path: Path,
        serial_hint: str | None,
        flights: List[SharePointFlight],
        ensaios_root: Path,
    ) -> None:
        if not folder_path.exists():
            print(f"[debug][_walk_program] Ignorando pasta inexistente: {folder_path}")
            return
        try:
            entries = sorted(folder_path.iterdir())
        except PermissionError:
            print(f"[debug][_walk_program] Sem permissão para acessar: {folder_path}")
            return

        print(f"[debug][_walk_program] Varredura em: {folder_path}")
        for entry in entries:
            kind = "dir" if entry.is_dir() else "file"
            print(f"  [debug][_walk_program] Encontrado {kind}: {entry.name}")
            if not entry.is_dir():
                continue
            name = entry.name
            match = FLIGHT_FOLDER_RE.match(name)
            if match:
                date = datetime.strptime(match.group("date"), "%Y%m%d")
                print(f"  [debug][_walk_program] Pasta de voo detectada por padrão: {name}")
                has_logs, log_types = self._folder_log_types(entry)
                flights.append(
                    SharePointFlight(
                        program=program,
                        name=name,
                        relative_path=entry.relative_to(root),
                        serial_folder=serial_hint,
                        date=date,
                        log_types=tuple(sorted(log_types)) if has_logs else tuple(),
                    )
                )
                if not has_logs:
                    print(
                        "  [debug][_walk_program] Pasta encaixa no padrão de voo, mas nenhum log foi "
                        "identificado; mantendo na lista com tipos vazios."
                    )
                continue

            has_logs, log_types = self._folder_log_types(entry)
            if has_logs:
                inferred_date = self._infer_date_from_name(name)
                print(
                    "  [debug][_walk_program] Pasta tratada como voo por conter logs: "
                    f"{name} (data inferida: {inferred_date})"
                )
                flights.append(
                    SharePointFlight(
                        program=program,
                        name=name,
                        relative_path=entry.relative_to(root),
                        serial_folder=serial_hint,
                        date=inferred_date,
                        log_types=tuple(sorted(log_types)),
                    )
                )
                if folder_path == ensaios_root:
                    # A pasta parece conter logs, mas pode agrupar vários voos; continue explorando.
                    print(
                        "  [debug][_walk_program] Descendo para identificar voos dentro do serial/agenda "
                        f"{name}"
                    )
                else:
                    continue

            next_serial = serial_hint
            if folder_path == ensaios_root or name.upper().startswith("NS"):
                next_serial = name
            self._walk_program(program, root, entry, next_serial, flights, ensaios_root)

    def _folder_log_types(self, folder: Path) -> tuple[bool, set[str]]:
        try:
            found_types: set[str] = set()
            for candidate in folder.rglob("*"):
                if not candidate.is_file():
                    continue
                suffix = candidate.suffix.lower()
                if suffix in SUPPORTED_LOG_EXTS:
                    print(f"  [debug][_walk_program] Arquivo de log identificado: {candidate}")
                    found_types.add(suffix)
            return (len(found_types) > 0, found_types)
        except PermissionError:
            print(f"  [debug][_walk_program] Sem permissão para inspecionar logs em: {folder}")
        return (False, set())

    def _infer_date_from_name(self, name: str) -> datetime | None:
        date_match = re.search(r"(\d{8})", name)
        if not date_match:
            return None
        try:
            return datetime.strptime(date_match.group(1), "%Y%m%d")
        except ValueError:
            return None

    def download_flight(
        self,
        flight: SharePointFlight,
        destination_root: Path,
        progress_callback: Callable[[str], None] | None = None,
    ) -> Path:
        root = self.require_programs_root()
        source_dir = root / flight.relative_path
        print(f"[debug][download_flight] Copiando voo {flight.name}")
        print(f"[debug][download_flight] Origem: {source_dir}")
        if not source_dir.exists():
            raise FileNotFoundError(f"Voo não encontrado em {source_dir}")
        target_dir = destination_root / flight.local_subpath()
        print(f"[debug][download_flight] Destino: {target_dir}")
        self._copy_logs_only(source_dir, target_dir, progress_callback)
        return target_dir

    def _copy_logs_only(
        self,
        source: Path,
        destination: Path,
        progress_callback: Callable[[str], None] | None,
    ) -> bool:
        """Copia apenas arquivos suportados preservando subpastas.

        Retorna True se ao menos um arquivo elegível foi copiado.
        """

        copied_any = False
        print(f"[debug][_copy_logs_only] Varredura: {source}")
        for entry in source.iterdir():
            target = destination / entry.name
            if entry.is_dir():
                copied_child = self._copy_logs_only(entry, target, progress_callback)
                copied_any = copied_any or copied_child
                continue

            if not entry.is_file():
                continue

            suffix = entry.suffix.lower()
            if suffix not in SUPPORTED_LOG_EXTS:
                print(f"  [debug][_copy_logs_only] Ignorando arquivo não suportado: {entry}")
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            print(f"  [debug][_copy_logs_only] Copiando arquivo de log: {entry} -> {target}")
            shutil.copy2(entry, target)
            copied_any = True
            if progress_callback:
                progress_callback(entry.name)

        return copied_any


def available_programs() -> Sequence[SharePointProgram]:
    return DEFAULT_PROGRAMS
