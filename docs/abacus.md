# Einrichtung in Abacus

Der Service wird im Abacus-Prozess mit dem Baustein **„Webservice Aufruf ausführen“** aufgerufen.
Die XML-Datei wird als Request-Body geschickt, die Excel-Datei kommt als Antwort zurück.

## Eingaben des Bausteins

| Feld | Wert |
|---|---|
| **Method** | `POST` |
| **URI** | Adresse des Service + `/convert/raw` (siehe unten) |
| **Headers** | `Content-Type: application/xml`, zusätzlich `X-API-Key: <Schlüssel>`, falls ein API-Key eingerichtet ist |
| **QueryParameters** | `filename=<Name der XML-Datei>` (empfohlen, bestimmt den Namen der Excel-Datei). Optional `type=timeEfforts` bzw. `type=expenses` |
| **Cookies** | leer |
| **BodyFile** | die XML-Datei |
| **AuthenticationDefinition** | leer (der API-Key läuft über den Header) |
| **NoResponse** | nein |
| **ContinueProcessOnFailure** | nach Bedarf |

### URI je Betriebsvariante

| Variante | URI |
|---|---|
| Windows-Dienst auf dem Abacus-Server | `http://localhost:8000/convert/raw` |
| Windows-Dienst auf einem anderen Server | `http://<servername>:8000/convert/raw` (mit API-Key) |
| Docker lokal | `http://localhost:8000/convert/raw` |
| AWS Lambda | `https://<id>.execute-api.eu-central-2.amazonaws.com/convert/raw` (wird von `deploy-aws.ps1` ausgegeben) |

## Ausgaben des Bausteins

| Feld | Inhalt |
|---|---|
| **ResponseFile** | **die Excel-Datei**, diese im weiteren Prozess verwenden |
| **Response** | nicht verwenden: Bei Erfolg ist das die binäre Excel-Datei als Text. Bei Fehlern steht hier die Fehlermeldung als JSON |
| **StatusCode** | `200` bei Erfolg |
| **Succeeded** | `true` bei Erfolg |
| **ResponseHeaders** | enthält u.a. `X-Row-Count` (Anzahl Zeilen) und `X-Record-Type` |
| **FailureReason** | Grund bei Verbindungsfehlern |

## Wichtig: Die Datei muss für Abacus lesbar sein

Den Aufruf macht der **Abacus-Server**, nicht der Arbeitsplatz. Die Datei in `BodyFile` muss deshalb für den
Abacus-Dienst lesbar sein. Kann Abacus die Datei nicht lesen, schickt der Baustein trotzdem einen Request,
aber **ohne Inhalt**. Der Service antwortet dann mit:

```
400  {"detail": "Die XML-Datei ist leer: Im Request-Body kamen 0 Bytes an (…)"}
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

- `body_length` > 0 und `body_start` beginnt mit dem XML: Die Einstellungen stimmen, jetzt die URI zurück auf `/convert/raw` stellen.
- `body_length` = 0: Abacus hat die Datei nicht gelesen (siehe oben).

`/debug/echo` liefert immer nur dieses JSON und nie eine Excel-Datei.
