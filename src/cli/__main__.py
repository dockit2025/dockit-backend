# src/cli/__main__.py
import sys, json
from pathlib import Path

from src.core.render import render_offer
from src.core.cleanup import cleanup
from src.core.validate import validate

USAGE = """Usage:
  python -m src.cli render <offer.json> [template_path] [--out=out.html]
  python -m src.cli validate <offer.json> [template_path]

Examples:
  python -m src.cli render examples/offer_input.json --out=out.html
  python -m src.cli render examples/offer_input.json templates/offer_template.html --out=out.html
"""

def _load_json(p: str):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Error reading JSON '{p}': {e}", file=sys.stderr)
        sys.exit(2)

def main():
    if len(sys.argv) < 3:
        print(USAGE, file=sys.stderr); sys.exit(1)

    cmd = sys.argv[1].lower()
    offer_path = sys.argv[2]

    # defaults
    template_path = "templates/offer_template.html"
    out_path = None

    # parse optional args (order-agnostic)
    for arg in sys.argv[3:]:
        if arg.startswith("--out="):
            out_path = arg.split("=", 1)[1]
        elif arg.startswith("--"):
            continue
        elif template_path == "templates/offer_template.html":
            template_path = arg  # first non-flag arg after offer is template

    offer = _load_json(offer_path)

    if cmd == "render":
        r = render_offer(offer, template_path)
        html = cleanup(r["html"])
        if out_path:
            Path(out_path).write_text(html, encoding="utf-8")
        else:
            sys.stdout.write(html)
        return

    if cmd == "validate":
        r = render_offer(offer, template_path)
        html = cleanup(r["html"])
        print(validate(html))
        return

    print(USAGE, file=sys.stderr); sys.exit(1)

if __name__ == "__main__":
    main()

