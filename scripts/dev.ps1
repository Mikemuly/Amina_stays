# One command for local development on Windows: Django API + scheduler + Next.js (the Windows twin of dev.sh).
#
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1           # start everything
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Reseed   # also reset the demo data
#
# The first run installs the dependencies, migrates and seeds the demo. PostgreSQL comes from DATABASE_URL if it
# is set, else localhost:5432 (create the amina user and database as the README shows); when nothing listens there
# and Docker is installed, the database is started with docker compose. Stop with Ctrl+C.
# Runs in Windows PowerShell 5.1 and PowerShell 7, so keep it ASCII-only and free of PowerShell 7-only syntax.
param([switch]$Reseed)

$Root = Split-Path -Parent $PSScriptRoot
$OnWindows = $env:OS -eq "Windows_NT"
if (-not $env:DEBUG) { $env:DEBUG = "1" }
if (-not $env:DEMO) { $env:DEMO = "1" }

function Say([string]$Text) { Write-Host "> $Text" -ForegroundColor Magenta }

function Fail([string]$Text) {
    Write-Host $Text -ForegroundColor Red
    exit 1
}

# Runs native commands in a project folder and stops the script if one fails.
function Invoke-In([string]$Dir, [scriptblock]$Command) {
    Push-Location (Join-Path $Root $Dir)
    try {
        & $Command
        if ($LASTEXITCODE) { Fail "Failed in ${Dir} (exit code $LASTEXITCODE)." }
    } finally {
        Pop-Location
    }
}

function Find-Tool([string]$Name) {
    $cmd = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd) { return $cmd.Path }
    return $null
}

function Test-Port([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $client.Connect("127.0.0.1", $Port)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

# 0. Tools
$Uv = Find-Tool "uv"
if (-not $Uv) {
    # the uv installer's default folder, in case this terminal was opened before uv was installed
    $Uv = @("uv.exe", "uv") | ForEach-Object { Join-Path $HOME ".local/bin/$_" } | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $Uv) { Fail "uv not found. Install it (see the README), then open a new terminal." }
$Node = Find-Tool "node"
if (-not $Node) { Fail "Node.js not found. Install it (see the README), then open a new terminal." }
$Npm = if ($OnWindows) { "npm.cmd" } else { "npm" }  # npm.cmd still works where PowerShell scripts are blocked
$Compose = Join-Path $Root "docker-compose.yml"

# 1. Database
if ($env:DATABASE_URL) {
    Say "Using DATABASE_URL"
} elseif (Test-Port 5432) {
    Say "PostgreSQL is up on localhost:5432"
} elseif (Find-Tool "docker") {
    Say "Starting PostgreSQL in Docker"
    docker compose -f $Compose up -d db
    if ($LASTEXITCODE) { Fail "docker compose couldn't start the database. Is Docker Desktop running?" }
    $tries = 0
    do {
        Start-Sleep -Seconds 1
        $tries++
        docker compose -f $Compose exec -T db pg_isready -U amina *> $null
    } until ($LASTEXITCODE -eq 0 -or $tries -ge 60)
    if ($LASTEXITCODE) { Fail "The database container didn't become ready." }
} else {
    Fail "PostgreSQL isn't running on localhost:5432. Install it and create the amina database (see the README), or install Docker Desktop."
}

# 2. Backend
Say "Backend dependencies"
Invoke-In "backend" { & $Uv sync -q }
Say "Migrations"
Invoke-In "backend" { & $Uv run python manage.py migrate --noinput -v 0 }
Push-Location (Join-Path $Root "backend")
& $Uv run python manage.py shell -c "from apps.properties.models import Unit; import sys; sys.exit(0 if Unit.objects.exists() else 1)" *> $null
$HasData = $LASTEXITCODE -eq 0
Pop-Location
if ($Reseed -or -not $HasData) {
    Say "Seeding demo data"
    Invoke-In "backend" { & $Uv run python manage.py seed_demo --reset }
}

# 3. Frontend
if (-not (Test-Path (Join-Path $Root "frontend/node_modules"))) {
    Say "Frontend dependencies"
    Invoke-In "frontend" { & $Npm install --no-audit --no-fund }
}

# 4. Run: the API and the scheduler in the background, Next.js in front; Ctrl+C stops all three.
$Backend = Join-Path $Root "backend"
$Phone = if ($env:AMINA_PHONE) { $env:AMINA_PHONE } else { "+254700000001" }
$Children = @()
Push-Location (Join-Path $Root "frontend")
try {
    $Children += Start-Process -FilePath $Uv -ArgumentList "run python manage.py runserver 127.0.0.1:8000" -WorkingDirectory $Backend -NoNewWindow -PassThru
    $Children += Start-Process -FilePath $Uv -ArgumentList "run python manage.py run_scheduler" -WorkingDirectory $Backend -NoNewWindow -PassThru
    Say "Guest site  http://localhost:3000"
    Say "Demo Lab    http://localhost:3000/demo"
    Say "Host        http://localhost:3000/host   (log in as $Phone; the code is shown on screen in DEMO mode)"
    Say "API docs    http://localhost:8000/api/docs"
    Say "Press Ctrl+C to stop."
    # node directly rather than next.cmd, so Ctrl+C doesn't stop at cmd's "Terminate batch job (Y/N)?"
    & $Node "node_modules/next/dist/bin/next" dev --port 3000
} finally {
    Pop-Location
    foreach ($p in $Children) {
        if ($p -and -not $p.HasExited) {
            if ($OnWindows) {
                taskkill /PID $p.Id /T /F *> $null  # the whole tree: uv, Python and the runserver reloader
            } else {
                & "/bin/kill" -TERM $p.Id  # uv passes it on to Python
            }
        }
    }
}
