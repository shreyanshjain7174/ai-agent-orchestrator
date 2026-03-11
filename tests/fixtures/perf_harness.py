from __future__ import annotations

import asyncio
import gc
import importlib
import math
import statistics
import sys
import time
import tracemalloc
import types
from contextlib import contextmanager
from typing import Any

from tests.fakes import FakeLLMClient


def _install_mcp_server_stubs() -> None:
    """Install lightweight deterministic stubs so mcp_server imports offline."""
    agent_framework = types.ModuleType("agent_framework")

    class ChatMessage:
        def __init__(self, role: str, text: str = ""):
            self.role = role
            self.text = text

    class AgentExecutorRequest:
        def __init__(self, messages, should_respond: bool = True):
            self.messages = messages
            self.should_respond = should_respond

    class WorkflowOutputEvent:
        def __init__(self, data):
            self.data = data

    class WorkflowStatusEvent:
        def __init__(self, state):
            self.state = state

    agent_framework.ChatMessage = ChatMessage
    agent_framework.AgentExecutorRequest = AgentExecutorRequest
    agent_framework.WorkflowOutputEvent = WorkflowOutputEvent
    agent_framework.WorkflowStatusEvent = WorkflowStatusEvent
    sys.modules["agent_framework"] = agent_framework

    mcp_module = types.ModuleType("mcp")
    mcp_server_module = types.ModuleType("mcp.server")
    fastmcp_module = types.ModuleType("mcp.server.fastmcp")

    class FastMCP:
        def __init__(self, _name: str):
            self.name = _name

        def tool(self):
            def _decorator(fn):
                return fn

            return _decorator

        def run(self, transport: str = "stdio") -> None:
            _ = transport

    fastmcp_module.FastMCP = FastMCP
    sys.modules["mcp"] = mcp_module
    sys.modules["mcp.server"] = mcp_server_module
    sys.modules["mcp.server.fastmcp"] = fastmcp_module

    orchestrator = types.ModuleType("orchestrator")
    orchestrator.DEFAULT_ARCHITECT_MODEL = "architect-model"
    orchestrator.DEFAULT_DEVELOPER_MODEL = "developer-model"
    orchestrator.DEFAULT_QA_MODEL = "qa-model"

    fake_llm = FakeLLMClient()

    def _make_fake_executor(default_name: str):
        class _FakeExecutor:
            def __init__(self, *_args, **_kwargs):
                agent_id = str(_kwargs.get("id", default_name))
                self.agent = fake_llm.create_agent(
                    name=agent_id,
                    instructions=f"Stub instructions for {default_name}",
                )

        return _FakeExecutor

    def _create_orchestrator_workflow():
        class _Workflow:
            async def run_stream(self, _messages):
                yield WorkflowOutputEvent("legacy-output")
                yield WorkflowStatusEvent("legacy-complete")

        return _Workflow()

    orchestrator.DeveloperAgent = _make_fake_executor("DeveloperAgent")
    orchestrator.PrincipalArchitect = _make_fake_executor("PrincipalArchitect")
    orchestrator.QualityAssuranceAgent = _make_fake_executor("QualityAssuranceAgent")
    orchestrator.create_ai_client = lambda *_args, **_kwargs: object()
    orchestrator.create_orchestrator_workflow = _create_orchestrator_workflow
    orchestrator.get_base_deployment_name = lambda: "base-model"
    orchestrator.get_credential_for_endpoint = lambda _endpoint: None
    orchestrator.get_project_endpoint = lambda: "https://example.test"
    orchestrator.resolve_deployment_name = lambda _name, default, _base: default
    orchestrator.fake_llm = fake_llm
    sys.modules["orchestrator"] = orchestrator

    autonomous = types.ModuleType("autonomous_orchestrator")
    autonomous.DEFAULT_PLANNER_MODEL = "planner-model"
    autonomous.DEFAULT_EVALUATOR_MODEL = "evaluator-model"
    autonomous.DEFAULT_RESEARCHER_MODEL = "researcher-model"
    autonomous.DEFAULT_VERIFIER_MODEL = "verifier-model"

    class _MemorySystem:
        def __init__(self):
            self.memories = []

    def _create_autonomous_workflow(execution_order=None):
        _ = execution_order

        class _Workflow:
            async def run_stream(self, _messages):
                yield WorkflowOutputEvent("▶ Phase: PLAN")
                yield WorkflowStatusEvent("COMPLETE")

        return _Workflow()

    autonomous.MemorySystem = _MemorySystem
    autonomous.create_autonomous_workflow = _create_autonomous_workflow
    sys.modules["autonomous_orchestrator"] = autonomous


