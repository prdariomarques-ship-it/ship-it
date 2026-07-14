#!/bin/bash

# DRT-001 Performance Benchmarks
# Measures startup time, execution latency, recovery time, memory usage

set -e

echo ""
echo "============================================"
echo "DRT-001 PERFORMANCE BENCHMARKS"
echo "============================================"
echo ""

BENCH_DIR=".runtime_benchmarks"
rm -rf "$BENCH_DIR"
mkdir -p "$BENCH_DIR"

# Benchmark 1: Workflow Execution Latency
echo "=== Benchmark 1: Workflow Execution Latency ==="
echo "Measuring time to execute 10 workflows..."
echo ""

python3 << 'PYTHON'
import sys
import time
sys.path.insert(0, 'src')
from workflow_engine import WorkflowEngine
from persistence import FilePersistence

persistence = FilePersistence('.runtime_benchmarks')
engine = WorkflowEngine(persistence)

workflow = {
    'name': 'bench-wf',
    'workflow_version': '1.0',
    'runtime_version': '1.0',
    'steps': [
        {'name': 'step-1', 'type': 'system'},
        {'name': 'step-2', 'type': 'system'},
        {'name': 'step-3', 'type': 'system'},
    ]
}

times = []
for i in range(10):
    start = time.time()
    execution = engine.execute_workflow(workflow)
    elapsed = (time.time() - start) * 1000  # ms
    times.append(elapsed)
    print(f"  Run {i+1}: {elapsed:.1f}ms")

avg = sum(times) / len(times)
min_t = min(times)
max_t = max(times)

print(f"\n✓ Execution Latency")
print(f"  Average: {avg:.1f}ms")
print(f"  Min: {min_t:.1f}ms")
print(f"  Max: {max_t:.1f}ms")
PYTHON

echo ""

# Benchmark 2: Recovery Time
echo "=== Benchmark 2: Recovery Time ==="
echo "Measuring time to recover 10 executions..."
echo ""

python3 << 'PYTHON'
import sys
import time
sys.path.insert(0, 'src')
from workflow_engine import WorkflowEngine
from persistence import FilePersistence

persistence = FilePersistence('.runtime_benchmarks')
engine = WorkflowEngine(persistence)

# Create executions
workflow = {
    'name': 'recovery-bench',
    'workflow_version': '1.0',
    'runtime_version': '1.0',
    'steps': [{'name': 'step-1', 'type': 'system'}]
}

exec_ids = []
for i in range(10):
    execution = engine.execute_workflow(workflow)
    exec_ids.append(execution.execution_id)

# Measure recovery
times = []
for exec_id in exec_ids:
    start = time.time()
    recovered = engine.recover_execution(exec_id)
    elapsed = (time.time() - start) * 1000  # ms
    times.append(elapsed)
    print(f"  Recovery: {elapsed:.2f}ms - {exec_id[:8]}...")

avg = sum(times) / len(times)
min_t = min(times)
max_t = max(times)

print(f"\n✓ Recovery Time")
print(f"  Average: {avg:.2f}ms")
print(f"  Min: {min_t:.2f}ms")
print(f"  Max: {max_t:.2f}ms")
PYTHON

echo ""

# Benchmark 3: Dry Run Time
echo "=== Benchmark 3: Dry Run Time (Parse/Validate/Compile) ==="
echo "Measuring time to dry-run 10 workflows..."
echo ""

python3 << 'PYTHON'
import sys
import time
sys.path.insert(0, 'src')
from workflow_engine import WorkflowEngine
from persistence import FilePersistence

persistence = FilePersistence('.runtime_benchmarks')
engine = WorkflowEngine(persistence)

workflow = {
    'name': 'dryrun-bench',
    'workflow_version': '1.0',
    'runtime_version': '1.0',
    'steps': [
        {'name': 'step-1', 'type': 'system'},
        {'name': 'step-2', 'type': 'system'},
        {'name': 'step-3', 'type': 'system'},
    ]
}

