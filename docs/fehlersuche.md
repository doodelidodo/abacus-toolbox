# Fehlersuche

## Schnellcheck

1. **Läuft der Service?** `…/health` im Browser öffnen. Erwartet: `{"status":"ok", …}`
2. **Kommt die Datei an?** In Abacus die URI vorübergehend auf `…/debug/echo` stellen, siehe
   [Einrichtung in Abacus](abacus.md). `body_length` muss grösser als 0 sein.
3. **Logs ansehen:**
   - Docker: `docker compose logs -f`
   - Windows-Dienst: `C:\Program Files\FsmXmlToXlsx\logs\service.log`
   - AWS: `aws logs tail /aws/lambda/fsm-xml-to-xlsx --follow --region eu-central-2`

   Pro Aufruf wird protokolliert, was ankam (Content-Type, Grösse, Absender) und was erzeugt wurde (Typ, Zeilen).

## Häufige Meldungen

| Meldung | Ursache | Lösung |
|---|---|---|
| `400 Die XML-Datei ist leer: Im Request-Body kamen 0 Bytes an` | Der Aufrufer hat keinen Inhalt geschickt. In Abacus: Die Datei in `BodyFile` ist für den Abacus-Server nicht lesbar | Pfad bzw. Datei-Variable im Baustein prüfen, mit `/debug/echo` testen |
| `400 Ungültiges XML: …` | Datei ist kein XML oder beschädigt | Datei prüfen |
| `400 XML enthält nicht erlaubte Konstrukte (DTD/Entities)` | XML enthält eine DTD, wird aus Sicherheitsgründen abgelehnt | Die FSM-Dateien enthalten keine DTD. Quelle prüfen |
| `401 Ungültiger oder fehlender X-API-Key` | Header fehlt oder Wert falsch | Header `X-API-Key` im Baustein prüfen (Gross-/Kleinschreibung des Werts, keine Leerzeichen) |
| `404 Not Found` | Falscher Pfad oder alte Version läuft | URI prüfen (`/convert/raw`). Docker: `docker compose up -d --build --force-recreate`. Version steht in `/docs` |
| `413 Datei grösser als …` | Datei grösser als `MAX_UPLOAD_MB` | Wert erhöhen (AWS: max. 5) |
| `422 Im XML wurden keine …-Einträge gefunden` | XML enthält keine `<timeEfforts>` bzw. `<expenses>` unter `<activities>`, oder der Typ wurde falsch erkannt | `?type=expenses` bzw. `?type=timeEfforts` mitgeben |
| `500 Config konnte nicht geladen werden` | Feldkonfiguration ist kein gültiges JSON oder unvollständig | JSON prüfen (jedes Feld braucht `name`, `context`, `path`) |
| Excel in `Response` statt `ResponseFile` / „Zeichensalat“ | Die Excel-Datei ist binär | In Abacus `ResponseFile` verwenden |
| Excel enthält das JSON von `/debug/echo` | URI steht noch auf `/debug/echo` | URI auf `/convert/raw` zurückstellen |

## Windows-Dienst

| Problem | Lösung |
|---|---|
| Dienst startet nicht | `logs\service.log` und Ereignisanzeige → Windows-Protokolle → Anwendung prüfen |
| Port belegt | Anderen Port: `install-service.ps1 -Port 8001` bzw. `settings.json` anpassen und `Restart-Service FsmXmlToXlsx` |
| `fsm-xml-service.exe` per Doppelklick schliesst sofort | Normal. Die Datei ist ein Dienst. Zum Testen `fsm-xml-service.exe run` in einer Konsole |
| Virenscanner blockiert die .exe | Installationsordner freigeben oder .exe signieren |
| Build: `pip install` schlägt fehl | Oft ist die Python-Version zu neu für ein Paket. Python 3.12 oder 3.13 installieren und mit `py -3.12` bauen |

## AWS

| Meldung | Ursache / Lösung |
|---|---|
| `InvalidClientTokenId` | Region nicht aktiviert (Zürich ist Opt-in) oder Zugriffsschlüssel falsch. `deploy-aws.ps1` erkennt das und sagt, was zutrifft |
| `explicit deny in a service control policy` | Konto mit AWS-verwalteten Einschränkungen, siehe [AWS-Anleitung](betrieb-aws-lambda.md#hinweis-zu-neuen-aws-konten-idea-launchpad--free-plan) |
| `CreateFunctionUrlConfig … Unable to determine service/operation name` | Function URLs gibt es in der Region nicht. Das Script weicht automatisch auf API Gateway aus |
| Erster Aufruf langsam | Kaltstart nach Pause (1–2 s), normal |
