# Werkzeug: FSM XML → Excel

Modul `fsm_xlsx`. Wandelt die XML-Dateien aus dem **SAP Field Service Management (FSM) Connector**
(`timeEfforts` = Zeiterfassungen, `expenses` = Spesen) in eine flache Excel-Tabelle (.xlsx) um.

- Eine Zeile pro Zeiterfassung bzw. Spesenposition. Werte aus den übergeordneten Ebenen (Serviceauftrag,
  Geschäftspartner, Aktivität, Verantwortliche) werden auf jede Zeile übernommen.
- Welche Spalten entstehen, steht in der [Feldkonfiguration](#feldkonfiguration).

## Endpunkte

### `POST /fsm/xml-to-xlsx` für Abacus

| | |
|---|---|
| Body | Inhalt der XML-Datei (Content-Type beliebig, empfohlen `application/xml`) |
| Query `filename` | empfohlen. Name der XML-Datei, bestimmt den Namen der Excel-Datei und hilft bei der Typ-Erkennung |
| Query `type` | optional. `timeEfforts` oder `expenses`; ohne Angabe automatisch |

```powershell
curl.exe --data-binary "@samples\2001_20260819095441_expenses.xml" `
  "http://localhost:8000/fsm/xml-to-xlsx?filename=2001_20260819095441_expenses.xml" -o ergebnis.xlsx
```

### `POST /fsm/xml-to-xlsx/upload` für Formular-Uploads

`multipart/form-data` mit dem Feld `file`, z.B. aus der Swagger-Oberfläche oder mit `curl.exe -F "file=@datei.xml"`.

### Antwort

- `200` mit der Excel-Datei. Der Dateiname entspricht dem der XML-Datei, mit Endung `.xlsx`.
- `X-Record-Type`: `timeEfforts` oder `expenses`
- `X-Row-Count`: Anzahl Zeilen

Werkzeugspezifische Fehler:

| Code | Meldung |
|---|---|
| 400 | `Ungültiges XML: …`, `XML enthält nicht erlaubte Konstrukte (DTD/Entities)`, `Unbekannter type …` |
| 422 | `Im XML wurde kein <data>-Element gefunden`, `Im XML wurden keine …-Einträge gefunden` |
| 500 | `Config konnte nicht geladen werden` |

Alte Adressen aus Version 1 (`/convert/raw`, `/convert`) funktionieren weiterhin.

## Typ-Erkennung

1. Parameter `type`, falls angegeben
2. Dateiname: enthält `expenses` → Spesen, enthält `timeEfforts` → Zeiterfassungen
3. Inhalt: gibt es `<activities>/<expenses>`, aber keine `<timeEfforts>` → Spesen, sonst Zeiterfassungen

## Feldkonfiguration

`converter/xml_to_xlsx_config.json` legt pro Typ fest, welche Spalten die Excel-Datei bekommt und woher die Werte stammen.

```json
{
  "profiles": {
    "timeEfforts": [
      {"name": "EventId",         "context": "root",       "path": "eventID"},
      {"name": "Subject",         "context": "data",       "path": "subject"},
      {"name": "ResponsibleCode", "context": "activity",   "path": "responsibles/code", "multiple": true},
      {"name": "StartDateTime",   "context": "timeEffort", "path": "startDateTime"}
    ],
    "expenses": [
      {"name": "ExpenseQuantity", "context": "expense",    "path": "udfValues/value", "index": 0}
    ]
  }
}
```

| Feld | Bedeutung |
|---|---|
| `name` | Spaltenüberschrift in Excel |
| `context` | Ebene im XML, von der aus `path` gesucht wird: `root` (ganze Nachricht), `data` (Serviceauftrag), `activity` (Aktivität), `timeEffort` bzw. `expense` (die einzelne Zeile) |
| `path` | Pfad zum Element, mit `/` getrennt, z.B. `businessPartner/code` |
| `multiple` | optional `true`: alle Vorkommen mit `; ` verbunden (z.B. mehrere Verantwortliche) |
| `index` | optional Zahl ab 0: nur das n-te Vorkommen (z.B. erster UDF-Wert) |

Pro `<timeEfforts>`- bzw. `<expenses>`-Element entsteht eine Zeile. Die erste Spalte `FileType` enthält immer den Typ.
Fehlt die Konfigurationsdatei, werden die im Konverter eingebauten Standardfelder verwendet.

Wo die Konfiguration im Betrieb liegt:

| Variante | Datei | Änderung wirkt |
|---|---|---|
| Docker (compose) | `converter/xml_to_xlsx_config.json` (eingebunden) | sofort |
| Windows-Dienst | `C:\Program Files\FsmXmlToXlsx\xml_to_xlsx_config.json` | sofort |
| AWS Lambda | im Image eingebaut | nach erneutem `deploy-aws.ps1` |

## Kommandozeilen-Variante

Der Konverter funktioniert auch ohne Service: `converter/xml_to_xlsx.py` wandelt alle `.xml`-Dateien im
eigenen Ordner in `.xlsx` um (liest die Konfiguration aus demselben Ordner). Mit PyInstaller lässt er sich zu einer
eigenständigen `.exe` packen (`pyinstaller --onefile xml_to_xlsx.py`).
