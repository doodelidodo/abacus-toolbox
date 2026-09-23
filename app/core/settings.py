"""
Einstellungen aus Umgebungsvariablen. Gelten für alle Werkzeuge.

    API_KEY          leer = kein Key nötig, sonst Pflicht-Header X-API-Key
    MAX_UPLOAD_MB    maximale Grösse einer Anfrage (Standard 20)
    LOG_LEVEL        INFO, DEBUG, ...
    ENABLED_MODULES  kommagetrennte Liste der aktiven Werkzeuge, z.B. "fsm_xlsx,encoding".
                     Leer = alle verfügbaren Werkzeuge.
"""

import os

VERSION = "2.0.0"
SERVICE_TITLE = "Abacus Toolbox"

API_KEY = os.environ.get("API_KEY", "").strip()
MAX_UPLOAD_BYTES = int(float(os.environ.get("MAX_UPLOAD_MB", "20")) * 1024 * 1024)
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
ENABLED_MODULES = [m.strip() for m in os.environ.get("ENABLED_MODULES", "").split(",") if m.strip()]
