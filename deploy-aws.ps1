<#
.SYNOPSIS
    Baut die Abacus Toolbox und stellt sie als AWS Lambda mit öffentlicher HTTPS-URL bereit.

.DESCRIPTION
    Erster Aufruf: legt alles an (ECR-Repository, IAM-Rolle, Lambda, Function URL)
                   und erzeugt einen API-Key, falls keiner angegeben wurde.
    Jeder weitere Aufruf: baut neu und aktualisiert nur den Code/die Config.
                   Der bestehende API-Key bleibt erhalten, ausser du gibst -ApiKey an.

    Voraussetzungen: Docker Desktop läuft, AWS CLI v2 installiert und angemeldet
    (aws configure  oder  aws configure sso).

.EXAMPLE
    .\deploy-aws.ps1
    .\deploy-aws.ps1 -Profile abacus
    .\deploy-aws.ps1 -ApiKey "neuer-schluessel"
#>
param(
    [string]$Region = "eu-central-2",            # Zürich
    [string]$FunctionName = "fsm-xml-to-xlsx",
    [string]$RepositoryName = "fsm-xml-to-xlsx",
    [string]$RoleName = "fsm-xml-to-xlsx-lambda-role",
    [string]$ApiKey = "",
    [string]$Modules = $null,                    # z.B. "fsm_xlsx,encoding"; leer = alle; ohne Angabe = unverändert
    [string]$Profile = "",
    [int]$MemoryMb = 512,
    [int]$TimeoutSeconds = 30
)

# Native Befehle (aws, docker) werden über $LASTEXITCODE geprüft, nicht über Exceptions.
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$ServiceDir = $PSScriptRoot
$BuildContext = $ServiceDir                                            # Repository-Hauptverzeichnis
$TmpDir = Join-Path ([System.IO.Path]::GetTempPath()) "fsm-deploy"
New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "FEHLER: $text" -ForegroundColor Red; exit 1 }

$AwsConn = @("--region", $Region)
if ($Profile) { $AwsConn += @("--profile", $Profile) }
$AwsBase = $AwsConn + @("--output", "json")

# aws aufrufen; liefert geparstes JSON (oder $null), bricht bei Fehler ab ausser -AllowFail
function AwsJson {
    $AwsArgs = @()
    $allowFail = $false
    foreach ($a in $args) {
        if ("$a" -eq "-AllowFail") { $allowFail = $true } else { $AwsArgs += "$a" }
    }
    # stdout und stderr getrennt einsammeln (ohne die PowerShell-"NativeCommandError"-Hülle)
    $raw = & aws @AwsArgs @AwsBase 2>&1
    $code = $LASTEXITCODE
    $stdout = @($raw | Where-Object { $_ -isnot [System.Management.Automation.ErrorRecord] })
    $stderr = (@($raw | Where-Object { $_ -is [System.Management.Automation.ErrorRecord] } | ForEach-Object { $_.Exception.Message }) -join "`n").Trim()
    $script:LastAwsError = $stderr
    if ($code -ne 0) {
        if ($allowFail) { return $null }
        Fail ("aws " + ($AwsArgs -join " ") + "`n" + $stderr)
    }
    $text = ($stdout -join "`n").Trim()
    if ($text) { return $text | ConvertFrom-Json }
    return $null
}

# JSON-Datei ohne BOM schreiben (für file://-Parameter der AWS CLI)
function Write-JsonFile($name, $object) {
    $path = Join-Path $TmpDir $name
    [System.IO.File]::WriteAllText($path, ($object | ConvertTo-Json -Depth 10 -Compress))
    return "file://$path"
}

function New-RandomKey {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return ([Convert]::ToBase64String($bytes) -replace '[+/=]', '').Substring(0, 40)
}

# ---------------------------------------------------------------------------
Step "Voraussetzungen prüfen"
if (-not (Get-Command aws -ErrorAction SilentlyContinue)) { Fail "AWS CLI nicht gefunden. Installieren: https://aws.amazon.com/cli/" }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail "Docker nicht gefunden." }
docker info *> $null
if ($LASTEXITCODE -ne 0) { Fail "Docker läuft nicht. Bitte Docker Desktop starten." }

$identity = AwsJson sts get-caller-identity -AllowFail
if (-not $identity) {
    $firstError = $script:LastAwsError
    if ($firstError -match "InvalidClientTokenId") {
        # Häufigste Ursache: Region (z.B. Zürich) ist im Konto nicht aktiviert -> Gegenprobe in Frankfurt
        $probeArgs = @("sts", "get-caller-identity", "--region", "eu-central-1", "--output", "json")
        if ($Profile) { $probeArgs += @("--profile", $Profile) }
        & aws @probeArgs *> $null
        if ($LASTEXITCODE -eq 0 -and $Region -ne "eu-central-1") {
            Fail ("Die Region '$Region' ist in deinem AWS-Konto nicht aktiviert (der Zugangsschlüssel selbst ist gültig).`n" +
                  "Entweder die Region aktivieren (Konto -> AWS-Regionen) oder eine Standard-Region verwenden:`n" +
                  "  powershell -ExecutionPolicy Bypass -File .\deploy-aws.ps1 -Region eu-central-1")
        }
        Fail ("Der AWS-Zugangsschlüssel ist ungültig. Bitte 'aws configure' erneut ausführen und Access Key / Secret aus der CSV prüfen.`n" + $firstError)
    }
    Fail ("aws sts get-caller-identity`n" + $firstError)
}
$AccountId = $identity.Account
Write-Host "AWS-Konto: $AccountId  |  Benutzer: $($identity.Arn)  |  Region: $Region"

