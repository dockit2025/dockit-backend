# Dockit AI – Specifikation för generering av nya tasks från fri text (+ ATL)

Syfte:  
Denna spec styr hur GPT ska föreslå nya standardiserade arbetsmoment (tasks) baserat på kundernas fria text.  
Tasks ska passa in i Dockits befintliga struktur med YAML-mappings, ATL-tider och materialkopplingar.

Målet är att:
1. Skapa **återanvändbara arbetsmoment** (tasks) som passar många jobb.  
2. I första hand använda **ATL-ackordstidlistan** som grund för tidsåtgång.  
3. Skriva ut resultat i **strikt JSON** enligt formatet i denna spec.  
4. Undvika dubbletter mot redan befintliga tasks i biblioteket.

---

## 1. Input – `gpt_input`

Systemet skickar ett JSON-objekt med minst nyckeln `"segments"`.  
I sandlådeläget finns även `"atl_candidates"`.

Exempel på övergripande struktur:

```json
{
  "segments": [ ... ],
  "atl_candidates": [ ... ]
}
```

### 1.1. `segments[]`

`segments` är en lista av objekt:

* `segment_id`        – sträng, unikt ID
* `segment_text`      – sträng, kundens fria text på svenska
* `source_type`       – t.ex. `"missing_task_segment"` eller `"sandbox_ui"`
* `room_hint`         – t.ex. `"vardagsrum"`, `"kök"`, `"hall"`, `"badrum"` eller `null`
* `language`          – alltid `"sv"`
* `existing_task_ref` – kan vara `null` eller en befintlig `task_ref` som ligger nära

Exempel:

```json
{
  "segment_id": "seg_001",
  "segment_text": "Jag ska sätta upp tre utanpåliggande vägguttag på gipsvägg",
  "source_type": "missing_task_segment",
  "room_hint": "vardagsrum",
  "language": "sv",
  "existing_task_ref": null
}
```

Din uppgift per segment:

1. Tolka vilket elektrikerjobb som beskrivs.
2. Avgöra om det bör bli en ny återanvändbar standard-task.
3. Om ja: skapa ett task-förslag enligt **Task-format** nedan.
4. Om nej: hoppa över segmentet (ingen post för det segmentet i `suggested_tasks`).

---

### 1.2. `atl_candidates[]` (ATL – ackordstidlista)

För vissa körningar får du dessutom:

```json
"atl_candidates": [
  {
    "segment_id": "seg_001",
    "segment_text": "Jag ska sätta upp tre utanpåliggande vägguttag på gipsvägg",
    "rows": [
      {
        "arbetsmoment": 169,
        "moment_id": "169",
        "grupp": "1020",
        "rad": "10",
        "moment_text": "Kabeldragning i rör",
        "underlag_text": "<16 mm²",
        "enhet": "m kabel",
        "times": {
          "0": 0.06,
          "-1": 0.07,
          "-2": 0.08,
          "-3": 0.09
        }
      }
    ]
  }
]
```

Varje `rows[]`-element motsvarar en rad i ATL-ackordstidlistan:

* `arbetsmoment`  – heltal, unikt id för ATL-momentet
* `moment_id`     – samma som ovan, fast sträng
* `grupp`         – ATL-grupp, t.ex. `"1020"`
* `rad`           – rad i gruppen
* `moment_text`   – texten i kolumnen *Moment/Typ/Sort*
* `underlag_text` – variant/förutsättning (underlag, dimension osv)
* `enhet`         – ATL-enhet, t.ex. `"m rör"`, `"m kabel"`, `"uttag"`, `"central"`, `"apparat"`
* `times`         – dictionary med variant → tid i timmar per enhet, t.ex. `"0": 0.06` = 0,06 h/enhet

Du ska använda `atl_candidates` för att:

* Hitta en **passande ATL-rad** som representerar arbetet
* Välja en **variant** (nyckel i `times`) när det är rimligt
* Översätta tiden till minuter per enhet och fylla i rätt fält i task-objektet

---

## 2. Output – strikt JSON

Du ska **alltid** svara med ett JSON-objekt med exakt **en** toppnivånyckel:

```json
{
  "suggested_tasks": [ ... ]
}
```

* `suggested_tasks` är en lista (kan vara tom).
* Varje element är ett task-objekt enligt **Task-formatet** nedan.
* Om du inte hittar några rimliga tasks kan listan vara tom:

```json
{
  "suggested_tasks": []
}
```

Inga andra nycklar på toppnivå.
Ingen text, inga kommentarer, ingen förklaring utanför JSON-objektet.

---

## 3. Task-format – fält och betydelse

Varje element i `suggested_tasks` är ett objekt med följande fält.

