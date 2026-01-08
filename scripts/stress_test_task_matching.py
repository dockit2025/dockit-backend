#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Dockit stress test for electrician task matching (FAS1/FAS2).
- Generates realistic text variants from seeds using an LLM.
- Sends each variant through Dockit endpoints.
- Writes JSONL logs and a deduped admin backlog summary.

No writes to tasks/ATL. Pure read-only testing.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


# -----------------------------
# Helpers
# -----------------------------

def utc_ts() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def norm_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def stable_id(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()[:16]


def backoff_sleep(attempt: int) -> None:
    # 0.5, 1, 2, 4...
    time.sleep(min(8.0, 0.5 * (2 ** attempt)))


# -----------------------------
# LLM generation (OpenAI REST)
# -----------------------------

def openai_generate_variants(
    *,
    api_key: str,
    model: str,
    seed: str,
    n: int,
    temperature: float,
    max_tokens: int = 800,
    timeout_s: int = 60,
) -> List[str]:
    """
    Uses OpenAI Chat Completions-compatible endpoint via HTTPS.
    You can swap base URL if you use another gateway.
    """
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    system = (
        "Du är en svensk elektriker. Skriv många realistiska varianter av en kort arbetsbeskrivning.\n"
        "Krav:\n"
        "- Svenska.\n"
        "- Variera slang, förkortningar, stavfel, ordning, och mängdangivelser.\n"
        "- Skriv EN rad per variant.\n"
        "- Ingen punktlista, inga nummer, inga citationstecken.\n"
        "- Ingen extra text.\n"
    )
    user = (
        f"Seed:\n{seed}\n\n"
        f"Generera exakt {n} varianter av samma jobb. Endast raderna."
    )

    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }

    r = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
    r.raise_for_status()
    data = r.json()
    text = data["choices"][0]["message"]["content"]

    # split lines, strip, dedupe
    lines = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        # guard against accidental bullets
        ln = re.sub(r"^[\-\*\d\.\)\s]+", "", ln).strip()
        if ln:
            lines.append(ln)

    # ensure size n (truncate if too many)
    out = []
    seen = set()
    for ln in lines:
        k = norm_text(ln)
        if k in seen:
            continue
        seen.add(k)
        out.append(ln)
        if len(out) >= n:
            break
    return out


# -----------------------------
# Dockit client
# -----------------------------

@dataclasses.dataclass
class DockitConfig:
    base_url: str
    api_key: str
    timeout_s: int = 60

    def headers(self) -> Dict[str, str]:
        # Backend expects x-dockit-api-key (FastAPI Header)
        return {"x-dockit-api-key": self.api_key, "Content-Type": "application/json"}


def dockit_gpt_extract_segments(cfg: DockitConfig, job_text: str) -> List[Dict[str, Any]]:
    url = f"{cfg.base_url}/sandbox/gpt-extract-segments"
    body = {"job_text": job_text}
    r = requests.post(url, headers=cfg.headers(), json=body, timeout=cfg.timeout_s)
    r.raise_for_status()
    data = r.json()
    segs = data.get("segments") or []
    if not isinstance(segs, list):
        return []
    # expected: [{segment_id, segment_text}]
    return [s for s in segs if isinstance(s, dict) and s.get("segment_text")]


def dockit_gpt_match_tasks(cfg: DockitConfig, segments: List[str]) -> Dict[str, Any]:
    url = f"{cfg.base_url}/sandbox/gpt-match-tasks"
    body = {"segments": segments}
    r = requests.post(url, headers=cfg.headers(), json=body, timeout=cfg.timeout_s)
    r.raise_for_status()
    return r.json()


# -----------------------------
# Classification / backlog build
# -----------------------------

def classify_match(match: Dict[str, Any], threshold: float) -> str:
    """
    Returns: ok | uncertain | no_match
    """
    matched_task_id = (match.get("matched_task_id") or "").strip()
    needs_new_task = match.get("needs_new_task") is True
    conf = float(match.get("confidence") or 0.0)

    if not matched_task_id or needs_new_task:
        return "no_match"
    if conf < threshold:
        return "uncertain"
    return "ok"


