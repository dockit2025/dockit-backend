from fastapi import APIRouter
from fastapi.routing import APIRoute

router = APIRouter(tags=["system"])

@router.get("/__debug/routes")
def list_routes():
    out = []
    app_router = router.parent if router.parent else router
    for r in app_router.routes:
        if isinstance(r, APIRoute):
            fn = r.endpoint
            out.append({
                "path": r.path,
                "methods": sorted(list(r.methods or [])),
                "name": r.name,
                "endpoint": f"{getattr(fn, '__module__', '?')}.{getattr(fn, '__name__', '?')}",
            })
    return out
