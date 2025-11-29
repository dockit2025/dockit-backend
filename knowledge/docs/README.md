# Dockit AI – Knowledge-paket för GPT → Offert (QuoteDraftIn)

Detta paket gör att din GPT kan ta fri text (dikterad jobb-beskrivning) och producera ett komplett `QuoteDraftIn` som backend accepterar via POST /quotes/draft eller /quotes.

Se mapparna:
- knowledge/catalogs/  → Storel-GN.xlsx (prislista), ev. price_catalog.json
- knowledge/atl/       → Del7_ATL_Total.csv (ATL-tider), atl_mapping.yaml
- knowledge/rules/     → parser-/renderregler
- knowledge/synonyms/  → synonyms.yaml
- knowledge/templates/ → offer_template.html
- knowledge/examples/  → offert_*.json / *.html

Output-kontrakt (måste följas): QuoteDraftIn { customer_name, customer_email, job_summary, apply_rot, lines[kind, ref, description, qty, unit_price_sek] }.