### 3.1. Grundläggande identitet och beskrivning

* `task_ref`

  * Kort intern kod i VERSALER med bindestreck.
  * Format: VERB-OBJEKT, t.ex.:

    * `"BYTA-VAGGUTTAG-INFALLT"`
    * `"INSTALLERA-SPOTLIGHT-TAK"`
    * `"LAGGA-KABELKANAL"`
    * `"DRA-VP-ROR-INFALLT"`
  * Använd verb som: `BYTA`, `INSTALLERA`, `DRA`, `LAGGA`, `SATTA-UPP`, `FELSOKA`.

* `title_sv`

  * Kort svensk titel.
  * Exempel:

    * `"Byta infällt vägguttag"`
    * `"Installera utanpåliggande vägguttag"`
    * `"Dra VP-rör infällt i vägg"`

* `description_sv`

  * 1–3 meningar som konkret beskriver arbetsmomentet på svenska.
  * Fokus på vad elektrikern praktiskt gör, inte på kundens upplevelse.

* `category`

  * En av dessa kategorier:

    * `"brytare_och_uttag"`
    * `"belysning"`
    * `"kok"`
    * `"badrum"`
    * `"natverk_och_media"`
    * `"felsokning_och_service"`
    * `"ror_och_vp"`
    * `"ovrigt"`
  * Välj kategorin där arbetsmomentet typiskt skulle ligga i en el-offert.

---

### 3.2. Tid och mängd

* `estimated_hours_per_unit`

  * Timmar per enhet (float).

  Om du använder ATL:

  * Hämta tiden i timmar från `times[vald_variant]`.
  * Sätt `estimated_hours_per_unit` exakt till detta värde.

  Om du **inte** använder ATL:

  * Använd rimliga steg: 0.25, 0.5, 0.75, 1.0, 1.5, 2.0 osv.

  Riktlinjer:

  * 0.25–0.5: enkla byten (1 uttag, 1 brytare, 1 dimmer).
  * 0.5–1.5: nyinstallation, flytt av punkt, mindre kabeldragning.
  * 1.5+: större moment, längre sträckor, flera delmoment.

* `time_source`

  * `"atl"` om tiden kommer från ATL-tabellen.
  * `"gpt"` om tiden är en expertuppskattning utan direkt ATL-stöd.

* `time_minutes_per_unit`

  * Tid per enhet i **minuter**.
  * Exempel: 0.06 timmar → `3.6` minuter.

* `quantity_type`

  * Styr hur kvantitet tolkas.
  * I första hand:

    * `"per_unit"` – per styck (uttag, armatur, central, apparat).
  * Vid behov:

    * `"per_meter"` – t.ex. kabel, kabelkanal, VP-rör.
    * `"per_room"` – t.ex. allmän belysning i ett rum.

* `default_unit`

  * Kort enhetstext som matchar `quantity_type`.
  * Exempel:

    * `"st"` för `per_unit`.
    * `"m"`  för `per_meter`.
    * `"rum"` för `per_room`.

> Notera: även om segmentet nämner antal (t.ex. “tre uttag”, “12 meter rör”) ska du ändå ange **tid per enhet**. Totaltiden räknas senare i systemet.

---

### 3.3. Matchning och återanvändning

* `patterns`

  * Lista med typiska kundfraser som ska matcha denna task.
  * Minst 2–3 patterns per task.
  * Minst en pattern ska:

    * bygga på `segment_text`, men
    * vara normaliserad (ta bort “jag”, “du”, “tack” osv, gör frasen generell).

  Exempel (utanpåliggande uttag):

  ```json
  "patterns": [
    "sätta upp utanpåliggande vägguttag",
    "installera utanpåliggande vägguttag",
    "montera utanpåliggande eluttag"
  ]
  ```

* `default_materials`

  * Lista med material-objekt:

    * `material_ref_hint` – t.ex. `"VAGGUTTAG-INF-VIT"`, `"KABELKANAL-VIT"`, `"VP-ROR-16MM"`
    * `qty_per_unit`      – float, t.ex. `1`, `1.5`, `2`
    * `unit`              – t.ex. `"st"`, `"m"`
    * `note`              – kort svensk beskrivning

  * Använd **inte** riktiga artikelnummer.

  * `material_ref_hint` ska vara generiska etiketter som kopplar till rätt materialgrupp.

* `room_type_hint`

  * T.ex. `"vardagsrum"`, `"kök"`, `"hall"`, `"sovrum"`, `"badrum"`, `"utomhus"` eller `null`.
  * Sätts bara om segmentet tydligt avser en viss rumstyp.

---

### 3.4. Kvalitet och spårbarhet

