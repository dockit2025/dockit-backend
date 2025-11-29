import sys
from src.server.loaders.atl_loader_new import search_atl

def main() -> None:
    query = " ".join(sys.argv[1:]).strip() or "infällda rör"
    print(f"Sökterm: {query}")
    hits = search_atl(query, top_k=5)  # använder interna standardvägar
    if not hits:
        print("Inga träffar.")
        return
    for r in hits:
        print(f"- {r.get('moment_name')} | variant: {r.get('variant')} | enhet: {r.get('unit')} | tid/h per enhet: {r.get('time_h_per_unit')}")

if __name__ == "__main__":
    main()