def load_mcp_server_module():
    """Load mcp_server after deterministic stubs are registered."""
    _install_mcp_server_stubs()
    sys.modules.pop("mcp_server", None)
    return importlib.import_module("mcp_server")


def _nearest_rank_percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[rank]


def summarize_latency_ms(samples_ms: list[float]) -> dict[str, float]:
    if not samples_ms:
        return {"mean": 0.0, "median": 0.0, "p95": 0.0, "max": 0.0}

    return {
        "mean": round(statistics.fmean(samples_ms), 4),
        "median": round(statistics.median(samples_ms), 4),
        "p95": round(_nearest_rank_percentile(samples_ms, 0.95), 4),
        "max": round(max(samples_ms), 4),
    }


def profile_execution_modes(
    mcp_server: Any,
    *,
    iterations: int,
    mode: str = "implement",
    max_loops: int = 1,
    execution_modes: tuple[str, ...] = ("legacy", "dynamic", "auto"),
    task: str = "Implement endpoint with tests",
) -> dict[str, dict[str, Any]]:
    """Profile single-request latencies and control-path metrics by execution_mode."""
    results: dict[str, dict[str, Any]] = {}

    for execution_mode in execution_modes:
        latency_samples: list[float] = []
        loops_executed_samples: list[int] = []
        fallback_samples: list[int] = []
        order_validity_samples: list[float] = []

        for _ in range(iterations):
            started = time.perf_counter()
            response = asyncio.run(
                mcp_server.autonomous_execute(
                    task,
                    mode=mode,
                    execution_mode=execution_mode,
                    max_loops=max_loops,
                    enable_legacy_fallback=True,
                )
            )
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            latency_samples.append(elapsed_ms)

            loops_executed_samples.append(int(response.get("loops_executed", 0)))
            fallback_samples.append(1 if response.get("fallback", {}).get("triggered", False) else 0)

            telemetry = response.get("telemetry", {})
            ratio = telemetry.get("execution_order_valid_ratio")
            if isinstance(ratio, (int, float)):
                order_validity_samples.append(float(ratio))

        execution_order_valid_ratio: float | None
        if execution_mode == "legacy":
            execution_order_valid_ratio = None
        elif order_validity_samples:
            execution_order_valid_ratio = round(statistics.fmean(order_validity_samples), 4)
        else:
            execution_order_valid_ratio = None

        results[execution_mode] = {
            "iterations": iterations,
            "latency_ms": summarize_latency_ms(latency_samples),
            "loops_executed": {
                "mean": round(statistics.fmean(loops_executed_samples), 4),
                "min": min(loops_executed_samples),
                "max": max(loops_executed_samples),
            },
            "fallback_rate": round(sum(fallback_samples) / max(1, iterations), 4),
            "execution_order_valid_ratio": execution_order_valid_ratio,
        }

    return results


async def _run_parallel_batch(
    mcp_server: Any,
    *,
    execution_mode: str,
    parallelism: int,
    mode: str,
    max_loops: int,
    task: str,
) -> dict[str, Any]:
    latencies_ms: list[float] = []
    responses: list[dict[str, Any]] = []

    async def _invoke(index: int) -> None:
        started = time.perf_counter()
        response = await mcp_server.autonomous_execute(
            f"{task} [req-{index}]",
            mode=mode,
            execution_mode=execution_mode,
            max_loops=max_loops,
            enable_legacy_fallback=True,
        )
        latencies_ms.append((time.perf_counter() - started) * 1000.0)
        responses.append(response)

    started = time.perf_counter()
    await asyncio.gather(*(_invoke(i) for i in range(parallelism)))
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return {
        "elapsed_ms": elapsed_ms,
        "latencies_ms": latencies_ms,
        "responses": responses,
    }


