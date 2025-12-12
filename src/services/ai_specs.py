from __future__ import annotations

from pathlib import Path


# Projektrot (ex: D:\dockit-ai)
ROOT = Path(__file__).resolve().parents[2]

# Paths till våra GPT-specar
TASK_SPEC_PATH = ROOT / "documentation" / "ai_spec_task_generation.md"
MATERIAL_SPEC_PATH = ROOT / "documentation" / "ai_spec_material_generation.md"
TEXT_CLEANER_SPEC_PATH = ROOT / "documentation" / "ai_spec_text_cleaner.md"
TASK_MATCHING_SPEC_PATH = ROOT / "documentation" / "ai_spec_task_matching.md"


def load_task_generation_spec() -> str:
    """
    Läser in GPT-specen för tasks (fri text -> suggested_tasks).
    """
    if not TASK_SPEC_PATH.exists():
        raise FileNotFoundError(f"Hittar inte filen för task-spec: {TASK_SPEC_PATH}")

    return TASK_SPEC_PATH.read_text(encoding="utf-8")


def load_material_generation_spec() -> str:
    """
    Läser in GPT-specen för materialmappningar.
    (Skapas senare om den inte finns ännu.)
    """
    if not MATERIAL_SPEC_PATH.exists():
        return (
            "Du är en assistent som föreslår artikelnummer för saknade material_ref "
            "baserat på svensk elgrossist-prislista."
        )

    return MATERIAL_SPEC_PATH.read_text(encoding="utf-8")


def load_text_cleaner_spec() -> str:
    """
    Läser in GPT-specen för textrensaren (fri jobbeskrivning -> clean_segments).
    """
    if not TEXT_CLEANER_SPEC_PATH.exists():
        raise FileNotFoundError(
            f"Hittar inte filen för text-cleaner-spec: {TEXT_CLEANER_SPEC_PATH}"
        )

    return TEXT_CLEANER_SPEC_PATH.read_text(encoding="utf-8")


def load_task_matching_spec() -> str:
    """
    Läser in GPT-specen för task matching (segments -> existing tasks).
    """
    if not TASK_MATCHING_SPEC_PATH.exists():
        raise FileNotFoundError(
            f"Hittar inte filen för task-matching-spec: {TASK_MATCHING_SPEC_PATH}"
        )

    return TASK_MATCHING_SPEC_PATH.read_text(encoding="utf-8")
