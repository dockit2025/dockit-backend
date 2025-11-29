import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "knowledge" / "catalogs" / "Storel-GN.csv"
JSON_PATH = ROOT / "knowledge" / "catalogs" / "price_catalog.json"


def parse_price(value: str) -> float:
    """
    Tar ett prisvärde som t.ex. '97', '1 705', '114,50'
    och gör om det till float.
    """
    if value is None:
        return 0.0
    s = str(value).strip()
    if not s:
        return 0.0

    # Ta bort mellanslag som används som tusentalsavskiljare
    s = s.replace(" ", "")

    # Ersätt eventuellt kommatecken med punkt
    s = s.replace(",", ".")

    try:
        return float(s)
    except ValueError:
        return 0.0


def main() -> None:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Hittar inte CSV-filen: {CSV_PATH}")

    rows = []

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=";")

        # Läs första raden som header
        header = next(reader, None)
        if not header:
            raise RuntimeError("CSV-filen verkar vara tom.")

        # Förväntade kolumner (kan justeras om grossisten ändrar formatet)
        # Vi mappar dem till enklare nycklar i vår JSON.
        # Exempel-header från din fil:
        # "Artikelnummer;Benämning;Enhet;Materialgrupp;GN-pris;Prisdatum;..."
        try:
            idx_artnr = header.index("Artikelnummer")
            idx_namn = header.index("Benämning")
            idx_enhet = header.index("Enhet")
            idx_mg = header.index("Materialgrupp")
            idx_gnpris = header.index("GN-pris")
        except ValueError as e:
            raise RuntimeError(f"Kunde inte hitta förväntad kolumn i headern: {e}")

        for raw in reader:
            if not raw or all((c or "").strip() == "" for c in raw):
                continue  # hoppa över tomma rader

            # Säkerhetskoll om raderna är kortare än headern
            if len(raw) <= max(idx_artnr, idx_namn, idx_enhet, idx_mg, idx_gnpris):
                continue

            artnr = (raw[idx_artnr] or "").strip()
            benamning = (raw[idx_namn] or "").strip()
            enhet = (raw[idx_enhet] or "").strip()
            mg = (raw[idx_mg] or "").strip()
            gnpris_raw = (raw[idx_gnpris] or "").strip()

            if not artnr:
                continue  # hoppa rader utan artikelnummer

            gnpris = parse_price(gnpris_raw)

            rows.append(
                {
                    "artikelnummer": artnr,
                    "benamning": benamning,
                    "enhet": enhet,
                    "materialgrupp": mg,
                    "gn_pris": gnpris,
                }
            )

    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with JSON_PATH.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    print(f"Skrev {len(rows)} rader till {JSON_PATH}")


if __name__ == "__main__":
    main()
