# test_atl_loader_freeform.py
from src.server.loaders.atl_loader_new import ATLLoader, ATLConfig

def main():
    import sys
    query = " ".join(sys.argv[1:]) or "rör"
    loader = ATLLoader(ATLConfig(
        atl_csv_path="knowledge/atl/Del7_ATL_Total.csv",
        atl_mapping_path="knowledge/atl/atl_mapping.yaml"  # byt om din mapping ligger annanstans
    ))
    loader.load()
    hits = loader.search(query, top_k=5)
    print(f"Sökterm: {query}")
    if not hits:
        print("Inga träffar.")
        return
    for i, row in enumerate(hits, 1):
        print(f"\n# Rad {i}")
        for k, v in row.items():
            if k == "_search_text":
                continue
            print(f"- {k}: {v}")

if __name__ == "__main__":
    main()
