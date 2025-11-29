\# render\_validator.md — v1.2



Syfte

\- Validera en renderad offert-HTML mot krav. Returnera en \*\*kort rapport\*\* med PASS/FAIL per rad enligt checklistan.



Indata

\- `html`: fullständig HTML-sträng efter post\_render\_cleanup.



Rapportformat (exakt)

\- En rad per kontroll i samma ordning som checklistan.

\- Format: `\[PASS] <text>` eller `\[FAIL] <text> – <orsak/korrigeringsförslag>`

\- Om något FAIL: lägg till en avslutande sektion `Åtgärdsförslag:` med punktlista över brister.



Checklistan (kontroller och regler)



1\) Inga templatemarkörer kvar ("{{" eller "}}")

\- FAIL om `{{` eller `}}` förekommer någonstans i `html`.



2\) "Org.nr:" finns inför sifferraden i både Leverantör och Kund

\- Gäller `#supplier-box` och `#client-box`.

\- PASS om båda boxar innehåller texten `Org.nr:`.

\- Rekommenderad extra kontroll: minst en sifferföljd `\\d{6,}` i respektive box på samma rad eller efterföljande rad.

\- FAIL exempel: `#client-box saknar "Org.nr:"` → föreslå att infoga rad `Org.nr: <värde>`.



3\) Alla pengar har två decimaler och U+202F som tusentalsavskiljare (ex: 11 670,00 kr)

\- Gäller alla belopp som slutar med `kr` (med mellanslag före).

\- Tillåt både U+202F och HTML-entiteten `\&#8239;` mellan grupper.

\- Mönster som ska PASS:a:

&nbsp; - `^\\d{1,3}(\\u202F|\&#8239;)?\\d{3}(?:\\1?\\d{3})\*,\\d{2}\\skr$`

&nbsp; - eller `^\\d+,\\d{2}\\skr$` för belopp < 1 000.

\- FAIL om:

&nbsp; - inte exakt två decimaler, eller

&nbsp; - fel tusentalsavskiljare (vanligt blanktecken eller `\&nbsp;`), eller

&nbsp; - saknat blanktecken före `kr`.

\- Vid FAIL: rapportera första 3 felande belopp och föreslå `post\_render\_cleanup` körning.



4\) "Arbete (X,YY h)" visar timmar med exakt två decimaler

\- Sök i `#totals-box` efter raden som börjar med `Arbete (` och slutar med `h)`.

\- Mönster: `Arbete \\(\\d+,\\d{2} h\\)`

\- FAIL om format avviker, decimalpunkt används, eller antal decimaler ≠ 2.



5\) mm2 inte förekommer (ska vara mm²)

\- FAIL om regex `\\bmm2\\b` matchar (case-sensitiv).

\- PASS om endast `mm²` förekommer.



6\) Datum/offertnr använder en-dash (–) mellan tal

\- Datum: i `#meta-box` ersätts `-` mellan siffror av en-dash. Validera med `\\d{4}–\\d{2}–\\d{2}`.

\- Offertnr: om mönster prefix–år–löpnummer förekommer, krävs en-dash mellan segment, t.ex. `OFR–2025–041`.

\- FAIL om ASCII-`-` används mellan tal i datum/offertnr.



7\) Tabellernas kolumnordning följer reglerna

\- Material (`#material-rows` tabellhuvud exakt ordning):

&nbsp; - `Artikel`, `Benämning`, `Enhet`, `Antal`, `À-pris`, `Radsumma`, `Lev.`

\- Arbete (`#labor-rows` tabellhuvud exakt ordning):

&nbsp; - `Arbetsmoment`, `Moment/Typ/Sort`, `Underlag/Variant`, `Enhet`, `Tid`, `À-pris`, `Radsumma`

\- PASS om `th`-texter matchar exakt i given ordning för respektive tabell.

\- FAIL: lista vilken tabell och förväntad vs faktisk ordning.



Implementationsskisser (regex och urval)



\- Extrahera boxar:

&nbsp; - supplier: `<div\[^>]\*id=\["']supplier-box\["']\[^>]\*>(.\*?)</div>` (DOTALL)

&nbsp; - client:   `<div\[^>]\*id=\["']client-box\["']\[^>]\*>(.\*?)</div>` (DOTALL)

&nbsp; - totals:   `<div\[^>]\*id=\["']totals-box\["']\[^>]\*>(.\*?)</div>` (DOTALL)

&nbsp; - meta:     `<div\[^>]\*id=\["']meta-box\["']\[^>]\*>(.\*?)</div>` (DOTALL)



\- Pengar (hitta alla kandidater):

&nbsp; - `(\\d\[\\d \\u00A0\\u202F]\*,\\d{2})\\s\*kr`



\- Datum/offertnr:

&nbsp; - datum PASS: `\\b\\d{4}–\\d{2}–\\d{2}\\b`

&nbsp; - datum FAIL: `\\b\\d{4}-\\d{2}-\\d{2}\\b`

&nbsp; - offertnr en-dash mellan sifferblock: `(\\d)\\s\*–\\s\*(\\d)`



\- Tabellhuvuden:

&nbsp; - material: samla alla `<th>` i första `table` före `#material-rows`.

&nbsp; - arbete: samla alla `<th>` i första `table` före `#labor-rows`.



Utdata (exempel)



```



\[PASS] Inga templatemarkörer kvar ("{{" eller "}}")

\[PASS] "Org.nr:" finns inför sifferraden i både Leverantör och Kund

\[PASS] Alla pengar har två decimaler och U+202F som tusentalsavskiljare (ex: 11 670,00 kr)

\[PASS] "Arbete (X,YY h)" visar timmar med exakt två decimaler

\[PASS] mm2 inte förekommer (ska vara mm²)

\[PASS] Datum/offertnr använder en-dash (–) mellan tal

\[PASS] Tabellernas kolumnordning följer reglerna



```



Vid fel (exempel)



```



\[PASS] Inga templatemarkörer kvar ("{{" eller "}}")

\[FAIL] "Org.nr:" finns inför sifferraden i både Leverantör och Kund – client-box saknar etiketten

\[FAIL] Alla pengar har två decimaler och U+202F som tusentalsavskiljare (ex: 11 670,00 kr) – felaktiga belopp: "1 450,00 kr", "7395,00 kr"

\[PASS] "Arbete (X,YY h)" visar timmar med exakt två decimaler

\[PASS] mm2 inte förekommer (ska vara mm²)

\[FAIL] Datum/offertnr använder en-dash (–) mellan tal – datum använder '-' i "2025-11-03"

\[PASS] Tabellernas kolumnordning följer reglerna



Åtgärdsförslag:

• Kör post\_render\_cleanup för att normalisera valuta och datum (U+202F och en-dash).

• Infoga "Org.nr:"-rad i #client-box (tomt värde om okänt).

• Formatera pengar till två decimaler och infoga   som tusentalsavskiljare.



```

```



