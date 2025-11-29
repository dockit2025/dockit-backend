import csv, sys
from pathlib import Path

query = " ".join(sys.argv[1:]).strip().lower()
if not query:
    print("Användning: python list_atl_terms.py <sökord>")
    sys.exit(0)

atl_path = Path("knowledge/atl/Del7_ATL_Total.csv")
if not atl_path.exists():
    print(f"Hittar inte {atl_path}")
    sys.exit(1)

def norm(s):
    return (s or "").strip()

def parse_float(s):
    s = (s or "").strip().replace(",", ".")
    try:
        return float(s)
    except:
        return None

hits = []
with atl_path.open("r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        name = norm(row.get("Moment/Typ/Sort"))
        if not name:
            continue
        if all(tok in name.lower() for tok in query.split()):
            item = {
                "arbetsmoment": norm(row.get("Arbetsmoment")),
                "grupp": norm(row.get("Grupp")),
                "rad": norm(row.get("Rad")),
                "moment_name": name,
                "unit": norm(row.get("Enhet")),
                # några vanliga variantkolumner:
                "t_0": parse_float(row.get("0")),
                "t_m3": parse_float(row.get("-3")),  # ex. "i rör" i vissa tabeller
            }
            hits.append(item)

if not hits:
    print(f"Inga träffar på: {query}")
    sys.exit(0)

print(f"Träffar ({len(hits)}): {query}\n")
for h in hits[:50]:  # visa upp till 50
    tinfo = []
    if h["t_0"] is not None:  tinfo.append(f"0={h['t_0']} h/enhet")
    if h["t_m3"] is not None: tinfo.append(f"-3={h['t_m3']} h/enhet")
    tstr = (" | ".join(tinfo)) or "—"
    print(f"- [{h['arbetsmoment']}] {h['moment_name']}  (enhet: {h['unit']})  {tstr}")
