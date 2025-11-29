from sys import argv
from src.server.loaders.atl_loader import init_atl_index, find_time_by_name, find_times

# Initiera index
cnt = init_atl_index()
print("ATL-indexrader:", cnt)

# Ta sökterm från kommandoraden om angiven, annars default
probe = argv[1] if len(argv) > 1 else "Infällda rör"  # exempel: "downlight", "kabelkanal", "uttag utanpåliggande", "spisuttag"
print("Sökterm:", probe)

# En (valfri) huvudträff med metadata
hit = find_time_by_name(probe)
print("Exempelträff:", hit)

# Lista de första 5 varianterna/tid per enhet
alts = find_times(probe)[:5]
print("Första 5 varianter:")
for r in alts:
    print("-", r["moment_name"], "| variant:", r["variant"], "| enhet:", r["unit"], "| tid/h per enhet:", r["time_h_per_unit"])
