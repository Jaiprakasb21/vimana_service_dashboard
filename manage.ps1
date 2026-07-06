param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("setup", "start", "stop")]
    [string]$Action
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPath = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
$PidFile = Join-Path $ProjectRoot ".server.pid"
$ServerUrl = "http://127.0.0.1:8010"
$ServerPort = 8010
$ServerScript = Join-Path $ProjectRoot "server.py"
$RequirementsFile = Join-Path $ProjectRoot "requirements.txt"

function Test-ServerResponsive {
    try {
        Invoke-WebRequest -UseBasicParsing $ServerUrl -TimeoutSec 2 | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Get-ServerPortProcessId {
    try {
        $connection = Get-NetTCPConnection -LocalPort $ServerPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($connection) {
            return [int]$connection.OwningProcess
        }
    } catch {
    }
    return $null
}

function Stop-TrackedServer {
    $stopped = $false

    if (-not (Test-Path -LiteralPath $PidFile)) {
        Write-Host "No tracked server PID file found. Checking port $ServerPort..."
    } else {
        $pidValue = (Get-Content -LiteralPath $PidFile -Raw).Trim()
        if (-not $pidValue) {
            Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
            Write-Host "Removed empty PID file."
        } else {
            $process = Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue
            if ($process) {
                Stop-Process -Id $process.Id -Force
                Write-Host "Stopped tracked server process $($process.Id)."
                $stopped = $true
            } else {
                Write-Host "Tracked server process not running."
            }
        }
    }

    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue

    $portPid = Get-ServerPortProcessId
    if ($portPid) {
        $portProcess = Get-Process -Id $portPid -ErrorAction SilentlyContinue
        if ($portProcess) {
            Stop-Process -Id $portProcess.Id -Force
            Write-Host "Stopped server process on port ${ServerPort}: $($portProcess.Id)."
            $stopped = $true
        }
    }

    if (-not $stopped) {
        Write-Host "No running server found."
    }
}

function Do-Setup {
    Write-Host "Running fresh setup..."
    Stop-TrackedServer

    if (Test-Path -LiteralPath $VenvPath) {
        Remove-Item -LiteralPath $VenvPath -Recurse -Force
        Write-Host "Removed existing .venv"
    }

    $cachePath = Join-Path $ProjectRoot "__pycache__"
    if (Test-Path -LiteralPath $cachePath) {
        Remove-Item -LiteralPath $cachePath -Recurse -Force -ErrorAction SilentlyContinue
    }

    python -m venv $VenvPath
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        throw "Virtual environment creation failed."
    }

    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r $RequirementsFile

    Write-Host "Setup complete."
}

function Start-Server {
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        throw ".venv is missing. Run option 1 (Do setup) first."
    }

    if (Test-ServerResponsive) {
        Write-Host "Server already running. Opening dashboard..."
        $existingPid = Get-ServerPortProcessId
        if ($existingPid) {
            Set-Content -LiteralPath $PidFile -Value $existingPid -NoNewline
        }
        Start-Process $ServerUrl
        return
    }

    if (Test-Path -LiteralPath $PidFile) {
        Stop-TrackedServer
    }

    $process = Start-Process -FilePath $VenvPython -ArgumentList "`"$ServerScript`"" -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru
    Set-Content -LiteralPath $PidFile -Value $process.Id -NoNewline

    $started = $false
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-ServerResponsive) {
            $started = $true
            break
        }
    }

    if (-not $started) {
        throw "Server did not start on $ServerUrl"
    }

    Write-Host "Server started on $ServerUrl"
    Start-Process $ServerUrl
}

switch ($Action) {
    "setup" { Do-Setup }
    "start" { Start-Server }
    "stop" { Stop-TrackedServer }
}
