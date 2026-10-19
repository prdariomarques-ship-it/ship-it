set -u
cd "$HOME/darius-p2"
OUT="$HOME/darius-p2/evidence"; rm -rf "$OUT"; mkdir -p "$OUT"
T=$(mktemp -d); export DB_PATH="$T/p2.db"
export BIND_HOST=127.0.0.1 OLLAMA_URL=http://127.0.0.1:9 DARIUS_QUEUE_CONSUMER=off
export DARIUS_API_CLIENTS='{"op":{"token":"p2-operator-token-0123456789","admin":true}}'
res() { echo "$1 | $2 | $3" | tee -a "$OUT/results.txt"; }
cat > q.mjs <<'EOF'
import Database from "better-sqlite3";
const d = new Database(process.argv[2], { readonly: true });
const rows = d.prepare("SELECT idempotencyKey k, status s FROM tasks WHERE idempotencyKey LIKE 'schedule:%' ORDER BY idempotencyKey").all();
const keys = rows.map(r => r.k);
console.log(JSON.stringify({ n: rows.length, distinct: new Set(keys).size, keys }));
EOF
count() { node q.mjs "$DB_PATH"; }
start() { # name port extra-env...
  local name=$1 port=$2; shift 2
  rm -f "$OUT/$name.exit"
  ( env PORT=$port "$@" node --import tsx src/server.ts > "$OUT/$name.log" 2>&1 &
    p=$!; echo $p > "$OUT/$name.pid"; wait $p; echo $? > "$OUT/$name.exit" ) &
  sleep 0.3
}
waitup() { for i in $(seq 1 80); do curl -s -o /dev/null "http://127.0.0.1:$1/api/health" && return 0; grep -q "is running" "$OUT/$2.log" 2>/dev/null && return 0; sleep 0.25; done; return 1; }
term() { # name -> prints "exit=<code> ms=<elapsed>"
  local pid=$(cat "$OUT/$1.pid"); local t0=$(date +%s%3N)
  kill -TERM $pid 2>/dev/null
  for i in $(seq 1 400); do [ -f "$OUT/$1.exit" ] && break; sleep 0.05; done
  echo "exit=$(cat "$OUT/$1.exit" 2>/dev/null || echo TIMEOUT) ms=$(( $(date +%s%3N) - t0 ))"
}
killhard() { local pid=$(cat "$OUT/$1.pid"); kill -9 $pid 2>/dev/null; for i in $(seq 1 100); do [ -f "$OUT/$1.exit" ] && break; sleep 0.05; done; echo "exit=$(cat "$OUT/$1.exit" 2>/dev/null)"; }
# ---- S1 invalid config must refuse to start (exit!=0, never listens)
i=0
for envs in "DARIUS_SCHEDULER=maybe" "DARIUS_SCHEDULER=on DARIUS_SCHEDULES=not-json" \
  'DARIUS_SCHEDULER=on DARIUS_SCHEDULES=[{"id":"x","objective":"o","agentId":"agent-cli-1","intervalMs":10}]' \
  "DARIUS_SCHEDULER_TICK_MS=5" "DARIUS_QUEUE_RETRY_MAX=99"; do
  i=$((i+1)); P=$((4100+i))
  env PORT=$P $envs timeout 20 node --import tsx src/server.ts > "$OUT/s1_$i.log" 2>&1; code=$?
  if [ $code -eq 1 ] && grep -q "REFUSING TO START" "$OUT/s1_$i.log" && ! grep -q "is running" "$OUT/s1_$i.log"; then v=PASS; else v=FAIL; fi
  res "S1.$i invalid config [$envs]" "$v" "exit=$code; $(grep -m1 'REFUSING' "$OUT/s1_$i.log")"
done

# ---- S2 default: scheduler off
start s2 4120 ; waitup 4120 s2 || res S2 FAIL "did not start"
sleep 1.5
curl -s -H "Authorization: Bearer p2-operator-token-0123456789" http://127.0.0.1:4120/api/admin/metrics > "$OUT/s2_metrics.json"
en=$(node -e "const j=JSON.parse(require('fs').readFileSync('$OUT/s2_metrics.json','utf8'));console.log(JSON.stringify(j.scheduler))")
r=$(term s2)
[ "$en" = '{"enabled":false}' ] && v=PASS || v=FAIL
res "S2 default off (scheduler=$en)" "$v" "$r; tasks=$(count)"

