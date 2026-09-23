# Schickt alle XML-Dateien aus einem Ordner (Standard: samples\) an den Service und speichert die Excel-Dateien.
# Aufruf (im Repository-Ordner):   .\test.ps1
# Mit API-Key:                      .\test.ps1 -ApiKey "dein-token"
param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$XmlFolder = "$PSScriptRoot\samples",
    [string]$OutFolder = "$PSScriptRoot\output",
    [string]$ApiKey = ""
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutFolder | Out-Null

Write-Host "Health: " -NoNewline
curl.exe -s "$BaseUrl/health"
Write-Host ""

$keyHeader = @()
if ($ApiKey) { $keyHeader = @("-H", "X-API-Key: $ApiKey") }

Get-ChildItem -Path $XmlFolder -Filter *.xml | ForEach-Object {
    $out = Join-Path $OutFolder ($_.BaseName + ".xlsx")
    $status = curl.exe -s -o $out -w "%{http_code}" @keyHeader -F "file=@$($_.FullName)" "$BaseUrl/convert"
    if ($status -eq "200") {
        Write-Host "OK   $($_.Name) -> $out" -ForegroundColor Green
    } else {
        Write-Host "FAIL $($_.Name) (HTTP $status): $(Get-Content $out -Raw)" -ForegroundColor Red
        Remove-Item $out -ErrorAction SilentlyContinue
    }
}