def profile_concurrent_load(
    mcp_server: Any,
    *,
    mode: str = "implement",
    max_loops: int = 1,
    execution_modes: tuple[str, ...] = ("legacy", "dynamic", "auto"),
    parallelism_values: tuple[int, ...] = (2, 4),
    batches: int = 2,
    task: str = "Implement endpoint with tests",
) -> dict[str, Any]:
    """Profile deterministic concurrent autonomous_execute load scenarios."""
    scenarios: list[dict[str, Any]] = []

    for execution_mode in execution_modes:
        for parallelism in parallelism_values:
            all_latencies_ms: list[float] = []
            total_elapsed_ms = 0.0
            total_requests = 0
            total_fallbacks = 0

            for _ in range(batches):
                batch = asyncio.run(
                    _run_parallel_batch(
                        mcp_server,
                        execution_mode=execution_mode,
                        parallelism=parallelism,
                        mode=mode,
                        max_loops=max_loops,
                        task=task,
                    )
                )
                total_elapsed_ms += float(batch["elapsed_ms"])
                all_latencies_ms.extend(batch["latencies_ms"])

                responses = batch["responses"]
                total_requests += len(responses)
                total_fallbacks += sum(
                    1 for response in responses if response.get("fallback", {}).get("triggered", False)
                )

            elapsed_seconds = max(total_elapsed_ms / 1000.0, 0.000001)
            throughput_rps = round(total_requests / elapsed_seconds, 4)
            scenario_key = f"{execution_mode}:p{parallelism}"

            scenarios.append(
                {
                    "key": scenario_key,
                    "execution_mode": execution_mode,
                    "parallelism": parallelism,
                    "batches": batches,
                    "requests": total_requests,
                    "throughput_rps": throughput_rps,
                    "latency_ms": summarize_latency_ms(all_latencies_ms),
                    "fallback_rate": round(total_fallbacks / max(1, total_requests), 4),
                }
            )

    return {
        "scenarios": scenarios,
        "parallelism_values": list(parallelism_values),
        "batches": batches,
    }


def _build_task_by_complexity(repeat: int) -> str:
    return " ".join(["Implement deterministic endpoint with tests."] * max(1, repeat))


@contextmanager
def _force_incomplete_loops(mcp_server: Any):
    """Force loop completion=False so memory scenarios can exercise max_loops deterministically."""
    original = mcp_server._collect_autonomous_run

    async def _incomplete_run(task_prompt: str, execution_order=None) -> dict[str, Any]:
        _ = execution_order
        return {
            "phases_executed": ["PLAN", "EXECUTE", "VERIFY"],
            "final_status": "INCOMPLETE",
            "iteration_count": 1,
            "outputs": [f"forced-loop:{len(task_prompt)}"],
            "success_indicators": {"completed": False, "verified": False},
        }

    mcp_server._collect_autonomous_run = _incomplete_run
    try:
        yield
    finally:
        mcp_server._collect_autonomous_run = original