# ---- S3 enabled: fires, SIGTERM stops it cleanly
SCH='[{"id":"p2","objective":"p2 probe","agentId":"agent-cli-1","intervalMs":2000}]'
start s3 4130 DARIUS_SCHEDULER=on DARIUS_SCHEDULER_TICK_MS=100 DARIUS_SCHEDULES="$SCH"
waitup 4130 s3 || res S3 FAIL "did not start"
sleep 7
curl -s -H "Authorization: Bearer p2-operator-token-0123456789" http://127.0.0.1:4130/api/admin/metrics > "$OUT/s3_metrics.json"
before=$(count)
r=$(term s3)
sleep 4
after=$(count)
n1=$(node -e "console.log(JSON.parse(process.argv[1]).n)" "$before"); n2=$(node -e "console.log(JSON.parse(process.argv[1]).n)" "$after")
code=$(echo "$r" | sed 's/exit=\([0-9]*\).*/\1/')
{ [ "$code" = 0 ] && [ "$n1" -ge 2 ] && [ "$n1" = "$n2" ]; } && v=PASS || v=FAIL
res "S3 enabled: fires then SIGTERM graceful, nothing fires after exit" "$v" "$r; before=$before after=$after"
grep -c "scheduler: started" "$OUT/s3.log" | xargs -I{} echo "  s3 scheduler started lines: {}" >> "$OUT/results.txt"

# ---- S4 restart on the same DB: no duplicated / burst slots
start s4 4140 DARIUS_SCHEDULER=on DARIUS_SCHEDULER_TICK_MS=100 DARIUS_SCHEDULES="$SCH"
waitup 4140 s4 || res S4 FAIL "did not start"
sleep 1.5
c1=$(count)
sleep 5
r=$(term s4); c2=$(count)
d=$(node -e "const j=JSON.parse(process.argv[1]);console.log(j.n===j.distinct?'unique':'DUPLICATE')" "$c2")
# after >=11s downtime-equivalent, restart must catch up with ONE run, not a burst
first_n=$(node -e "console.log(JSON.parse(process.argv[1]).n)" "$c1"); prev=$n2
burst=$((first_n - prev))
{ [ "$d" = unique ] && [ "$burst" -le 2 ]; } && v=PASS || v=FAIL
res "S4 restart same DB: $d slots; tasks created in first 1.5s after restart=$burst (<=2 means no burst)" "$v" "$r; final=$c2"

# ---- S5 two live processes, one DB: each slot exactly once
rm -f "$DB_PATH"*
start a 4151 DARIUS_SCHEDULER=on DARIUS_SCHEDULER_TICK_MS=50 DARIUS_SCHEDULES="$SCH"
start b 4152 DARIUS_SCHEDULER=on DARIUS_SCHEDULER_TICK_MS=50 DARIUS_SCHEDULES="$SCH"
waitup 4151 a; waitup 4152 b
sleep 9
curl -s -H "Authorization: Bearer p2-operator-token-0123456789" http://127.0.0.1:4151/api/admin/metrics > "$OUT/s5_a_metrics.json"
curl -s -H "Authorization: Bearer p2-operator-token-0123456789" http://127.0.0.1:4152/api/admin/metrics > "$OUT/s5_b_metrics.json"
ra=$(term a); rb=$(term b)
c=$(count)
d=$(node -e "const j=JSON.parse(process.argv[1]);console.log(j.n===j.distinct&&j.n>=3?'exactly-once('+j.n+' slots)':'BAD')" "$c")
node -e "for (const p of ['a','b']){const j=JSON.parse(require('fs').readFileSync('$OUT/s5_'+p+'_metrics.json','utf8'));console.log('  '+p+' scheduler stats:',JSON.stringify(j.scheduler))}" >> "$OUT/results.txt"
case "$d" in exactly*) v=PASS;; *) v=FAIL;; esac
res "S5 two processes, one DB, 50ms ticks: $d" "$v" "a:$ra b:$rb"

# ---- S6 SIGKILL then restart: durable, no duplicate
start k 4160 DARIUS_SCHEDULER=on DARIUS_SCHEDULER_TICK_MS=100 DARIUS_SCHEDULES="$SCH"
waitup 4160 k; sleep 3
killhard k > "$OUT/k_kill.txt"
c1=$(count); sleep 5
start k2 4161 DARIUS_SCHEDULER=on DARIUS_SCHEDULER_TICK_MS=100 DARIUS_SCHEDULES="$SCH"
waitup 4161 k2; sleep 4
r=$(term k2); c2=$(count)
d=$(node -e "const j=JSON.parse(process.argv[1]);console.log(j.n===j.distinct?'unique':'DUPLICATE')" "$c2")
[ "$d" = unique ] && v=PASS || v=FAIL
res "S6 kill -9 + restart: slots $d" "$v" "$r; before=$c1 after=$c2"
echo DONE >> "$OUT/results.txt"
