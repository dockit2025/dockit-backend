# Dockit AI Spec – ATL Rank (Admin-only)

## Syfte
Välj den mest rimliga ATL-raden (moment + variant) för en given task/segment,
men endast från en given kandidatlista.

## Absoluta regler
- Du får INTE hitta på ett moment_id som inte finns i kandidatlistan.
- Du får INTE hitta på en variant som inte finns i kandidatens 'times'-nycklar.
- Du får INTE räkna ut eller föreslå tid i minuter. Endast peka på ATL-referensen.

## Input (JSON)
{
  "task": {
    "task_id": "string",
    "label": "string",
    "category": "string (valfritt)"
  },
  "segment_text": "string",
  "atl_candidates": [
    {
      "moment_id": "string",
      "arbetsmoment": 169,
      "moment_text": "string",
      "underlag_text": "string",
      "enhet": "string",
      "times": { "0": 0.06, "-1": 0.07 }
    }
  ]
}

## Output (JSON)
{
  "selected": {
    "moment_id": "string",
    "variant": 0
  },
  "confidence": 0.0,
  "reason": "kort motivering",
  "alternatives": [
    { "moment_id": "string", "variant": 0, "reason": "kort" }
  ]
}

## Svara ENDAST med JSON.
