from fastapi import APIRouter
from fastapi.routing import APIRoute

router = APIRouter(tags=["system"])

@router.get("/health")
def health():
    return {"message": "ok"}

@router.get("/__debug/routes")
def list_routes():
    # Reflektera appens rutter så vi ser exakt vad som är registrerat
    try:
        from src.server.main import app  # fungerar när du startar som "src.server.main:app"
    except Exception:
        from src.server.main import app      # fallback om du startar med --app-dir src
    out = []
    for r in app.router.routes:
        if isinstance(r, APIRoute):
            fn = r.endpoint
            out.append({
                "path": r.path,
                "methods": sorted(list(r.methods or [])),
                "name": r.name,
                "endpoint": f"{getattr(fn,'__module__','?')}.{getattr(fn,'__name__','?')}",
            })
    return out


