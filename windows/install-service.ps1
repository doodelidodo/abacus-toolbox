<#
.SYNOPSIS
    Installiert (oder aktualisiert) den FSM XML -> XLSX Service als Windows-Dienst.
    Muss als Administrator laufen. Vorher build-windows-service.ps1 ausführen.

.PARAMETER InstallDir  Zielordner (Standard: C:\Program Files\AbacusToolbox)
.PARAMETER Port        Port (Standard 8000)
.PARAMETER ListenAll   Auch von anderen Rechnern erreichbar (0.0.0.0) + Firewall-Regel.
                       Ohne Schalter nur lokal (127.0.0.1) – richtig, wenn Abacus auf demselben Server läuft.
.PARAMETER ApiKey      Optionaler API-Key (Header X-API-Key). Bei -ListenAll dringend empfohlen.
.PARAMETER Modules     Aktive Werkzeuge, kommagetrennt, z.B. "fsm_xlsx,encoding". Leer = alle.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\install-service.ps1
    powershell -ExecutionPolicy Bypass -File .\install-service.ps1 -Port 8001
    powershell -ExecutionPolicy Bypass -File .\install-service.ps1 -ListenAll -ApiKey "langer-geheimer-key"
#>
param(
    [string]$InstallDir = "C:\Program Files\AbacusToolbox",
    [int]$Port = 0,
    [switch]$ListenAll,
    [string]$ApiKey = $null,
    [string]$Modules = $null
)
$ErrorActionPreference = "Stop"
$ServiceName = "AbacusToolbox"
$DisplayName = "Abacus Toolbox"
$Source = Join-Path $PSScriptRoot "dist\abacus-toolbox"

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { throw "Bitte PowerShell als Administrator starten (Rechtsklick -> Als Administrator ausführen)." }
if (-not (Test-Path (Join-Path $Source "abacus-toolbox.exe"))) { throw "Build nicht gefunden: $Source. Zuerst build-windows-service.ps1 ausführen." }

$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue

# Vorgängerversion (bis 1.x hiess der Dienst "FsmXmlToXlsx") wird abgelöst, Einstellungen werden übernommen
$LegacyName = "FsmXmlToXlsx"
$LegacyDir = "C:\Program Files\FsmXmlToXlsx"
$legacy = Get-Service -Name $LegacyName -ErrorAction SilentlyContinue
$settingsSource = Join-Path $InstallDir "settings.json"
if (-not (Test-Path $settingsSource) -and (Test-Path (Join-Path $LegacyDir "settings.json"))) {
    $settingsSource = Join-Path $LegacyDir "settings.json"
}