* `confidence`

  * Tal mellan 0 och 1.
  * 0.9–1.0: mycket säker.
  * 0.6–0.8: ganska säker, bör kontrolleras.
  * <0.6: osäker, bör granskas extra eller kanske avvisas.

* `notes_internal`

  * Valfritt fält för kommentarer till mänsklig granskare.
  * Exempel:

    * `"liknar INSTALLERA-VAGGUTTAG-INFALLT men för utanpåliggande montage."`
    * `"ATL: valt kabeldragning i rör <16 mm² som bas för tiden."`

* `source_segment_id`

  * Kopiera `segment_id` från input.

* `source_segment_text`

  * Kopiera `segment_text` från input.

---

### 3.5. ATL-specifika fält

För att koppla tasks till ATL används:

* `atl_moment`

  * Om du använder ATL:

    * sätt den till en begriplig kombination av `moment_text` + ev. variant/underlag,
      t.ex. `"Kabeldragning i rör <16 mm²"`.
  * Om du **inte** använder ATL:

    * sätt `atl_moment` till `null`.

* `atl_variant`

  * Heltal som motsvarar en nyckel i `times` för vald ATL-rad, t.ex. `0`, `-1`, `-2`.
  * Om du inte använder ATL:

    * sätt `atl_variant` till `null`.

Regler för ATL:

1. Använd bara ATL-moment från `atl_candidates.rows` för aktuellt segment.
2. Välj den rad som **bäst** motsvarar arbetsmomentet:

   * Rörjobb → enhet `"m rör"` eller liknande.
   * Kabeljobb → enhet `"m kabel"`.
   * Uttag, armaturer, apparater → `"uttag"`, `"apparat"`, `"central"` osv.
3. Välj variant:

   * Om underlag/dimension nämns → välj variant som passar bäst.
   * Annars → välj `"0"` som normalvariant om den finns.
4. Hämta tiden i timmar från `times[vald_variant]`:

   * `estimated_hours_per_unit` = detta värde (timmar)
   * `time_minutes_per_unit`   = detta värde * 60 (minuter)
   * `time_source` = `"atl"`
5. Hitta aldrig på egna ATL-koder eller moment.

   * Om inget passar bra:

     * `atl_moment = null`
     * `atl_variant = null`
     * `time_source = "gpt"` och välj en rimlig `estimated_hours_per_unit`.

---

## 4. Regler och riktlinjer

### 4.1. Endast elektrikerjobb

* Tasks ska beskriva arbeten som en behörig elektriker normalt utför.
* Städning, målning, flyttstäd, snickeri osv ska inte bli tasks.
* Sådant kan få låg `confidence` eller helt hoppas över (ingen task skapas).

### 4.2. Återanvändbara tasks

* Varje task ska kunna användas hundratals gånger.
* Ta bort kundens personliga detaljer (namn, adresser, “min lägenhet”, osv).
* Håll titlar och beskrivningar neutrala och professionella.

### 4.3. Förhållande till befintliga tasks och `existing_task_ref`

Systemet har redan många definierade tasks i sitt bibliotek, t.ex.:

* `INSTALLERA-SPOTLIGHT-TAK`
* `LAGGA-KABELKANAL`
* `LAGGA-VP-ROR`
* `INSTALLERA-VAGGUTTAG-INFALLT`
* `INSTALLERA-DIMMER`
* `INSTALLERA-KRONBRYTARE`
* `DRA-VP-ROR-INFALLT` (och liknande)

Följ dessa regler:

1. Om `existing_task_ref` är satt och segmentet tydligt täcks av den tasken:

   * Skapa **inte** en ny `task_ref`.
   * Segmentet ska då normalt inte resultera i en ny post i `suggested_tasks`.

2. Skapa **inte** en ny task bara för:

   * små språkliga variationer,
   * synonymer (t.ex. “montera” vs “installera”),
   * mindre skillnader som elektriker normalt inte vill ha som separata offert-rader.

3. Skapa ny task endast vid tydlig lucka:

   * Segmentet beskriver ett arbetsmoment som tydligt skiljer sig från befintliga tasks.
   * Exempel: annan typ av montage, annan miljö (mark, fasad, våtrum) eller väsentligt annorlunda arbetsinnehåll.

4. Hellre ingen ny task än en dublett:

   * Är du osäker på om något redan täcks av befintliga tasks:

     * Låt bli att skapa en ny task.
     * Det är bättre att biblioteket är lite för smalt än fullt av dubbletter.

---

### 4.4. Material

* Hitta inte på riktiga artikelnummer.
* Använd logiska `material_ref_hint`, t.ex:

  * `"VAGGUTTAG-INF-VIT"`
  * `"VAGGUTTAG-UTANPA-JORD"`
  * `"KABELKANAL-VIT"`
  * `"SPOTLIGHT-INF-TAK"`
  * `"VP-ROR-16MM"`
