from fastapi import APIRouter
from fastapi.routing import APIRoute

router = APIRouter(tags=["system"])

@router.get("/health")
def health():
    return {"message": "ok"}

@router.get("/__debug/routes")
def list_routes():
    out = []
    try:
        app_router = router.parent if getattr(router, "parent", None) else router
        for r in getattr(app_router, "routes", []):
            if isinstance(r, APIRoute):
                fn = r.endpoint
                out.append({
                    "path": r.path,
                    "methods": sorted(list(r.methods)),
                    "name": r.name,
                    "endpoint": f"{getattr(fn, '__module__', '?')}.{getattr(fn, '__name__', '?')}",
                })
    except Exception as e:
        out.append({"error": str(e)})
    return out


