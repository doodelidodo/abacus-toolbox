#!/usr/bin/env python3
"""
xml_to_xlsx.py
--------------
Wandelt alle Abacus/FSM "timeEfforts"-XML-Dateien im gleichen Ordner in flache XLSX-Tabellen um.
Pro <timeEfforts>-Eintrag wird eine Zeile erzeugt. Werte aus höheren Ebenen
(data, businessPartner, activities, responsibles) werden auf jede dazugehörige
Zeile "heruntergezogen".

Verwendung:
    python xml_to_xlsx.py

Das Script sucht automatisch nach allen .xml-Dateien im gleichen Verzeichnis
und speichert die Ergebnisse mit gleichem Namen (Endung .xlsx) neben den
XML-Dateien ab.

Kompilierbar mit PyInstaller, z.B.:
    pyinstaller --onefile xml_to_xlsx.py
"""

import sys
import os
import json
from datetime import datetime
import xml.etree.ElementTree as ET
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter


DEFAULT_FIELDS = [
    {"name": "EventId", "context": "root", "path": "eventID"},
    {"name": "EventTime", "context": "root", "path": "eventTime"},
    {"name": "Code", "context": "data", "path": "code"},
    {"name": "BusinessPartnerCode", "context": "data", "path": "businessPartner/code"},
    {"name": "Subject", "context": "data", "path": "subject"},
    {"name": "ActivityCode", "context": "activity", "path": "code"},
    {
        "name": "ResponsibleCode",
        "context": "activity",
        "path": "responsibles/code",
        "multiple": True,
    },
    {"name": "TimeEffortId", "context": "timeEffort", "path": "id"},
    {"name": "StartDateTime", "context": "timeEffort", "path": "startDateTime"},
    {"name": "EndDateTime", "context": "timeEffort", "path": "endDateTime"},
    {"name": "BreakInMinutes", "context": "timeEffort", "path": "breakInMinutes"},
    {"name": "ChargeOption", "context": "timeEffort", "path": "chargeOption"},
    {"name": "TaskId", "context": "timeEffort", "path": "task/id"},
    {
        "name": "UdfValue",
        "context": "timeEffort",
        "path": "udfValues/value",
        "multiple": True,
    },
]

DEFAULT_EXPENSE_FIELDS = [
    {"name": "EventId", "context": "root", "path": "eventID"},
    {"name": "EventTime", "context": "root", "path": "eventTime"},
    {"name": "BusinessPartnerCode", "context": "data", "path": "businessPartner/code"},
    {"name": "ServiceCallCode", "context": "data", "path": "code"},
    {"name": "ServiceCallSubject", "context": "data", "path": "subject"},
    {"name": "ActivityCode", "context": "activity", "path": "code"},
    {"name": "ActivitySubject", "context": "activity", "path": "subject"},
    {"name": "ExpenseId", "context": "expense", "path": "id"},
    {"name": "ExpenseDate", "context": "expense", "path": "date"},
    {"name": "ExpenseTypeCode", "context": "expense", "path": "type/code"},
    {"name": "ExpenseTypeId", "context": "expense", "path": "type/id"},
    {"name": "ExpenseQuantity", "context": "expense", "path": "udfValues/value", "index": 0},
    {"name": "ExpenseUdfValue2", "context": "expense", "path": "udfValues/value", "index": 1},
    {"name": "ExpenseUdfValue3", "context": "expense", "path": "udfValues/value", "index": 2},
    {"name": "ChargeOption", "context": "expense", "path": "chargeOption"},
    {"name": "ExternalAmount", "context": "expense", "path": "externalAmount"},
    {"name": "InternalAmount", "context": "expense", "path": "internalAmount"},
    {"name": "Tax", "context": "expense", "path": "tax"},
    {"name": "ApprovalStatus", "context": "expense", "path": "approvalStatus"},
    {"name": "SyncStatus", "context": "expense", "path": "syncStatus"},
    {"name": "Inactive", "context": "expense", "path": "inactive"},
    {"name": "CreateDateTime", "context": "expense", "path": "createDateTime"},
    {"name": "ObjectId", "context": "expense", "path": "object/objectId"},
]


def text_of(element, path):
    """Liefert den Text eines untergeordneten Elements oder '' falls nicht vorhanden/leer."""
    node = element.find(path)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def joined_text_of_all(element, path, sub_path):
    """
    Für Elemente, die mehrfach vorkommen können (z.B. mehrere <responsibles>
    oder mehrere <udfValues> innerhalb eines timeEfforts): sammelt den Text
    von sub_path aus jedem Vorkommen von path und verbindet sie mit '; '.
    """
    values = []
    for node in element.findall(path):
        sub = node.find(sub_path) if sub_path else node
        if sub is not None and sub.text and sub.text.strip():
            values.append(sub.text.strip())
    return "; ".join(values)