def profile_memory_trends(
    mcp_server: Any,
    *,
    repeats: int = 2,
    scenarios: tuple[dict[str, Any], ...] = (
        {"name": "small_l1", "loop_count": 1, "task_repeat": 1},
        {"name": "medium_l1", "loop_count": 1, "task_repeat": 8},
        {"name": "medium_l3", "loop_count": 3, "task_repeat": 8},
        {"name": "large_l5", "loop_count": 5, "task_repeat": 16},
    ),
) -> dict[str, Any]:
    """Profile memory trends over loop_count and task complexity via tracemalloc."""
    measured: list[dict[str, Any]] = []

    for scenario in scenarios:
        peaks: list[float] = []
        currents: list[float] = []
        executed_loops: list[int] = []

        for _ in range(repeats):
            gc.collect()
            tracemalloc.start()

            with _force_incomplete_loops(mcp_server):
                response = asyncio.run(
                    mcp_server.autonomous_execute(
                        _build_task_by_complexity(int(scenario["task_repeat"])),
                        mode="implement",
                        execution_mode="dynamic",
                        max_loops=int(scenario["loop_count"]),
                        enable_legacy_fallback=False,
                    )
                )

            current_bytes, peak_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            peaks.append(float(peak_bytes) / 1024.0)
            currents.append(float(current_bytes) / 1024.0)
            executed_loops.append(int(response.get("loops_executed", 0)))

        measured.append(
            {
                "name": str(scenario["name"]),
                "loop_count": int(scenario["loop_count"]),
                "task_repeat": int(scenario["task_repeat"]),
                "task_words": len(_build_task_by_complexity(int(scenario["task_repeat"])).split()),
                "loops_executed_mean": round(statistics.fmean(executed_loops), 4),
                "current_kib": round(statistics.median(currents), 4),
                "peak_kib": round(statistics.median(peaks), 4),
            }
        )

    peaks_only = [item["peak_kib"] for item in measured]
    peak_min = min(peaks_only) if peaks_only else 0.0
    peak_max = max(peaks_only) if peaks_only else 0.0
    growth_ratio = peak_max / max(peak_min, 0.0001)

    return {
        "scenarios": measured,
        "summary": {
            "peak_kib_min": round(peak_min, 4),
            "peak_kib_max": round(peak_max, 4),
            "peak_growth_ratio": round(growth_ratio, 4),
        },
        "repeats": repeats,
    }


def build_performance_profile(
    *,
    iterations: int,
    concurrency_batches: int,
    memory_repeats: int,
) -> dict[str, Any]:
    mcp_server = load_mcp_server_module()

    execution_modes = profile_execution_modes(
        mcp_server,
        iterations=iterations,
        mode="implement",
        max_loops=1,
    )
    concurrent_load = profile_concurrent_load(
        mcp_server,
        mode="implement",
        max_loops=1,
        batches=concurrency_batches,
    )
    memory_trends = profile_memory_trends(
        mcp_server,
        repeats=memory_repeats,
    )

    profile = {
        "schema_version": 1,
        "deterministic_offline": True,
        "methodology": {
            "stubbed_imports": True,
            "task": "Implement endpoint with tests",
            "iterations": iterations,
            "concurrency_batches": concurrency_batches,
            "memory_repeats": memory_repeats,
            "execution_modes": ["legacy", "dynamic", "auto"],
        },
        "execution_modes": execution_modes,
        "concurrent_load": concurrent_load,
        "memory_trends": memory_trends,
    }
    profile["soft_budgets"] = derive_soft_budgets(profile)
    return profile


def derive_soft_budgets(profile: dict[str, Any]) -> dict[str, Any]:
    mode_latency_ms: dict[str, dict[str, float]] = {}
    execution_order_valid_ratio_min: dict[str, float] = {}

    for mode, result in profile.get("execution_modes", {}).items():
        latency = result.get("latency_ms", {})
        median = float(latency.get("median", 0.0))
        p95 = float(latency.get("p95", 0.0))
        mode_latency_ms[mode] = {
            "median_max": round(max(6.0, median * 5.0), 4),
            "p95_max": round(max(12.0, p95 * 6.0), 4),
        }

        ratio = result.get("execution_order_valid_ratio")
        if isinstance(ratio, (int, float)):
            execution_order_valid_ratio_min[mode] = round(min(1.0, max(0.5, float(ratio) * 0.75)), 4)

    concurrency_budgets: dict[str, dict[str, float]] = {}
    for scenario in profile.get("concurrent_load", {}).get("scenarios", []):
        key = str(scenario.get("key"))
        throughput = float(scenario.get("throughput_rps", 0.0))
        p95 = float(scenario.get("latency_ms", {}).get("p95", 0.0))
        concurrency_budgets[key] = {
            "throughput_min": round(max(10.0, throughput * 0.01), 4),
            "p95_max": round(max(20.0, p95 * 7.0), 4),
        }

    memory_summary = profile.get("memory_trends", {}).get("summary", {})
    peak_kib_max = float(memory_summary.get("peak_kib_max", 0.0))
    growth_ratio = float(memory_summary.get("peak_growth_ratio", 1.0))

    return {
        "mode_latency_ms": mode_latency_ms,
        "fallback_rate_max": 0.25,
        "execution_order_valid_ratio_min": execution_order_valid_ratio_min,
        "concurrency": concurrency_budgets,
        "memory_kib": {
            "peak_kib_max": round(max(256.0, peak_kib_max * 4.0), 4),
            "peak_growth_ratio_max": round(max(6.0, growth_ratio * 2.5), 4),
        },
    }


