from __future__ import annotations

"""
ATL Apply (Sandbox admin-only)

Syfte:
- Preview och Confirm för att skriva vald ATL-referens till rätt mapping-fil för en befintlig task.
- Måste vara defensiv: bevara struktur så långt som möjligt, validera, backup före write.
- Får ALDRIG skriva utan explicit confirm från admin.

Denna modul är endast för Steg C i Sandbox (admin).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml

ROOT = Path(__file__).resolve().parents[2]
MAPPINGS_DIR = ROOT / "mappings"


def _validate_mapping_filename(mapping_file: str) -> str:
    """
    Tillåt endast filnamn (inga path-delar). Ex: 'ror_och_vp.yaml'
    """
    name = str(mapping_file or "").strip()
    if not name:
        raise ValueError("mapping_file krävs")

    # path traversal / separators
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError("Ogiltigt mapping_file (path traversal)")

    if not name.endswith(".yaml"):
        raise ValueError("mapping_file måste sluta med .yaml")

    return name


def resolve_mapping_path(mapping_file: str) -> Path:
    """
    Returnerar absolut path till mappingfilen (mappings/<file>), efter validering.
    """
    filename = _validate_mapping_filename(mapping_file)
    path = MAPPINGS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Mapping-fil hittades inte: {path}")
    return path


def load_mapping_yaml(path: Path) -> Any:
    """
    Läser YAML med safe_load. (Ingen write i denna funktion.)
    Returnerar root-objektet (dict/list/None).
    """
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def find_task_in_mapping(*, mapping_root: Any, task_id: str) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    Letar upp en task med task_id i en mapping.

    Returnerar:
      (task_dict_or_none, meta)

    meta innehåller:
      - tasks_container_type: "list" | "dict" | "unknown"
      - found: bool
      - task_id: str
    """
    tid = str(task_id or "").strip()
    if not tid:
        raise ValueError("task_id krävs")

    meta: Dict[str, Any] = {
        "task_id": tid,
        "found": False,
        "tasks_container_type": "unknown",
    }

    # Case 1: root är dict med "tasks"
    if isinstance(mapping_root, dict) and "tasks" in mapping_root:
        tasks_obj = mapping_root.get("tasks")

        # tasks: [ {...}, {...} ]
        if isinstance(tasks_obj, list):
            meta["tasks_container_type"] = "list"
            for t in tasks_obj:
                if not isinstance(t, dict):
                    continue
                if str(t.get("task_id") or "").strip() == tid:
                    meta["found"] = True
                    return t, meta
            return None, meta

        # tasks: { task_id: {...}, ... }
        if isinstance(tasks_obj, dict):
            meta["tasks_container_type"] = "dict"
            tdef = tasks_obj.get(tid)
            if isinstance(tdef, dict):
                meta["found"] = True
                out = dict(tdef)
                out.setdefault("task_id", tid)
                return out, meta
            return None, meta

        return None, meta

    # Case 2: root är lista (implicit tasks-list)
    if isinstance(mapping_root, list):
        meta["tasks_container_type"] = "list"
        for t in mapping_root:
            if not isinstance(t, dict):
                continue
            if str(t.get("task_id") or "").strip() == tid:
                meta["found"] = True
                return t, meta
        return None, meta

    return None, meta


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup_mapping_file(path: Path) -> Path:
    """
    Skapar backup i samma mapp: <file>.bak.<timestamp>
    """
    stamp = _utc_stamp()
    backup_path = path.with_name(path.name + f".bak.{stamp}")
    backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup_path


def _write_yaml_preserve_shape(path: Path, root_obj: Any) -> None:
    """
    Skriver YAML tillbaka med samma "root-shape" (dict/list).
    Vi kan inte bevara kommentarer med PyYAML, men vi försöker bevara struktur + nyckelordning.
    """
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(root_obj, f, allow_unicode=True, sort_keys=False, indent=2)


