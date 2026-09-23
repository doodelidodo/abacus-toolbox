# Betrieb mit Docker

Geeignet zum Testen auf dem eigenen Rechner, für Linux-Server und für Container-Plattformen.

## Lokal mit Docker Desktop

```powershell
git clone https://github.com/doodelidodo/fsm-xml-to-xlsx.git
cd fsm-xml-to-xlsx
docker compose up -d --build
```

- Service: <http://localhost:8000> · Swagger: <http://localhost:8000/docs> · Health: <http://localhost:8000/health>
- Die Feldkonfiguration `converter/xml_to_xlsx_config.json` ist in den Container eingebunden. Änderungen wirken sofort.
- Änderungen am Code (`app/`, `converter/xml_to_xlsx.py`): `docker compose up -d --build`
- Wurde Code geändert und läuft trotzdem noch die alte Version: `docker compose up -d --build --force-recreate`.
  Die Version steht oben in der Swagger-Oberfläche.
- Logs: `docker compose logs -f` · Stoppen: `docker compose down`

### Test

```powershell
.\test.ps1                                   # alle XMLs aus samples\ → output\
.\test.ps1 -XmlFolder C:\pfad\zu\xmls        # eigene Dateien
.\test.ps1 -BaseUrl http://server:8000 -ApiKey "…"
```

### Werkzeuge ein-/ausschalten

In `docker-compose.yml` die Zeile `ENABLED_MODULES` einkommentieren, z.B. `"fsm_xlsx"`, dann `docker compose up -d`.
Leer bzw. nicht gesetzt = alle Werkzeuge.

### API-Key aktivieren

In `docker-compose.yml` die Zeile `API_KEY` einkommentieren und einen langen, zufälligen Wert eintragen, dann
`docker compose up -d`. Einen Schlüssel erzeugen, z.B.:

```powershell
-join ((48..57)+(65..90)+(97..122) | Get-Random -Count 40 | ForEach-Object {[char]$_})
```

### Aus dem Netzwerk erreichbar machen

Docker veröffentlicht Port 8000 auf allen Netzwerkschnittstellen. Damit ein anderer Rechner (z.B. ein Abacus-Server)
zugreifen kann, unter Windows den Port freigeben (PowerShell als Administrator):

```powershell
New-NetFirewallRule -DisplayName "fsm-service 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
```

In diesem Fall immer einen API-Key setzen.

## Andere Container-Plattformen

Das `Dockerfile` erzeugt ein normales Linux-Container-Image (Port 8000, Healthcheck `/health`). Es läuft
unverändert auf jeder Container-Plattform, z.B. **Azure Container Apps**, Azure App Service for Containers oder
Kubernetes. Zu beachten:

- Umgebungsvariablen `API_KEY` (als Secret), optional `ENABLED_MODULES`, `MAX_UPLOAD_MB`, `LOG_LEVEL`
- Die Feldkonfiguration ist im Image enthalten. Für eine eigene Konfiguration eine Datei nach
  `/config/xml_to_xlsx_config.json` einbinden oder `CONFIG_PATH` setzen.
- Im Internet nur über HTTPS betreiben (bieten die genannten Plattformen automatisch).
- Bei Azure Container Apps kann der Dienst auch nur intern im VNet erreichbar gemacht werden. Dann braucht es keine
  öffentliche Adresse.

Image bauen und in eine Registry laden (Beispiel):

```powershell
docker build -t <registry>/abacus-toolbox:2.0.0 .
docker push <registry>/abacus-toolbox:2.0.0
```
