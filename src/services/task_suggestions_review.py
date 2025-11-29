from __future__ import annotations

import sys
from pathlib import Path

# Se till att projektroten finns i sys.path (så "src" hittas)
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json
from typing import Any, Dict, List

# Projektrot
ROOT = Path(__file__).resolve().parents[2]

# Paths
MAPPINGS_DIR = ROOT / "mappings"
LOG_DIR = ROOT / "knowledge" / "logs"

# Importera funktioner från vårt nuvarande system
from src.services.task_suggestions import (
    log_task_suggestions,
    apply_suggested_tasks,
)

import yaml


def load_gpt_output(json_path: str | Path) -> Dict[str, Any]:
    """
    Läser GPT-output från en JSON-fil.
    Filformatet ska innehålla:
      {
        "suggested_tasks": [ ... ]
      }
    """
    p = Path(json_path)
    if not p.exists():
        raise FileNotFoundError(f"Kan inte hitta GPT-output: {p}")

    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict) or "suggested_tasks" not in data:
        raise ValueError("GPT-output saknar expected key 'suggested_tasks'.")

    return data


def load_existing_tasks() -> List[Dict[str, Any]]:
    """
    Läser in tasks från alla YAML-mappingfiler i mappen /mappings.
    Returnerar en lista med dictar.
    """
    tasks: List[Dict[str, Any]] = []

    for yfile in MAPPINGS_DIR.glob("*.yaml"):
        try:
            with yfile.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            continue

        # Stöd för både:
        # tasks: [ ... ]
        # tasks: { task_id: {...}, ... }
        # och hela filen som lista
        raw = None

        if isinstance(data, dict) and "tasks" in data:
            raw = data["tasks"]
        elif isinstance(data, list):
            raw = data
        else:
            continue

        if isinstance(raw, list):
            for t in raw:
                if isinstance(t, dict):
                    tasks.append(t)

        elif isinstance(raw, dict):
            for tid, t in raw.items():
                if isinstance(t, dict):
                    t2 = dict(t)
                    t2.setdefault("task_id", tid)
                    tasks.append(t2)

    return tasks


