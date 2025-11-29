Dockit AI – Specifikation för generering av nya tasks från fri text

SYFTE:
Denna spec styr hur GPT ska föreslå nya standardiserade arbetsmoment (tasks) baserat på kundernas fria text.  
Tasks ska passa in i Dockits befintliga struktur med YAML-mappings, ATL-tider och materialkopplingar.

------------------------------------------------------------
INPUT
------------------------------------------------------------

Systemet skickar ett JSON-objekt med nyckeln "segments".

"segments" är en lista av objekt med fälten:

- segment_id          (sträng, unikt ID)
- segment_text        (sträng, kundens fria text på svenska)
- source_type         (t ex "missing_task_segment")
- room_hint           (t ex "vardagsrum", "kök", "hall", "badrum" eller null)
- language            (alltid "sv")
- existing_task_ref   (kan vara null eller en befintlig task_ref som ligger nära)

Exempel på ett segment:

{
  "segment_id": "seg_001",
  "segment_text": "Jag ska sätta upp tre utanpåliggande vägguttag på gipsvägg",
  "source_type": "missing_task_segment",
  "room_hint": "vardagsrum",
  "language": "sv",
  "existing_task_ref": null
}

------------------------------------------------------------
UPPDRAG
------------------------------------------------------------

För varje segment ska du:

1) Tolka vilket elektrikerjobb som beskrivs.
2) Avgöra om det bör bli en ny återanvändbar standard-task.
3) Om ja: skapa ett task-förslag enligt TASK-FORMAT nedan.
4) Om nej: hoppa över segmentet eller ge låg confidence.

Viktigt:
- Tasks ska vara generella och kunna användas för många kunder.
- Tasks ska inte vara kundspecifika, inte innehålla adresser, namn eller liknande.
- Flera segment kan mappas till samma task_ref om jobbet i grunden är samma typ av arbete.

------------------------------------------------------------
OUTPUT
------------------------------------------------------------

Du ska ALLTID svara med ett JSON-objekt med EN toppnivånyckel:

{
  "suggested_tasks": [ ... ]
}

- "suggested_tasks" är en lista.
- Varje element är ett task-objekt enligt TASK-FORMAT.
- Om du inte hittar några rimliga tasks kan listan vara tom: "suggested_tasks": [].

Inga andra fält får finnas på toppnivå.  
Ingen text, inga kommentarer, ingen förklaring utanför JSON-objektet.

------------------------------------------------------------
TASK-FORMAT
------------------------------------------------------------

Varje task-objekt ska ha följande fält:

- task_ref
  - Kort intern kod i VERSALER med bindestreck.
  - Format: VERB-OBJEKT, t ex:
    - "BYTA-VAGGUTTAG-INFALLT"
    - "INSTALLERA-SPOTLIGHT-TAK"
    - "LAGGA-KABELKANAL"
  - Återanvänd gärna verb som BYTA, INSTALLERA, DRA, LAGGA, SATT-UPP, FELSOKA.

- title_sv
  - Kort svensk titel.
  - Exempel: "Byta infällt vägguttag", "Lägga kabelkanal på vägg".

- description_sv
  - 1–3 meningar som beskriver arbetsmomentet tydligt på svenska.
  - Fokus på vad elektrikern praktiskt gör, inte hur kunden upplever det.

- category
  - En av dessa kategorier:
    - "brytare_och_uttag"
    - "belysning"
    - "kok"
    - "badrum"
    - "natverk_och_media"
    - "felsokning_och_service"
    - "ror_och_vp"
    - "ovrigt"
  - Välj kategori som bäst motsvarar var tasken hör hemma i en vanlig el-offert.

- estimated_hours_per_unit
  - Uppskattad tid per enhet i timmar (float).
  - Använd rimliga steg, t ex 0.25, 0.5, 0.75, 1.0, 1.5, 2.0.
  - Riktlinjer:
    - 0.25–0.5: enkla byten, t ex byta 1 vägguttag eller 1 brytare.
    - 0.5–1.5: nyinstallation, flytt av punkt, flera moment i samma task.
    - 1.5+   : större moment, t ex längre kabeldragning eller flera enheter.

- quantity_type
  - Styr hur quantity tolkas.
  - Använd i första hand:
    - "per_unit"   – per styck, t ex per uttag, per armatur.
  - Vid behov kan du använda:
    - "per_meter"  – t ex kabelkanal eller kabeldragning.
    - "per_room"   – t ex allmän belysning i ett rum.
  - Välj den modell som är mest praktisk för att räkna tid och material.

- default_unit
  - Kort enhetstext som matchar quantity_type.
  - Exempel:
    - "st" för per_unit.
    - "m"  för per_meter.
    - "rum" för per_room.

