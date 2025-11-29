# post_render_cleanup.md — v1.5.1

Mål: Säkerställa att all HTML-offert uppfyller formateringsreglerna så att `render_validator` returnerar PASS. Endast typografiska, språkliga och etikettmässiga justeringar – HTML-struktur ska bevaras.

## 0. Allmänt
- Kör stegen i ordning 1 → 6.
- Operationerna ska vara **idempotenta** (upprepade körningar får inte förändra redan korrigerad text).
- Arbeta endast i HTML-body-innehållet; rör inte `<style>`, `<script>` eller attributvärden.

## 1. Org.nr-rader
Gäller behållarna `#supplier-box` och `#client-box`.

### 1.a Prefixa rad med Org.nr:
- Om en rad (blocknivå eller `<br>`-separerad) innehåller ett enda organisationsnummer **utan** prefix, lägg till `Org.nr: ` i början.
- Organisationsnummer detekteras med:
  - `(?<!\d)(\d{6,})(?!\d)`  *(minst 6 siffror, inga angränsande siffror)*

### 1.b Infoga tom etikett om saknas
- Om **ingen** rad i respektive box börjar med `Org.nr:` → infoga en ny rad `Org.nr: ` **precis ovanför** e-postraden om den finns, annars längst ned i boxen.
- E-postrad detekteras heuristiskt med: `[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}` (case-insensitiv).

> Resultat: Etiketten “Org.nr:” ska alltid finnas i båda boxarna, även vid tomt värde.

## 2. Valuta – tvångsinför U+202F i tusental
Gäller endast belopp som **slutar på** `kr` (ev. mellanslag/HTML-mellanrum före).

### 2.a Träffdetektering
- Regex (global, case-sensitiv):  
  `(?P<int>\d{1,3}(?:[ \u00A0\u202F]?\d{3})*)(?P<dec>,\d{2})\s*(?:kr)`  
  – fångar heltal + exakt två decimaler + “kr”.

### 2.b Normalisering
- Ta bort **alla** mellanslagstyper i `int`.
- Om `int` har fler än tre siffror: gruppera från höger i 3-grupper och infoga **smalt NBSP**: `&#8239;` mellan grupperna.
- Sätt ihop `int_grouped + dec + " kr"`.

**Exempel**
- `11670,00 kr` → `11&#8239;670,00 kr`
- `1 450,00 kr` → `1&#8239;450,00 kr`
- `7 395,00 kr` (NBSP) → `7&#8239;395,00 kr`
- `39,75 kr` → *oförändrat* (inga tusental).

> Rör inte numerik utan `kr` (t.ex. `120,00` eller `3,60 h`).

## 3. En-dash i numeriska separeringar
- Datum: byt ASCII-bindestreck mellan tal till en-dash:  
  Regex: `(\d)\s*-\s*(\d)` → ersätt med `$1–$2`.
- Offertnummer med prefix–år–löpnummer: säkerställ en-dash mellan segment (behåll befintliga en-dash).  
  Exempel: `OFR-2025-041` → `OFR–2025–041`.

> Andra bindestreck lämnas orörda.

## 4. mm²-notation
- I text- och tabellceller: ersätt `(\d)\s*mm2\b` → `$1 mm²`.  
- Lämna redan korrekta `mm²` orört.

## 5. Dubbla mellanslag
- Ersätt följder av **vanliga** mellanslag (ASCII 0x20) på 2+ i följd med ett enkelmellanrum.
- Skydda `&#8239;` (U+202F) och `&nbsp;`/U+00A0: de ska **inte** påverkas.

## 6. Templatemarkörer
- Sök efter `{{` eller `}}`. Om någon förekomst hittas → **avbryt och rendera om** tills inga markörer återstår.

## 7. Ej tidsatta moment
- För varje rad i arbetestabellen:
  - Om `time_total` saknas eller är `0` (`0,00 h` efter formatering):
    - Lägg till texten **“(Ej tidsatt i Del 7 – tidsätts i annan ATL-del)”** i kolumnen *Arbetsmoment* (om inte redan tillagd).
    - Lämna *Tid*, *À-pris* och *Radsumma* **tomma** (bevara övriga celler).

## 8. Numerikprincip
- Alla beräkningar ska redan vara gjorda numeriskt före cleanup.
- Cleanup får endast formatera presentationen (två decimaler, mellanrum, symboler).

## 9. Output
- Returnera **fullständig HTML** med **identisk struktur** (endast textuella/typografiska ändringar).
- Resultatet ska passera alla PASS-krav i `render_validator.md`.
