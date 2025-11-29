ATL\_ALIASES v1.1 — slang \& sökord per arbetsmoment (svenska)

Format per block:

\[moment: "<ATL: Arbetsmoment eller entydig etikett>"]

\- keywords: uttryck som betyder samma sak (kommatecken eller semikolon mellan)

\- negatives: uttryck som ska uteslutas (om nämns, matcha inte detta moment)

\- surfaces: underlag/placering som ofta nämns (hjälper NL→ATL-varianten)

\- unit\_alias: hur folk säger enheterna

\- notes: särskilda regler (t.ex. "i rör" ⇒ kolumn −3)

\[moment: "Kabeldragning i rör"]

* keywords: kabel i rör; dra kabel i rör; dra ny kabel; dra slang; lägga vp; vp-rör; vp; flex; flexrör; slang; installationsrör; rördragning; rördra
* negatives:
* surfaces: betong; tegel; lättbetong; stål; fasad; utomhus; inne; tak; vägg
* unit\_alias: m; meter; met
* notes: om texten innehåller "i rör", "vp", "flex", "slang" ⇒ använd ATL-kolumn −3

\[moment: "Kabeldragning klamrad (utan rör)"]

* keywords: klamra kabel; klamrad kabel; utan rör; utan slang; utan vp; på vägg; längs vägg; utanpåliggande
* negatives: i rör; vp; flex; slang
* surfaces: trä; gips; betong; tegel; fasad
* unit\_alias: m; meter
* notes:

\[moment: "Montering av kapslad dosa"]

* keywords: kapslad dosa; kopplingsdosa; dosa utomhus; skarvdosa; kopplingsbox; box utomhus; doslock
* negatives:
* surfaces: fasad; utomhus; betong; tegel; lättbetong
* unit\_alias: st; styck; stycken; dosa
* notes: om IP-klass nämns (IP44/IP54/IP65) behåll den i materialvalet

\[moment: "Montering/byte väggarmatur utomhus"]

* keywords: utelampa; väggarmatur; entrélampa; fasadlampa; ytterbelysning; lampa ute; armatur ute; skymningsrelä; ljusrelä; skymningssensor
* negatives: takarmatur inne; plafond inne
* surfaces: fasad; utomhus; entré; carport; garage
* unit\_alias: st; styck; lampor; armatur
* notes: om både "skymningsrelä" och "armatur" nämns ⇒ välj armatur med inbyggt relä i första hand

\[moment: "Montering/byte armatur inomhus"]

* keywords: taklampa; plafond; armatur inne; lysrörsarmatur; LED-list; köksbelysning; badrumslampa
* negatives: utomhus; fasad; skymningsrelä
* surfaces: tak; vägg; badrum; kök; hall
* unit\_alias: st; lampor; armatur

\[moment: "Byte av strömbrytare (med indikering)"]

* keywords: strömbrytare; brytare; knapp; knapp med lampa; indikator; indikering; lysande knapp; 1-pol; 1-polig; med lysdiod; med lampa
* negatives: dimmer
* surfaces: inne; hall; entre; trapphus
* unit\_alias: st; brytare
* notes:

\[moment: "Montering/byte dimmer"]

* keywords: dimmer; dim; vrid; tryckdimmer; fasdim
* negatives:
* surfaces: inne; vardagsrum; kök; sovrum
* unit\_alias: st

\[moment: "Montering/byte vägguttag"]

* keywords: uttag; vägguttag; eluttag; schuko; dubbeluttag; trippeluttag; utanpåliggande uttag; infällt uttag
* negatives: ladduttag bil; CEE
* surfaces: kök; hall; sovrum; fasad (utomhus)
* unit\_alias: st; uttag
* notes: om "utomhus/ute/fasad/IP" nämns ⇒ välj IP44+ i material

\[moment: "Installation av jordfelsbrytare (JFB)"]

* keywords: jordfelsbrytare; JFB; jordfel; RCD; montera jordfelsbrytare; installera JFB
* negatives:
* surfaces: central; elcentral; proppskåp
* unit\_alias: st

\[moment: "Arbete i elcentral (tillägg)"]

* keywords: arbete i central; proppskåp; elcentral; omkoppling i central; säkring; gruppförteckning; anslut i central
* negatives:
* surfaces: central; elskåp
* unit\_alias: tim; h
* notes: om bara kort nämns ⇒ tidsätt låg standard (t.ex. 0,25–0,5 h) om ATL-rad saknas

\[moment: "Håltagning/infästning (tillägg)"]

* keywords: borra; plugg; skruv; infästning; hål i betong; slagborr; plugga
* negatives:
* surfaces: betong; tegel; lättbetong; trä
* unit\_alias: st
* notes: använd endast om specifikt efterfrågat eller krävs för armatur/dosa

YTTERLIGARE HJÄLPFRASELISTOR (påverkar val av material/variant)

\[facet: "kabeltyper"]

* keywords: EXQJ; EKKJ; FK; N1XV; N1XE; EQLQ; EKLK; EXLQ; PFXP
* dimension\_alias: 3x1,5; 3G1,5; 3G1.5; 3x2,5; 3G2,5; 5x1,5; 5G1,5
* notes: normalisera "×"→"x", komma↔punkt i dimensioner

\[facet: "IP-klass"]

* keywords: IP20; IP21; IP44; IP54; IP55; IP65; IP66
* notes: utomhus ⇒ minst IP44, gärna IP54/IP65 enligt praxis

\[facet: "enheter"]

* keywords: m; meter; met; st; styck; stycken; h; tim; timmar
* notes: normalisera till m/st/h

\[facet: "plats/placering"]

* keywords: ute; utomhus; fasad; entré; carport; garage; inne; hall; kök; badrum; trädgård
* notes: ute/fasad ⇒ välj utomhusklassade produkter och ATL-underlag för hårda ytor

MATCHNINGSREGLER (sammanfattning)

* Poängsätt kandidatmoment:
  score = (#träffar i keywords) + bonus(underlag/placering) + bonus(korrekt enhet)
* Exkludera om något i negatives finns.
* Vid "i rör/vp/flex/slang" ⇒ forcerad kolumn −3 i ATL.
* Om flera moment binder: välj det med högst score; vid lika – välj mest specifika (t.ex. "kapslad dosa" före generisk "arbete i central").
