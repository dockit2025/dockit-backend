from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Projektrot, t.ex. D:\dockit-ai
ROOT = Path(__file__).resolve().parents[2]

# Här förväntar vi oss work_profiles.yaml
WORK_PROFILES_PATH = ROOT / "knowledge" / "catalogs" / "work_profiles.yaml"


@lru_cache(maxsize=1)
def _load_raw_work_profiles_yaml() -> Any:
    """
    Läser YAML-filen med arbetsprofiler en gång och cache:ar resultatet.
    Returnerar den råa YAML-strukturen (dict eller list).
    """
    if not WORK_PROFILES_PATH.exists():
        return {}

    try:
        with WORK_PROFILES_PATH.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        # Vi vill inte krascha om YAML är trasig – då beter vi oss bara som
        # om inga profiler finns.
        return {}

    return data


def load_work_profiles() -> List[Dict[str, Any]]:
    """
    Returnerar en normaliserad lista med profiler.

    Stödjer två vanliga YAML-strukturer:

      1) Top-nivå dict med "profiles": [ {...}, {...} ]
      2) Top-nivå lista: [ {...}, {...} ]

    Varje profil får minst:
      - id (om saknas genereras ett tekniskt id)
      - matches (dict, kan vara tom)
      - tasks (lista, kan vara tom)
    """
    raw = _load_raw_work_profiles_yaml()

    profiles: List[Dict[str, Any]] = []

    if isinstance(raw, dict):
        src = raw.get("profiles") or []
    elif isinstance(raw, list):
        src = raw
    else:
        src = []

    # Stöd både:
    #   profiles: [ {...}, {...} ]
    #   profiles: { key1: {...}, key2: {...} }
    if isinstance(src, dict):
        src = list(src.values())

    if not isinstance(src, list):
        return profiles

    for idx, item in enumerate(src):
        if not isinstance(item, dict):
            continue

        profile = dict(item)
        if not profile.get("id"):
            profile["id"] = f"profile_{idx}"

        # Säkerställ att matches/tasks alltid finns
        if not isinstance(profile.get("matches"), dict):
            profile["matches"] = {}
        if not isinstance(profile.get("tasks"), list):
            profile["tasks"] = []

        profiles.append(profile)

    return profiles


def find_profiles_for_material(
    material_ref: str,
    *,
    environment: Optional[str] = None,
    work_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Hittar alla profiler som matchar ett visst material_ref,
    med enkel prioritering på environment och work_type.

    Strategi:
      1) Filtrera bort profiler där matches.material_ref inte matchar.
      2) Beräkna score per profil:
           +2 om environment (om anges) matchar exakt
           +1 om work_type (om anges) matchar exakt
      3) Sortera profiler efter score (högst först), men returnera alla.

    Alla jämförelser görs case-insensitive.
    """
    material_ref_norm = (material_ref or "").strip().lower()
    env_norm = (environment or "").strip().lower() if environment else None
    work_type_norm = (work_type or "").strip().lower() if work_type else None

    if not material_ref_norm:
        return []

    candidates: List[Dict[str, Any]] = []

    for profile in load_work_profiles():
        matches = profile.get("matches") or {}
        if not isinstance(matches, dict):
            continue

        m_ref = (
            matches.get("material_ref")
            or matches.get("material")
            or matches.get("ref")
            or ""
        )
        m_ref_norm = str(m_ref).strip().lower()

        if m_ref_norm != material_ref_norm:
            continue

        score = 0

        if env_norm:
            p_env = (matches.get("environment") or "").strip().lower()
            if p_env == env_norm:
                score += 2

        if work_type_norm:
            p_work = (matches.get("work_type") or "").strip().lower()
            if p_work == work_type_norm:
                score += 1

        candidates.append(
            {
                **profile,
                "_match_score": score,
            }
        )

    # Sortera på score (högst först), stabil sort så att YAML-ordning
    # bibehålls när score är lika.
    candidates.sort(key=lambda p: p.get("_match_score", 0), reverse=True)

    # Ta bort den interna score-nyckeln innan vi returnerar
    for c in candidates:
        c.pop("_match_score", None)

    return candidates


def find_best_profile_for_material(
    material_ref: str,
    *,
    environment: Optional[str] = None,
    work_type: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Bekvämlighetsfunktion: returnerar den "bästa" profilen,
    dvs första elementet från find_profiles_for_material, eller None.
    """
    profiles = find_profiles_for_material(
        material_ref=material_ref,
        environment=environment,
        work_type=work_type,
    )
    return profiles[0] if profiles else None


if __name__ == "__main__":
    # Enkel manuell test om man kör filen direkt.
    import json

    print("Laddade profiler:")
    print(json.dumps(load_work_profiles(), ensure_ascii=False, indent=2))

    print("\nExempel: hitta profiler för material_ref='VP-ROR-20', environment='infalt', work_type='socket'")
    best = find_best_profile_for_material(
        "VP-ROR-20",
        environment="infalt",
        work_type="socket",
    )
    print(json.dumps(best, ensure_ascii=False, indent=2))




