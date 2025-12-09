from __future__ import annotations

from pathlib import Path

# Projektrot (ex: D:\\dockit-ai)
ROOT = Path(__file__).resolve().parents[2]

# Path till GPT-specen för textrensning
TEXT_CLEANER_SPEC_PATH = ROOT / "documentation" / "ai_spec_text_cleaner.md"


def load_text_cleaner_spec() -> str:
    """
    Läser in GPT-specen för textrensaren.

    Används när vi vill:
      - ta en fri text från elektriker
      - plocka ut rena arbetsmoment/meningar
      - filtrera bort hälsningsfraser, småprat, upprepningar m.m.
      - få ut en strukturerad lista av segment som sedan kan tolkas av interpret_free_text

    Om markdown-filen inte finns ännu returnerar vi en enkel fallback-spec.
    """
    if not TEXT_CLEANER_SPEC_PATH.exists():
        return (
            "Du är en assistent som rensar och strukturerar svensk hantverkstext. "
            "Du får in en jobbeskrivning från en elektriker och ska plocka ut rena, "
            "självständiga arbetsmoment/fraser som beskriver jobb som ska göras. "
            "Ta bort hälsningsfraser, småprat och sådant som inte är konkreta arbetsmoment. "
            "Returnera en lista av korta segment i JSON-format enligt den input/utdata-struktur "
            "som anropet beskriver."
        )

    return TEXT_CLEANER_SPEC_PATH.read_text(encoding="utf-8")