* `qty_per_unit` ska vara en rimlig uppskattning, inte perfekt vetenskap.

### 4.5. Språk

* All text i `title_sv`, `description_sv`, `note`, `notes_internal` ska vara på svenska.
* Undvik “du” och “jag”. Skriv neutralt:

  * Bra: `"Byta befintligt infällt vägguttag mot nytt jordat uttag."`
  * Undvik: `"Jag byter ditt gamla uttag mot ett nytt."`

---

## 5. Exempel

### 5.1. Exempel – utanpåliggande vägguttag

Input `segment_text`:

> "Jag ska sätta upp tre utanpåliggande vägguttag på gipsvägg"

Möjligt task-objekt:

```json
{
  "task_ref": "INSTALLERA-VAGGUTTAG-UTANPA",
  "title_sv": "Installera utanpåliggande vägguttag",
  "description_sv": "Installation av utanpåliggande jordat vägguttag på vägg, inklusive montering och inkoppling mot befintlig matning.",
  "category": "brytare_och_uttag",
  "estimated_hours_per_unit": 0.5,
  "time_source": "gpt",
  "time_minutes_per_unit": 30.0,
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
      "qty_per_unit": 1.0,
      "unit": "st",
      "note": "Utanpåliggande jordat vägguttag"
    },
    {
      "material_ref_hint": "SKRUV-PLUGG-VAGG",
      "qty_per_unit": 2.0,
      "unit": "st",
      "note": "Fästdon för montage på vägg"
    }
  ],
  "room_type_hint": "vardagsrum",
  "confidence": 0.9,
  "notes_internal": "Nytt standardmoment för utanpåliggande vägguttag, separat från infällda uttag.",
  "source_segment_id": "seg_001",
  "source_segment_text": "Jag ska sätta upp tre utanpåliggande vägguttag på gipsvägg",
  "atl_moment": null,
  "atl_variant": null
}
```

### 5.2. Exempel – ATL-baserad tid (rör/kabel)

Input `segment_text`:

> "Det finns inga rör dragna sedan innan, så jag behöver dra cirka 12 meter VP-rör infällt i vardagsrummet."

Om `atl_candidates` innehåller en rad:

* `moment_text`: `"Kabeldragning i rör"`
* `underlag_text`: `"<16 mm²"`
* `enhet`: `"m kabel"`
* `times`: `{ "0": 0.06 }`

kan ett task-objekt se ut så här:

```json
{
  "task_ref": "DRA-VP-ROR-INFALLT",
  "title_sv": "Dra infällt VP-rör",
  "description_sv": "Dragning av VP-rör infällt i vägg eller tak för elinstallation, inklusive fästning och anpassning till underlaget.",
  "category": "ror_och_vp",
  "estimated_hours_per_unit": 0.06,
  "time_source": "atl",
  "time_minutes_per_unit": 3.6,
  "quantity_type": "per_meter",
  "default_unit": "m",
  "patterns": [
    "dra vp-rör infällt",
    "dra infällda vp-rör",
    "installera vp-rör i vägg",
    "dra vp-rör i vardagsrum"
  ],
  "default_materials": [
    {
      "material_ref_hint": "VP-ROR-16MM",
      "qty_per_unit": 1.0,
      "unit": "m",
      "note": "VP-rör 16 mm för infällt montage"
    },
    {
      "material_ref_hint": "FESTKLAMMER-VP",
      "qty_per_unit": 1.0,
      "unit": "st",
      "note": "Fästklammer för VP-rör"
    }
  ],
  "room_type_hint": "vardagsrum",
  "confidence": 0.95,
  "notes_internal": "Standardmoment för infälld dragning av VP-rör, tid baserad på ATL för kabeldragning i rör <16 mm².",
  "source_segment_id": "ui_0001",
  "source_segment_text": "Det finns inga rör dragna sedan innan, så jag behöver dra cirka 12 meter VP-rör infällt i vardagsrummet.",
  "atl_moment": "Kabeldragning i rör <16 mm²",
  "atl_variant": 0
}
```

---

## 6. Sammanfattning

1. Läs varje `segment_text` noga.
2. Använd `atl_candidates` där det finns för att välja rimliga ATL-moment och varianter.
3. Skapa endast nya tasks när det finns en **tydlig lucka** i befintligt bibliotek.
4. Undvik dubbletter och onödiga synonymer.
5. Svara alltid med giltig JSON:

```json
{
  "suggested_tasks": [ ... ]
}
```

Inga andra toppnivåfält och ingen text utanför JSON.
