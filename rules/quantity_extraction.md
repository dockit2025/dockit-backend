# Quantity Extraction Rules  
Version: 1.0  
Author: Robin / Dockit AI  
Updated: 2025-11-13

## Syfte
Den här regelfilen styr hur GPTN ska identifiera **antal**, **längder**, **meter**, **stycken** och andra kvantitetsuttryck i naturligt språk.  
Reglerna används innan task-mapping för att säkerställa att varje matchad task får rätt `quantity`.

## Grundprinciper
1. När en kund uttrycker antal ska GPTN alltid:
   - hitta talet  
   - koppla det till rätt objekt  
   - tilldela `quantity` till rätt task  

2. Om inget antal nämns → `quantity = 1`.

3. Vid uttryck av total längd (t.ex. meter rör/kabel):
   - GPTN tar värdet som **hela mängden**, inte per delsträcka.
   - Exempel: *"dra tio meter rör i hallen"* → quantity = 10.

## Regler: vanliga uttryck
### 1. Grundtal
GPTN ska känna igen:
- 1, 2, 3, 4 …  
- "ett", "en", "två", "tre", "fyra" …  
- "ett par" → 2  
- "några" → 3 (standardvärde)  

### 2. Längder
GPTN ska tolka:
- "1 meter", "1m", "1 m"  
- "fem meter"  
- "10 meter kabelkanal"  

Det tilldelas quantity exakt som talet anger.

### 3. Styck
GPTN ska koppla uttryck som:
- "styck", "st", "st.", "enheter", "punkter", "uttag", "brytare", "lampor"  
till quantity.

Exempel:  
- *"byta tre vägguttag"* → 3  
- *"sätta upp två taklampor"* → 2  

### 4. Implicit singel
Om ingen mängd uttrycks:
- "installera vägguttag i hallen" → quantity = 1  
- "installera jordfelsbrytare" → 1  
- "montera taklampa" → 1  

### 5. Flera tasks i en mening
GPTN ska fördela kvantitet per objekt.

Exempel:
*"Byta två uttag i köket och tre i hallen"*  

→ Ska ge:  
- byta_vagguttag = 2  
- byta_vagguttag (ny instans) = 3  
(detta hanteras av NL-parsern, men quantity-regeln används per delsegment)

### 6. Hela fraser med mängd
GPTN ska fånga konstruktioner där antalet står **före** eller **efter** objektet:

- "tre vägguttag"  
- "vägguttag, tre stycken"  
- "installera 4 nya lampor"  
- "sätta upp lampor, två st"  

### 7. Prioritetsordning
Vid motstridiga signaler ska GPTN prioritera:
1. Exakta tal (10, "tio")  
2. Frasspecifika ord (styck, meter, punkter)  
3. Approximerade uttryck ("några", "ett par")  

## Specialfall
### Meter rör/kabel
Följande ska alltid tolkas som meter:
- "dra rör 10 meter"  
- "10m vp-rör"  
- "lägga 15 meter kabel"  

### Uttag i serie eller grupp
- "byta alla uttag i vardagsrummet" → quantity = ALLA, men sätts till 1 och NL-parsern ska fråga efter exakt antal.  
(Detta är ett undantag: ALLA → quantity unknown → hanteras i render-validator.)

### Komplexa uttryck
GPTN ska klara:  
- "sätta upp totalt fem lampor, varav två i köket"  
- "montera tre nya och byta två gamla"  

→ quantity per task delas ut efter semantik.

## Outputformat (internt)
Quantity ska alltid hamna i:
```json
{
  "task_id": "...",
  "quantity": <float>
}
```

Decimaler används endast om uttrycket kommer från meterspecifikation.

## Validering
- Negativa värden ignoreras.  
- Quantity = 0 → flaggas som fel i `render_validator`.  
- Quantity > 100 → GPTN ska överväga missförståelse.  

## Felhantering
Om GPTN är osäker ska den:
- använda 1 som fallback  
- men markera i metadata: `"quantity_confidence": "low"`  

Detta läses senare i offer-generatorn.

## Exempel
### Input:
"Byta två uttag i köket och installera en dimmer"

### Expected (internt):
- byta_vagguttag → 2  
- installera_dimmer → 1  

### Input:
"Dra 15 meter utanpåliggande rör och sätt upp en lampa"

→ dra_ror_utanpa = 15  
→ montera_taklampa = 1  

---

## Slutkommentar
Det här dokumentet ska läsas av GPTN tillsammans med:
- `nl_parser.md`  
- `render_rules.md`  
- `merge_rules.md`  

Quantity-extraction körs **före** task-mapping och **efter** NL-segmentering.