def load_config(config_path):
    with open(config_path, "r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    if "profiles" in config:
        profiles = config["profiles"]
    else:
        profiles = {"timeEfforts": config.get("fields")}

    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("Die Config muss 'profiles' enthalten.")

    for fields in profiles.values():
        if not isinstance(fields, list) or not fields:
            raise ValueError("Jedes Config-Profil muss eine nicht-leere Feldliste enthalten.")
        for field in fields:
            if not all(key in field for key in ("name", "context", "path")):
                raise ValueError("Jedes Config-Feld braucht 'name', 'context' und 'path'.")

    return profiles


def field_value(context, field):
    path = field["path"]
    if field.get("multiple", False) or "index" in field:
        parent_path, separator, sub_path = path.rpartition("/")
        if not separator:
            nodes = context.findall(path)
        else:
            nodes = context.findall(parent_path)
            nodes = [node.find(sub_path) for node in nodes]
        values = [node.text.strip() for node in nodes if node is not None and node.text and node.text.strip()]
        if "index" in field:
            index = field["index"]
            return values[index] if index < len(values) else ""
        return "; ".join(values)
    return text_of(context, path)


def parse_xml(xml_path, fields, record_type):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    data = root.find("data")
    if data is None:
        raise ValueError("Im XML wurde kein <data>-Element gefunden.")

    rows = []

    for activity in data.findall("activities"):
        records = activity.findall("timeEfforts" if record_type == "timeEfforts" else "expenses")
        for record in records:
            contexts = {
                "root": root,
                "data": data,
                "activity": activity,
                "timeEffort": record,
                "expense": record,
            }
            row = []
            for field in fields:
                context = contexts.get(field["context"])
                if context is None:
                    raise ValueError(f"Unbekannter Config-Kontext: {field['context']}")
                row.append(field_value(context, field))
            rows.append(row)

    return rows


def write_xlsx(rows, columns, xlsx_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "timeEfforts"

    header_font = Font(name="Arial", bold=True)
    normal_font = Font(name="Arial")

    ws.append(columns)
    for col_idx in range(1, len(columns) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.alignment = Alignment(horizontal="left")

    for row in rows:
        ws.append(row)

    # Schriftart für alle Datenzeilen setzen + Spaltenbreiten grob anpassen
    max_lengths = [len(str(c)) for c in columns]
    for r_idx, row in enumerate(rows, start=2):
        for c_idx, value in enumerate(row, start=1):
            cell = ws.cell(row=r_idx, column=c_idx)
            cell.font = normal_font
            length = len(str(value)) if value is not None else 0
            if length > max_lengths[c_idx - 1]:
                max_lengths[c_idx - 1] = length

    for c_idx, length in enumerate(max_lengths, start=1):
        ws.column_dimensions[get_column_letter(c_idx)].width = min(max(length + 2, 10), 40)

    ws.freeze_panes = "A2"
    wb.save(xlsx_path)


def main():
    # Bei einer EXE ist das Working Directory der vom aufrufenden Prozess
    # vorgegebene Ordner, in dem die XML-Dateien liegen.
    if getattr(sys, "frozen", False):
        script_dir = os.getcwd()
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))

    config_name = "xml_to_xlsx_config.json"
    config_candidates = [os.path.join(script_dir, config_name)]
    if getattr(sys, "frozen", False):
        config_candidates.append(os.path.join(os.path.dirname(os.path.abspath(sys.executable)), config_name))

    print(f"Start: {datetime.now().isoformat(timespec='seconds')}")
    print(f"Working Directory: {os.getcwd()}")
    print(f"Executable: {sys.executable}")
    print(f"XML search directory: {script_dir}")
    print(f"Frozen: {getattr(sys, 'frozen', False)}")

    profiles = None
    for config_path in config_candidates:
        if os.path.isfile(config_path):
            try:
                profiles = load_config(config_path)
                print(f"Config: {config_path}")
                break
            except Exception as exc:
                print(f"WARNUNG Config konnte nicht geladen werden ({config_path}): {exc}")

    if profiles is None:
        profiles = {
            "timeEfforts": DEFAULT_FIELDS,
            "expenses": DEFAULT_EXPENSE_FIELDS,
        }
        print("Config: eingebaute Standardfelder (keine externe Config gefunden)")

    # Suche nach allen XML-Dateien im gleichen Verzeichnis
    xml_files = [f for f in os.listdir(script_dir) if f.lower().endswith('.xml')]
    
    if not xml_files:
        print(f"FEHLER Keine XML-Dateien in '{script_dir}' gefunden.")
        sys.exit(1)
    
    print(f"Gefundene XML-Dateien: {len(xml_files)}")
    for xml_file in xml_files:
        print(f"  - {xml_file}")
    
    processed_count = 0
    for xml_file in xml_files:
        record_type = "expenses" if "expenses" in xml_file.lower() else "timeEfforts"
        fields = profiles.get(record_type)
        if not fields:
            print(f"\nFEHLER Kein Config-Profil für '{xml_file}' ({record_type}) gefunden.")
            continue
        columns = ["FileType"] + [field["name"] for field in fields]
        print(f"\nDateityp: {record_type}")
        print(f"Konfigurierte Felder: {len(fields)}")
        print(f"Spalten: {', '.join(columns)}")

        xml_path = os.path.join(script_dir, xml_file)
        base, _ = os.path.splitext(xml_file)
        xlsx_path = os.path.join(script_dir, base + ".xlsx")
        
        try:
            print(f"Verarbeite: {xml_file}")
            rows = parse_xml(xml_path, fields, record_type)
            rows = [[record_type] + row for row in rows]
            if not rows:
                print(f"  Warnung: Es wurden keine timeEfforts-Einträge gefunden.")
            else:
                write_xlsx(rows, columns, xlsx_path)
                print(f"  ✓ {len(rows)} Zeile(n) geschrieben nach: {base}.xlsx")
                processed_count += 1
        except Exception as exc:
            print(f"  FEHLER: {exc}")
    
    print(f"\n{processed_count}/{len(xml_files)} Datei(en) erfolgreich verarbeitet.")
    sys.exit(0 if processed_count == len(xml_files) else 1)


if __name__ == "__main__":
    main()
