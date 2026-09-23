# Werkzeug: Zeichensatz umwandeln

Modul `encoding`. Wandelt Textdateien (CSV, TXT, XML …) in einen anderen Zeichensatz um und vereinheitlicht
auf Wunsch die Zeilenenden. Typischer Fall: Eine Datei kommt als UTF-8, der Abacus-Import erwartet ANSI
(Windows-1252), oder umgekehrt. Ohne Umwandlung werden Umlaute dann zu `Ã¼` und Ähnlichem.

## `POST /text/convert-encoding`

| Parameter | Standard | Bedeutung |
|---|---|---|
| Body | | Die Textdatei |
| `filename` | | Name der Datei. Die Antwort bekommt denselben Namen |
| `source` | `auto` | Zeichensatz der Eingabe. `auto` erkennt: BOM (UTF-8/UTF-16), sonst gültiges UTF-8, sonst ANSI (Windows-1252) |
| `target` | `windows-1252` | Zielzeichensatz, z.B. `windows-1252` (ANSI), `utf-8`, `iso-8859-1`, `utf-16` |
| `newline` | `keep` | Zeilenenden: `keep` (unverändert), `crlf` (Windows), `lf` (Unix) |
| `bom` | `false` | Bei UTF-8 ein BOM voranstellen (manche Programme, z.B. Excel, erkennen UTF-8 nur damit) |
| `errors` | `strict` | `strict` = Fehler, wenn ein Zeichen im Zielzeichensatz nicht existiert (z.B. `€` in ISO-8859-1); `replace` = durch `?` ersetzen |

Antwort: `200` mit der umgewandelten Datei, Header `X-Source-Encoding` (erkannter bzw. angegebener Zeichensatz der
Eingabe) und `X-Target-Encoding`.

### Beispiele

UTF-8-CSV für einen Abacus-Import nach ANSI mit Windows-Zeilenenden:

```powershell
curl.exe --data-binary "@export.csv" `
  "http://localhost:8000/text/convert-encoding?filename=export.csv&target=windows-1252&newline=crlf" -o export_ansi.csv
```

ANSI-Datei aus Abacus nach UTF-8 mit BOM:

```powershell
curl.exe --data-binary "@abacus_export.txt" `
  "http://localhost:8000/text/convert-encoding?target=utf-8&bom=true" -o abacus_export_utf8.txt
```

### Fehlermeldungen

| Code | Meldung |
|---|---|
| 400 | `Unbekannter Zeichensatz …`, ungültiger Wert für `newline` oder `errors` |
| 422 | `Die Datei ist nicht im Zeichensatz '…'`: falscher `source`, `auto` versuchen |
| 422 | `Zeichen '€' (Zeile 3) gibt es im Zielzeichensatz '…' nicht`: anderen Zielzeichensatz wählen oder `errors=replace` |

## In Abacus

Wie bei jedem Werkzeug, siehe [Einrichtung in Abacus](abacus.md). URI z.B.
`http://localhost:8000/text/convert-encoding`, QueryParameters `filename=…`, `target=windows-1252`, `newline=crlf`.
Das Ergebnis steht in `ResponseFile`.
