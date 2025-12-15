from __future__ import annotations

import re
from typing import Any, Dict, List

from src.services.ai_client import AIClient
from src.services.ai_specs import load_atl_rank_spec
from src.services.ai_suggestions import find_atl_candidates_for_segment


def _norm(s: str) -> str:
    return str(s or "").strip().lower()


def _segment_mentions_cable(segment_text: str) -> bool:
    """
    Returnerar True om segmentet tydligt handlar om kabeldragning som huvudmoment.
    Exempel: 'dra 6 meter 3g1,5', 'kabeldragning', 'dra kabel'.
    """
    t = _norm(segment_text)
    if not t:
        return False

    # tydliga kabelord
    cable_words = [
        "kabeldragning",
        "dra kabel",
        "drag kabel",
        "förlägg kabel",
        "forlagg kabel",
        "kabel i rör",
        "kabel i ror",
        "dra 3g",
        "dra 5g",
    ]
    if any(w in t for w in cable_words):
        return True

    # "dra <tal> m/meter" + kabeltyp (t.ex. 3g1,5)
    if re.search(r"\bdra\b.*\b(\d+)\s*(m|meter)\b", t) and re.search(r"\b[35]g\s*\d", t):
        return True

    return False


def _is_outlet_task(task: Dict[str, Any], segment_text: str) -> bool:
    """
    Klassificera om detta är ett 'uttag/dosa/strömbrytare'-jobb där kabelmoment
    normalt inte ska vinna om segmentet inte uttryckligen handlar om kabeldragning.
    """
    cat = _norm(task.get("category") or "")
    tid = _norm(task.get("task_id") or "")
    lbl = _norm(task.get("label") or "")
    seg = _norm(segment_text)

    # Styr främst av category/task_id/label
    if cat in {"brytare_och_uttag"}:
        return True

    # fallback heuristik
    outlet_words = ["vägguttag", "vagguttag", "uttag", "strömbrytare", "strombrytare", "dosa", "apparatdosa"]
    if any(w in tid for w in outlet_words):
        return True
    if any(w in lbl for w in outlet_words):
        return True
    if any(w in seg for w in outlet_words):
        return True

    return False


def _filter_candidates_for_intent(
    *,
    task: Dict[str, Any],
    segment_text: str,
    candidates: List[Any],
) -> List[Any]:
    """
    Filtrerar bort 'fel typ' av ATL-rader innan GPT får se dem.

    Princip:
    - Om task/segment avser uttag/dosa och segmentet inte explicit nämner kabeldragning:
      filtrera bort kabelmoment (enhet m kabel, moment_text innehåller 'kabeldragning', etc.)
    - Om segmentet explicit handlar om kabeldragning: behåll kabelmoment.
    """
    seg = _norm(segment_text)
    mentions_cable = _segment_mentions_cable(seg)
    is_outlet = _is_outlet_task(task, seg)

    if not is_outlet:
        # inga extra filter än (kan utökas senare per kategori)
        return candidates

    if mentions_cable:
        # Uttagsjobb men segmentet handlar explicit om kabeldragning -> tillåt kabelmoment
        return candidates

    filtered: List[Any] = []
    for r in candidates:
        # ATLRow-objekt från ai_suggestions har attributen moment_text/underlag_text/enhet
        moment_text = _norm(getattr(r, "moment_text", "") or "")
        underlag_text = _norm(getattr(r, "underlag_text", "") or "")
        enhet = _norm(getattr(r, "enhet", "") or "")

        # filtrera bort kabeldragning per meter
        if "m kabel" in enhet:
            continue
        if "kabeldragning" in moment_text:
            continue
        if moment_text.startswith("kabel"):
            continue
        # filtrera bort tydliga "kabel i ..." även om enhet inte säger m kabel
        if "kabel" in moment_text and "vägguttag" not in moment_text and "uttag" not in moment_text:
            continue
        if "kabel" in underlag_text and "vägguttag" not in moment_text and "uttag" not in moment_text:
            # underlag nämner kabel men momentet handlar inte om uttag
            continue

        filtered.append(r)

    return filtered


def suggest_atl_ref_for_task(
    *,
    task: Dict[str, Any],
    segment_text: str,
    max_rows: int = 25,
    min_score: float = 0.01,
) -> Dict[str, Any]:
    """
    Admin-only: Föreslå ATL-referens (moment_id + variant) för en task,
    baserat på text + top-kandidater från ATL-listan.

    Robusthet:
    - Vi hämtar fler kandidater än max_rows först (för att kunna filtrera),
    - filtrerar enligt intent,
    - tar sedan top max_rows.
    """
    spec = load_atl_rank_spec()
    client = AIClient()

    # Hämta fler kandidater först så att vi har något kvar efter filtrering
    initial_max = max(10, int(max_rows) * 4)

    raw_candidates = find_atl_candidates_for_segment(
        segment_text=segment_text,
        max_rows=initial_max,
        min_score=min_score,
    )

    filtered_candidates = _filter_candidates_for_intent(
        task=task,
        segment_text=segment_text,
        candidates=raw_candidates,
    )

    # Om vi filtrerade bort allt: fallback till raw (hellre något än inget)
    candidates_final = (filtered_candidates or raw_candidates)[: int(max_rows)]

    atl_candidates: List[Dict[str, Any]] = []
    for r in candidates_final:
        atl_candidates.append(
            {
                "moment_id": r.id_str,
                "arbetsmoment": r.arbetsmoment,
                "moment_text": r.moment_text,
                "underlag_text": r.underlag_text,
                "enhet": r.enhet,
                "times": r.times,
            }
        )

    gpt_input: Dict[str, Any] = {
        "task": {
            "task_id": task.get("task_id"),
            "label": task.get("label"),
            "category": task.get("category"),
        },
        "segment_text": segment_text,
        "atl_candidates": atl_candidates,
    }

    result = client.generate_atl_rank(spec=spec, gpt_input=gpt_input)

    # Lägg på debug-metadata (Sandbox-only) så du kan se att filtrering skett
    result["candidate_stats"] = {
        "raw_count": len(raw_candidates),
        "filtered_count": len(filtered_candidates),
        "final_count": len(candidates_final),
        "filter_applied": _is_outlet_task(task, segment_text) and not _segment_mentions_cable(segment_text),
    }

    return result
