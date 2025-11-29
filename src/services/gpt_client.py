from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import dotenv
import requests


# ---------------------------------------------------------
# Ladda miljövariabler
# ---------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"

if ENV_PATH.exists():
    dotenv.load_dotenv(ENV_PATH)


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

API_URL = "https://api.openai.com/v1/chat/completions"
MODEL_DEFAULT = "gpt-4.1-mini"   # billig & mycket bra för vårt use case


# ---------------------------------------------------------
# GPT-klient
# ---------------------------------------------------------

def call_gpt(prompt: Dict[str, Any], *, model: Optional[str] = None) -> Dict[str, Any]:
    """
    Skickar en JSON-prompt till OpenAI och returnerar svar i JSON-format.

    Om API-nyckel saknas returnerar vi en dummy-svarstruktur så att resten av systemet
    kan fortsätta köra utan att krascha.
    """

    if not OPENAI_API_KEY:
        print("[gpt_client] Ingen OPENAI_API_KEY i .env – använder dummy-output.", file=sys.stderr)
        return {
            "error": "missing_api_key",
            "suggested_tasks": [],
            "suggested_materials": {}
        }

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    body = {
        "model": model or MODEL_DEFAULT,
        "messages": [
            {
                "role": "system",
                "content": "Du är en AI som returnerar strikt JSON och aldrig text utanför JSON-strukturen."
            },
            {
                "role": "user",
                "content": json.dumps(prompt, ensure_ascii=False)
            }
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    try:
        resp = requests.post(API_URL, headers=headers, json=body, timeout=30)
    except Exception as e:
        print(f"[gpt_client] nätverksfel: {e}", file=sys.stderr)
        return {"error": "network_error", "details": str(e)}

    if resp.status_code != 200:
        print(f"[gpt_client] API ERROR {resp.status_code}: {resp.text}", file=sys.stderr)
        return {"error": "api_error", "status": resp.status_code, "details": resp.text}

    try:
        data = resp.json()
    except ValueError:
        print("[gpt_client] ogiltig JSON i API-svar.", file=sys.stderr)
        return {"error": "invalid_json"}

    # Extract actual model output
    try:
        content_raw = data["choices"][0]["message"]["content"]
        return json.loads(content_raw)
    except Exception as e:
        print(f"[gpt_client] JSON-dekoderingsfel: {e}", file=sys.stderr)
        return {"error": "decode_error", "raw": data}


if __name__ == "__main__":
    # Manuell snabbtest
    demo = {"ping": "hello, model"}
    out = call_gpt(demo)
    print(json.dumps(out, ensure_ascii=False, indent=2))
