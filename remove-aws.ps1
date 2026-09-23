<#
.SYNOPSIS
    Entfernt alles, was deploy-aws.ps1 in AWS angelegt hat (Lambda, URL, IAM-Rolle, ECR-Repository inkl. Images).
#>
param(
    [string]$Region = "eu-central-2",
    [string]$FunctionName = "fsm-xml-to-xlsx",
    [string]$RepositoryName = "fsm-xml-to-xlsx",
    [string]$RoleName = "fsm-xml-to-xlsx-lambda-role",
    [string]$Profile = ""
)

$ErrorActionPreference = "Continue"
$AwsBase = @("--region", $Region)
if ($Profile) { $AwsBase += @("--profile", $Profile) }

$answer = Read-Host "Wirklich '$FunctionName' samt URL/API Gateway, Rolle und Images in $Region löschen? (ja/nein)"
if ($answer -ne "ja") { Write-Host "Abgebrochen."; exit 0 }

$apiIds = aws apigatewayv2 get-apis --query "Items[?Name=='$FunctionName'].ApiId" --output text @AwsBase 2>$null
foreach ($id in ("$apiIds" -split "\s+" | Where-Object { $_ -and $_ -ne "None" })) {
    aws apigatewayv2 delete-api --api-id $id @AwsBase 2>$null
}
aws lambda delete-function-url-config --function-name $FunctionName @AwsBase 2>$null
aws lambda delete-function --function-name $FunctionName @AwsBase 2>$null
aws iam detach-role-policy --role-name $RoleName --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" @AwsBase 2>$null
aws iam delete-role --role-name $RoleName @AwsBase 2>$null
aws ecr delete-repository --repository-name $RepositoryName --force @AwsBase 2>$null | Out-Null

Write-Host "Erledigt. (Log-Gruppe /aws/lambda/$FunctionName bleibt in CloudWatch bestehen und kann dort gelöscht werden.)"
