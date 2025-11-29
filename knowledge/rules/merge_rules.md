Mall-merge och formatering (offer_template.html → HTML)

Den här regeln beskriver exakt hur modellen ska rendera offerten från data (offer-JSON) och mallen (offer_template.html). Inga templatemarkörer får lämnas kvar i output.

1) Datakälla (offer-JSON: schema, fält)
{
  "supplier": { "name": "", "street": "", "zip_city": "", "orgno": "", "email": "" },
  "client":   { "name": "", "street": "", "zip_city": "", "orgno": "", "email": "" },
  "project":  { "id": "", "title": "", "valid_until": "", "date": "" },
  "pricing":  { "labor_rate": 0, "vat_rate": 0.25 },
  "material": [
    { "sku": "", "name": "", "unit": "", "qty": 0, "unit_price": 0.0, "supplier": "Storel" }
  ],
  "labor": [
    {
      "arbetsmoment": "",
      "moment": "",
      "underlag": "",
      "unit": "",
      "qty": 0,
      "time_per_unit": 0.0,
      "time_total": 0.0,
      "notes": ""
    }
  ],
  "notes": { "terms": "" }
}


Viktigt:

arbetsmoment ska alltid komma från ATL-filen och visas för kund.

Grupp och Rad får aldrig exponeras i HTML.

2) Renderingsregler (obligatoriskt)

Läs offer_template.html.

Ersätt alla {{…}} med värden från offer-JSON.

Hantera blocken {{#each material}} … {{/each}} och {{#each labor}} … {{/each}} genom att generera motsvarande <tr>-rader.

Saknas ett värde → använd tom sträng (aldrig kvar {{placeholder}}).

Returnera renderad HTML i ett (1) kodblock.

Returnera därefter offer-JSON i ett separat kodblock (för spårbarhet).

2.1) Fältplacering i mallen (standard-IDs i offer_template.html)

Leverantör fylls i #supplier-box (radbrytningar <br>).

Kund fylls i #client-box.

Metainfo fylls i #meta-box (Offertnr, Datum, Giltig t.o.m., Projekt).

Materialrader injiceras i <tbody id="material-rows">.

Arbetesrader injiceras i <tbody id="labor-rows">.

Sammanställningen injiceras i #totals-box (se 3.3).

3) Beräkningar och summeringar
3.1) Material

Per rad:

radsumma_material = qty * unit_price


Totalsumma material:

sum_material = Σ radsumma_material

3.2) Arbete (ATL)

Per rad (om time_total saknas):

time_total = time_per_unit * qty


Tid ska alltid vara numeriskt och avrundat till 2 decimaler (se §4).

Radsumma arbete:

radsumma_arbete = time_total * pricing.labor_rate


Totalsumma arbete och timmar:

sum_hours  = Σ time_total
sum_labor  = Σ radsumma_arbete

3.3) Slutrader (exkl./inkl. moms)
subtotal_excl = sum_material + sum_labor
vat_amount    = subtotal_excl * pricing.vat_rate
total_incl    = subtotal_excl + vat_amount


Följande rader ska visas i #totals-box som “line”-divar (se CSS i mallen):

Material

Arbete (inkl. total timmar efter texten, t.ex. “Arbete (4,25 h)”)

Delsumma (exkl. moms)

Moms 25 % (texten speglar pricing.vat_rate)

Totalsumma (inkl. moms)

Exempel (HTML som ska genereras i #totals-box):

<div class="line"><span>Material</span><span>22 844,20 kr</span></div>
<div class="line"><span>Arbete (4,25 h)</span><span>17 360,00 kr</span></div>
<div class="line"><span>Delsumma (exkl. moms)</span><span>40 204,20 kr</span></div>
<div class="line"><span>Moms 25&nbsp;%</span><span>10 051,05 kr</span></div>
<div class="line total"><span>Totalsumma (inkl. moms)</span><span>50 255,25 kr</span></div>

4) Talformat (svenska)

Tusental: smalt mellanrum (U+202F).

Decimaltecken: komma.

Exakt två decimaler för alla pengar och timmar.

Formatteringsfunktion (konceptuellt):

format_money(22844.2) → "22 844,20 kr"
format_hours(3.6)     → "3,60 h"
format_qty(25)        → "25,00"

5) Kolumnordning & dolda fält

Arbetsrader (tabellhuvud och varje <tr> måste följa denna ordning):

Arbetsmoment

Moment/Typ/Sort

Underlag/Variant

Enhet

Tid (format_hours)

À-pris (format_money av pricing.labor_rate)

Radsumma (format_money av radsumma_arbete)

Dölj alltid: Grupp, Rad (får inte renderas i HTML).

Materialrader: Artikel, Benämning, Enhet, Antal, À-pris, Radsumma, Lev.

6) Fallback (om mallen inte kan läsas)

Rendera en enkel, fristående HTML-sida med samma sektioner och tabeller enligt fältordningen ovan.

Behåll samma summeringslogik och formatering.

7) Post-render cleanup (måste köras sist)

1) Ersätt tecken/markörer

Dubbla mellanslag → ett mellanslag.

ASCII-bindestreck mellan tal → en dash:

RegEx: (\d)\?(\d) → $1–$2

RegEx: (\d)-(\d) → $1–$2

mm2 → mm²

I leverantör/kund-block: om en ensam siffersträng (\d{6,}) förekommer på egen rad och inte redan har prefix → lägg till Org.nr: framför.

2) Templatemarkörer får inte finnas kvar

Sök efter {{ eller }}. Om något hittas måste renderingen göras om tills inga markörer återstår.

3) Ej tidsatta moment

Om en arbetsrad saknar tid (time_total = 0 eller null):

Lägg till texten “(Ej tidsatt i Del 7 – tidsätts i annan ATL-del)” i beskrivningskolumnen.

Lämna tid/à-pris/radsumma tomma (behåll raden).

4) Numerik

Alla interna beräkningar görs på numeriska värden.

Avrunda alltid till 2 decimaler först vid presentation.

8) Validering före output

Kontrollera att Arbetsmoment finns på varje arbetsrad – annars ska raden inte renderas.

Kontrollera att summeringar (sum_material, sum_labor, sum_hours, subtotal_excl, vat_amount, total_incl) finns och är numeriska.

Om något saknas → rendera ändå HTML men lämna de saknade fälten tomma och lägg en HTML-kommentar, t.ex.:
<!-- validation: saknar sum_labor -->.

Klar! När du sparat detta som rules/merge_rules.md kan vi testköra igen. Vill du att jag även skickar en uppdaterad offer_template.html som matchar exakt (med #totals-box etc.)?