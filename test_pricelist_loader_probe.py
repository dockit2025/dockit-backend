from __future__ import annotations
from src.server.loaders.pricelist_loader import PriceListLoader, PriceListConfig

def main():
    cfg = PriceListConfig(csv_path=r"knowledge\catalogs\Storel-GN.csv")
    pl = PriceListLoader(cfg)
    pl.load()
    df = pl.df

    print("Kolumner (städade):", list(df.columns))
    print("Första 5 rader:")
    print(df.head(5).to_string(index=False))

    for term in ["downlight", "gacrux", "plafond"]:
        hits = pl.search(term, top_k=10)
        print(f"\nTräffar för '{term}': {len(hits)}")
        if not hits.empty:
            show_cols = [c for c in ["Artikelnummer","Benämning","Enhet","Pris"] if c in hits.columns]
            print(hits[show_cols].head(10).to_string(index=False))

if __name__ == "__main__":
    main()
