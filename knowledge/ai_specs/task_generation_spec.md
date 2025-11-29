\# Dockit AI – Specifikation för Generering av Nya Tasks från Fri Text



Den här specifikationen instruerar GPT-modellen hur den ska analysera råa textsegment

(som inte matchade några existerende mappingar) och generera nya arbetsmoment (tasks)

i Dockits standardiserade JSON-format.



GPT ska producera strukturerade förslag som kan läggas direkt in i YAML-mappingfilerna.



---



\# 1. INPUTFORMAT (från systemet)



Systemet skickar ett JSON-objekt med listan:



```json

{

&nbsp; "segments": \[

&nbsp;   {

&nbsp;     "segment\_id": "missingseg\_20251117T190247Z\_0001",

&nbsp;     "segment\_text": "Byta två vägguttag i vardagsrummet",

&nbsp;     "source\_type": "missing\_task\_segment",

&nbsp;     "room\_hint": null,

&nbsp;     "language": "sv",

&nbsp;     "existing\_task\_ref": null

&nbsp;   }

&nbsp; ]

}



