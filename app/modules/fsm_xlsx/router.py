"""
Werkzeug: FSM-XML (timeEfforts / expenses) -> Excel

    POST /fsm/xml-to-xlsx          XML als Body (Abacus)        -> .xlsx
    POST /fsm/xml-to-xlsx/upload   Formular-Upload, Feld "file" -> .xlsx

Alte Adressen aus Version 1 bleiben gültig (bestehende Abacus-Prozesse):
    POST /convert/raw  = /fsm/xml-to-xlsx
    POST /convert      = /fsm/xml-to-xlsx/upload
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile

from core import settings
from core.http import file_response, output_filename, read_body

from .converter import CONFIG_PATH, convert

NAME = "fsm_xlsx"
TITLE = "FSM XML → Excel"
DESCRIPTION = "Wandelt SAP-FSM-XML (Zeiterfassungen timeEfforts, Spesen expenses) in eine Excel-Tabelle um."

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
log = logging.getLogger("toolbox.fsm")
router = APIRouter(tags=[TITLE])

TYPE_QUERY = Query(default=None, description="timeEfforts oder expenses. Leer = automatisch (Dateiname, sonst Inhalt).")
EXCEL_RESPONSE = {200: {"content": {XLSX: {}}, "description": "Die erzeugte Excel-Datei"}}


def health_info():
    return {"fsm_config": CONFIG_PATH if os.path.isfile(CONFIG_PATH) else "builtin-defaults"}


def _excel(xml_bytes: bytes, filename: Optional[str], record_type: Optional[str]):
    result = convert(xml_bytes, filename, record_type)
    out_name = output_filename(filename, ".xlsx", f"converted_{result.record_type}")
    log.info("%s -> %s (%s, %d Zeilen)", filename, out_name, result.record_type, result.row_count)
    return file_response(result.content, out_name, XLSX,
                         {"X-Record-Type": result.record_type, "X-Row-Count": str(result.row_count)})


@router.post("/fsm/xml-to-xlsx", responses=EXCEL_RESPONSE, summary="FSM-XML im Body schicken, Excel zurückbekommen (für Abacus)")
async def xml_to_xlsx_raw(
    request: Request,
    filename: Optional[str] = Query(default=None, description="Name der XML-Datei, z.B. 4711_expenses.xml (bestimmt den Excel-Namen)"),
    type: Optional[str] = TYPE_QUERY,
):
    data, form_name = await read_body(request)
    return _excel(data, filename or form_name, type)


@router.post("/fsm/xml-to-xlsx/upload", responses=EXCEL_RESPONSE, summary="FSM-XML als Datei hochladen, Excel zurückbekommen")
async def xml_to_xlsx_upload(file: UploadFile = File(..., description="timeEfforts- oder expenses-XML"), type: Optional[str] = TYPE_QUERY):
    data = await file.read(settings.MAX_UPLOAD_BYTES + 1)
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Datei grösser als {settings.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    return _excel(data, file.filename, type)


# --- Alte Adressen (Version 1), weiterhin gültig -------------------------------
@router.post("/convert/raw", responses=EXCEL_RESPONSE, deprecated=True, summary="Alt: wie POST /fsm/xml-to-xlsx")
async def legacy_convert_raw(request: Request, filename: Optional[str] = Query(default=None), type: Optional[str] = TYPE_QUERY):
    return await xml_to_xlsx_raw(request, filename, type)


@router.post("/convert", responses=EXCEL_RESPONSE, deprecated=True, summary="Alt: wie POST /fsm/xml-to-xlsx/upload")
async def legacy_convert(file: UploadFile = File(...), type: Optional[str] = TYPE_QUERY):
    return await xml_to_xlsx_upload(file, type)
