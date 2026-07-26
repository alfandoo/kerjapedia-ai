[CmdletBinding()]
param(
    [string]$BackupDirectory,
    [int]$RetentionDays = 14,
    [switch]$VerifyRestore
)

$ErrorActionPreference = "Stop"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI is required to back up the PostgreSQL service."
}
$projectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($BackupDirectory)) {
    $BackupDirectory = Join-Path $projectRoot "storage\backups\postgres"
}

$resolvedProjectRoot = [System.IO.Path]::GetFullPath($projectRoot)
$resolvedBackupDirectory = [System.IO.Path]::GetFullPath($BackupDirectory)
if (-not $resolvedBackupDirectory.StartsWith($resolvedProjectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "BackupDirectory must remain inside the project workspace."
}
if ($RetentionDays -lt 1) {
    throw "RetentionDays must be at least 1."
}

$postgresUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "postgres" }
$postgresDatabase = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "kerjapedia" }
$containerName = "kerjapedia-postgres"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupName = "kerjapedia-$timestamp.dump"
$containerBackup = "/tmp/$backupName"
$localBackup = Join-Path $resolvedBackupDirectory $backupName

New-Item -ItemType Directory -Path $resolvedBackupDirectory -Force | Out-Null

function Invoke-Docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed with exit code $LASTEXITCODE."
    }
}

try {
    Invoke-Docker compose -f (Join-Path $projectRoot "compose.yaml") exec -T postgres `
        pg_dump -U $postgresUser -d $postgresDatabase --format=custom --file=$containerBackup
    Invoke-Docker cp "${containerName}:$containerBackup" $localBackup

    $checksum = (Get-FileHash -LiteralPath $localBackup -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath "$localBackup.sha256" -Value "$checksum  $backupName" -Encoding ascii

    if ($VerifyRestore) {
        $restoreDatabase = "kerjapedia_restore_check_$([guid]::NewGuid().ToString('N').Substring(0, 12))"
        try {
            Invoke-Docker compose -f (Join-Path $projectRoot "compose.yaml") exec -T postgres `
                createdb -U $postgresUser $restoreDatabase
            Invoke-Docker compose -f (Join-Path $projectRoot "compose.yaml") exec -T postgres `
                pg_restore -U $postgresUser -d $restoreDatabase --exit-on-error $containerBackup
            Invoke-Docker compose -f (Join-Path $projectRoot "compose.yaml") exec -T postgres `
                psql -U $postgresUser -d $restoreDatabase -v ON_ERROR_STOP=1 -c `
                "SELECT COUNT(*) AS restored_tables FROM information_schema.tables WHERE table_schema = 'public';"
        }
        finally {
            if ($restoreDatabase -and $restoreDatabase.StartsWith("kerjapedia_restore_check_")) {
                & docker compose -f (Join-Path $projectRoot "compose.yaml") exec -T postgres `
                    dropdb -U $postgresUser --if-exists $restoreDatabase
            }
        }
    }
}
finally {
    & docker compose -f (Join-Path $projectRoot "compose.yaml") exec -T postgres `
        rm -f $containerBackup
}

$cutoff = (Get-Date).AddDays(-$RetentionDays)
Get-ChildItem -LiteralPath $resolvedBackupDirectory -File |
    Where-Object {
        $_.LastWriteTime -lt $cutoff -and
        ($_.Name -like "kerjapedia-*.dump" -or $_.Name -like "kerjapedia-*.dump.sha256")
    } |
    Remove-Item -Force

Write-Output "backup_path=$localBackup"
Write-Output "sha256=$checksum"
Write-Output "restore_verified=$($VerifyRestore.IsPresent)"
