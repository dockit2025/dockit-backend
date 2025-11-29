# KÄRNA – Rendera Offert (HTML + JSON) v1.2

## Datakällor
- Offert-JSON enligt schema i rules/merge_rules.md
- offer_template.html

## Hårda regler (prioritet: följ rule-filerna)
- ATL/arbetsmoment: första kolumnen i arbetstabellen ska visa kundvänlig text (använd `labor[i].moment` om `labor[i].arbetsmoment` är en sifferkod). Aldrig exponera interna fält som “Grupp”/“Rad”. [rules/merge_rules.md]
- Talformat: svenskt format. Pengar och timmar alltid två decimaler. Tusental med U+202F (&#8239;). [rules/merge_rules.md]
- Templatemarkörer får inte finnas kvar i output. [rules/merge_rules.md]
- Om tid saknas (ej tidsatt i Del 7): visa raden, men lämna Tid/À-pris/Radsumma tomma och lägg förklarande text i beskrivningen. [rules/merge_rules.md]
- CSV-export styrs separat av rules/csv_export.md (påverkar inte offerten). [rules/csv_export.md]

## Indata
1) `offer` (JSON-objekt)
2) `offer_template_html` (sträng)

## Steg A — Beräkningar (numerik)
Material per rad:
- `row_total_material = qty * unit_price`

Summering material:
- `sum_material = Σ row_total_material`

Arbete per rad:
- Om `time_total` saknas men `time_per_unit` finns: `time_total = time_per_unit * qty`
- `row_total_labor = time_total * offer.pricing.labor_rate` (om `time_total` saknas → 0)

Summering arbete:
- `sum_hours = Σ (time_total || 0)`
- `sum_labor = Σ row_total_labor`

Slutsummor:
- `subtotal_excl = sum_material + sum_labor`
- `vat_amount    = subtotal_excl * offer.pricing.vat_rate`
- `total_incl    = subtotal_excl + vat_amount`

> Skydda mot `null/NaN`: behandla saknade numeriska fält som 0 i beräkning.

## Steg B — Formatteringsfunktioner (svenska)
- `format_money(x)`: två decimaler, decimalkomma, suffix `" kr"`, tusengrupp med U+202F (&#8239;) **endast om heltalsdelen > 3 siffror**.
  - Ex: `39,75 kr` (ingen gruppering), `1&#8239;234,00 kr`
- `format_hours(x)`: två decimaler + “ h” (ex: `3,60 h`)
- `format_qty(x)`: två decimaler (ex: `25,00`)

## Steg C — Rendera rader
### Material (`<tbody id="material-rows">`)
Kolumner i ordning: Artikel | Benämning | Enhet | Antal | À-pris | Radsumma | Lev.

Regler:
- Enhet visas i gemener för kund: `"M"→"m"`, `"ST"→"st"` (ändra **inte** JSON-data).
- `Antal = format_qty(qty)`
- `À-pris = format_money(unit_price)`
- `Radsumma = format_money(row_total_material)`

### Arbete (`<tbody id="labor-rows">`)
Kolumner i ordning: Arbetsmoment | Moment/Typ/Sort | Underlag/Variant | Enhet | Tid | À-pris | Radsumma

Regler:
- **Arbetsmoment (visning):**
  - Om `arbetsmoment` är heltal (ex `"78"`), visa i stället `moment`.
  - Annars visa `arbetsmoment`.
- Enhet: skriv texten från JSON (ex: “m kabel”, “dosa”, “apparat”).
- Tid:
  - Om `time_total` finns → `format_hours(time_total)`
  - Annars lämna tomt.
- À-pris arbete: `format_money(offer.pricing.labor_rate)` (lämna tomt om `time_total` saknas)
- Radsumma arbete: `format_money(row_total_labor)` (lämna tomt om `time_total` saknas)
- Om posten är “Ej tidsatt i Del 7” (notes eller saknad tid):
  - Lägg texten “(Ej tidsatt i Del 7 – tidsätts i annan ATL-del)” i beskrivningskolumnen (t.ex. efter `moment`).
  - Lämna Tid/À-pris/Radsumma tomma.

## Steg D — Totals-box (`#totals-box`)
Visa:
- Material = `format_money(sum_material)`
- Arbete (`(format_hours(sum_hours))`) = `format_money(sum_labor)`
- Delsumma (exkl. moms) = `format_money(subtotal_excl)`
- Moms `{(offer.pricing.vat_rate * 100)|0} %` = `format_money(vat_amount)`
- Totalsumma (inkl. moms) = `format_money(total_incl)`

## Steg E — Fältboxar
- `#supplier-box` och `#client-box`: radordning `name`, `street`, `zip_city`, `Org.nr: <orgno>`, `email` (radbryt med `<br>`). Om `orgno` saknas → lämna tomt efter “Org.nr:”.
- `#meta-box`: Offertnr (`project.id`), Datum (`project.date`), Giltig t.o.m. (`project.valid_until`), Projekt (`project.title`)
- `#scope`: `offer.notes.terms`

## Steg F — Templating
- Ersätt alla `{{…}}` i mallen.
- Hantera `{{#each material}}` och `{{#each labor}}` som tabellrader.
- Sätt `{{vat_percent}} = heltal(round(offer.pricing.vat_rate * 100))`.

## Steg G — Post-render cleanup (kalla `post_render_cleanup.md`)
- Dubbla mellanslag → ett (ändra ej U+202F).
- ASCII-bindestreck mellan tal → en-dash (–).
- `mm2` → `mm²`.
- Tvinga rätt valuta-formatering (U+202F bara om >3 siffror).
- Säkerställ att raden “Org.nr:” finns i både leverantör och kund.
- Sök efter `{{`/`}}` → om kvar, rendera om tills inga templatemarkörer finns.

## Output (exakt ordning)
1) Komplett HTML (börjar med `<!doctype html>` och innehåller `<meta charset="utf-8">` samt inline-CSS).
2) Separat kodblock med **uppdaterad offert-JSON** (inkl. beräknade fält:
   `time_total`, `row_total` per rad, samt `sum_material`, `sum_hours`, `sum_labor`,
   `subtotal_excl`, `vat_amount`, `total_incl`). Behåll ev. `diagnostics`.

## Felhantering
- Saknas någon summa: rendera HTML ändå, lämna fältet tomt och lägg HTML-kommentar `<!-- validation: saknar <fält> -->`.
- Saknas `labor_rate` eller `vat_rate`: sätt radsummor till tomt och lista brister i `diagnostics.warnings` i JSON (ändra inte mallens layout).
