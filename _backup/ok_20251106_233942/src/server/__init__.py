# src/core/validate.py
import re
from html import unescape

# --- helpers ------------------------------------------------------------

def _strip_accents(s: str) -> str:
    # gör valideringen tolerant: ersätt À-pris/A-pris/&#192;-pris/&Agrave;-pris till "a-pris"
    s = unescape(s)                  # &Agrave; -> À, &ndash; -> –
    s = s.lower()
    s = s.replace("à", "a").replace("ä", "a").replace("å", "a")
    s = s.replace("ö", "o")
    s = re.sub(r"\s+", " ", s)       # normalisera mellanrum
    return s.strip()

def _has_en_dash_between_digits(html: str) -> bool:
    # godkänn både unicode en-dash och HTML-entity
    if re.search(r"(?<=\d)\u2013(?=\d)", html):
        return True
    if re.search(r"(?<=\d)&ndash;(?=\d)", html):
        return True
    return False

def _thead_columns(html: str, table_aria: str) -> list[str]:
    m = re.search(
        rf'<table[^>]*aria-label="{re.escape(table_aria)}"[^>]*>.*?<thead>(.*?)</thead>',
        html, flags=re.S | re.I,
    )
    if not m:
        return []
    head = m.group(1)
    cols = re.findall(r"<th[^>]*>(.*?)</th>", head, flags=re.S | re.I)
    cols = [ _strip_accents(re.sub("<.*?>", "", c)) for c in cols ]
    return cols

# --- main ---------------------------------------------------------------

def validate(html: str) -> str:
    report = []

    # 1) templatemarkörer
    if "{{" in html or "}}" in html:
        report.append('[FAIL] Inga templatemarkörer kvar ("{{" eller "}}")')
    else:
        report.append('[PASS] Inga templatemarkörer kvar ("{{" eller "}}")')

    # 2) org.nr i båda boxar
    ok_org = all([
        re.search(r'id="supplier-box".*?Org\.nr:', html, flags=re.S),
        re.search(r'id="client-box".*?Org\.nr:', html, flags=re.S),
    ])
    report.append('[PASS] "Org.nr:" finns inför sifferraden i både Leverantör och Kund' if ok_org
                  else '[FAIL] "Org.nr:" saknas i Leverantör eller Kund')

    # 3) pengar – två decimaler och U+202F
    money_ok = True
    for m in re.finditer(r"(\d[\d \u00A0\u202F]*,\d{2})\s*kr", html):
        s = m.group(1)
        # två decimaler har vi redan i regexen; kontrollera u+202f i tusental om fler än 3 siffror
        int_part = s.split(",")[0]
        digits = re.sub(r"[ \u00A0\u202F]", "", int_part)
        if len(digits) > 3 and "\u202f" not in int_part:
            money_ok = False
            break
    report.append('[PASS] Alla pengar har två decimaler och U+202F som tusentalsavskiljare (ex: 11 670,00 kr)'
                  if money_ok else
                  '[FAIL] Pengar saknar U+202F i tusental eller fel decimalformat')

    # 4) arbetstimmar "Arbete (X,YY h)" – leta i totals-box
    m = re.search(r"Arbete \((\d+,\d{2}) h\)", html)
    report.append('[PASS] "Arbete (X,YY h)" visar timmar med exakt två decimaler'
                  if m else
                  '[FAIL] "Arbete (X,YY h)" visar timmar med exakt två decimaler – format saknas/ogiltigt')

    # 5) mm²
    report.append('[PASS] mm2 inte förekommer (ska vara mm²)'
                  if "mm2" not in html else
                  '[FAIL] mm2 förekommer – ska vara mm²')

    # 6) en-dash mellan tal (tolerera &ndash;)
    en_ok = _has_en_dash_between_digits(html)
    report.append('[PASS] Datum/offertnr använder en-dash (–) mellan tal – kontrollera meta-box & offertnr'
                  if en_ok else
                  '[FAIL] Datum/offertnr använder en-dash (–) mellan tal – kontrollera meta-box & offertnr')

    # 7) tabellernas kolumnordning
    mat_cols = _thead_columns(html, "Material")
    arb_cols = _thead_columns(html, "Arbete")

    mat_expected = ["artikel","benamning","enhet","antal","a-pris","radsumma","lev."]
    arb_expected = ["arbetsmoment","moment/typ/sort","underlag/variant","enhet","tid","a-pris","radsumma"]

    mat_ok = (mat_cols == mat_expected)
    arb_ok = (arb_cols == arb_expected)

    if mat_ok and arb_ok:
        report.append("[PASS] Tabellernas kolumnordning följer reglerna")
    else:
        report.append("[FAIL] Tabellernas kolumnordning följer reglerna – rubriker saknas/fel ordning")

    return "\n".join(report)


