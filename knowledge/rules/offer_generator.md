# OFFER_GENERATOR — controller för JSON→HTML→PDF v1.0

Syfte
- Ta emot en offer_json enligt rules/merge_rules.md och producera:
  1) Färdig HTML-offert (helt renderad utan templatemarkörer)
  2) Matchande JSON med beräknade summor
- Kör alltid post_render_cleanup och render_validator internt tills PASS.

Indata
- offer_json: följer schemat från merge_rules.md (supplier, client, project, pricing, material[], labor[], notes).
- Om någon del saknas: lämna fält tomt i HTML men behåll layouten (enligt FELHANTERING i kärnreglerna).

Kedja (obligatorisk ordning)
1) MERGE: Fyll offer_template.html med värden från offer_json enligt rules/merge_rules.md.
2) SUMS: Räkna:
   - sum_material = Σ(material.qty * material.unit_price)
   - sum_hours    = Σ(labor.time_total)
   - sum_labor    = sum_hours * pricing.labor_rate
   - subtotal_excl = sum_material + sum_labor
   - vat_amount    = subtotal_excl * pricing.vat_rate
   - total_incl    = subtotal_excl + vat_amount
   Lägg in värdena i JSON (behåll originaldata oförändrad i övrigt).
3) RENDER: Skriv ut komplett HTML (<!doctype html>…</html>) med alla tabeller och summeringar.
4) CLEANUP: Kör post_render_cleanup.md (Org.nr:, en-dash, svenska talformat med U+202F, mm², etc.).
5) VALIDERA: Kör render_validator.md; om FAIL → justera och rendera om tills allt blir PASS.

Regler/format
- HTML först i svaret, sedan JSON i separat kodblock.
- Ingen templatemarkör ({{…}}) får finnas kvar i HTML.
- Svenska talformat: två decimaler, komma som decimaltecken, narrow no-break space (U+202F) endast i heltalsdelar med >3 siffror.
- Kolumnordning i kundtabeller:
  Material: Artikel | Benämning | Enhet | Antal | À-pris | Radsumma | Lev.
  Arbete:   Arbetsmoment | Moment/Typ/Sort | Underlag/Variant | Enhet | Tid | À-pris | Radsumma
- Visa aldrig interna “Grupp/Rad” i kunddokument.

Felsäkerhet
- Saknas pris eller tid → behåll raden, sätt värde tomt eller 0 men bryt inte layouten.
- Finns “diagnostics” i offer_json → lämna kvar opåverkat i JSON-utdata (bra för granskning).
- Om HTML blir längre än 1 sida: bryt med CSS/”page-break” där det är lämpligt (ej obligatoriskt).

Output
- 1) En komplett HTML-offert.
- 2) Ett JSON-block (samma offer_json men med inräknade sums-fält).
