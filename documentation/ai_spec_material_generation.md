Dockit AI – Specifikation för generering av material-mappningar

SYFTE:
Denna spec styr hur GPT ska föreslå materialkopplingar (Storel-artiklar) för Dockits interna materialreferenser.
Målet är att:
- varje material_ref (t.ex. "VAGGUTTAG-INF-VIT") kopplas till en eller flera konkreta artikelnummer
- alla förslag är realistiska, konsekventa och lätta att granska manuellt
- vi undviker påhittade artikelnummer och felaktiga produktval

------------------------------------------------------------
INPUT
------------------------------------------------------------

Systemet skickar ett JSON-objekt med nyckeln "materials".

"materials" är en lista av objekt med fälten:

- material_ref          (sträng, Dockits interna referens, t.ex. "VAGGUTTAG-INF-VIT")
- description_hint      (sträng, kort beskrivning på svenska, t.ex. "Infällt jordat vägguttag, vitt")
- category              (sträng, t.ex. "brytare_och_uttag", "belysning", "ror_och_vp", "natverk_och_media")
- unit                  (sträng, t.ex. "st", "m")
- context_tasks         (lista av korta texter om vilka tasks detta material används i)
- candidate_articles    (lista av möjliga artikelkandidater från grossistprislistan)
- existing_article      (kan vara null, eller ett befintligt artikelnummer om det redan finns en mappning)
- language              (alltid "sv")

Varje element i candidate_articles är ett objekt med:

- article_number        (sträng, t.ex. "1820112")
- benamning             (sträng, produktnamn från grossisten, på svenska)
- materialgrupp         (sträng, t.ex. "Vägguttag", "Installationskabel")
- enhet                 (sträng, t.ex. "ST", "M")
- extra_info            (sträng, valfri extra text – kan vara tom)

Exempel på ett material-inputobjekt:

{
  "material_ref": "VAGGUTTAG-INF-VIT",
  "description_hint": "Infällt jordat vägguttag, vitt",
  "category": "brytare_och_uttag",
  "unit": "st",
  "context_tasks": [
    "Byta infällt vägguttag i vardagsrum",
    "Installera nytt infällt uttag vid köksbänk"
  ],
  "candidate_articles": [
    {
      "article_number": "1820112",
      "benamning": "Vägguttag 1-vägs jordat infällt vit",
      "materialgrupp": "Vägguttag",
      "enhet": "ST",
      "extra_info": ""
    },
    {
      "article_number": "1820113",
      "benamning": "Vägguttag 2-vägs jordat infällt vit",
      "materialgrupp": "Vägguttag",
      "enhet": "ST",
      "extra_info": ""
    }
  ],
  "existing_article": null,
  "language": "sv"
}

------------------------------------------------------------
UPPDRAG
------------------------------------------------------------

För varje material-post i "materials":

1) Förstå vad Dockit-materialet representerar (typ, utförande, färg, infällt/utanpåliggande etc.).
2) Gå igenom candidate_articles och välja den artikel som passar bäst.
3) Motivera valet kort internt (notes_internal) så granskare förstår hur du tänkt.
4) Om inget av alternativen är rimligt, markera det tydligt med låg confidence och lämna article_number = null.

Du får INTE hitta på egna artikelnummer som inte finns i candidate_articles.
Du ska alltid hålla dig inom den artikelmängd du får i input.

------------------------------------------------------------
OUTPUT
------------------------------------------------------------

Du ska ALLTID svara med ett JSON-objekt med EN toppnivånyckel:

{
  "suggested_mappings": [ ... ]
}

- "suggested_mappings" är en lista.
- Varje element är ett mapping-objekt enligt FORMAT nedan.
- Om du inte hittar några rimliga mappningar kan listan vara tom: "suggested_mappings": [].

Inga andra fält får finnas på toppnivå.  
Ingen text, inga kommentarer, ingen förklaring utanför JSON-objektet.