$Registry = "$AccountId.dkr.ecr.$Region.amazonaws.com"
$Tag = Get-Date -Format "yyyyMMdd-HHmmss"
$ImageUri = "$Registry/${RepositoryName}:$Tag"

# ---------------------------------------------------------------------------
Step "ECR-Repository '$RepositoryName'"
$repo = AwsJson ecr describe-repositories --repository-names $RepositoryName -AllowFail
if (-not $repo) {
    AwsJson ecr create-repository --repository-name $RepositoryName --image-scanning-configuration scanOnPush=true | Out-Null
    # nur die letzten 10 Images behalten
    $lifecycle = @{ rules = @(@{ rulePriority = 1; description = "keep last 10"; selection = @{ tagStatus = "any"; countType = "imageCountMoreThan"; countNumber = 10 }; action = @{ type = "expire" } }) }
    AwsJson ecr put-lifecycle-policy --repository-name $RepositoryName --lifecycle-policy-text (Write-JsonFile "lifecycle.json" $lifecycle) | Out-Null
    Write-Host "angelegt"
} else { Write-Host "vorhanden" }

# ---------------------------------------------------------------------------
Step "Docker-Image bauen und hochladen ($Tag)"
$loginArgs = @("ecr", "get-login-password") + $AwsConn
& aws @loginArgs | docker login --username AWS --password-stdin $Registry
if ($LASTEXITCODE -ne 0) { Fail "docker login bei ECR fehlgeschlagen." }