# --- Port prüfen, bevor irgendetwas geändert wird -------------------------------
$checkPort = $Port
if ($checkPort -le 0) {
    $checkPort = 8000
    if (Test-Path $settingsSource) { try { $checkPort = [int]((Get-Content $settingsSource -Raw | ConvertFrom-Json).port) } catch { } }
}
# eigene Prozesse (dieser Dienst bzw. die Vorgängerversion) zählen nicht als Konflikt
$ownPids = @()
foreach ($svcName in @($ServiceName, $LegacyName)) {
    $svc = Get-CimInstance Win32_Service -Filter "Name='$svcName'" -ErrorAction SilentlyContinue
    if ($svc -and $svc.ProcessId) { $ownPids += [int]$svc.ProcessId }
}
$listeners = @(Get-NetTCPConnection -LocalPort $checkPort -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $ownPids -notcontains [int]$_.OwningProcess })
if ($listeners.Count -gt 0) {
    $names = ($listeners | ForEach-Object {
        $proc = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
        "$($_.LocalAddress):$($_.LocalPort) -> $($proc.ProcessName) (PID $($_.OwningProcess))"
    }) -join "`n  "
    throw "Port $checkPort ist bereits belegt:`n  $names`nEs wurde nichts geändert. Bitte einen freien Port wählen, z.B.: .\install-service.ps1 -Port 8765"
}
Write-Host "Port $checkPort ist frei." -ForegroundColor Green
if ($existing -and $existing.Status -ne "Stopped") {
    Step "Dienst stoppen (Update)"
    Stop-Service -Name $ServiceName -Force
    (Get-Service $ServiceName).WaitForStatus("Stopped", [TimeSpan]::FromSeconds(30))
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

if ($legacy) {
    Step "Vorgängerversion '$LegacyName' ablösen"
    if ($legacy.Status -ne "Stopped") {
        Stop-Service -Name $LegacyName -Force
        (Get-Service $LegacyName).WaitForStatus("Stopped", [TimeSpan]::FromSeconds(30))
    }
    sc.exe delete $LegacyName | Out-Null
    Get-NetFirewallRule -DisplayName "FSM XML to XLSX (*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    Write-Host "alter Dienst entfernt"
}
foreach ($f in @("settings.json", "xml_to_xlsx_config.json")) {
    $old = Join-Path $LegacyDir $f
    $new = Join-Path $InstallDir $f
    if ((Test-Path $old) -and -not (Test-Path $new)) {
        Copy-Item $old $new
        Write-Host "$f aus $LegacyDir übernommen"
    }
}

Step "Dateien nach $InstallDir kopieren"
# Programmdateien ersetzen, settings.json / Config / logs des Kunden behalten
Get-ChildItem $Source | Where-Object { $_.Name -notin @("settings.json", "xml_to_xlsx_config.json") } |
    ForEach-Object { Copy-Item $_.FullName $InstallDir -Recurse -Force }
# Dateien aus einer heruntergeladenen ZIP freigeben (Zone.Identifier), sonst kann Windows den Start blockieren
Get-ChildItem $InstallDir -Recurse -File | Unblock-File -ErrorAction SilentlyContinue
$configTarget = Join-Path $InstallDir "xml_to_xlsx_config.json"
if (-not (Test-Path $configTarget)) { Copy-Item (Join-Path $Source "xml_to_xlsx_config.json") $configTarget }

Step "Einstellungen (settings.json)"
$settingsPath = Join-Path $InstallDir "settings.json"
$settings = [ordered]@{ host = "127.0.0.1"; port = 8000; api_key = ""; modules = @(); config_path = "xml_to_xlsx_config.json"; log_level = "INFO" }
if (Test-Path $settingsPath) {
    $old = Get-Content $settingsPath -Raw | ConvertFrom-Json
    foreach ($p in $old.PSObject.Properties) { $settings[$p.Name] = $p.Value }
}
if ($Port -gt 0) { $settings.port = $Port }
if ($ListenAll) { $settings.host = "0.0.0.0" }
if ($PSBoundParameters.ContainsKey("ApiKey")) { $settings.api_key = $ApiKey }
if ($PSBoundParameters.ContainsKey("Modules")) { $settings.modules = @(($Modules -split ",") | ForEach-Object { $_.Trim() } | Where-Object { $_ }) }
[System.IO.File]::WriteAllText($settingsPath, ($settings | ConvertTo-Json))
Write-Host ($settings | ConvertTo-Json)

$exe = Join-Path $InstallDir "abacus-toolbox.exe"
if (-not $existing) {
    Step "Dienst '$ServiceName' anlegen"
    New-Service -Name $ServiceName -DisplayName $DisplayName -BinaryPathName "`"$exe`"" `
        -StartupType Automatic -Description "Wandelt FSM/Abacus-XML per REST-API in Excel um." | Out-Null
    # bei Absturz automatisch neu starten (nach 5 s, 3x; Zähler nach 1 Tag zurücksetzen)
    sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/5000/restart/5000 | Out-Null
}

if ($settings.host -eq "0.0.0.0") {
    Step "Firewall-Regel für Port $($settings.port)"
    $ruleName = "Abacus Toolbox ($($settings.port))"
    if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort $settings.port -Action Allow | Out-Null
    }
    if (-not $settings.api_key) { Write-Host "WARNUNG: Von aussen erreichbar, aber ohne API-Key!" -ForegroundColor Yellow }
}

Step "Dienst starten"
Start-Service -Name $ServiceName
(Get-Service $ServiceName).WaitForStatus("Running", [TimeSpan]::FromSeconds(30))

Step "Test"
$url = "http://localhost:$($settings.port)"
$ok = $false
for ($i = 0; $i -lt 15 -and -not $ok; $i++) {
    try { $h = Invoke-RestMethod "$url/health" -TimeoutSec 3; $ok = $true } catch { Start-Sleep -Seconds 1 }
}
if ($ok) {
    Write-Host "Health: $($h.status)  |  Config: $($h.config)" -ForegroundColor Green
    Write-Host "`nDienst läuft:  $url/convert/raw   (Swagger: $url/docs)"
    Write-Host "Logs:          $InstallDir\logs\service.log"
    if (Test-Path $LegacyDir) { Write-Host "Hinweis: Der Ordner der Vorgängerversion ($LegacyDir) wird nicht mehr gebraucht und kann gelöscht werden." -ForegroundColor Yellow }
} else {
    Write-Host "Dienst antwortet nicht. Siehe $InstallDir\logs\service.log bzw. Ereignisanzeige -> Windows-Protokolle -> Anwendung." -ForegroundColor Red
    exit 1
}
