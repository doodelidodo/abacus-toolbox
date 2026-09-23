<#
.SYNOPSIS
    Baut den Service als Windows-Programm (Ordner dist\fsm-xml-service) – ohne Docker.
    Danach: install-service.ps1 (als Administrator) installiert ihn als Windows-Dienst.

.EXAMPLE
    cd <Repository>\windows
    powershell -ExecutionPolicy Bypass -File .\build-windows-service.ps1
#>
$ErrorActionPreference = "Stop"
$Here = $PSScriptRoot
$AppDir = (Resolve-Path (Join-Path $Here "..\app")).Path
$FsmDir = (Resolve-Path (Join-Path $Here "..\converter")).Path
$Venv = Join-Path $Here ".build-venv"

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }

Step "Python suchen"
$pyExe = $null; $pyArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) { $pyExe = "py"; $pyArgs = @() }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $pyExe = "python" }
else { throw "Python nicht gefunden. Bitte Python 3.11+ installieren (https://www.python.org)." }
& $pyExe @pyArgs --version

Step "Build-Umgebung (.build-venv)"
if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    & $pyExe @pyArgs -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "venv konnte nicht erstellt werden." }
}
$py = Join-Path $Venv "Scripts\python.exe"
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -r (Join-Path $Here "requirements-windows.txt") --quiet
if ($LASTEXITCODE -ne 0) { throw "pip install fehlgeschlagen." }

Step "PyInstaller"
Push-Location $Here
try {
    & $py -m PyInstaller --noconfirm --clean --onedir --console `
        --name fsm-xml-service `
        --paths $AppDir --paths $FsmDir `
        --hidden-import main --hidden-import xml_to_xlsx `
        --collect-submodules core --collect-submodules modules `
        --hidden-import win32timezone --hidden-import python_multipart `
        --collect-submodules uvicorn `
        --distpath (Join-Path $Here "dist") --workpath (Join-Path $Here "build") --specpath (Join-Path $Here "build") `
        (Join-Path $Here "service.py")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller fehlgeschlagen." }
} finally { Pop-Location }

$Dist = Join-Path $Here "dist\fsm-xml-service"
Copy-Item (Join-Path $FsmDir "xml_to_xlsx_config.json") $Dist -Force

Step "Installationspaket (ZIP) für Kundenserver"
$version = "dev"
$m = Select-String -Path (Join-Path $AppDir "main.py") -Pattern 'version="([^"]+)"' | Select-Object -First 1
if ($m) { $version = $m.Matches[0].Groups[1].Value }
$ReleaseDir = Join-Path $Here "release"
$Stage = Join-Path $ReleaseDir "fsm-xml-service-$version"
if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path (Join-Path $Stage "dist") | Out-Null
Copy-Item $Dist (Join-Path $Stage "dist") -Recurse
Copy-Item (Join-Path $Here "install-service.ps1"), (Join-Path $Here "uninstall-service.ps1"), (Join-Path $Here "INSTALLATION.txt") $Stage
$Zip = Join-Path $ReleaseDir "fsm-xml-service-$version.zip"
if (Test-Path $Zip) { Remove-Item $Zip -Force }
Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $Zip
Remove-Item $Stage -Recurse -Force

Step "Fertig"
Write-Host "Programm:  $Dist\fsm-xml-service.exe"
Write-Host "Paket:     $Zip   <- diese Datei auf den Kundenserver kopieren (Anleitung: INSTALLATION.txt in der ZIP)"
Write-Host ""
Write-Host "Schnelltest im Fenster (Ctrl+C beendet):"
Write-Host "  & '$Dist\fsm-xml-service.exe' run"
Write-Host ""
Write-Host "Auf diesem Rechner als Dienst installieren (PowerShell als Administrator):"
Write-Host "  powershell -ExecutionPolicy Bypass -File '$Here\install-service.ps1'"