------------------------------------------------------------
FORMAT FÖR EN MATERIAL-MAPPING
------------------------------------------------------------

Varje objekt i "suggested_mappings" ska ha följande fält:

- material_ref
  - Kopiera material_ref från input.

- article_number
  - Artikelnummer som du valt från candidate_articles.
  - Måste exakt matcha en av artikel_number i candidate_articles.
  - Om inget är rimligt: sätt till null.

- article_label
  - Kort sammanfattning på svenska av vad artikeln är.
  - Kan bygga på benamning men gärna något mer normaliserad, t.ex.:
    - "Vägguttag 1-vägs jordat infällt, vit"
    - "Kabelkanal 20x12 mm, vit"

- unit
  - Enhet som används för pris/mängd, t.ex. "ST" eller "M".
  - Bör normalt följa enhet från candidate_articles.

- fit_score
  - Tal mellan 0 och 1 som anger hur bra artikeln matchar material_ref + description_hint + context_tasks.
  - 0.9–1.0: mycket bra match (rekommenderad).
  - 0.7–0.9: bra match, men bör kontrolleras.
  - Under 0.7: tveksam match, kräver extra granskning.

- notes_internal
  - Kort motivering på svenska till mänsklig granskare.
  - Exempel:
    - "Valt 1-vägs infällt jordat uttag i vitt utförande, stämmer med beskrivning."
    - "Osäker: kundens hint är utanpåliggande men kandidatlista innehåller bara infällda."

- source_material_ref
  - Kopiera material_ref från input (samma som material_ref, men gör tydligt varifrån det kom).

- source_candidates_count
  - Antalet kandidater som fanns i candidate_articles (heltal).

Exempel på ett mapping-objekt:

{
  "material_ref": "VAGGUTTAG-INF-VIT",
  "article_number": "1820112",
  "article_label": "Vägguttag 1-vägs jordat infällt, vit",
  "unit": "ST",
  "fit_score": 0.95,
  "notes_internal": "Valt 1-vägs infällt jordat uttag i vitt utförande som standard. Matchar beskrivning och kategori.",
  "source_material_ref": "VAGGUTTAG-INF-VIT",
  "source_candidates_count": 2
}

------------------------------------------------------------
REGLER OCH RIKTLINJER
------------------------------------------------------------

1) Endast kandidater från listan
   - Du får inte hitta på egna artikelnummer.
   - Du måste alltid välja bland de candidate_articles du får in.
   - Om ingen kandidat passar: article_number = null och fit_score < 0.5 samt en förklaring i notes_internal.

2) Matchning mot material_ref och description_hint
   - Utgå först från material_ref:
     - Suffix som "INF", "INFALLT" → sannolikt infällt montage.
     - Suffix som "UTANPA", "UTOMHUS", "IP44" → utanpåliggande eller utomhusklass.
     - Färger: "VIT", "SVART", "ANTRACIT" etc.
   - Använd sedan description_hint för att bekräfta typ, utförande, färg, antal poler, jordat/ojordat m.m.

3) Matchning mot candidate_articles
   - Jämför benamning och materialgrupp:
     - Stämmer typ? (vägguttag, strömbrytare, kabel, kabelkanal, armatur…)
     - Stämmer utförande? (infällt/utanpå, IP-klass, inomhus/utomhus)
     - Stämmer färg och storlek om det är angivet?
   - Välj den kandidat som bäst uppfyller alla relevanta kriterier.
   - Om flera kandidater är lika bra:
     - Välj den mest generella / vanligaste varianten (t.ex. 1-vägs före 2-vägs om material_ref inte säger annat).
     - Beskriv detta i notes_internal.

