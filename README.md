# README.md
# Dockit AI – Offertassistent

En modulär, testbar och säljbar kärna för AI-driven offertgenerering. Byggd för att skala, integreras i mobil/webb och vara enkel att due-diligence-granska.

## ✔️ Funktioner (v1)
- NL/“slarvig hantverkstext” → ATL-moment (synonymer & n-gram)
- Mängduttag, materialbindningar
- Rendering till kundren HTML via mall
- Post-render cleanup (U+202F, en-dash, mm², Org.nr)
- Validator (kort PASS/FAIL-rapport)
- CLI och enkel FastAPI för integration

## Kom igång
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
uvicorn src.api.main:app --reload
