# Stop / start the ISOLATED e2e stack by exact port. Usage: stack.ps1 -Action stop|fresh|darius-stop|darius-start
param([ValidateSet("stop", "fresh", "darius-stop", "darius-start")] [string]$Action)
$s = 'C:\Users\dario\.venvs\e2e\start_e2e.ps1'; $L = 'C:\Users\dario\.venvs\e2e\logs'
New-Item -ItemType Directory -Force $L | Out-Null
function Stop-Port([int]$p) {
    Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
        $pr = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
        if ($pr) { "stop :$p pid $($pr.Id) $($pr.ProcessName)"; Stop-Process -Id $pr.Id -Force }
    }
}
function Start-Step([string]$st) {
    Start-Process powershell -ArgumentList '-NoProfile', '-File', $s, '-Step', $st -WindowStyle Hidden -RedirectStandardOutput "$L\$st.out.txt" -RedirectStandardError "$L\$st.err.txt"
}
if ($Action -eq "stop" -or $Action -eq "fresh") { foreach ($p in 13100, 18000, 18100) { Stop-Port $p }; Start-Sleep 3 }
if ($Action -eq "fresh") {
    & powershell -NoProfile -File $s -Step prepare 2>&1 | Select-Object -Last 3
    & 'C:\Users\dario\.venvs\shipit\Scripts\python.exe' -I 'C:\Users\dario\.venvs\e2e\fix_emails.py'
    foreach ($st in 'darius', 'backend', 'frontend') { Start-Step $st }
    $deadline = (Get-Date).AddSeconds(120)
    do { Start-Sleep 3; $up = @(18100, 18000, 13100 | Where-Object { Get-NetTCPConnection -LocalPort $_ -State Listen -ErrorAction SilentlyContinue }).Count } while ($up -lt 3 -and (Get-Date) -lt $deadline)
    "listening=$up/3"
}
if ($Action -eq "darius-stop") { Stop-Port 18100 }
if ($Action -eq "darius-start") { Start-Step 'darius'; Start-Sleep 12; "18100 up=" + [bool](Get-NetTCPConnection -LocalPort 18100 -State Listen -ErrorAction SilentlyContinue) }
