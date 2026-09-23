"""
HTTP-Hilfen für Werkzeuge:
  - ToolError:      fachlicher Fehler -> JSON {"detail": ...} mit passendem Statuscode
  - read_body():    Datei aus dem Request lesen (roher Body ODER multipart/form-data)
  - file_response(): Datei als Download zurückgeben (Dateiname, Zusatz-Header)
"""

import logging
import os
from typing import Dict, Optional, Tuple
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import Response

from core import settings

log = logging.getLogger("toolbox")


class ToolError(Exception):
    """Fachlicher Fehler eines Werkzeugs, wird als 4xx/5xx mit Klartext zurückgegeben."""

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def read_body(request: Request) -> Tuple[bytes, Optional[str]]:
    """
    Liest die Datei aus dem Request.
    Normalfall (Abacus): Dateiinhalt direkt als Body.
    Falls multipart/form-data geschickt wird, wird die erste Datei (bzw. das erste Textfeld) verwendet.
    Rückgabe: (bytes, dateiname_aus_formular_oder_None). Wirft 413 bei Überschreitung von MAX_UPLOAD_MB
    und 400, wenn nichts ankam.
    """
    limit = settings.MAX_UPLOAD_BYTES
    content_type = (request.headers.get("content-type") or "").lower()
    data, form_name = b"", None

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        for _, value in form.multi_items():
            if hasattr(value, "read"):
                data, form_name = await value.read(limit + 1), value.filename
                break
        else:
            for _, value in form.multi_items():
                if isinstance(value, str) and value.strip():
                    data = value.encode("utf-8")
                    break
    else:
        buffer = bytearray()
        async for chunk in request.stream():
            buffer.extend(chunk)
            if len(buffer) > limit:
                break
        data = bytes(buffer)

    log.info(
        "%s: content-type=%s content-length=%s user-agent=%s -> %d Bytes",
        request.url.path, request.headers.get("content-type"), request.headers.get("content-length"),
        request.headers.get("user-agent"), len(data),
    )
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=f"Datei grösser als {limit // (1024 * 1024)} MB.")
    if not data.strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "Die Datei ist leer: Im Request-Body kamen 0 Bytes an "
                f"(Content-Type: {request.headers.get('content-type') or '-'}, "
                f"Content-Length: {request.headers.get('content-length') or '-'}). "
                "Prüfen, ob die Datei für den aufrufenden Server lesbar ist."
            ),
        )
    return data, form_name


def output_filename(input_name: Optional[str], extension: str, fallback: str) -> str:
    """Dateiname der Antwort: gleicher Name wie die Eingabe, neue Endung."""
    base = os.path.splitext(os.path.basename(input_name or ""))[0]
    return (base or fallback) + extension


def file_response(content: bytes, filename: str, media_type: str, headers: Optional[Dict[str, str]] = None) -> Response:
    ascii_name = filename.encode("ascii", "ignore").decode() or "download"
    all_headers = {"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"}
    all_headers.update(headers or {})
    return Response(content=content, media_type=media_type, headers=all_headers)