def _format_table(headers: list[str], rows: list[list[str]]) -> str:
    header_line = "| " + " | ".join(headers) + " |"
    divider_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header_line, divider_line, *body])


def _build_recommendations(profile: dict[str, Any]) -> list[dict[str, str]]:
    recommendations: list[dict[str, str]] = []
    execution = profile.get("execution_modes", {})
    legacy = execution.get("legacy", {}).get("latency_ms", {})
    dynamic = execution.get("dynamic", {}).get("latency_ms", {})
    auto = execution.get("auto", {}).get("latency_ms", {})

    legacy_median = float(legacy.get("median", 0.0))
    dynamic_median = float(dynamic.get("median", 0.0))
    auto_p95 = float(auto.get("p95", 0.0))
    dynamic_p95 = float(dynamic.get("p95", 0.0))

    if dynamic_median > max(legacy_median * 1.15, legacy_median + 0.2):
        recommendations.append(
            {
                "title": "Cache dynamic planning artifacts per normalized task signature",
                "observation": (
                    "Dynamic median latency is higher than legacy, indicating recurring planner and classification "
                    "overhead on repeated prompts."
                ),
                "action": (
                    "Memoize build_dynamic_planning_result outputs using task hash + mode + registry version with "
                    "short TTL to reduce repeated planning latency without changing execution semantics."
                ),
            }
        )

    if auto_p95 > max(dynamic_p95 * 1.1, dynamic_p95 + 0.25):
        recommendations.append(
            {
                "title": "Reduce auto-mode tail latency via early guardrail checks",
                "observation": (
                    "Auto mode p95 exceeds dynamic p95, suggesting branch checks and fallback diagnostics increase "
                    "tail latency."
                ),
                "action": (
                    "Pre-validate execution order and fallback preconditions before entering the autonomous loop, "
                    "so invalid plans fail fast with fewer allocations."
                ),
            }
        )

    memory_summary = profile.get("memory_trends", {}).get("summary", {})
    growth_ratio = float(memory_summary.get("peak_growth_ratio", 1.0))
    if growth_ratio > 1.2:
        recommendations.append(
            {
                "title": "Trim prompt payload growth across loop retries",
                "observation": (
                    "Peak memory grows across loop_count/task complexity scenarios, showing prompt expansion is a "
                    "primary allocation driver."
                ),
                "action": (
                    "Store structured loop context separately and pass compact prompt references (mode/loop/order IDs) "
                    "instead of repeatedly embedding full task text."
                ),
            }
        )

    recommendations.append(
        {
            "title": "Bound concurrent autonomous_execute fan-out with semaphore control",
            "observation": (
                "Concurrent scenarios increase p95 latency compared with single-request runs as request fan-out grows."
            ),
            "action": (
                "Introduce a lightweight per-process semaphore for high parallelism paths and expose queue depth in "
                "telemetry to keep throughput stable under burst load."
            ),
        }
    )

    recommendations.append(
        {
            "title": "Split telemetry payload assembly from hot execution path",
            "observation": (
                "Every loop currently builds full telemetry dictionaries even in deterministic success paths where "
                "fallback is not triggered."
            ),
            "action": (
                "Collect hot-path counters first and build expanded telemetry payloads only once at response assembly, "
                "reducing per-loop object churn."
            ),
        }
    )

    return recommendations[:5]


