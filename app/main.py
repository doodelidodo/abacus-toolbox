"""
REST-API für xml_to_xlsx:
  POST /convert        multipart/form-data, Feld "file"  -> XLSX
  POST /convert/raw    XML direkt im Body               -> XLSX
  GET  /health         Healthcheck
  GET  /docs           Swagger-UI zum Testen im Browser
"""

import logging
import os
import secrets
from typing import Optional
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from converter import CONFIG_PATH, ConversionError, convert, xlsx_filename

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_UPLOAD_BYTES = int(float(os.environ.get("MAX_UPLOAD_MB", "20")) * 1024 * 1024)
API_KEY = os.environ.get("API_KEY", "").strip()

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fsm-xml-to-xlsx")

app = FastAPI(
    title="FSM XML → XLSX",
    description="Wandelt FSM/Abacus timeEfforts- und expenses-XML in eine Excel-Datei um.",
    version="1.1.0",
)


def check_api_key(x_api_key: Optional[str] = Header(default=None)):
    """Nur aktiv, wenn die Umgebungsvariable API_KEY gesetzt ist."""
    if API_KEY and not (x_api_key and secrets.compare_digest(x_api_key, API_KEY)):
        raise HTTPException(status_code=401, detail="Ungültiger oder fehlender X-API-Key.")


@app.exception_handler(ConversionError)
async def conversion_error_handler(request: Request, exc: ConversionError):
    log.warning("Konvertierung fehlgeschlagen: %s", exc.message)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


def xlsx_response(xml_bytes: bytes, filename: Optional[str], record_type: Optional[str]) -> Response:
    if len(xml_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Datei grösser als {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")

    result = convert(xml_bytes, filename, record_type)
    out_name = xlsx_filename(filename, result.record_type)
    log.info("%s -> %s (%s, %d Zeilen)", filename, out_name, result.record_type, result.row_count)

    ascii_name = out_name.encode("ascii", "ignore").decode() or "converted.xlsx"
    return Response(
        content=result.content,
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(out_name)}",
            "X-Record-Type": result.record_type,
            "X-Row-Count": str(result.row_count),
        },
    )


@app.get("/health", tags=["System"])
def health():
    return {"status": "ok", "config": CONFIG_PATH if os.path.isfile(CONFIG_PATH) else "builtin-defaults"}


@app.post(
    "/convert",
    tags=["Convert"],
    dependencies=[Depends(check_api_key)],
    response_class=Response,
    responses={200: {"content": {XLSX_MEDIA_TYPE: {}}, "description": "Die erzeugte Excel-Datei"}},
    summary="XML-Datei hochladen, Excel zurückbekommen",
)
async def convert_upload(
    file: UploadFile = File(..., description="timeEfforts- oder expenses-XML"),
    type: Optional[str] = Query(
        default=None,
        description="timeEfforts oder expenses. Leer = automatisch (Dateiname, sonst Inhalt).",
    ),
):
    xml_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    return xlsx_response(xml_bytes, file.filename, type)


@app.post(
    "/convert/raw",
    tags=["Convert"],
    dependencies=[Depends(check_api_key)],
    response_class=Response,
    responses={200: {"content": {XLSX_MEDIA_TYPE: {}}, "description": "Die erzeugte Excel-Datei"}},
    summary="XML direkt im Request-Body senden (Content-Type: application/xml)",
)
async def convert_raw(
    request: Request,
    filename: Optional[str] = Query(default=None, description="Name für die Excel-Datei, z.B. 4711_expenses.xml"),
    type: Optional[str] = Query(default=None, description="timeEfforts oder expenses. Leer = automatisch."),
):
    xml_bytes, form_filename = await read_body(request)
    log.info(
        "convert/raw: content-type=%s content-length=%s transfer-encoding=%s user-agent=%s -> %d Bytes gelesen",
        request.headers.get("content-type"),
        request.headers.get("content-length"),
        request.headers.get("transfer-encoding"),
        request.headers.get("user-agent"),
        len(xml_bytes),
    )
    if not xml_bytes.strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "Die XML-Datei ist leer: Im Request-Body kamen 0 Bytes an "
                f"(Content-Type: {request.headers.get('content-type') or '-'}, "
                f"Content-Length: {request.headers.get('content-length') or '-'}). "
                "Prüfen, ob die Datei für den aufrufenden Server lesbar ist."
            ),
        )
    return xlsx_response(xml_bytes, filename or form_filename, type)


async def read_body(request: Request):
    """
    Liest den Body. Normalfall: XML direkt im Body.
    Falls der Aufrufer doch multipart/form-data schickt, wird die erste Datei
    (bzw. das erste Feld) aus dem Formular genommen.
    Rückgabe: (bytes, dateiname_aus_formular_oder_None)
    """
    content_type = (request.headers.get("content-type") or "").lower()
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        for _, value in form.multi_items():
            if hasattr(value, "read"):
                return (await value.read(MAX_UPLOAD_BYTES + 1)), value.filename
        for _, value in form.multi_items():
            if isinstance(value, str) and value.strip():
                return value.encode("utf-8"), None
        return b"", None

    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_UPLOAD_BYTES:
            break
    return bytes(data), None


@app.api_route(
    "/debug/echo",
    methods=["GET", "POST", "PUT"],
    tags=["System"],
    dependencies=[Depends(check_api_key)],
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
