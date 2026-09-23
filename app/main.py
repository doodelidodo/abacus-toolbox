"""
Abacus Toolbox: ein REST-Service mit mehreren Werkzeugen für Aufgaben, die Abacus nicht selbst erledigt.

Aufbau:
    core/      gemeinsame Bausteine (Einstellungen, API-Key, Datei lesen/zurückgeben, Fehler)
    modules/   ein Unterordner pro Werkzeug (eigener Router)

Allgemeine Endpunkte:
    GET  /health       Healthcheck + aktive Werkzeuge
    GET  /modules      Liste der aktiven Werkzeuge mit Endpunkten
    *    /debug/echo   zeigt, was ankommt (Fehlersuche)
    GET  /docs         Swagger-Oberfläche
"""

import logging

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from core import settings
from core.http import ToolError
from core.security import require_api_key
from modules import AVAILABLE

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("toolbox")

unknown = [name for name in settings.ENABLED_MODULES if name not in AVAILABLE]
if unknown:
    log.warning("Unbekannte Module in ENABLED_MODULES ignoriert: %s (verfügbar: %s)", unknown, list(AVAILABLE))
ENABLED = {
    name: module for name, module in AVAILABLE.items()
    if not settings.ENABLED_MODULES or name in settings.ENABLED_MODULES
}

app = FastAPI(
    title=settings.SERVICE_TITLE,
    version=settings.VERSION,
    description=(
        "Werkzeuge für Abacus-Prozesse (Baustein „Webservice Aufruf ausführen“): Datei als Request-Body schicken, "
        "Ergebnis als Datei zurückbekommen.\n\n"
        "Aktive Werkzeuge: " + ", ".join(f"**{m.TITLE}**" for m in ENABLED.values())
    ),
    openapi_tags=[{"name": m.TITLE, "description": m.DESCRIPTION} for m in ENABLED.values()]
    + [{"name": "System", "description": "Healthcheck, Übersicht, Fehlersuche"}],
)

for module in ENABLED.values():
    app.include_router(module.router, dependencies=[Depends(require_api_key)])
log.info("%s %s – aktive Werkzeuge: %s", settings.SERVICE_TITLE, settings.VERSION, ", ".join(ENABLED) or "keine")


@app.exception_handler(ToolError)
async def tool_error_handler(request: Request, exc: ToolError):
    log.warning("%s: %s", request.url.path, exc.message)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.get("/health", tags=["System"])
def health():
    extra = {}
    for module in ENABLED.values():
        extra.update(getattr(module, "health_info", lambda: {})())
    return {"status": "ok", "version": settings.VERSION, "modules": list(ENABLED), **extra}


@app.get("/modules", tags=["System"], summary="Aktive Werkzeuge mit ihren Endpunkten")
def modules_overview():
    result = []
    for name, module in ENABLED.items():
        endpoints = sorted(
            {f"{method} {route.path}" for route in module.router.routes for method in route.methods
             if not getattr(route, "deprecated", False)}
        )
        result.append({"name": name, "title": module.TITLE, "description": module.DESCRIPTION, "endpoints": endpoints})
    return result


@app.api_route(
    "/debug/echo",
    methods=["GET", "POST", "PUT"],
    tags=["System"],
    dependencies=[Depends(require_api_key)],
    summary="Zeigt, was beim Service ankommt (Header, Body-Länge, Body-Anfang) – zur Fehlersuche",
)
async def debug_echo(request: Request):
    body = await request.body()
    return {
        "method": request.method,
        "url": str(request.url),
        "query": dict(request.query_params),
        "headers": {k: v for k, v in request.headers.items() if k.lower() != "x-api-key"},
        "body_length": len(body),
        "body_start": body[:300].decode("utf-8", errors="replace"),
    }
