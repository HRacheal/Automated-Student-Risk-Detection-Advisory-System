<#
  Starts the local My Coach LMS development stack, in order:
    Moodle (Apache :8081 + MariaDB :3307)  ->  LMS backend (FastAPI :8100)  ->  frontend (Vite :5173)

  Usage (from moodle-lms):   .\start-lms.ps1
  Safe to re-run: anything already listening on its port is left alone.
  Reads no secrets - the backend loads backend\.env itself.
#>
param(
    [string]$MoodleDir = "C:\Users\Admin\Downloads\Moodle",
    [int]$MoodleTimeoutSeconds = 180,
    [int]$ServiceTimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"
$Root        = $PSScriptRoot
$BackendDir  = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"

$MoodleUrl   = "http://localhost:8081/login/index.php"   # needs Apache AND the database to answer 200
$BackendUrl  = "http://127.0.0.1:8100/api/health"
$FrontendUrl = "http://localhost:5173/"

function Write-Step($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Write-Info($msg) { Write-Host "    $msg" }

function Test-Port([int]$Port) {
    [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

# Returns the HTTP status code, or 0 when nothing answered.
function Get-HttpStatus([string]$Url) {
    try {
        (Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5).StatusCode
    } catch {
        if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
    }
}

# Polls $Url until it answers 2xx/3xx or the timeout runs out.
function Wait-Http([string]$Url, [int]$TimeoutSeconds, [string]$Name) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    Write-Host -NoNewline "    Waiting for $Name "
    while ((Get-Date) -lt $deadline) {
        $code = Get-HttpStatus $Url
        if ($code -ge 200 -and $code -lt 400) { Write-Host " ready"; return $true }
        Write-Host -NoNewline "."
        Start-Sleep -Seconds 2
    }
    Write-Host " timed out (last status: $code)"
    return $false
}

function Start-InNewWindow([string]$Title, [string]$Dir, [string]$Command) {
    $script = "`$Host.UI.RawUI.WindowTitle = '$Title'; Set-Location -LiteralPath '$Dir'; $Command"
    Start-Process powershell.exe -WorkingDirectory $Dir -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $script) | Out-Null
}

# ------------------------------------------------------------------ 1. Moodle
Write-Step "Moodle (http://localhost:8081)"
if ((Get-HttpStatus $MoodleUrl) -eq 200) {
    Write-Ok "Moodle is already running."
} else {
    $exe = Join-Path $MoodleDir "Start Moodle.exe"
    if (-not (Test-Path -LiteralPath $exe)) {
        Write-Host "    [ERROR] Not found: $exe" -ForegroundColor Red
        exit 1
    }
    Write-Info "Starting Moodle with '$exe' ..."
    Start-Process -FilePath $exe -WorkingDirectory $MoodleDir | Out-Null

    # Start Moodle.exe = install\install.php + server\xampp_start.exe. When launched from a script its
    # wrapper can exit before reaching xampp_start.exe, so run that step directly if Apache never binds.
    $deadline = (Get-Date).AddSeconds(30)
    while (-not (Test-Port 8081) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 1 }
    if (-not (Test-Port 8081)) {
        $serverDir = Join-Path $MoodleDir "server"
        Write-Info "Apache did not start yet - running server\xampp_start.exe ..."
        Start-Process -FilePath (Join-Path $serverDir "xampp_start.exe") -WorkingDirectory $serverDir -WindowStyle Minimized | Out-Null
    }

    if (-not (Wait-Http $MoodleUrl $MoodleTimeoutSeconds "Moodle")) {
        Write-Host ""
        Write-Host "    [ERROR] Moodle failed to start: http://localhost:8081 did not respond within $MoodleTimeoutSeconds s." -ForegroundColor Red
        Write-Host "      Apache listening on 8081 : $(Test-Port 8081)"
        Write-Host "      MariaDB listening on 3307: $(Test-Port 3307)"
        Write-Host "      Check $MoodleDir\server\apache\logs\error.log and $MoodleDir\server\mysql\data\mysql_error.log"
        Write-Host "      The LMS backend was NOT started (sign-in would only return 503 without Moodle)."
        exit 1
    }
    Write-Ok "Moodle is running."
}

# ------------------------------------------------------------------ 2. LMS backend
Write-Step "LMS backend (http://localhost:8100)"
if (Test-Port 8100) {
    Write-Ok "Something is already listening on port 8100 - not starting another backend."
} else {
    $python = Join-Path $BackendDir ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) { $python = "python" }
    if (-not (Test-Path -LiteralPath (Join-Path $BackendDir ".env"))) {
        Write-Host "    [WARN] backend\.env is missing - copy backend\.env.example and fill it in." -ForegroundColor Yellow
    }
    Start-InNewWindow "My Coach LMS - backend :8100" $BackendDir "& '$python' -m uvicorn lms.main:app --host 0.0.0.0 --port 8100"
    if (-not (Wait-Http $BackendUrl $ServiceTimeoutSeconds "backend")) {
        Write-Host "    [ERROR] The backend did not respond on port 8100. See its PowerShell window." -ForegroundColor Red
        exit 1
    }
    Write-Ok "Backend started (in its own window)."
}
try {
    $health = Invoke-RestMethod -Uri $BackendUrl -TimeoutSec 10
    if ($health.moodle -eq "ok") { Write-Ok "Backend can reach Moodle." }
    else { Write-Host "    [WARN] Backend reports Moodle as '$($health.moodle)'." -ForegroundColor Yellow }
} catch {
    Write-Host "    [WARN] Could not read $BackendUrl" -ForegroundColor Yellow
}

# ------------------------------------------------------------------ 3. Frontend
Write-Step "Frontend (http://localhost:5173)"
if (Test-Port 5173) {
    Write-Ok "Something is already listening on port 5173 - not starting another Vite server."
} else {
    if (-not (Test-Path -LiteralPath (Join-Path $FrontendDir "node_modules"))) {
        Write-Info "Installing frontend dependencies (first run) ..."
        Push-Location $FrontendDir
        try { npm install } finally { Pop-Location }
    }
    Start-InNewWindow "My Coach LMS - frontend :5173" $FrontendDir "npm run dev"
    if (-not (Wait-Http $FrontendUrl $ServiceTimeoutSeconds "frontend")) {
        Write-Host "    [ERROR] The frontend did not respond on port 5173. See its PowerShell window." -ForegroundColor Red
        exit 1
    }
    Write-Ok "Frontend started (in its own window)."
}

# ------------------------------------------------------------------ summary
Write-Host ""
Write-Host "My Coach LMS is running:" -ForegroundColor Green
Write-Host "  LMS (open this)  http://localhost:5173"
Write-Host "  LMS backend      http://localhost:8100/api/health"
Write-Host "  Moodle           http://localhost:8081"
Write-Host ""
Write-Host "To stop: close the backend and frontend windows, then run '$MoodleDir\Stop Moodle.exe'."
