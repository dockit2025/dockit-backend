# src/core/cleanup.py
import re

def cleanup(html: str) -> str:
    if not html:
        return html

    out = html

    # 1) Org.nr i båda boxar – om rad med 6+ siffror utan prefix, lägg till "Org.nr: "
    def _ensure_orgnr(block_id: str, s: str) -> str:
        # hitta blocket
        m = re.search(rf'(<div class="box" id="{block_id}">.*?</div>)', s, flags=re.S)
        if not m:
            return s
        block = m.group(1)

        # a) prefixa ensamma sifferrader
        def prefix_line(line: str) -> str:
            if re.fullmatch(r"\s*\d{6,}\s*", line) and not line.strip().startswith("Org.nr:"):
                return re.sub(r"(\S.*)", r"Org.nr: \1", line)
            return line

        lines = block.split("\n")
        lines = [prefix_line(l) for l in lines]

        # b) om ingen rad börjar med Org.nr:, lägg tom rad ovanför e-post
        if not any(l.strip().startswith("Org.nr:") for l in lines):
            for i, l in enumerate(lines):
                if "@" in l:
                    lines.insert(i, "Org.nr: ")
                    break

        new_block = "\n".join(lines)
        return s.replace(block, new_block)

    out = _ensure_orgnr("supplier-box", out)
    out = _ensure_orgnr("client-box", out)

    # 2) Valuta – tvinga U+202F mellan tusental (matcha bara belopp som slutar med " kr")
    def _fix_money(m):
        number = m.group(1)  # t.ex. 11670,00
        if "," not in number:
            return number + " kr"
        int_part, dec_part = number.split(",")
        int_digits = re.sub(r"[ \u00A0\u202F]", "", int_part)
        # gruppera tre och tre från höger
        chunks = []
        while int_digits:
            chunks.append(int_digits[-3:])
            int_digits = int_digits[:-3]
        int_grouped = "\u202f".join(reversed(chunks))
        return f"{int_grouped},{dec_part} kr"

    out = re.sub(r"(\d{1,}(?:[ \u00A0\u202F]?\d{3})*,\d{2})\s*kr", lambda m: _fix_money(m), out)

    # 3) En-dash i numeriska separeringar (datum, offertnr)
    # ASCII '-' mellan siffror → '–'
    out = re.sub(r"(?<=\d)-(?!\s)(?=\d)", "–", out)

    # 4) mm2 → mm²
    out = out.replace("mm2", "mm²")

    # 5) Dubbla mellanslag → ett (rör inte U+202F)
    out = re.sub(r"(?!\u202f) {2,}", " ", out)

    # 6) Ta bort templatemarkörer om de hänger kvar
    out = out.replace("{{", "").replace("}}", "")

    return out