# linux/amd64 + keine Attestations: Lambda akzeptiert nur ein einfaches Single-Arch-Image
docker build --platform linux/amd64 --provenance=false --sbom=false `
    -f (Join-Path $ServiceDir "Dockerfile.lambda") -t $ImageUri $BuildContext
if ($LASTEXITCODE -ne 0) { Fail "docker build fehlgeschlagen." }
docker push $ImageUri
if ($LASTEXITCODE -ne 0) { Fail "docker push fehlgeschlagen." }

# ---------------------------------------------------------------------------
Step "IAM-Rolle '$RoleName'"
$role = AwsJson iam get-role --role-name $RoleName -AllowFail
if (-not $role) {
    $trust = @{ Version = "2012-10-17"; Statement = @(@{ Effect = "Allow"; Principal = @{ Service = "lambda.amazonaws.com" }; Action = "sts:AssumeRole" }) }
    $role = AwsJson iam create-role --role-name $RoleName --assume-role-policy-document (Write-JsonFile "trust.json" $trust)
    # nur CloudWatch-Logs, sonst keine Rechte
    AwsJson iam attach-role-policy --role-name $RoleName --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" | Out-Null
    Write-Host "angelegt, warte 15 s bis die Rolle aktiv ist ..."
    Start-Sleep -Seconds 15
} else { Write-Host "vorhanden" }
$RoleArn = $role.Role.Arn

# ---------------------------------------------------------------------------
Step "Lambda-Funktion '$FunctionName'"
$existing = AwsJson lambda get-function-configuration --function-name $FunctionName -AllowFail
$newKeyCreated = $false

if (-not $ApiKey) {
    if ($existing -and $existing.Environment -and $existing.Environment.Variables.API_KEY) {
        $ApiKey = $existing.Environment.Variables.API_KEY
    } else {
        $ApiKey = New-RandomKey
        $newKeyCreated = $true
    }
}
$envVars = @{ API_KEY = $ApiKey; LOG_LEVEL = "INFO" }
if ($PSBoundParameters.ContainsKey("Modules")) {
    if ($Modules) { $envVars.ENABLED_MODULES = $Modules }
} elseif ($existing -and $existing.Environment -and $existing.Environment.Variables.ENABLED_MODULES) {
    $envVars.ENABLED_MODULES = $existing.Environment.Variables.ENABLED_MODULES
}
$envFile = Write-JsonFile "env.json" @{ Variables = $envVars }

if (-not $existing) {
    AwsJson lambda create-function --function-name $FunctionName --package-type Image `
        --code "ImageUri=$ImageUri" --role $RoleArn `
        --memory-size $MemoryMb --timeout $TimeoutSeconds --architectures x86_64 `
        --environment $envFile | Out-Null
    AwsJson lambda wait function-active-v2 --function-name $FunctionName | Out-Null
    Write-Host "angelegt"
} else {
    AwsJson lambda update-function-code --function-name $FunctionName --image-uri $ImageUri | Out-Null
    AwsJson lambda wait function-updated-v2 --function-name $FunctionName | Out-Null
    AwsJson lambda update-function-configuration --function-name $FunctionName `
        --memory-size $MemoryMb --timeout $TimeoutSeconds --environment $envFile | Out-Null
    AwsJson lambda wait function-updated-v2 --function-name $FunctionName | Out-Null
    Write-Host "aktualisiert"
}

# ---------------------------------------------------------------------------
# Öffentliche HTTPS-Adresse:
#   1. Lambda Function URL (gratis) – nicht in allen Regionen verfügbar (z.B. nicht in Zürich)
#   2. sonst API Gateway HTTP API (ca. 1 USD pro Mio. Aufrufe)
Step "Öffentliche HTTPS-URL"
$BaseUrl = $null
$LambdaArn = "arn:aws:lambda:${Region}:${AccountId}:function:$FunctionName"

# bereits vorhandenes API Gateway?
$apis = AwsJson apigatewayv2 get-apis -AllowFail
$api = $null
if ($apis) { $api = @($apis.Items | Where-Object { $_.Name -eq $FunctionName })[0] }

if ($api) {
    $BaseUrl = $api.ApiEndpoint
    Write-Host "API Gateway vorhanden"
} else {
    $urlConfig = AwsJson lambda get-function-url-config --function-name $FunctionName -AllowFail
    if (-not $urlConfig) {
        $urlConfig = AwsJson lambda create-function-url-config --function-name $FunctionName --auth-type NONE -AllowFail
        if ($urlConfig) {
            # Seit Okt. 2025 braucht eine öffentliche Function URL beide Berechtigungen.
            # (als JSON-Datei übergeben, damit "*" nicht als Platzhalter interpretiert wird)
            $perm1 = @{ FunctionName = $FunctionName; StatementId = "FunctionUrlPublicAccess"; Action = "lambda:InvokeFunctionUrl"; Principal = "*"; FunctionUrlAuthType = "NONE" }
            $perm2 = @{ FunctionName = $FunctionName; StatementId = "FunctionUrlInvoke"; Action = "lambda:InvokeFunction"; Principal = "*"; InvokedViaFunctionUrl = $true }
            AwsJson lambda add-permission --cli-input-json (Write-JsonFile "perm1.json" $perm1) | Out-Null
            AwsJson lambda add-permission --cli-input-json (Write-JsonFile "perm2.json" $perm2) | Out-Null
            Write-Host "Function URL angelegt"
        } else {
            Write-Host "Function URL in $Region nicht verfügbar -> verwende API Gateway" -ForegroundColor Yellow
        }
    } else { Write-Host "Function URL vorhanden" }

    if ($urlConfig) {
        $BaseUrl = $urlConfig.FunctionUrl
    } else {
        # "Quick create": HTTP API mit Standard-Route und -Stage, leitet alles an die Lambda weiter
        $api = AwsJson apigatewayv2 create-api --name $FunctionName --protocol-type HTTP --target $LambdaArn
        $permApi = @{ FunctionName = $FunctionName; StatementId = "ApiGatewayInvoke"; Action = "lambda:InvokeFunction"; Principal = "apigateway.amazonaws.com"; SourceArn = "arn:aws:execute-api:${Region}:${AccountId}:$($api.ApiId)/*" }
        AwsJson lambda add-permission --cli-input-json (Write-JsonFile "perm-api.json" $permApi) | Out-Null
        $BaseUrl = $api.ApiEndpoint
        Write-Host "API Gateway angelegt"
    }
}
$BaseUrl = $BaseUrl.TrimEnd("/")

# ---------------------------------------------------------------------------
Step "Test"
Start-Sleep -Seconds 3
try {
    $health = Invoke-RestMethod -Uri "$BaseUrl/health" -TimeoutSec 30
    Write-Host "Health: $($health.status)" -ForegroundColor Green
} catch {
    Write-Host "Health-Check noch nicht erfolgreich ($($_.Exception.Message)). Erster Start kann etwas dauern, in 1 Minute nochmals $BaseUrl/health aufrufen." -ForegroundColor Yellow
}

$keyFile = Join-Path $ServiceDir ".aws-api-key.txt"
[System.IO.File]::WriteAllText($keyFile, $ApiKey)

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Green
Write-Host " Service online:  $BaseUrl"
Write-Host " Swagger-UI:      $BaseUrl/docs"
Write-Host " Werkzeuge:       $BaseUrl/modules"
Write-Host " FSM -> Excel:    POST $BaseUrl/fsm/xml-to-xlsx   (Header X-API-Key)"
if ($newKeyCreated) {
    Write-Host " Neuer API-Key:   $ApiKey" -ForegroundColor Yellow
}
Write-Host " API-Key liegt in: $keyFile  (nicht weitergeben / nicht einchecken)"
Write-Host "====================================================================="
Write-Host ""
Write-Host "Testen:  .\test.ps1 -BaseUrl $BaseUrl -ApiKey (Get-Content .aws-api-key.txt)"
