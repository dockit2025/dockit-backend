from free_text_interpreter import interpret_free_text
import json

free = (
    "Byta tre vägguttag i vardagsrummet, byta en strömbrytare och installera en dimmer, "
    "dra infällda rör till ett nytt uttag i sovrummet, installera en diskmaskin i köket, "
    "sätta upp en taklampa i hallen och installera en laddbox på uppfarten"
)

result = interpret_free_text(free)

print(json.dumps(result, indent=2, ensure_ascii=False))
