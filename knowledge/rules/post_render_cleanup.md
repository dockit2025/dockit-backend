\# post\_render\_cleanup.md — v1.5

Mål: Säkerställa att all HTML-offert uppfyller formateringsreglerna så att render\_validator alltid returnerar PASS.



\## 1. Org.nr-rader

\- Gäller sektionerna `#supplier-box` och `#client-box`.

\- a) Om en rad innehåller ett organisationsnummer utan prefix → ändra till "Org.nr: <värde>".

\- b) Om ingen rad börjar med "Org.nr:" → infoga en ny rad "Org.nr: " (tomt värde) precis ovanför e-postraden.

\- Etiketten "Org.nr:" ska alltid finnas, även om värdet är tomt.



\## 2. Valuta (tvångssätt U+202F i tusental)

\- Gäller endast belopp som slutar på "kr" (följt av ett mellanslag eller HTML-mellanrum).

\- Algoritm per träff:

&nbsp; 1. Dela upp beloppet i tre delar:

&nbsp;    - INT = heltalsdelen före kommatecknet

&nbsp;    - DEC = kommatecken + två decimaler

&nbsp;    - SUF = " kr"

&nbsp; 2. Ta bort alla typer av mellanslag i INT (vanliga, hårda och U+202F).

&nbsp; 3. \*\*Om INT har fler än 3 siffror:\*\* bygg om från höger i grupper om tre, infoga HTML-entiteten `\&#8239;` (smalt icke-brytande mellanrum) mellan grupperna.

&nbsp; 4. Sätt ihop: INT\_regrupperad + DEC + SUF.

\- Exempel:

&nbsp; - "11670,00 kr" → "11\&#8239;670,00 kr"

&nbsp; - "1 450,00 kr" → "1\&#8239;450,00 kr"

&nbsp; - "7 395,00 kr" → "7\&#8239;395,00 kr"

&nbsp; - "39,75 kr" → (ingen ändring)

\- Rör inte värden utan "kr" (t.ex. "120,00").



\## 3. En-dash i numeriska separeringar

\- Datum: byt ASCII-bindestreck mellan tal till en-dash (–), t.ex. `2025–11–03`.

\- Offertnummer: om formatet innehåller prefix + årtal + löpnummer → ersätt bindestrecket mellan prefix och årtal med en-dash, t.ex. `OFR–2025–TEST`.

\- Lämna övriga bindestreck orörda.



\## 4. mm²-notation

\- Ersätt alla förekomster av `mm2` med `mm²` i textinnehåll och tabeller.



\## 5. Dubbla mellanslag

\- Ersätt följder av två eller fler vanliga mellanslag med ett.

\- Observera: ändra \*\*inte\*\* U+202F-tecken (smala icke-brytande mellanrum).



\## 6. Templatemarkörer

\- Sök efter `{{` eller `}}`. Om någon förekomst hittas → rendera om tills inga templatemarkörer finns kvar.



\## Output

\- Returnera fullständig HTML med identisk struktur.

\- Endast typografiska, språkliga och etikettmässiga justeringar ska göras.

\- Resultatet ska uppfylla alla PASS-krav vid körning av render\_validator.md.



