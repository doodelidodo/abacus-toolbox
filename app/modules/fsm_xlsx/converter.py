"""
FSM-Werkzeug, Adapter um converter/xml_to_xlsx.py:
nimmt XML als Bytes entgegen und liefert die XLSX-Datei als Bytes zurück,
ohne etwas auf die Platte zu schreiben.

Die eigentliche Logik (parse_xml, write_xlsx, load_config, Default-Felder)
kommt unverändert aus converter/xml_to_xlsx.py.
"""

import io
import os
from dataclasses import dataclass

import defusedxml.ElementTree as SafeET
from defusedxml import DefusedXmlException

import xml_to_xlsx
from core.http import ToolError

RECORD_TYPES = ("timeEfforts", "expenses")
CONFIG_PATH = os.environ.get("CONFIG_PATH", "/config/xml_to_xlsx_config.json")


def ConversionError(message, status_code=422):
    """Fachlicher Fehler -> wird von der API als JSON mit Statuscode zurückgegeben."""
    return ToolError(message, status_code)


@dataclass
class ConversionResult:
    content: bytes
    record_type: str
    row_count: int
    config_source: str


def load_profiles():
    """
    Lädt die Config bei jedem Aufruf neu, damit Änderungen an der
    (gemounteten) JSON-Datei ohne Neustart wirken.
    Fallback wie im Script: eingebaute Standardfelder.
    """
    if os.path.isfile(CONFIG_PATH):
        try:
            return xml_to_xlsx.load_config(CONFIG_PATH), CONFIG_PATH
        except Exception as exc:
            raise ConversionError(
                f"Config konnte nicht geladen werden ({CONFIG_PATH}): {exc}", status_code=500
            )
    return (
        {"timeEfforts": xml_to_xlsx.DEFAULT_FIELDS, "expenses": xml_to_xlsx.DEFAULT_EXPENSE_FIELDS},
        "builtin-defaults",
    )


def detect_record_type(root, filename, requested_type):
    """
    Reihenfolge:
      1. explizit angegebener Typ (?type=expenses)
      2. Dateiname (wie im Script: enthält 'expenses' -> expenses)
      3. Inhalt: gibt es <activities>/<expenses> bzw. <activities>/<timeEfforts>?
    """
    if requested_type:
        for record_type in RECORD_TYPES:
            if requested_type.lower() == record_type.lower():
                return record_type
        raise ConversionError(
            f"Unbekannter type '{requested_type}'. Erlaubt: {', '.join(RECORD_TYPES)}", status_code=400
        )

    name = (filename or "").lower()
    if "expenses" in name:
        return "expenses"
    if "timeefforts" in name:
        return "timeEfforts"

    data = root.find("data")
    if data is not None:
        has_expenses = data.find("activities/expenses") is not None
        has_efforts = data.find("activities/timeEfforts") is not None
        if has_expenses and not has_efforts:
            return "expenses"
    return "timeEfforts"


def convert(xml_bytes, filename=None, requested_type=None):
    if not xml_bytes or not xml_bytes.strip():
        raise ConversionError("Die XML-Datei ist leer.", status_code=400)

    # Sicher parsen (keine Entities / keine externen Referenzen), bevor das
    # Original-Script die Datei verarbeitet.
    try:
        root = SafeET.fromstring(xml_bytes)
    except DefusedXmlException:
        raise ConversionError("XML enthält nicht erlaubte Konstrukte (DTD/Entities).", status_code=400)
    except SafeET.ParseError as exc:
        raise ConversionError(f"Ungültiges XML: {exc}", status_code=400)

    record_type = detect_record_type(root, filename, requested_type)
    profiles, config_source = load_profiles()
    fields = profiles.get(record_type)
    if not fields:
        raise ConversionError(f"Kein Config-Profil für '{record_type}' gefunden.", status_code=500)

    try:
        rows = xml_to_xlsx.parse_xml(io.BytesIO(xml_bytes), fields, record_type)
    except ValueError as exc:
        raise ConversionError(str(exc))

    if not rows:
        raise ConversionError(f"Im XML wurden keine {record_type}-Einträge gefunden.")

    rows = [[record_type] + row for row in rows]
    columns = ["FileType"] + [field["name"] for field in fields]

    buffer = io.BytesIO()
    xml_to_xlsx.write_xlsx(rows, columns, buffer)
    return ConversionResult(buffer.getvalue(), record_type, len(rows), config_source)
