from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "knowledge" / "logs"


class AIClient:
    """
    Central GPT-klient för Dockit.
    Hanterar:
      - Task suggestions
      - Material suggestions
    """

    def _safe_json_loads(self, raw: str, *, context: str) -> Dict[str, Any]:
        """
        Försöker parsa GPT-output som JSON.
        Om det misslyckas:
          - försöker klippa ut första '{' till sista '}'
          - loggar råtext till LOG_DIR
          - höjer ett mer begripligt fel
        """
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: hitta JSON-del i råtexten
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                candidate = raw[start:end+1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass

            # Logga råoutput för felsökning
            try:
                LOG_DIR.mkdir(parents=True, exist_ok=True)
                log_path = LOG_DIR / f"gpt_{context}_raw_error.json"
                with log_path.open("w", encoding="utf-8") as f:
                    f.write(raw)
            except Exception:
                # Vi vill inte krascha bara för att loggning misslyckas
                pass

            raise RuntimeError(
                f"Kunde inte tolka GPT-svar som JSON för context='{context}'. "
                "Råoutput är sparad i knowledge/logs (om skrivning lyckades)."
            )

    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Miljövariabeln OPENAI_API_KEY saknas. "
                "Sätt den med t.ex. (Powershell): "
                '$env:OPENAI_API_KEY = "DIN_NYCKEL"'
            )

        self.client = OpenAI(api_key=api_key)
        # Du kan byta till gpt-4.1-mini om du vill spara mer pengar
        self.model = "gpt-4.1"

    # -------------------------------------------------------------
    #  TASK SUGGESTIONS (huvudmetod)
    # -------------------------------------------------------------
    def generate_task_suggestions(
        self, *, gpt_spec: str, segments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Tar emot:
          - gpt_spec   (instruktionerna vi skrev i ai_spec_task_generation.md)
          - segments   (byggt via task_suggestions.build_gpt_input_from_missing_segments)

        Returnerar GPT:ens JSON-output som dict.
        """
        prompt = (
            gpt_spec
            + "\n\nHär är segment-datan i JSON-format:\n"
            + json.dumps(segments, ensure_ascii=False, indent=2)
        )

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du är en assistent som genererar nya electrical tasks "
                        "i korrekt JSON-format enligt specifikationen."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )

        raw = response.choices[0].message.content

        # Hantera både str och ev. list-format från klienten
        if isinstance(raw, list):
            parts = []
            for part in raw:
                if isinstance(part, dict) and "text" in part:
                    parts.append(str(part["text"]))
                else:
                    parts.append(str(part))
            raw = "".join(parts)

        return self._safe_json_loads(raw, context="tasks")

    # Liten wrapper så vårt review-skript kan kalla generate_tasks(...)
    def generate_tasks(self, spec: str, gpt_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Wrapper runt generate_task_suggestions för enklare anrop.
        """
        return self.generate_task_suggestions(gpt_spec=spec, segments=gpt_input)

    # -------------------------------------------------------------
    #  MATERIAL SUGGESTIONS
    # -------------------------------------------------------------
    def generate_material_suggestions(
        self, *, instruction: str, missing_material_refs: Dict[str, int]
    ) -> Dict[str, Any]:
        """
        Tar emot:
          - instruction: kort GPT-instruktion (t.ex. byggd av build_material_mapping_prompt)
          - missing_material_refs: dict {ref: count}
        """
        payload = {
            "missing_refs": missing_material_refs
        }

        prompt = (
            instruction
            + "\n\nHär är material_ref som saknar mapping:\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "Du föreslår artikelnummer från grossistens prislista i JSON-format.",
                },
                {"role": "user", "content": prompt},
            ],
        )

        raw = response.choices[0].message.content

        # Hantera både str och ev. list-format från klienten
        if isinstance(raw, list):
            parts = []
            for part in raw:
                if isinstance(part, dict) and "text" in part:
                    parts.append(str(part["text"]))
                else:
                    parts.append(str(part))
            raw = "".join(parts)

        return self._safe_json_loads(raw, context="tasks")


if __name__ == "__main__":
    print("AIClient-test: importera AIClient i andra moduler och använd där.")



