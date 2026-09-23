"""API-Key-Prüfung. Wird von allen Werkzeug-Endpunkten als Dependency verwendet."""

import secrets
from typing import Optional

from fastapi import Header, HTTPException

from core import settings


def require_api_key(x_api_key: Optional[str] = Header(default=None, description="Nur nötig, wenn ein API-Key konfiguriert ist")):
    """Nur aktiv, wenn die Umgebungsvariable API_KEY gesetzt ist."""
    if settings.API_KEY and not (x_api_key and secrets.compare_digest(x_api_key, settings.API_KEY)):
        raise HTTPException(status_code=401, detail="Ungültiger oder fehlender X-API-Key.")
