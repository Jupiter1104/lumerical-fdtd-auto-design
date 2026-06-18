param(
    [Parameter(Mandatory = $true)]
    [string]$Source
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$DestinationDir = Join-Path $ProjectRoot "templates\metasurface"
$Destination = Join-Path $DestinationDir "base_model.fsp"

if (-not (Test-Path -LiteralPath $Source)) {
    throw "Template not found: $Source"
}

New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
Copy-Item -LiteralPath $Source -Destination $Destination -Force
$hash = Get-FileHash -Algorithm SHA256 -LiteralPath $Destination
$item = Get-Item -LiteralPath $Destination

Write-Host "[OK] Template installed"
Write-Host "Path:   $Destination"
Write-Host "Bytes:  $($item.Length)"
Write-Host "SHA256: $($hash.Hash)"
