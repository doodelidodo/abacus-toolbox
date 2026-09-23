# Neues Werkzeug hinzufügen

Ein Werkzeug ist ein Ordner unter `app/modules/` mit einer Datei `router.py`. API-Key, Grössenlimit, Logging,
einheitliche Fehler, Swagger-Doku und alle Betriebsvarianten gelten automatisch.

## 1. Ordner anlegen

```
app/modules/mein_werkzeug/
├── __init__.py        (leer)
├── router.py          Endpunkte + Beschreibung
└── logik.py           optional: die eigentliche Verarbeitung, ohne HTTP
```

Die Logik in eine eigene Datei ohne FastAPI zu legen lohnt sich: Sie lässt sich dann einfach testen und auch
ausserhalb des Service verwenden, wie `converter/xml_to_xlsx.py`.

## 2. `router.py` schreiben

Vorlage (Beispiel: Textdatei in Grossbuchstaben umwandeln):

```python
"""
Werkzeug: <kurze Beschreibung>

    POST /mein/pfad    Datei als Body -> Ergebnis-Datei
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query, Request

from core.http import ToolError, file_response, output_filename, read_body

NAME = "mein_werkzeug"                      # technischer Name, für ENABLED_MODULES
TITLE = "Mein Werkzeug"                     # Anzeigename in Swagger und /modules
DESCRIPTION = "Ein Satz, wofür das Werkzeug da ist."

log = logging.getLogger("toolbox.mein_werkzeug")
router = APIRouter(tags=[TITLE])


@router.post("/mein/pfad", summary="Was der Endpunkt tut")
async def ausfuehren(
    request: Request,
    filename: Optional[str] = Query(default=None, description="Name der Eingabedatei"),
):
    data, form_name = await read_body(request)          # Body (oder Formular) lesen, Limit + "leer"-Prüfung inklusive
    name = filename or form_name

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ToolError("Die Datei ist kein UTF-8-Text.", 422)   # -> {"detail": "..."} mit Status 422

    ergebnis = text.upper().encode("utf-8")
    log.info("%s: %d Bytes verarbeitet", name, len(data))
    return file_response(ergebnis, output_filename(name, ".txt", "ergebnis"), "text/plain; charset=utf-8",
                         {"X-Zeichen": str(len(text))})
```

Bausteine aus `core`:

| Baustein | Zweck |
|---|---|
| `read_body(request)` | Datei aus dem Body lesen (oder erste Datei aus einem Formular). Prüft Grösse (`413`) und leeren Body (`400`). Gibt `(bytes, dateiname_aus_formular)` zurück |
| `ToolError(meldung, status)` | Fachlicher Fehler; wird als `{"detail": meldung}` mit dem Statuscode zurückgegeben |
| `file_response(bytes, dateiname, media_type, headers)` | Ergebnis als Download zurückgeben |
| `output_filename(eingabe, ".endung", fallback)` | Name der Ergebnis-Datei aus dem Eingabenamen ableiten |
| `settings` | `MAX_UPLOAD_BYTES`, `API_KEY`, … |

Der API-Key wird automatisch für alle Endpunkte des Routers geprüft. Optional kann ein Modul eine Funktion
`health_info()` anbieten, deren Rückgabe (Dict) in `/health` erscheint.

Für XML-Eingaben immer `defusedxml` verwenden (siehe `modules/fsm_xlsx/converter.py`), nie `xml.etree` direkt auf
ungeprüfte Daten.

## 3. Werkzeug anmelden

In `app/modules/__init__.py` importieren und eintragen:

```python
from modules.encoding import router as encoding
from modules.fsm_xlsx import router as fsm_xlsx
from modules.mein_werkzeug import router as mein_werkzeug

AVAILABLE = {m.NAME: m for m in (fsm_xlsx, encoding, mein_werkzeug)}
```

## 4. Abhängigkeiten

Braucht das Werkzeug eine zusätzliche Python-Bibliothek, diese in **beide** Dateien eintragen:

- `requirements.txt` (Docker, AWS)
- `windows/requirements-windows.txt` (Windows-Dienst)

Reine Python-Bibliotheken sind unproblematisch. Werkzeuge, die grosse externe Programme brauchen (z.B. LibreOffice
für Word → PDF), besser als eigenen Service betreiben, damit die Toolbox klein bleibt.

## 5. Testen

```powershell
docker compose up -d --build
```

- In <http://localhost:8000/docs> erscheint das Werkzeug als eigener Abschnitt und kann direkt ausprobiert werden.
- <http://localhost:8000/modules> listet es mit seinen Endpunkten.
- Anonymisierte Beispieldateien in `samples/` ablegen (nie echte Kundendaten).

## 6. Dokumentieren und ausliefern

1. `docs/werkzeug-<name>.md` nach dem Muster der bestehenden Werkzeuge anlegen und in der Tabelle „Werkzeuge“ im
   `README.md` eintragen.
2. Version in `app/core/settings.py` erhöhen (`VERSION`).
3. Ausliefern wie gewohnt: Windows-Dienst neu bauen und `install-service.ps1` ausführen, Docker neu bauen,
   bzw. `deploy-aws.ps1` erneut ausführen.
4. Pro Kunde festlegen, ob er das Werkzeug bekommt: `ENABLED_MODULES` bzw. `modules` in `settings.json`
   (leer = alle Werkzeuge).

## Regeln für gute Werkzeuge

- **Ein Aufruf, ein Ergebnis:** Datei rein, Datei raus. Keine Zwischenspeicherung auf der Festplatte, keine Daten behalten.
- **Schnell:** Unter 30 Sekunden pro Aufruf (Grenze bei AWS, und Abacus wartet auf die Antwort).
- **Verständliche Fehler:** `ToolError` mit einer Meldung, die ein Abacus-Anwender versteht und die sagt, was zu tun ist.
- **Pfade nach Thema:** `/<bereich>/<aktion>`, z.B. `/pdf/merge`, `/text/convert-encoding`.
- **Keine Brüche:** Bestehende Endpunkte und Parameter nicht umbenennen. Neues als neuen Parameter oder Endpunkt ergänzen.