- patterns
  - Lista med typiska kundfraser som ska matcha denna task.
  - Minst en pattern ska bygga direkt på segment_text, men normaliserad:
    - ta bort onödiga ord (jag, du, vi, tack osv)
    - gör frasen mer generell
  - Lägg gärna till fler varianter som elektrikerkunder brukar skriva.
  - Exempel för en task som gäller utanpåliggande uttag:
    - "sätta upp utanpåliggande vägguttag"
    - "installera utanpåliggande uttag på vägg"

- default_materials
  - Lista av material-objekt:
    - material_ref_hint  (t ex "VAGGUTTAG-INF-VIT", "KABELKANAL-PLAST-VIT")
    - qty_per_unit       (float, t ex 1, 1.5, 2)
    - unit               (t ex "st", "m")
    - note               (kort beskrivning på svenska)
  - Använd generiska material_ref_hint, inte riktiga artikelnummer.
  - Syftet är att hjälpa systemet välja rätt materialgrupp, inte att vara exakt.

- room_type_hint
  - T ex "vardagsrum", "kök", "hall", "sovrum", "badrum", "utomhus" eller null.
  - Använd om segmentet tydligt pekar på en viss rumstyp.
  - Annars sätt null.

- confidence
  - Tal mellan 0 och 1 som anger hur säker du är på att detta är rätt task.
  - 0.9–1.0: mycket säker.
  - 0.6–0.8: ganska säker men kräver mänsklig granskning.
  - Under 0.6: osäker, bör granskas extra eller kanske avvisas.

- notes_internal
  - Valfritt fält för kommentarer till mänsklig granskare.
  - T ex "liknar BYTA-VAGGUTTAG men för utanpåliggande montage".

- source_segment_id
  - Kopiera segment_id från input.

- source_segment_text
  - Kopiera segment_text från input.

------------------------------------------------------------
REGLER OCH RIKTLINJER
------------------------------------------------------------

1) Endast elektrikerjobb
   - Tasks ska beskriva arbeten som en behörig elektriker normalt utför.
   - Städning, målning, fönsterputs, flyttstäd och liknande ska inte bli tasks.
   - Sådant kan få låg confidence eller helt hoppas över.

2) Återanvändbara tasks
   - Utgå från att varje task ska kunna användas hundratals gånger.
   - Ta bort kundens personliga detaljer.
   - Håll titlar och beskrivningar neutrala och professionella.

3) Relation till befintliga tasks
   - existing_task_ref innehåller normalt en befintlig task som redan ligger nära.
   - Om existing_task_ref inte är null eller tom:
     - utgå från att segmentet redan täcks av den befintliga tasken
     - skapa normalt inte en ny task_ref bara för en språklig variation.
   - Skapa endast en ny task_ref om segmentet tydligt beskriver ett annat arbetsmoment än alla befintliga tasks (t.ex. annan typ av montage, annan miljö eller väsentligt annorlunda arbetsinnehåll).
   - Om du bedömer att segmentet egentligen bara borde kopplas till en befintlig task:
     - hoppa över att skapa en ny task (lägg ingen post i suggested_tasks för det segmentet)
     - låt istället existing_task_ref fortsätta användas av systemet.
   - Undvik alltid att skapa dubbla tasks med nästan identiskt innehåll.

4) Tid och mängd
   - estimated_hours_per_unit ska vara rimlig för en erfaren elektriker.
   - Om segmentet nämner antal (t ex "tre uttag", "2 spotlights"):
     - utgå från att quantity hanteras i ett senare steg i systemet.
     - din uppgift är att sätta tid per enhet, inte total tid för hela jobbet.
   - För kabel och kabelkanal:
     - använd quantity_type "per_meter" och default_unit "m" när det är naturligt.

5) Material
   - Hitta inte på riktiga artikelnummer.
   - Använd material_ref_hint som logiska etiketter, t ex:
     - "VAGGUTTAG-INF-VIT"
     - "VAGGUTTAG-UTANPA"
     - "KABELKANAL-VIT"
     - "SPOTLIGHT-INF-TAK"
   - qty_per_unit ska vara en rimlig uppskattning, inte perfekt.

6) Språk
   - Använd alltid svenska i title_sv, description_sv, note och notes_internal.
   - Undvik "du" och "jag". Skriv neutralt och sakligt.
   - Exempel:
     - Bra: "Byta befintligt infällt vägguttag mot nytt jordat uttag."
     - Undvik: "Jag byter ditt gamla uttag mot ett nytt."

