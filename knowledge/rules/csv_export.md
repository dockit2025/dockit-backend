 Export av materiallista (CSV)

 Triggers
- “exportera materiallista”, “skapa beställningslista”, “ladda ned material”.

 Regler
- Samla enbart materialrader från aktuell kalkyl.
- Slå ihop identiska artikelnummer (summera kvantitet och radsumma).
- Skapa CSV med UTF-8 BOM, fältseparator ;, decimal ,.
- Rubriker och ordning (exakt):
  `Artikelnummer;Benämning;Enhet;Kvantitet;À-pris (SEK);Radsumma (SEK);Leverantör;Notering`
- Kvantitet utan tusentalsavskiljare (ex. 125 eller 12,5).
- Belopp med komma som decimal (ex. 69,00).
- “Radsumma” = Kvantitet × À-pris.
- “Leverantör”: skriv Storel om pris från Storel-listan, annars tomt.
- “Notering”: skriv t.ex. “Byt till IMPRESS vit” om användaren ändrat fabrikat.

 Output
- Returnera enbart CSV i ett kodblock (ingen text före/efter).
- Under CSV: kort summering (antal rader, totalsumma material i SEK).

Kolumnordning för export: Arbetsmoment; Benämning; Underlag/Variant; Enhet; Antal; Tid; Á-pris; Summa.
Dölj alltid: Grupp; Rad.
Formatering: två decimaler på alla talfält; decimaltecken = komma.