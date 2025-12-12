from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


def _tokens(s: str) -> List[str]:
    return re.findall(r"[a-zåäö0-9]+", (s or "").lower())


def _score_segment_to_task(segment: str, task: Dict[str, Any]) -> Tuple[int, int, int]:
    seg = (segment or "").lower()
    seg_toks = set(_tokens(seg))

    label = str(task.get("label") or "").lower()
    task_id = str(task.get("task_id") or "").lower()

    score = 0

    if label and label in seg:
        score += 50
    if task_id and task_id.replace("_", " ") in seg:
        score += 20

    label_toks = set(_tokens(label))
    score += 5 * len(seg_toks.intersection(label_toks))

    patterns = task.get("patterns") or []
    patt_hits = 0
    best_patt_len = 0
    for p in patterns:
        if not isinstance(p, str):
            continue
        pl = p.lower().strip()
        if not pl:
            continue
        if pl in seg:
            patt_hits += 1
            best_patt_len = max(best_patt_len, len(pl))
        else:
            pt = set(_tokens(pl))
            score += len(seg_toks.intersection(pt))

    score += 10 * patt_hits

    return (score, patt_hits, best_patt_len)


def _select_top_patterns(segment: str, patterns: List[str], max_patterns: int) -> List[str]:
    seg = (segment or "").lower()
    seg_toks = set(_tokens(seg))

    scored: List[Tuple[int, str]] = []
    for p in patterns or []:
        if not isinstance(p, str):
            continue
        pl = p.strip()
        if not pl:
            continue
        pll = pl.lower()
        s = 0
        if pll in seg:
            s += 100
        s += 2 * len(seg_toks.intersection(set(_tokens(pll))))
        s += min(len(pll), 30) // 3
        scored.append((s, pl))

    scored.sort(key=lambda x: x[0], reverse=True)
    out: List[str] = []
    for _, p in scored[:max_patterns]:
        if p not in out:
            out.append(p)
    return out


def build_candidates_by_segment(
    segments: List[Dict[str, Any]],
    all_tasks: List[Dict[str, Any]],
    *,
    max_tasks_per_segment: int = 25,
    max_patterns_per_task: int = 10,
) -> Dict[str, List[Dict[str, Any]]]:
    result: Dict[str, List[Dict[str, Any]]] = {}

    for seg in segments:
        seg_id = str(seg.get("segment_id") or "").strip()
        seg_text = str(seg.get("segment_text") or "").strip()
        if not seg_id or not seg_text:
            continue

        scored_tasks: List[Tuple[Tuple[int, int, int], Dict[str, Any]]] = []
        for t in all_tasks:
            if not isinstance(t, dict):
                continue
            tid = (t.get("task_id") or "").strip()
            if not tid:
                continue
            scored_tasks.append((_score_segment_to_task(seg_text, t), t))

        scored_tasks.sort(key=lambda x: x[0], reverse=True)
        top = [t for _, t in scored_tasks[:max_tasks_per_segment]]

        candidates: List[Dict[str, Any]] = []
        for t in top:
            patterns = t.get("patterns") or []
            patterns_trimmed = _select_top_patterns(seg_text, patterns, max_patterns_per_task)
            candidates.append(
                {
                    "task_id": t.get("task_id"),
                    "label": t.get("label"),
                    "category": t.get("category"),
                    "patterns": patterns_trimmed,
                    "notes": t.get("notes"),
                }
            )

        result[seg_id] = candidates

    return result
