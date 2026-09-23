"""
Werkzeug: Zeichensatz einer Textdatei umwandeln (z.B. UTF-8 -> ANSI/Windows-1252 für Abacus-Importe).

    POST /text/convert-encoding    Textdatei als Body -> gleiche Datei im Zielzeichensatz

Dient auch als kleines Beispiel dafür, wie ein Werkzeug aufgebaut ist (siehe docs/neues-werkzeug.md).
"""

import codecs
import logging
from typing import Optional

from fastapi import APIRouter, Query, Request

from core.http import ToolError, file_response, read_body

NAME = "encoding"
TITLE = "Zeichensatz umwandeln"
DESCRIPTION = "Wandelt Textdateien (CSV, TXT, XML …) in einen anderen Zeichensatz um, z.B. UTF-8 → ANSI, und vereinheitlicht Zeilenenden."

log = logging.getLogger("toolbox.encoding")
router = APIRouter(tags=[TITLE])

BOMS = [(codecs.BOM_UTF8, "utf-8-sig"), (codecs.BOM_UTF16_LE, "utf-16"), (codecs.BOM_UTF16_BE, "utf-16")]


def _codec(name: str, what: str) -> str:
    try:
        return codecs.lookup(name).name
    except LookupError:
        raise ToolError(f"Unbekannter Zeichensatz für {what}: '{name}'. Beispiele: utf-8, windows-1252, iso-8859-1, utf-16", 400)


def detect(data: bytes) -> str:
    """BOM -> UTF-8/UTF-16; sonst gültiges UTF-8 -> utf-8; sonst windows-1252 (ANSI)."""
    for bom, name in BOMS:
        if data.startswith(bom):
            return name
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "windows-1252"


@router.post(
    "/text/convert-encoding",
    summary="Textdatei im Body schicken, im Zielzeichensatz zurückbekommen",
    responses={200: {"content": {"text/plain": {}}, "description": "Die umgewandelte Datei"}},
)
async def convert_encoding(
    request: Request,
    filename: Optional[str] = Query(default=None, description="Dateiname der Eingabe; die Antwort bekommt denselben Namen"),
    source: str = Query(default="auto", description="Zeichensatz der Eingabe. auto = erkennen (BOM, UTF-8, sonst ANSI)"),
    target: str = Query(default="windows-1252", description="Zielzeichensatz, z.B. windows-1252 (ANSI), utf-8, iso-8859-1"),
    newline: str = Query(default="keep", description="Zeilenenden: keep, crlf (Windows) oder lf (Unix)"),
    bom: bool = Query(default=False, description="Bei UTF-8/UTF-16 ein BOM voranstellen"),
    errors: str = Query(default="strict", description="strict = Fehler bei nicht darstellbaren Zeichen, replace = durch ? ersetzen"),
):
    data, form_name = await read_body(request)
    name = filename or form_name or "datei.txt"

    if newline not in ("keep", "crlf", "lf"):
        raise ToolError("newline muss keep, crlf oder lf sein.", 400)
    if errors not in ("strict", "replace"):
        raise ToolError("errors muss strict oder replace sein.", 400)

    src = detect(data) if source.lower() == "auto" else _codec(source, "source")
    dst = _codec(target, "target")
    dst_label = target.strip().lower()  # so wie angegeben, z.B. windows-1252 statt cp1252

    try:
        text = data.decode(src)
    except UnicodeDecodeError as exc:
        raise ToolError(f"Die Datei ist nicht im Zeichensatz '{src}' (Byte {exc.start}). source=auto versuchen.", 422)
    text = text.lstrip("\ufeff")

    if newline != "keep":
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if newline == "crlf":
            text = text.replace("\n", "\r\n")

    try:
        out = text.encode(dst, errors=errors)
    except UnicodeEncodeError as exc:
        bad = text[exc.start:exc.end]
        line = text.count("\n", 0, exc.start) + 1
        raise ToolError(
            f"Zeichen {bad!r} (Zeile {line}) gibt es im Zielzeichensatz '{dst_label}' nicht. "
            "Mit errors=replace werden solche Zeichen durch ? ersetzt.", 422)

    if bom and dst in ("utf-8", "utf-16"):
        if dst == "utf-8":
            out = codecs.BOM_UTF8 + out
        # utf-16 schreibt das BOM bereits selbst

    log.info("%s: %s -> %s, %d -> %d Bytes", name, src, dst_label, len(data), len(out))
    return file_response(out, name, f"text/plain; charset={dst_label}",
                         {"X-Source-Encoding": src, "X-Target-Encoding": dst_label})
