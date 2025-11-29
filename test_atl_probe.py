# test_atl_probe.py
from pathlib import Path
import pandas as pd

path = Path("knowledge/atl/Del7_ATL_Total.csv")
if not path.exists():
    raise SystemExit(f"Hittar inte filen: {path.resolve()}")

last_err = None
df = None
sep_used = None
for sep in (";", ",", "\t", "|"):
    try:
        df = pd.read_csv(path, encoding="utf-8-sig", sep=sep, dtype=str, engine="python")
        sep_used = sep
        break
    except Exception as e:
        last_err = e

if df is None:
    raise SystemExit(f"Kunde inte läsa CSV (sista fel: {last_err})")

df.columns = [str(c).strip() for c in df.columns]

print("=== PROBE ===")
print(f"Separator gissad: {repr(sep_used)}")
print(f"Antal rader: {len(df)}")
print("Kolumner:")
for c in df.columns:
    print(" -", c)

print("\nFörsta 5 rader (komprimerat):")
print(df.head(5).fillna("").to_string(index=False)[:2000])

# Visa 5 rader som innehåller några typiska ord
def show_match(term: str):
    m = df.apply(lambda r: r.astype(str).str.lower().str.contains(term).any(), axis=1)
    sub = df[m].head(5).fillna("")
    print(f"\n--- Träffexempel för '{term}' ({len(sub)} visade) ---")
    if not sub.empty:
        print(sub.to_string(index=False)[:2000])
    else:
        print("(inga visade, men kan finnas längre ned)")

for t in ["rör", "kabelkanal", "uttag", "armatur", "downlight", "spis", "perilex"]:
    show_match(t)
