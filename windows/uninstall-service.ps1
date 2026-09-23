<#
.SYNOPSIS
    Entfernt den Windows-Dienst FsmXmlToXlsx (als Administrator ausführen).
    -RemoveFiles löscht zusätzlich den Programmordner (inkl. settings.json und Logs).
#>
param(
    [string]$InstallDir = "C:\Program Files\FsmXmlToXlsx",
    [switch]$RemoveFiles
)
$ServiceName = "FsmXmlToXlsx"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { throw "Bitte PowerShell als Administrator starten." }

if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    sc.exe delete $ServiceName | Out-Null
    Write-Host "Dienst entfernt."
} else { Write-Host "Dienst war nicht installiert." }

Get-NetFirewallRule -DisplayName "FSM XML to XLSX (*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule

if ($RemoveFiles -and (Test-Path $InstallDir)) {
    Remove-Item $InstallDir -Recurse -Force
    Write-Host "Ordner $InstallDir gelöscht."
}
