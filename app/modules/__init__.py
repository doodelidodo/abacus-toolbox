"""
Verzeichnis aller Werkzeuge (Module).

Jedes Modul ist ein Unterordner mit einer Datei router.py, die bereitstellt:
    NAME         technischer Name (für ENABLED_MODULES / settings.json)
    TITLE        Anzeigename
    DESCRIPTION  ein Satz, wofür das Werkzeug da ist
    router       FastAPI-APIRouter mit den Endpunkten

Neues Werkzeug: Ordner anlegen, router.py schreiben, hier in AVAILABLE eintragen.
Anleitung: docs/neues-werkzeug.md
"""

from modules.encoding import router as encoding
from modules.fsm_xlsx import router as fsm_xlsx

# Reihenfolge = Reihenfolge in der Swagger-Oberfläche
AVAILABLE = {m.NAME: m for m in (fsm_xlsx, encoding)}