def _set_task_fields(task: Dict[str, Any], *, moment_text: str, variant: int) -> None:
    """
    Muterar task-dict:
    - time_source -> atl
    - atl_refs -> [{moment: <moment_text>, variant: <variant>}]
    - manual_time_minutes_per_unit -> 0 (för att matcha andra ATL-kopplade tasks)
    """
    task["time_source"] = "atl"
    task["atl_refs"] = [{"moment": str(moment_text), "variant": int(variant)}]
    task["manual_time_minutes_per_unit"] = 0


def apply_atl_ref_to_mapping_root(
    *,
    mapping_root: Any,
    task_id: str,
    moment_text: str,
    variant: int,
) -> Dict[str, Any]:
    """
    Applicerar ATL-ref i mapping_root (in-memory). Ingen write här.

    Returnerar meta:
      - updated: bool
      - tasks_container_type
    """
    tid = str(task_id or "").strip()
    if not tid:
        raise ValueError("task_id krävs")

    # dict root with tasks
    if isinstance(mapping_root, dict) and "tasks" in mapping_root:
        tasks_obj = mapping_root.get("tasks")

        # tasks list
        if isinstance(tasks_obj, list):
            for t in tasks_obj:
                if not isinstance(t, dict):
                    continue
                if str(t.get("task_id") or "").strip() == tid:
                    _set_task_fields(t, moment_text=moment_text, variant=variant)
                    return {"updated": True, "tasks_container_type": "list"}
            return {"updated": False, "tasks_container_type": "list"}

        # tasks dict
        if isinstance(tasks_obj, dict):
            tdef = tasks_obj.get(tid)
            if isinstance(tdef, dict):
                _set_task_fields(tdef, moment_text=moment_text, variant=variant)
                return {"updated": True, "tasks_container_type": "dict"}
            return {"updated": False, "tasks_container_type": "dict"}

        return {"updated": False, "tasks_container_type": "unknown"}

    # root list
    if isinstance(mapping_root, list):
        for t in mapping_root:
            if not isinstance(t, dict):
                continue
            if str(t.get("task_id") or "").strip() == tid:
                _set_task_fields(t, moment_text=moment_text, variant=variant)
                return {"updated": True, "tasks_container_type": "list"}
        return {"updated": False, "tasks_container_type": "list"}

    return {"updated": False, "tasks_container_type": "unknown"}


def confirm_apply_atl_ref(
    *,
    task_id: str,
    mapping_file: str,
    moment_text: str,
    variant: int,
) -> Dict[str, Any]:
    """
    CONFIRM = faktisk write:
    - validera + ladda mapping
    - backup
    - applicera in-memory
    - write tillbaka
    - re-read + verify att tasken nu har atl_refs/time_source
    """
    path = resolve_mapping_path(mapping_file)
    root = load_mapping_yaml(path)

    # skapa backup först
    backup_path = backup_mapping_file(path)

    meta_apply = apply_atl_ref_to_mapping_root(
        mapping_root=root,
        task_id=task_id,
        moment_text=moment_text,
        variant=variant,
    )
    if not meta_apply.get("updated"):
        raise ValueError(f"task_id '{task_id}' hittades inte i {mapping_file}")

    _write_yaml_preserve_shape(path, root)

    # re-read verify
    reread = load_mapping_yaml(path)
    task_after, _meta = find_task_in_mapping(mapping_root=reread, task_id=task_id)
    if not task_after:
        raise ValueError("Efter write: tasken hittades inte vid verifiering (oväntat).")

    tsrc = str(task_after.get("time_source") or "").strip().lower()
    atl_refs = task_after.get("atl_refs")

    if tsrc != "atl":
        raise ValueError("Efter write: time_source blev inte 'atl'.")

    if not isinstance(atl_refs, list) or not atl_refs:
        raise ValueError("Efter write: atl_refs saknas eller är tom.")

    return {
        "status": "ok",
        "mapping_file": mapping_file,
        "mapping_path": str(path),
        "backup_path": str(backup_path),
        "task_id": task_id,
        "tasks_container_type": meta_apply.get("tasks_container_type"),
    }
