# Einrichtung in Abacus

Jedes Werkzeug der Toolbox wird im Abacus-Prozess mit dem Baustein **„Webservice Aufruf ausführen“** aufgerufen.
Die Datei wird als Request-Body geschickt, das Ergebnis kommt als Datei zurück. Die Einstellungen sind für alle
Werkzeuge gleich, nur die URI (und evtl. zusätzliche QueryParameters) unterscheiden sich. Die Beispiele verwenden das
FSM-Werkzeug.

## Eingaben des Bausteins

| Feld | Wert |
|---|---|
| **Method** | `POST` |
| **URI** | Adresse des Service + Pfad des Werkzeugs, z.B. `/fsm/xml-to-xlsx` (siehe unten) |
| **Headers** | `Content-Type: application/xml` (bei Textdateien `text/plain`), zusätzlich `X-API-Key: <Schlüssel>`, falls ein API-Key eingerichtet ist |
| **QueryParameters** | `filename=<Name der Datei>` (empfohlen, bestimmt den Namen der Ergebnis-Datei), dazu die Parameter des Werkzeugs, z.B. `type=expenses` |
| **Cookies** | leer |
| **BodyFile** | die Eingabedatei |
| **AuthenticationDefinition** | leer (der API-Key läuft über den Header) |
| **NoResponse** | nein |
| **ContinueProcessOnFailure** | nach Bedarf |

### URI je Betriebsvariante (Beispiel FSM-Werkzeug)

| Variante | URI |
|---|---|
| Windows-Dienst auf dem Abacus-Server | `http://localhost:8000/fsm/xml-to-xlsx` |
| Windows-Dienst auf einem anderen Server | `http://<servername>:8000/fsm/xml-to-xlsx` (mit API-Key) |
| Docker lokal | `http://localhost:8000/fsm/xml-to-xlsx` |
| AWS Lambda | `https://<id>.execute-api.eu-central-2.amazonaws.com/fsm/xml-to-xlsx` (Adresse wird von `deploy-aws.ps1` ausgegeben) |

Pfade der anderen Werkzeuge: siehe Tabelle „Werkzeuge“ im [README](../README.md#werkzeuge) oder `…/modules`.
Die Adresse `/convert/raw` aus Version 1 funktioniert weiterhin.

## Ausgaben des Bausteins

| Feld | Inhalt |
|---|---|
| **ResponseFile** | **die Ergebnis-Datei** (z.B. die Excel-Datei), diese im weiteren Prozess verwenden |
| **Response** | bei Erfolg nicht verwenden (Datei als Text, bei Excel unlesbar). Bei Fehlern steht hier die Fehlermeldung als JSON |
| **StatusCode** | `200` bei Erfolg |
| **Succeeded** | `true` bei Erfolg |
| **ResponseHeaders** | werkzeugspezifische Angaben, z.B. `X-Row-Count` (Anzahl Zeilen) beim FSM-Werkzeug |
| **FailureReason** | Grund bei Verbindungsfehlern |

## Wichtig: Die Datei muss für Abacus lesbar sein

Den Aufruf macht der **Abacus-Server**, nicht der Arbeitsplatz. Die Datei in `BodyFile` muss deshalb für den
Abacus-Dienst lesbar sein. Kann Abacus die Datei nicht lesen, schickt der Baustein trotzdem einen Request,
aber **ohne Inhalt**. Der Service antwortet dann mit:

```
400  {"detail": "Die Datei ist leer: Im Request-Body kamen 0 Bytes an (…)"}
```

## Erster Test mit `/debug/echo`

Zum Einrichten die URI vorübergehend auf `…/debug/echo` stellen, z.B. `http://localhost:8000/debug/echo`.
Der Service schickt dann als JSON zurück, was angekommen ist:

```json
{
  "method": "POST",
  "headers": { "content-type": "application/xml", "content-length": "4821", "user-agent": "Apache-HttpClient/4.5.13 (Java/21.0.8)" },
  "body_length": 4821,
  "body_start": "<?xml version='1.0' encoding='UTF-8'?><root><eventType>activity.confirmed</eventType>…"
}
```

- `body_length` > 0 und `body_start` zeigt den Anfang der Datei: Die Einstellungen stimmen, jetzt die URI zurück auf das Werkzeug stellen.
- `body_length` = 0: Abacus hat die Datei nicht gelesen (siehe oben).

`/debug/echo` liefert immer nur dieses JSON und nie eine Ergebnis-Datei.