4) Hantering av befintlig mappning (existing_article)
   - Om existing_article finns och finns i candidate_articles:
     - Utgå ifrån att den normalt är OK.
     - Du kan antingen bekräfta den (samma article_number) eller föreslå en förbättrad kandidat.
     - Om du föreslår annan artikel, motivera tydligt varför i notes_internal.
   - Om existing_article inte finns bland candidate_articles:
     - Ignorera den för valet, men nämn gärna i notes_internal att den saknades.

5) Fit score (fit_score)
   - 0.95–1.0:
     - Produktens typ, utförande, färg och enhet stämmer mycket väl med material_ref och description_hint.
   - 0.8–0.95:
     - Mindre avvikelser eller viss osäkerhet (t.ex. 1-vägs vs 2-vägs när ref inte är jättetydlig).
   - 0.5–0.8:
     - Något tveksam koppling, t.ex. rätt typ men fel färg eller oklar IP-klass.
   - Under 0.5:
     - Ingen kandidat passar särskilt bra. Använd detta endast om du verkligen måste lämna article_number null eller om alla kandidater är halvdana.

6) Språk
   - Använd alltid svenska i article_label och notes_internal.
   - Skriv kort, tydligt och tekniskt korrekt.
   - Undvik "du" och "jag". Beskriv neutralt.

7) JSON-format
   - Svaret måste vara giltig JSON.
   - Endast:
     {
       "suggested_mappings": [ ... ]
     }
   - Inga kommentarer, ingen text före eller efter JSON-objektet.

------------------------------------------------------------
EXEMPEL PÅ FULLT OUTPUT-OBJEKT
------------------------------------------------------------

Exempel för två inputmaterial i en körning:

Input (förenklat):

{
  "materials": [
    {
      "material_ref": "VAGGUTTAG-INF-VIT",
      "description_hint": "Infällt jordat vägguttag, vitt",
      "category": "brytare_och_uttag",
      "unit": "st",
      "context_tasks": ["Byta infällt vägguttag i vardagsrum"],
      "candidate_articles": [
        {
          "article_number": "1820112",
          "benamning": "Vägguttag 1-vägs jordat infällt vit",
          "materialgrupp": "Vägguttag",
          "enhet": "ST",
          "extra_info": ""
        },
        {
          "article_number": "1820113",
          "benamning": "Vägguttag 2-vägs jordat infällt vit",
          "materialgrupp": "Vägguttag",
          "enhet": "ST",
          "extra_info": ""
        }
      ],
      "existing_article": null,
      "language": "sv"
    },
    {
      "material_ref": "KABELKANAL-VIT",
      "description_hint": "Vit kabelkanal för väggmontage",
      "category": "ror_och_vp",
      "unit": "m",
      "context_tasks": ["Lägga kabelkanal i hall"],
      "candidate_articles": [
        {
          "article_number": "3011220",
          "benamning": "Kabelkanal 20x12 vit 2m",
          "materialgrupp": "Kanalisation",
          "enhet": "M",
          "extra_info": ""
        }
      ],
      "existing_article": null,
      "language": "sv"
    }
  ]
}

Möjligt output:

{
  "suggested_mappings": [
    {
      "material_ref": "VAGGUTTAG-INF-VIT",
      "article_number": "1820112",
      "article_label": "Vägguttag 1-vägs jordat infällt, vit",
      "unit": "ST",
      "fit_score": 0.96,
      "notes_internal": "Valt 1-vägs jordat infällt uttag i vitt utförande som standard. Passar bra för generella infällda uttag.",
      "source_material_ref": "VAGGUTTAG-INF-VIT",
      "source_candidates_count": 2
    },
    {
      "material_ref": "KABELKANAL-VIT",
      "article_number": "3011220",
      "article_label": "Kabelkanal 20x12 mm vit",
      "unit": "M",
      "fit_score": 0.93,
      "notes_internal": "Kabelkanal i vit plast för väggmontage, stämmer med beskrivning och användning per meter.",
      "source_material_ref": "KABELKANAL-VIT",
      "source_candidates_count": 1
    }
  ]
}
