# Isolated stack for validating /admin/darius. Ports: backend 18000, DARIUS 18100, Next 13100.
# NEVER uses localhost:3000 (its Caddy forwards /api to production) and never reads a real .env:
# every process runs from a throw-away cwd and gets an explicit environment.
param([ValidateSet("prepare", "darius", "backend", "frontend", "stop-darius")] [string]$Step = "prepare")
$ErrorActionPreference = "Stop"
$root = "C:\Users\dario\.venvs\e2e"
$run = Join-Path $root "run"
$dariusRepo = "C:\Users\dario\Downloads\darius-rc2-prepush-gate"
$ship = "C:\Users\dario\FlowCore\ship-it"
$py = "C:\Users\dario\.venvs\shipit\Scripts\python.exe"
$svc = "e2e-service-token-0123456789"
$op = "e2e-operator-token-0123456789"
$tsx = Join-Path $dariusRepo "node_modules\tsx\dist\cli.mjs"

function Test-Port([int]$p) { try { (New-Object Net.Sockets.TcpClient("127.0.0.1", $p)).Close(); $true } catch { $false } }

if ($Step -eq "prepare") {
    foreach ($p in 18000, 18100, 13100) { if (Test-Port $p) { throw "port $p already in use" } }
    if (Test-Path $run) { Remove-Item -Recurse -Force $run }
    New-Item -ItemType Directory -Force -Path $run | Out-Null
    Push-Location $dariusRepo
    & node $tsx (Join-Path $root "seed_darius.mts") (Join-Path $run "darius.db")
    Pop-Location
    Push-Location $run
    $env:DATABASE_URL = "sqlite+aiosqlite:///" + ((Join-Path $run "darioos.db") -replace "\\", "/")
    $env:ENVIRONMENT = "development"; $env:JWT_SECRET = "e2e-jwt-secret-0123456789-0123456789-xx"
    & $py (Join-Path $root "seed_darioos.py")
    Pop-Location
}
elseif ($Step -eq "darius") {
    Set-Location $dariusRepo
    $env:PORT = "18100"; $env:BIND_HOST = "127.0.0.1"; $env:DB_PATH = (Join-Path $run "darius.db")
    $env:OLLAMA_URL = "http://127.0.0.1:9"; $env:DARIUS_QUEUE_CONSUMER = "off"
    $env:DARIUS_API_CLIENTS = (@{ svc = $svc; operator = @{ token = $op; admin = $true } } | ConvertTo-Json -Compress)
    $env:CORS_ORIGIN = "http://127.0.0.1:13100"
    & node $tsx src/server.ts
}
elseif ($Step -eq "backend") {
    Set-Location $run   # no .env here: nothing is read from the real project
    $env:PYTHONPATH = "$ship\backend"
    $env:DATABASE_URL = "sqlite+aiosqlite:///" + ((Join-Path $run "darioos.db") -replace "\\", "/")
    $env:ENVIRONMENT = "development"; $env:JWT_SECRET = "e2e-jwt-secret-0123456789-0123456789-xx"
    $env:WEBHOOK_SECRET = "e2e-webhook-secret-0123456789-0123456789"
    $env:JOBS_ENABLED = "false"; $env:OBSERVATION_ENABLED = "false"
    $env:CORS_ORIGINS = "http://127.0.0.1:13100,http://localhost:13100"
    $env:DARIUS_BASE_URL = "http://127.0.0.1:18100"; $env:DARIUS_API_TOKEN = $svc; $env:DARIUS_OPERATOR_TOKEN = $op
    $env:DARIUS_REQUEST_MAX_ATTEMPTS = "2"; $env:DARIUS_REQUEST_TIMEOUT_SECONDS = "3"
    $env:DARIUS_WHATSAPP_ENABLED = "true"; $env:DARIUS_WHATSAPP_INSTANCES = "store"
    $env:EVOLUTION_BASE_URL = "http://127.0.0.1:9"; $env:EVOLUTION_INSTANCE = "store"; $env:EVOLUTION_PERSONAL_INSTANCE = "personal"
    & $py -m uvicorn main:app --host 127.0.0.1 --port 18000
}
elseif ($Step -eq "frontend") {
    Set-Location "$ship\frontend"
    $env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:18000/api"
    & npx next dev -p 13100 -H 127.0.0.1
}
elseif ($Step -eq "stop-darius") {
    Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "tsx" -and $_.CommandLine -match "src/server.ts" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force; "stopped DARIUS pid $($_.ProcessId)" }
}