times = []
for i in range(10):
    start = time.time()
    result = engine.dry_run(workflow)
    elapsed = (time.time() - start) * 1000  # ms
    times.append(elapsed)
    print(f"  Run {i+1}: {elapsed:.2f}ms")

avg = sum(times) / len(times)
min_t = min(times)
max_t = max(times)

print(f"\n✓ Dry Run Time")
print(f"  Average: {avg:.2f}ms")
print(f"  Min: {min_t:.2f}ms")
print(f"  Max: {max_t:.2f}ms")
PYTHON

echo ""

# Benchmark 4: Idempotency Lookup Time
echo "=== Benchmark 4: Idempotency Lookup Time ==="
echo "Measuring time to check and retrieve same correlation_id..."
echo ""

python3 << 'PYTHON'
import sys
import time
sys.path.insert(0, 'src')
from workflow_engine import WorkflowEngine
from persistence import FilePersistence

persistence = FilePersistence('.runtime_benchmarks')
engine = WorkflowEngine(persistence)

workflow = {
    'name': 'idempotent-bench',
    'workflow_version': '1.0',
    'runtime_version': '1.0',
    'steps': [{'name': 'step-1', 'type': 'system'}]
}

# First execution with correlation ID
correlation_id = "bench-idempotent-123"
execution = engine.execute_workflow(workflow, correlation_id=correlation_id)
print(f"  First execution: {execution.execution_id[:8]}...")

# Measure subsequent lookups
times = []
for i in range(10):
    start = time.time()
    result = engine.execute_workflow(workflow, correlation_id=correlation_id)
    elapsed = (time.time() - start) * 1000  # ms
    times.append(elapsed)
    assert result.execution_id == execution.execution_id
    print(f"  Lookup {i+1}: {elapsed:.2f}ms (returned cached)")

avg = sum(times) / len(times)
min_t = min(times)
max_t = max(times)

print(f"\n✓ Idempotency Lookup Time")
print(f"  Average: {avg:.2f}ms")
print(f"  Min: {min_t:.2f}ms")
print(f"  Max: {max_t:.2f}ms")
PYTHON

echo ""

# Benchmark 5: Concurrent Executions
echo "=== Benchmark 5: Concurrent Execution Handling ==="
echo "Measuring simultaneous workflow execution (5 parallel)..."
echo ""

python3 << 'PYTHON'
import sys
import time
import threading
sys.path.insert(0, 'src')
from workflow_engine import WorkflowEngine
from persistence import FilePersistence

persistence = FilePersistence('.runtime_benchmarks')
engine = WorkflowEngine(persistence)

workflow = {
    'name': 'concurrent-bench',
    'workflow_version': '1.0',
    'runtime_version': '1.0',
    'steps': [{'name': 'step-1', 'type': 'system'}]
}

results = []
lock = threading.Lock()

def execute_workflow():
    start = time.time()
    execution = engine.execute_workflow(workflow)
    elapsed = (time.time() - start) * 1000
    with lock:
        results.append((elapsed, execution.execution_id))

threads = []
concurrent_start = time.time()
for i in range(5):
    t = threading.Thread(target=execute_workflow)
    threads.append(t)
    t.start()

for t in threads:
    t.join()

total_time = (time.time() - concurrent_start) * 1000

for i, (elapsed, exec_id) in enumerate(sorted(results)):
    print(f"  Thread {i+1}: {elapsed:.1f}ms - {exec_id[:8]}...")

print(f"\n✓ Concurrent Execution")
print(f"  Total time: {total_time:.1f}ms (5 parallel)")
print(f"  Avg per execution: {sum(e[0] for e in results)/len(results):.1f}ms")
PYTHON

echo ""

echo "============================================"
echo "PERFORMANCE BENCHMARKS COMPLETE"
echo "============================================"
echo ""
echo "Summary:"
echo "  ✓ Workflow execution latency measured"
echo "  ✓ Recovery time measured"
echo "  ✓ Dry-run (parse/validate/compile) measured"
echo "  ✓ Idempotency lookup performance measured"
echo "  ✓ Concurrent execution measured"
echo ""

# Cleanup
rm -rf "$BENCH_DIR"

