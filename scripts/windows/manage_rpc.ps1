param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Start", "Stop", "Restart", "Status", "UpdateAndRestart")]
    [string]$Action
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

# Load rpc.env from %LOCALAPPDATA%\fdtd-mcp\config\ if it exists
$StateRoot = Join-Path $env:LOCALAPPDATA "fdtd-mcp"
$ConfigDir = Join-Path $StateRoot "config"
$ConfigFile = Join-Path $ConfigDir "rpc.env"
if (Test-Path $ConfigFile) {
    Get-Content $ConfigFile | ForEach-Object {
        if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.+)\s*$' -and $matches[1] -notmatch '^#') {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2].Trim(), "Process")
        }
    }
}

$Python = if ($env:FDTD_PYTHON) {
    $env:FDTD_PYTHON
} else {
    "F:\Program Files\Lumerical\v242\python\python.exe"
}
$Pythonw = Join-Path (Split-Path $Python -Parent) "pythonw.exe"
$Launcher = if (Test-Path $Pythonw) { $Pythonw } else { $Python }
$Port = if ($env:FDTD_RPC_PORT) {
    [int]$env:FDTD_RPC_PORT
} else {
    5000
}

# Use %LOCALAPPDATA%\fdtd-mcp\ for runtime state (PID, logs)
$RunDir = Join-Path $StateRoot "run"
$LogDir = Join-Path $StateRoot "logs"
$PidFile = Join-Path $RunDir "rpc_server.pid"
$StdoutLog = Join-Path $LogDir "rpc_server.out.log"
$StderrLog = Join-Path $LogDir "rpc_server.err.log"
$ServerScript = Join-Path $ProjectRoot "rpc_server.py"
$HealthUri = "http://127.0.0.1:$Port/health"

function Get-RecordedProcess {
    if (-not (Test-Path $PidFile)) {
        return $null
    }

    $recordedPid = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    if ($recordedPid -notmatch "^\d+$") {
        throw "Invalid PID file: $PidFile"
    }

    return Get-CimInstance Win32_Process -Filter "ProcessId=$recordedPid" -ErrorAction SilentlyContinue
}

function Assert-ManagedProcess {
    param($Process)

    if (
        $Process.CommandLine -notlike "*rpc_server.py*" -or
        $Process.CommandLine -notlike "*$ProjectRoot*"
    ) {
        throw "Refusing to manage PID $($Process.ProcessId): command line does not match this project."
    }
}

function Get-Health {
    try {
        return Invoke-RestMethod -Uri $HealthUri -TimeoutSec 3
    } catch {
        return $null
    }
}

function Start-Rpc {
    if (-not (Test-Path $Python)) {
        throw "Python not found: $Python"
    }
    if (-not (Test-Path $ServerScript)) {
        throw "rpc_server.py not found: $ServerScript"
    }
    if (Test-Path $PidFile) {
        $recordedProcess = Get-RecordedProcess
        if ($recordedProcess) {
            Assert-ManagedProcess $recordedProcess
            throw "RPC Server is already running as PID $($recordedProcess.ProcessId)."
        }
        Write-Host "[INFO] Removing stale PID file."
        Remove-Item -LiteralPath $PidFile -Force
    }

    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    if ($listener) {
        throw "Port $Port is already in use by PID $($listener.OwningProcess)."
    }

    New-Item -ItemType Directory -Force -Path $RunDir, $LogDir | Out-Null
    Write-Host "Starting FDTD RPC v1 on 127.0.0.1:$Port..."

    $arguments = @(
        $ServerScript,
        "--host", "127.0.0.1",
        "--port", "$Port"
    )
    $process = Start-Process `
        -FilePath $Launcher `
        -ArgumentList $arguments `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $StdoutLog `
        -RedirectStandardError $StderrLog `
        -PassThru

    Set-Content -LiteralPath $PidFile -Value $process.Id -NoNewline

    for ($attempt = 1; $attempt -le 30; $attempt++) {
        $health = Get-Health
        if ($health -and $health.ok -and $health.api_version -eq "v1") {
            Write-Host "[OK] $HealthUri"
            Write-Host "PID:    $($process.Id)"
            Write-Host "stdout: $StdoutLog"
            Write-Host "stderr: $StderrLog"
            return
        }

        if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
            $tail = if (Test-Path $StderrLog) {
                (Get-Content -LiteralPath $StderrLog -Tail 20) -join [Environment]::NewLine
            } else {
                "No stderr log was created."
            }
            Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
            throw "RPC Server exited before becoming healthy.`n$tail"
        }

        Start-Sleep -Seconds 1
    }

    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    throw "Health check timed out. See $StderrLog"
}

function Stop-Rpc {
    if (-not (Test-Path $PidFile)) {
        Write-Host "[INFO] RPC Server PID file does not exist."
        return
    }

    $process = Get-RecordedProcess
    if (-not $process) {
        Write-Host "[INFO] Recorded process is no longer running."
        Remove-Item -LiteralPath $PidFile -Force
        return
    }

    Assert-ManagedProcess $process
    Stop-Process -Id $process.ProcessId -Force
    Remove-Item -LiteralPath $PidFile -Force
    Write-Host "[OK] Stopped RPC Server PID $($process.ProcessId)"
}

function Show-Status {
    $process = Get-RecordedProcess
    if ($process) {
        Assert-ManagedProcess $process
        Write-Host "Recorded PID: $($process.ProcessId)"
    } else {
        Write-Host "Recorded PID: none"
    }

    $health = Get-Health
    if (-not $health) {
        throw "Cannot reach $HealthUri"
    }
    $health | ConvertTo-Json -Compress
}

function Update-Repository {
    Push-Location $ProjectRoot
    try {
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            throw "git is not available in PATH."
        }
        $changes = git status --porcelain
        if ($changes) {
            git status --short
            throw "Working tree is not clean. Commit or discard local changes first."
        }
        git pull --ff-only
        if ($LASTEXITCODE -ne 0) {
            throw "git pull --ff-only failed."
        }
    } finally {
        Pop-Location
    }
}

try {
    switch ($Action) {
        "Start" {
            Start-Rpc
        }
        "Stop" {
            Stop-Rpc
        }
        "Restart" {
            Stop-Rpc
            Start-Rpc
        }
        "Status" {
            Show-Status
        }
        "UpdateAndRestart" {
            Update-Repository
            Stop-Rpc
            Start-Rpc
        }
    }
} catch {
    [Console]::Error.WriteLine("[ERROR] " + $_.Exception.Message)
    exit 1
}