7) JSON-format
   - Svaret måste vara giltig JSON.
   - Inga kommentarer, ingen text före eller efter.
   - Endast:
     {
       "suggested_tasks": [ ... ]
     }

------------------------------------------------------------
EXEMPEL PÅ TASK-FÖRSLAG
------------------------------------------------------------

Nedan är ett exempel för segment_text:
"Jag ska sätta upp tre utanpåliggande vägguttag på gipsvägg"

Ett möjligt task-objekt i suggested_tasks:

{
  "task_ref": "INSTALLERA-VAGGUTTAG-UTANPA",
  "title_sv": "Installera utanpåliggande vägguttag",
  "description_sv": "Installation av utanpåliggande jordat vägguttag på vägg, inklusive montering och inkoppling mot befintlig matning.",
  "category": "brytare_och_uttag",
  "estimated_hours_per_unit": 0.5,
  "quantity_type": "per_unit",
  "default_unit": "st",
  "patterns": [
    "sätta upp utanpåliggande vägguttag",
    "installera utanpåliggande vägguttag",
    "montera utanpåliggande eluttag"
  ],
  "default_materials": [
    {
      "material_ref_hint": "VAGGUTTAG-UTANPA-JORD",
      "qty_per_unit": 1,
      "unit": "st",
      "note": "Utanpåliggande jordat vägguttag"
    },
    {
      "material_ref_hint": "SKRUV-PLUGG-VAGG",
      "qty_per_unit": 2,
      "unit": "st",
      "note": "Fästdon för montage på vägg"
    }
  ],
  "room_type_hint": "vardagsrum",
  "confidence": 0.9,
  "notes_internal": "Nytt standardmoment för utanpåliggande vägguttag, separat från infällda uttag.",
  "source_segment_id": "seg_001",
  "source_segment_text": "Jag ska sätta upp tre utanpåliggande vägguttag på gipsvägg"
}

------------------------------------------------------------
VIKTIGT TILLÄGG – UNDVIK DUBBLETTER MOT BEFINTLIGA TASKS
------------------------------------------------------------

Systemet har redan många definierade tasks i sitt bibliotek (YAML-filerna), t.ex.:

- INSTALLERA-SPOTLIGHT-TAK
- LAGGA-KABELKANAL
- LAGGA-VP-ROR
- INSTALLERA-VAGGUTTAG-INFALLT
- INSTALLERA-DIMMER
- INSTALLERA-KRONBRYTARE
- DRA_VP_ROR_INFALD_VAGG/TAK/GOLV (och liknande varianter)

Du måste därför vara extra försiktig så att du inte föreslår "nya" tasks som i praktiken är samma sak som befintliga.

Följ dessa regler:

1) existing_task_ref
   - Om fältet existing_task_ref är satt och motsvarar en befintlig task som tydligt täcker segmentet:
     - Skapa INTE en ny task_ref.
     - Behandla segmentet som "redan täckt" av befintligt moment.
     - I sådana fall ska segmentet normalt INTE generera någon ny post i suggested_tasks.

2) Små variationer ska inte bli nya tasks
   - Skapa inte en ny task bara för att:
     - segmentet använder lite andra ord
     - segmentet beskriver samma typ av jobb men med annan formulering
   - Exempel:
     - Om biblioteket redan har "INSTALLERA-SPOTLIGHT-TAK" ska du normalt inte skapa:
       - "MONTERA-SPOTLIGHT-TAK"
       - "INSTALLERA-INFALLD-SPOTLIGHT-TAK" (om befintlig redan täcker detta)
     - Om biblioteket redan har "INSTALLERA-DIMMER" och "INSTALLERA-KRONBRYTARE" ska du inte skapa snarlika varianter om segmentet i grunden beskriver samma arbete.

3) Ny task endast vid tydlig lucka
   - Föreslå en NY task_ref bara om segmentet beskriver ett arbetsmoment som:
     - tydligt skiljer sig från befintliga tasks, och
     - du bedömer att det vore praktiskt att ha som separat standardmoment.
   - Tänk: "Skulle en elektriker vilja ha detta som ett eget rad/moment i offerten, skilt från de som redan finns?"

4) Hellre inget än en dublett
   - Om du är osäker på om något egentligen redan täcks av befintliga tasks:
     - Då är det bättre att INTE föreslå en ny task.
     - I sådana fall kan du sätta låg confidence eller helt enkelt låta bli att lägga in något i suggested_tasks för det segmentet.

Sammanfattning:
- existing_task_ref och befintliga tasks är primära.
- Nytt task-förslag ska bara skapas om jobbet inte redan täcks på ett rimligt sätt av biblioteket.
- Undvik "mellanvarianter" och synonymer till redan etablerade standardmoment.