def extract_top_candidates(match: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    If backend is extended to include candidates, consume it here.
    Expected optional field: match["candidates"] = [{task_id,label,score,mapping_file}, ...]
    """
    cands = match.get("candidates")
    if not isinstance(cands, list):
        return []
    out = []
    for c in cands[:5]:
        if not isinstance(c, dict):
            continue
        out.append({
            "task_id": c.get("task_id"),
            "label": c.get("label"),
            "score": c.get("score"),
            "mapping_file": c.get("mapping_file"),
        })
    return out


# -----------------------------
# Main
# -----------------------------

def load_seeds(path: Path) -> List[str]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".json"}:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
        raise ValueError("JSON seeds must be a list of strings.")
    # default: one per line
    seeds = []
    for ln in raw.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        seeds.append(ln)
    return seeds


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", required=True, help="Path to seeds file (.txt one per line or .json list)")
    ap.add_argument("--dockit-base", required=True, help="e.g. https://dockit-backend-0tt3.onrender.com")
    ap.add_argument("--dockit-key", required=True, help="Dockit API key")
    ap.add_argument("--openai-key", default=os.getenv("OPENAI_API_KEY", ""), help="OpenAI API key (or env OPENAI_API_KEY)")
    ap.add_argument("--openai-model", default="gpt-4.1-mini", help="Model for variant generation")
    ap.add_argument("--variants-per-seed", type=int, default=30)
    ap.add_argument("--max-seeds", type=int, default=100)
    ap.add_argument("--threshold", type=float, default=0.75, help="Confidence threshold for uncertain")
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--use-fas1", action="store_true", help="Run FAS1 segmentation before FAS2 matching")
    ap.add_argument("--outdir", default="runs", help="Output directory")
    ap.add_argument("--sleep-ms", type=int, default=0, help="Optional sleep between requests")
    args = ap.parse_args()

    seeds_path = Path(args.seeds)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    run_id = utc_ts().replace(":", "").replace("-", "").replace("Z", "")
    log_path = outdir / f"stress_{run_id}.jsonl"
    backlog_path = outdir / f"backlog_{run_id}.json"
    summary_path = outdir / f"summary_{run_id}.json"

    seeds = load_seeds(seeds_path)[: args.max_seeds]
    if not seeds:
        print("No seeds found.", file=sys.stderr)
        return 2

    if not args.openai_key:
        print("Missing OpenAI key. Set --openai-key or env OPENAI_API_KEY.", file=sys.stderr)
        return 2

    dockit = DockitConfig(base_url=args.dockit_base.rstrip("/"), api_key=args.dockit_key)

    seen_variants = set()

    totals = {
        "run_id": run_id,
        "ts_utc": utc_ts(),
        "seeds": len(seeds),
        "variants_per_seed": args.variants_per_seed,
        "threshold": args.threshold,
        "use_fas1": bool(args.use_fas1),
        "generated_total": 0,
        "unique_total": 0,
        "ok": 0,
        "uncertain": 0,
        "no_match": 0,
        "errors": 0,
    }

    # backlog key -> aggregated record
    backlog: Dict[str, Dict[str, Any]] = {}

    with log_path.open("w", encoding="utf-8") as logf:
        for si, seed in enumerate(seeds, start=1):
            variants = openai_generate_variants(
                api_key=args.openai_key,
                model=args.openai_model,
                seed=seed,
                n=args.variants_per_seed,
                temperature=args.temperature,
            )
            totals["generated_total"] += len(variants)

            for v in variants:
                vnorm = norm_text(v)
                if vnorm in seen_variants:
                    continue
                seen_variants.add(vnorm)
                totals["unique_total"] += 1

                try:
                    # optional FAS1
                    segments_texts: List[str]
                    if args.use_fas1:
                        segs = dockit_gpt_extract_segments(dockit, v)
                        segments_texts = [str(s.get("segment_text")).strip() for s in segs if s.get("segment_text")]
                        if not segments_texts:
                            segments_texts = [v]
                    else:
                        segments_texts = [v]

                    # FAS2
                    res = dockit_gpt_match_tasks(dockit, segments_texts)

                    matches = res.get("matches") or []
                    if not isinstance(matches, list):
                        matches = []

                    # Each match corresponds to a segment_id; we log per segment
                    for m in matches:
                        if not isinstance(m, dict):
                            continue
                        status = classify_match(m, args.threshold)
                        totals[status] += 1

                        segment_text = str(m.get("segment_text") or "").strip() or v
                        matched_task_id = (m.get("matched_task_id") or "").strip() or None
                        conf = float(m.get("confidence") or 0.0)

                        top_cands = extract_top_candidates(m)
                        nearest = top_cands[0]["task_id"] if top_cands else (matched_task_id or "unknown")

                        # backlog key: normalize by segment_text + nearest candidate
                        bkey = stable_id(status, norm_text(segment_text), str(nearest))
                        rec = backlog.get(bkey)
                        if rec is None:
                            rec = {
                                "status": status,
                                "nearest_task_id": nearest,
                                "count": 0,
                                "examples": [],
                                "max_confidence": 0.0,
                                "top_candidates": top_cands,  # may be empty until backend provides it
                            }
                            backlog[bkey] = rec

                        rec["count"] += 1
                        rec["max_confidence"] = max(float(rec["max_confidence"]), conf)
                        if len(rec["examples"]) < 5:
                            rec["examples"].append(segment_text)

                        # log event
                        event = {
                            "ts_utc": utc_ts(),
                            "seed": seed,
                            "variant": v,
                            "segment_text": segment_text,
                            "status": status,
                            "matched_task_id": matched_task_id,
                            "confidence": conf,
                            "task_meta": m.get("task_meta"),
                            "top_candidates": top_cands,
                            "raw_match": m,
                        }
                        logf.write(json.dumps(event, ensure_ascii=False) + "\n")

                    if args.sleep_ms > 0:
                        time.sleep(args.sleep_ms / 1000.0)

                except requests.HTTPError as e:
                    totals["errors"] += 1
                    err = {
                        "ts_utc": utc_ts(),
                        "seed": seed,
                        "variant": v,
                        "error": f"http_error: {e}",
                        "response_text": getattr(e.response, "text", "")[:2000] if getattr(e, "response", None) else "",
                    }
                    logf.write(json.dumps(err, ensure_ascii=False) + "\n")
                except Exception as e:
                    totals["errors"] += 1
                    err = {
                        "ts_utc": utc_ts(),
                        "seed": seed,
                        "variant": v,
                        "error": f"error: {e}",
                    }
                    logf.write(json.dumps(err, ensure_ascii=False) + "\n")

            print(f"[{si}/{len(seeds)}] seed done: {seed}")

    # backlog sorting: most frequent misses first
    backlog_list = sorted(backlog.values(), key=lambda r: (-int(r["count"]), r["status"], -float(r["max_confidence"])))

    backlog_path.write_text(json.dumps({
        "run_id": run_id,
        "ts_utc": utc_ts(),
        "threshold": args.threshold,
        "items": backlog_list,
        "note": "top_candidates will be empty unless backend returns candidates per match.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_path.write_text(json.dumps(totals, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK. log={log_path} backlog={backlog_path} summary={summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
