# NL_PARSER — Svenska (röst→text→kalkyl) v1.1

Syfte  
Tolkar fri svensk text (röst eller skriven) från hantverkare och bygger offer_json enligt rules/merge_rules.md.  
Parsern använder alla befintliga regel-filer:
- rules/atl_aliases.md  → slang & alias per arbetsmoment  
- rules/atl_mapping.md  → koppling mellan moment och ATL-tider  
- rules/material_filters.md  → val av material  
- rules/merge_rules.md  → slutlig struktur för JSON  

Den här filen returnerar **endast JSON**, ingen HTML.  
HTML och summering sker senare i render-steget.

--------------------------------------------
A) ALIAS-HANTERING (koppling mot atl_aliases.md)

1. Läs in rules/atl_aliases.md.
2. Normalisera all text:
   - Gemener (små bokstäver).
   - Ersätt "×", "x", "X" → "x".
   - Trimma extra mellanslag.
3. För varje [moment]-block i alias-filen:
   - Räkna träffar i keywords (delord eller tokenmatch).
   - Om något ord i negatives finns → sätt poängen till 0.
   - Om texten innehåller något från surfaces → +0,5 poäng.
   - Om texten innehåller enhetsord från unit_alias → +0,5 poäng.
4. Välj det moment som får högst totalpoäng.
   - Tillåt flera moment om texten beskriver fler jobb (t.ex. armatur + dosa + kabel + brytare).
5. Om texten innehåller "i rör", "vp", "flex" eller "slang" → använd ATL-kolumn −3 enligt rules/atl_mapping.md.
6. Mappa valt moment till ATL-rad i Del7_ATL_Total.csv.
   - Underlag och enhet tas från ATL-raden.
   - Justera underlag om miljön i texten antyder "utomhus", "fasad" osv.

--------------------------------------------
B) NORMALISERING AV TEXT (allmänt)

- Skriv om siffror och måttenheter:  
  - "120 m", "6 st", "1,2 m" → tolka som numeriska värden.  
- Komma och punkt: båda accepteras (12,5 == 12.5).  
- Behåll tekniska termer (EXQJ, IP44 osv).  
- Normalisera enheter:  
  - "m", "meter" → "m"  
  - "st", "styck", "stycken" → "st"  
  - "tim", "timmar", "h" → "h"  

--------------------------------------------
C) DATAUTVINNING (regex/semantik)

1. Mängder:
   - längd: `(\d+(?:[.,]\d+)?)\s*m\b`
   - antal: `(\d+(?:[.,]\d+)?)\s*st\b`
2. Kabeltyp/dimension:
   - typ: `(EXQJ|EKKJ|FK|N1XV|N1XE|EQLQ|EKLK|EXLQ|PFXP)`
   - dimension: `(\d)\s*x\s*(\d+(?:[.,]\d+)?)`
3. Underlag:
   - "betong", "tegel", "lättbetong", "stål" → Betong/Tegel/Lättbetong/Stål ≤5 mm  
   - "trä", "clips" → Trä/strips/clips/stål ≤3 mm  
   - "i rör" → använd kolumn −3
4. IP-klass och plats:
   - `IP\d{2}` → välj material med minst motsvarande IP-klass
   - ord som "ute", "fasad", "entré" → markera som utomhus
5. Typiska komponenter:
   - "kapslad dosa", "kopplingsdosa" → kapslad dosa (IP≥44)
   - "armatur", "lampa", "skymningsrelä" → armatur utomhus
   - "uttag" → vägguttag (IP-krav om utomhus)
   - "strömbrytare", "indikering" → strömbrytare med indikering

--------------------------------------------
D) ARBETSMOMENT (ATL-KOPPLING)

- "Kabel i rör" → alltid kolumn −3.  
- Övriga moment → kolumn enligt underlag (rules/atl_mapping.md).  
- Om exakt rad saknas:  
  `time_per_unit = null`, `time_total = 0`,  
  `notes = "Ej tidsatt i Del 7 – tidsätts i annan ATL-del"`.  

Labor-poster ska innehålla:
- arbetsmoment = ATL "Arbetsmoment"
- moment = "Moment/Typ/Sort"
- underlag = "Underlag/Variant"
- unit = "Enhet"
- qty = extraherad mängd
- time_per_unit = värde från ATL
- time_total = time_per_unit * qty

--------------------------------------------
E) MATERIALVAL (rules/material_filters.md)

- Matcha kabel via typ + dimension (t.ex. EXQJ 3x2,5).  
- Matcha armatur, dosa, brytare, uttag baserat på alias och IP-klass.  
- Om flera produkter matchar → välj den billigaste GN-priset.  
- Enhet styrs av ATL (t.ex. m eller st).

--------------------------------------------
F) OUTPUT (offer_json enligt merge_rules.md)

Struktur:
{
  "supplier": {...},
  "client": {...},
  "project": {...},
  "pricing": { "labor_rate": number, "vat_rate": number },
  "material": [
    { "sku": "", "name": "", "unit": "", "qty": number, "unit_price": number, "supplier": "Storel" }
  ],
  "labor": [
    { "arbetsmoment": "", "moment": "", "underlag": "", "unit": "", "qty": number,
      "time_per_unit": number|null, "time_total": number|null, "notes": "" }
  ],
  "notes": { "terms": "" }
}

Summor beräknas **inte** här – de görs i render-steget.  
Den här filen returnerar endast JSON.

--------------------------------------------
G) EXEMPEL-FLÖDE

Fri text:  
“Dra 5 meter EXQJ 3x1,5 i rör till ny utelampa, montera kapslad dosa IP54 och byt brytare med indikering.”

→ aliasparsern hittar:  
- Kabeldragning i rör (kolumn −3)  
- Montering kapslad dosa (IP54)  
- Byte strömbrytare (med indikering)  
- Montering väggarmatur utomhus (skymningsrelä implicit)  

→ bygger offer_json med:
- 4 labor-poster  
- 4 materialposter  
- samlade notes med eventuella antaganden  
