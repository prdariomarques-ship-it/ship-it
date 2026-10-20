# Timezone check of the panel API against a THROWAWAY PostgreSQL (container c6-pg-tz, port 15432).
param([ValidateSet("backend", "probe")] [string]$Step = "probe")
$ErrorActionPreference = "Stop"
$ship = "C:\Users\dario\FlowCore\ship-it"
$py = "C:\Users\dario\.venvs\shipit\Scripts\python.exe"
$svc = "e2e-service-token-0123456789"; $op = "e2e-operator-token-0123456789"
if ($Step -eq "backend") {
    Set-Location "C:\Users\dario\.venvs\e2e\run_pg"
    $env:PYTHONPATH = "$ship\backend"
    $env:DATABASE_URL = "postgresql+asyncpg://postgres:c6tmp@127.0.0.1:15432/c6"
    $env:ENVIRONMENT = "development"; $env:JWT_SECRET = "e2e-jwt-secret-0123456789-0123456789-xx"
    $env:WEBHOOK_SECRET = "e2e-webhook-secret-0123456789-0123456789"
    $env:JOBS_ENABLED = "false"; $env:OBSERVATION_ENABLED = "false"
    $env:DARIUS_BASE_URL = "http://127.0.0.1:18100"; $env:DARIUS_API_TOKEN = $svc; $env:DARIUS_OPERATOR_TOKEN = $op
    $env:DARIUS_WHATSAPP_ENABLED = "true"; $env:DARIUS_WHATSAPP_INSTANCES = "store"
    $env:EVOLUTION_BASE_URL = "http://127.0.0.1:9"; $env:EVOLUTION_INSTANCE = "store"; $env:EVOLUTION_PERSONAL_INSTANCE = "personal"
    & $py -m uvicorn main:app --host 127.0.0.1 --port 18001
    exit
}
$B = "http://127.0.0.1:18001/api"
$login = Invoke-RestMethod -Method Post -Uri "$B/auth/login" -ContentType "application/json" -Body (@{ email = "admin@example.com"; password = "e2e-admin-pass-1" } | ConvertTo-Json)
$tok = if ($login.access_token) { $login.access_token } else { $login.token }
$H = @{ Authorization = "Bearer $tok" }
Invoke-RestMethod -Method Put -Uri "$B/admin/automation/suspension/instances/store" -Headers $H -ContentType "application/json" -Body (@{ suspended = $true; reason = "teste pg" } | ConvertTo-Json) -ErrorAction SilentlyContinue | Out-Null
foreach ($e in "automation/suspension", "darius/whatsapp-tasks?limit=2", "darius/paused-conversations", "logs?limit=2") {
    $raw = (Invoke-WebRequest -UseBasicParsing -Headers $H -Uri "$B/admin/$e").Content
    $naive = [regex]::Matches($raw, '"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?"') | ForEach-Object { $_.Value } | Select-Object -First 2
    $aware = [regex]::Matches($raw, '\d{4}-\d{2}-\d{2}T[\d:.]+(Z|[+-]\d{2}:\d{2})"') | ForEach-Object { $_.Value } | Select-Object -First 2
    "{0,-34} naive=[{1}] aware=[{2}]" -f $e, ($naive -join ","), ($aware -join ",")
}