def find_similar_tasks(new_task: Dict[str, Any], existing_tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Hittar liknande tasks i befintliga YAML-filer.
    Detta används i review-flödet för att undvika dubbletter.

    Regler (enkla men mycket effektiva):
      - Samma kategori → +1
      - Liknande label/titel (case-insensitive substring match) → +1
      - Delade ord mellan patterns → +1
    Tasks med totalt score >= 2 inkluderas.
    """
    # Stöd både för nya (title_sv) och gamla (label) fält
    label_new = (new_task.get("label") or new_task.get("title_sv") or "").lower()
    cat_new = (new_task.get("category") or "").lower()
    pats_new = [p.lower() for p in new_task.get("patterns", []) if isinstance(p, str)]

    results: List[Dict[str, Any]] = []

    for t in existing_tasks:
        score = 0

        label_old = (t.get("label") or t.get("title_sv") or "").lower()
        cat_old = (t.get("category") or "").lower()
        pats_old = [p.lower() for p in t.get("patterns", []) if isinstance(p, str)]

        # 1. Matcha kategori
        if cat_new and cat_new == cat_old:
            score += 1

        # 2. Liknande label/titel
        if (label_new and label_new in label_old) or (label_old and label_old in label_new):
            score += 1

        # 3. Ord som överlappar mellan patterns
        words_new = set(" ".join(pats_new).split())
        words_old = set(" ".join(pats_old).split())

        if words_new and words_old and len(words_new.intersection(words_old)) > 0:
            score += 1

        if score >= 2:
            results.append(t)

    return results


def print_task_review(new_task: Dict[str, Any], similar: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 70)
    print(" GPT-FÖRSLAG – NY TASK".center(70))
    print("=" * 70)

    task_id = new_task.get("task_id") or new_task.get("task_ref")
    title = new_task.get("title_sv") or new_task.get("label") or ""
    desc = new_task.get("description_sv") or new_task.get("description") or ""

    print(f"Task ID:   {task_id}")
    print(f"Titel:     {title}")
    print(f"Kategori:  {new_task.get('category', '')}")
    print("Beskrivning:")
    print(f"  {desc.strip()}")

    print("\nPatterns:")
    for p in new_task.get("patterns", []):
        print(f"  - {p}")

    print("\nMaterials:")
    for m in new_task.get("materials", new_task.get("default_materials", [])):
        print(f"  - {m}")

    print("\nConfidence:", new_task.get("confidence") or new_task.get("gpt_confidence"))

    if not similar:
        print("\nInga liknande tasks hittades i YAML-filer.")
        return

    print("\n" + "-" * 70)
    print(" LIKNANDE BEFINTLIGA TASKS ".center(70, "-"))
    print("-" * 70)

    for t in similar:
        print(f"\nTask ID:  {t.get('task_id')}")
        print(f"Label:    {t.get('label')}")
        print(f"Kategori: {t.get('category')}")
        print("Patterns:")
        for p in t.get("patterns", []):
            print(f"  - {p}")


def prompt_user_choice() -> str:
    """
    Frågar användaren om vi ska acceptera, avvisa eller editera tasken.
    Returnerar: "accept" / "reject" / "edit".
    """
    while True:
        print("\nVad vill du göra?")
        print("  [A] Acceptera och skriva in i YAML")
        print("  [R] Avvisa (inget sparas)")
        print("  [E] Editera task innan sparning")
        val = input("Val: ").strip().lower()

        if val in ("a", "accept"):
            return "accept"
        if val in ("r", "reject"):
            return "reject"
        if val in ("e", "edit"):
            return "edit"

        print("Ogiltigt val, försök igen.")


def edit_task_interactively(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Låter användaren editera grundläggande textfält innan sparning.
    Returnerar en ny task-dict.
    """
    print("\n--- Redigera task (lämna tomt för att behålla värdet) ---")

    new = dict(task)

    # Titel (title_sv/label)
    old_title = new.get("title_sv") or new.get("label") or ""
    print("\nTitel:")
    print(f"Nuvarande: {old_title}")
    inp = input("Nytt värde: ").strip()
    if inp:
        new["title_sv"] = inp
        new["label"] = inp

    # Beskrivning (description_sv/description)
    old_desc = new.get("description_sv") or new.get("description") or ""
    print("\nBeskrivning:")
    print(f"Nuvarande: {old_desc}")
    inp = input("Nytt värde: ").strip()
    if inp:
        new["description_sv"] = inp
        new["description"] = inp

    # Kategori
    old_cat = new.get("category") or ""
    print("\nKategori:")
    print(f"Nuvarande: {old_cat}")
    inp = input("Nytt värde: ").strip()
    if inp:
        new["category"] = inp

    # Editera patterns
    pats = new.get("patterns", [])
    print("\nPatterns (matchningsfraser):")
    print("Nuvarande:")
    for p in pats:
        print("  -", p)

    inp = input("\nVill du skriva in en HELT ny lista? (j/n): ").strip().lower()
    if inp == "j":
        print("Skriv ett pattern per rad. Tom rad avslutar:")
        new_pats = []
        while True:
            line = input("> ").strip()
            if not line:
                break
            new_pats.append(line)
        if new_pats:
            new["patterns"] = new_pats

    return new


def make_dedup_key(task: Dict[str, Any]) -> str:
    """
    Bygger en enkel nyckel för att upptäcka dubbletter under EN körning.
    Vi kombinerar task_id / task_ref, titel och kategori (lowercase).
    """
    parts: List[str] = []

    for key in ("task_id", "task_ref", "title_sv", "label", "category"):
        val = task.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val.strip().lower())

    # Fallback: om allt ovan saknas, använd patterns som sista utväg
    if not parts:
        pats = task.get("patterns") or []
        if isinstance(pats, list) and pats:
            joined = " ".join(
                [p for p in pats if isinstance(p, str)]
            ).strip().lower()
            if joined:
                parts.append(joined)

    return " | ".join(parts)


