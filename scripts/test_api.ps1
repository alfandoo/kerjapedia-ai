[CmdletBinding()]
param(
    [switch]$KeepDatabase,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $root "compose.test.yaml"
$apiDirectory = Join-Path $root "apps/api"
$python = Join-Path $apiDirectory ".venv/Scripts/python.exe"
$env:TEST_DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/kerjapedia_test"
$env:DATABASE_URL = $env:TEST_DATABASE_URL
$exitCode = 1

try {
    docker compose -f $composeFile up --detach --wait
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL test container failed to start."
    }

    Push-Location $apiDirectory
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "Database migration failed."
    }

    & $python -m pytest @PytestArgs
    $exitCode = $LASTEXITCODE
}
finally {
    if ((Get-Location).Path -eq $apiDirectory) {
        Pop-Location
    }
    if (-not $KeepDatabase) {
        docker compose -f $composeFile down --volumes
    }
}

exit $exitCode