def render_markdown_report(profile: dict[str, Any]) -> str:
    execution_rows: list[list[str]] = []
    for mode in ("legacy", "dynamic", "auto"):
        result = profile["execution_modes"][mode]
        latency = result["latency_ms"]
        execution_rows.append(
            [
                mode,
                str(result["iterations"]),
                f"{latency['mean']:.4f}",
                f"{latency['median']:.4f}",
                f"{latency['p95']:.4f}",
                f"{result['loops_executed']['mean']:.2f}",
                f"{result['fallback_rate']:.4f}",
                (
                    "n/a"
                    if result["execution_order_valid_ratio"] is None
                    else f"{result['execution_order_valid_ratio']:.4f}"
                ),
            ]
        )

    concurrent_rows = []
    for scenario in profile["concurrent_load"]["scenarios"]:
        concurrent_rows.append(
            [
                scenario["key"],
                str(scenario["requests"]),
                f"{scenario['throughput_rps']:.4f}",
                f"{scenario['latency_ms']['mean']:.4f}",
                f"{scenario['latency_ms']['p95']:.4f}",
                f"{scenario['fallback_rate']:.4f}",
            ]
        )

    memory_rows = []
    for scenario in profile["memory_trends"]["scenarios"]:
        memory_rows.append(
            [
                scenario["name"],
                str(scenario["loop_count"]),
                str(scenario["task_words"]),
                f"{scenario['loops_executed_mean']:.2f}",
                f"{scenario['current_kib']:.4f}",
                f"{scenario['peak_kib']:.4f}",
            ]
        )

    recs = _build_recommendations(profile)
    recommendations_block = "\n\n".join(
        [
            f"{idx}. **{rec['title']}**\n"
            f"   Observation: {rec['observation']}\n"
            f"   Action: {rec['action']}"
            for idx, rec in enumerate(recs, start=1)
        ]
    )

    memory_summary = profile["memory_trends"]["summary"]

    return "\n".join(
        [
            "# Performance Baseline",
            "",
            "Deterministic baseline for Issue #11 generated with offline stubs and no external network calls.",
            "",
            "## Methodology",
            "",
            "- Imported mcp_server through deterministic stubs matching integration contract tests.",
            "- Benchmarked autonomous_execute across execution_mode values: legacy, dynamic, auto.",
            "- Recorded latency mean/median/p95, loops_executed, fallback_rate, execution_order_valid_ratio.",
            "- Ran concurrent load scenarios using asyncio gather with deterministic request prompts.",
            "- Sampled memory trends with tracemalloc while scaling loop_count and task complexity.",
            "",
            "## Execution Mode Results",
            "",
            _format_table(
                [
                    "execution_mode",
                    "iterations",
                    "latency_mean_ms",
                    "latency_median_ms",
                    "latency_p95_ms",
                    "loops_executed_mean",
                    "fallback_rate",
                    "execution_order_valid_ratio",
                ],
                execution_rows,
            ),
            "",
            "## Concurrent Load Results",
            "",
            _format_table(
                [
                    "scenario",
                    "requests",
                    "throughput_rps",
                    "latency_mean_ms",
                    "latency_p95_ms",
                    "fallback_rate",
                ],
                concurrent_rows,
            ),
            "",
            "## Memory Trend Results",
            "",
            _format_table(
                [
                    "scenario",
                    "loop_count",
                    "task_words",
                    "loops_executed_mean",
                    "current_kib",
                    "peak_kib",
                ],
                memory_rows,
            ),
            "",
            f"Memory summary: peak_kib_min={memory_summary['peak_kib_min']:.4f}, "
            f"peak_kib_max={memory_summary['peak_kib_max']:.4f}, "
            f"peak_growth_ratio={memory_summary['peak_growth_ratio']:.4f}.",
            "",
            "## Optimization Recommendations",
            "",
            recommendations_block,
            "",
            "## Reproduce",
            "",
            "- python3 scripts/profile_execution_paths.py --iterations 30 --output docs/performance-baseline.json --report docs/performance-baseline.md",
        ]
    )
