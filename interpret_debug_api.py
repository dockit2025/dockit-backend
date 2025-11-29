from fastapi import FastAPI
from pydantic import BaseModel

from free_text_interpreter import interpret_free_text


app = FastAPI(title="Dockit – Free text interpreter debug API")


class InterpretRequest(BaseModel):
    free_text: str


@app.post("/interpret")
def interpret_endpoint(req: InterpretRequest):
    """
    Enkel debug-endpoint:
    Tar emot fri text och returnerar hela JSON-strukturen
    från interpret_free_text().
    """
    result = interpret_free_text(req.free_text)
    return result
