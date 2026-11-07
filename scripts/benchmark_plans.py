"""Offline microbenchmark: sequential vs parallel DAG execution.

This does not measure LLM planning, MCP network overhead or real agent quality.
"""
import json
import statistics
import time

from agent_workflows.planned import execute_plan


def slow(_):
    time.sleep(0.04)
    return {"ok": True}


def measure(parallel, runs=10):
    plan = [{"id": f"step_{i}", "tool": "slow", "args": {}} for i in range(4)]
    return [
        execute_plan(plan, {"slow": slow}, authorize=lambda _: True, parallel=parallel)["duration_ms"]
        for _ in range(runs)
    ]


if __name__ == "__main__":
    sequential = measure(False)
    parallel = measure(True)
    print(json.dumps({
        "experiment": "offline_independent_io_waits",
        "runs_per_mode": len(sequential),
        "sequential": {"median_ms": statistics.median(sequential), "mean_ms": statistics.mean(sequential)},
        "parallel": {"median_ms": statistics.median(parallel), "mean_ms": statistics.mean(parallel)},
        "limitations": "Simulated I/O waits only; no LLM calls, MCP network or accuracy measurement",
    }, indent=2))