def review_and_process(gpt_json_path: str):
    """
    Kör hela review-flödet:
      1. Läs GPT-output
      2. Jämför mot existerande tasks
      3. Visa diff/review
      4. Fråga användaren
      5. Acceptera/avvisa/editera
    """
    gpt_data = load_gpt_output(gpt_json_path)
    suggested = gpt_data["suggested_tasks"]

    existing = load_existing_tasks()

    print("\n\n========== STARTAR TASK-REVIEW ==========\n")

    # Bygg nycklar för alla befintliga tasks i YAML
    existing_keys = set()
    existing_ids = set()
    for t in existing:
        ek = make_dedup_key(t)
        if ek:
            existing_keys.add(ek)
        tid = (t.get("task_id") or t.get("task_ref") or "").strip().lower()
        if tid:
            existing_ids.add(tid)

    # Task-id:n som vi *aldrig* vill se som GPT-förslag igen
    IGNORE_TASK_IDS = {"lagga-kabelkanal", "lagga-vp-ror"}

    # DEBUG: visa lite info om vad vi ser
    print("DEBUG: antal befintliga tasks i YAML:", len(existing))
    print("DEBUG: antal unika existing_ids:", len(existing_ids))
    print("DEBUG: innehåller 'lagga-kabelkanal'?:", "lagga-kabelkanal" in existing_ids)

    accepted_any = False
    seen_keys = set()

    for task in suggested:
        # Hämta task_id / task_ref från GPT-förslaget
        tid_new = (task.get("task_id") or task.get("task_ref") or "").strip().lower()
        print("DEBUG: GPT-förslag task_id/task_ref:", repr(tid_new))

        # 0) IGNORE-LISTA: hoppa över task_id:n vi vet att vi inte vill ha
        if tid_new and tid_new in IGNORE_TASK_IDS:
            print("\n--- HOPPAR ÖVER GPT-FÖRSLAG I IGNORE-LISTA ---")
            print(f"Task-id finns i IGNORE_TASK_IDS: {tid_new}")
            continue

        # 1) Hård kontroll: hoppa över förslag där task_id redan finns i YAML
        if tid_new and tid_new in existing_ids:
            print("\n--- HOPPAR ÖVER GPT-FÖRSLAG MED BEFINTLIGT TASK_ID ---")
            print(f"Task-id finns redan i YAML: {tid_new}")
            continue

        key = make_dedup_key(task)

        # 2) Hoppa över sådant som redan finns i YAML (nyckel-baserat)
        if key in existing_keys:
            print("\n--- HOPPAR ÖVER GPT-FÖRSLAG SOM REDAN FINNS I YAML ---")
            tid = task.get("task_id") or task.get("task_ref")
            title = task.get("title_sv") or task.get("label")
            print(f"Task finns redan i befintliga mapping-filer: {tid} / {title}")
            continue

        # 3) Hoppa över rena dubbletter i samma körning
        if key in seen_keys:
            print("\n--- HOPPAR ÖVER DUBBELT GPT-FÖRSLAG ---")
            tid = task.get("task_id") or task.get("task_ref")
            title = task.get("title_sv") or task.get("label")
            print(f"Task verkar redan ha visats i denna körning: {tid} / {title}")
            continue

        seen_keys.add(key)

        similar = find_similar_tasks(task, existing)

        print_task_review(task, similar)
        action = prompt_user_choice()

        if action == "reject":
            print("\n→ Avvisad. Ingenting sparat.\n")
            continue

        if action == "edit":
            task = edit_task_interactively(task)

        if action == "accept":
            print("\n→ Accepterad. Skriver in i systemet...")
            payload = {"suggested_tasks": [task]}
            # 1) Logga till task_suggestions.jsonl
            log_task_suggestions(payload)
            # 2) Uppdatera mapping-filerna direkt
            apply_suggested_tasks(payload)
            print("→ Klart.\n")
            accepted_any = True

    if not accepted_any:
        print("\nInga tasks accepterades.")
    else:
        print("\nFärdigt. En eller flera tasks har lagts till i YAML.")

    print("\n========== REVIEW KLAR ==========\n")

# =========================================================
# NY FUNKTION: Kör full GPT-generering baserat på missing segments
# =========================================================

from src.services.ai_client import AIClient
from src.services.ai_specs import load_task_generation_spec
from src.services.task_suggestions import build_gpt_input_from_missing_segments


def run_gpt_generation(limit: int = 20):
    """
    1. Hämtar GPT-specifikationen
    2. Hämtar senaste missing task-segments
    3. Anropar GPT via AIClient
    4. Returnerar GPT:s output som ett dict
    """
    print("\nLaddar GPT-specifikation...")
    spec = load_task_generation_spec()

    print("Samlar missing task-segments...")
    gpt_input = build_gpt_input_from_missing_segments(limit=limit)

    print("Kontaktar GPT-modellen...")
    client = AIClient()
    response = client.generate_tasks(spec, gpt_input)

    print("GPT-generering klar.")
    return response


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Användning:")
        print("  python task_suggestions_review.py <gpt_output.json>")
        print("  python task_suggestions_review.py --gpt")
        sys.exit(1)

    arg = sys.argv[1]

    if arg == "--gpt":
        gpt_data = run_gpt_generation(limit=20)
        out_path = LOG_DIR / "gpt_task_suggestions_runtime.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(gpt_data, f, ensure_ascii=False, indent=2)
        print(f"`nGPT-output sparad till: {out_path}")
        review_and_process(str(out_path))
    else:
        review_and_process(arg)







