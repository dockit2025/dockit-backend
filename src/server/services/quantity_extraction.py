"""
Quantity extraction utilities for Dockit.

Den här modulen implementerar en enkel, robust tolkning av "antal"
ur korta textsegment som redan har delats upp av NL-parsern.

Exempel på uttryck:
- "byta tre vägguttag"
- "2 uttag i köket"
- "dra tio meter rör"
- "sätta upp ett uttag"
- "några lampor"
- "ett par uttag"

Reglerna är synkade med rules/quantity_extraction.md.
"""

from __future__ import annotations

import re
from typing import Optional


SWEDISH_NUMBER_WORDS = {
    "noll": 0,
    "en": 1,
    "ett": 1,
    "två": 2,
    "tre": 3,
    "fyra": 4,
    "fem": 5,
    "sex": 6,
    "sju": 7,
    "åtta": 8,
    "nio": 9,
    "tio": 10,
    "elva": 11,
    "tolv": 12,
    "tretton": 13,
    "fjorton": 14,
    "femton": 15,
    "sexton": 16,
    "sjutton": 17,
    "arton": 18,
    "nitton": 19,
    "tjugo": 20,
}

APPROX_WORDS = {
    "några": 3,        # standardvärde
    "ett par": 2,
    "par": 2,
}


def _normalize(text: str) -> str:
    """Enkel normalisering: lower + ersätt kommatecken med punkt för tal."""
    return text.lower().replace(",", ".")


def _extract_digit_number(text: str) -> Optional[float]:
    """
    Hitta första explicita talet i texten, t.ex.:
    - '3'
    - '10'
    - '15.5'
    - '10m'
    - '10m2'
    Vi letar efter siffertal med ev. decimal.
    """
    # matcha t.ex. "10", "10.5", "3", "2.0"
    match = re.search(r"\b(\d+(?:\.\d+)?)\b", text)
    if not match:
        # fallback: försök plocka tal direkt framför enheten, t.ex. "10m"
        match = re.search(r"\b(\d+(?:\.\d+)?)(?=[a-zåäö]+)\b", text)
    if not match:
        return None
    try:
        value = float(match.group(1))
        if value < 0:
            return None
        return value
    except ValueError:
        return None


def _extract_exact_word_number(text: str) -> Optional[int]:
    """
    Försök tolka exakta svenska talord:
    'ett', 'två', 'tre', ... enligt SWEDISH_NUMBER_WORDS.
    """
    for word, value in SWEDISH_NUMBER_WORDS.items():
        # \b så vi inte matchar delar av andra ord
        if re.search(rf"\b{re.escape(word)}\b", text):
            return value
    return None


def _extract_approx_number(text: str) -> Optional[int]:
    """
    Försök tolka approx-uttryck:
    'några', 'ett par', 'par'
    """
    norm = " ".join(text.split())
    # först tvåordiga uttryck
    for phrase, value in APPROX_WORDS.items():
        if phrase in norm:
            return value
    return None


def extract_quantity_from_text_segment(text: str, *, default: float = 1.0) -> float:
    """
    Extrahera ett rimligt quantity-värde ur ett kort textsegment.

    Ordning:
    1) Exakta tal: '3', '10', '2.5'
    2) Svenska talord: 'tre', 'tio'
    3) Approx: 'några', 'ett par'
    4) Fallback: default (1.0)

    Returnerar alltid ett positivt tal.
    """
    if not text or not text.strip():
        return float(default)

    norm = _normalize(text)

    # 1. exakta tal
    value = _extract_digit_number(norm)
    if value is not None and value > 0:
        return float(value)

    # 2. exakta talord
    word_val = _extract_exact_word_number(norm)
    if word_val is not None and word_val > 0:
        return float(word_val)

    # 3. approx
    approx_val = _extract_approx_number(norm)
    if approx_val is not None and approx_val > 0:
        return float(approx_val)

    # 4. fallback
    return float(default)


if __name__ == "__main__":
    # Enkel manuell testkörning:
    samples = [
        "byta tre vägguttag",
        "2 uttag i köket",
        "dra tio meter rör",
        "sätta upp ett uttag",
        "några lampor i hallen",
        "ett par uttag i kök",
        "installera vägguttag i hallen",
        "dra 15m kabel",
        "dra 12.5 meter kabel",
    ]
    for s in samples:
        q = extract_quantity_from_text_segment(s)
        print(f"{s!r} -> quantity={q}")
