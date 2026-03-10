"""MCP server exposing autonomous and specialized AI orchestration tools to Copilot.

Two modes available:
1. Legacy mode: Direct architect/developer/QA tools
2. Autonomous mode: Self-healing Plan-Eval-Gather-Execute-Verify loop
"""

from __future__ import annotations

import json
import logging
import os
import time
from contextvars import ContextVar
from functools import lru_cache
from typing import Any, Literal
from uuid import uuid4

from agent_framework import AgentExecutorRequest, ChatMessage, WorkflowOutputEvent, WorkflowStatusEvent
from mcp.server.fastmcp import FastMCP

from orchestrator import (
    DEFAULT_ARCHITECT_MODEL,
    DEFAULT_DEVELOPER_MODEL,
    DEFAULT_QA_MODEL,
    DeveloperAgent,
    PrincipalArchitect,
    QualityAssuranceAgent,
    create_ai_client,
    create_orchestrator_workflow,
    get_base_deployment_name,
    get_credential_for_endpoint,
    get_project_endpoint,
    resolve_deployment_name,
)

from autonomous_orchestrator import (
    create_autonomous_workflow,
    MemorySystem,
    DEFAULT_PLANNER_MODEL,
    DEFAULT_EVALUATOR_MODEL,
    DEFAULT_RESEARCHER_MODEL,
    DEFAULT_VERIFIER_MODEL,
)
from dynamic_orchestration import build_default_registry, build_dynamic_planning_result

logger = logging.getLogger(__name__)

_MODE_ALIASES: dict[str, str] = {
    "bugfix": "fix_bug",
    "bug_fix": "fix_bug",
    "implementation": "implement",
}

_EXECUTION_MODE_ALIASES: dict[str, str] = {
    "static": "legacy",
    "classic": "legacy",
    "hybrid": "auto",
    "adaptive": "auto",
    "dynamic_only": "dynamic",
}

_TRUE_BOOL_VALUES = {"1", "true", "yes", "on"}
_FALSE_BOOL_VALUES = {"0", "false", "no", "off"}

_AUTONOMOUS_CORRELATION_ID: ContextVar[str | None] = ContextVar(
    "autonomous_correlation_id",
    default=None,
)
_AUTONOMOUS_LOOP_INDEX: ContextVar[int | None] = ContextVar(
    "autonomous_loop_index",
    default=None,
)


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _mean_metric(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _log_structured_event(event: str, **fields: Any) -> None:
    payload = {
        "event": event,
        "correlation_id": _AUTONOMOUS_CORRELATION_ID.get(),
    }
    payload.update(fields)
    logger.info("[Autonomous][Structured] %s", json.dumps(payload, sort_keys=True, default=str))


def _build_planning_telemetry(planning_payload: dict[str, Any], dag_latency_ms: float) -> dict[str, float]:
    discovered = planning_payload.get("discovered_skills", [])
    if not isinstance(discovered, list):
        discovered = []

    discovered_success = sum(
        1
        for item in discovered
        if isinstance(item, dict) and str(item.get("health", "unknown")).lower() != "unhealthy"
    )

    classified = planning_payload.get("classified_skills", [])
    confidence_scores: list[float] = []
    if isinstance(classified, list):
        for item in classified:
            if not isinstance(item, dict):
                continue
            confidence = item.get("confidence", {})
            if not isinstance(confidence, dict):
                continue
            for score in confidence.values():
                try:
                    confidence_scores.append(float(score))
                except (TypeError, ValueError):
                    continue

    return {
        "discovery_success_rate": _safe_rate(discovered_success, len(discovered)),
        "classification_confidence": _mean_metric(confidence_scores),
        "dag_latency_ms": round(max(0.0, dag_latency_ms), 3),
    }


def _aggregate_telemetry(
    loop_metrics: list[dict[str, float]],
    *,
    loops_executed: int,
    fallback_triggered: bool,
) -> dict[str, Any]:
    discovery_values = [item.get("discovery_success_rate", 0.0) for item in loop_metrics]
    classification_values = [item.get("classification_confidence", 0.0) for item in loop_metrics]
    dag_latency_values = [item.get("dag_latency_ms", 0.0) for item in loop_metrics]

    dag_latency_ms = _mean_metric(dag_latency_values)
    return {
        "discovery_success_rate": _mean_metric(discovery_values),
        "classification_confidence": _mean_metric(classification_values),
        "dag_latency_ms": dag_latency_ms,
        "dag_latency": round(dag_latency_ms / 1000.0, 6),
        "fallback_rate": _safe_rate(1 if fallback_triggered else 0, max(1, loops_executed)),
        "loop_metrics": loop_metrics,
    }


def _translate_setting_alias(value: str, aliases: dict[str, str], setting_name: str) -> str:
    normalized = str(value).strip().lower()
    translated = aliases.get(normalized, normalized)
    if translated != normalized:
        logger.warning(
            "[Autonomous][DEPRECATION] %s='%s' is deprecated; use '%s'.",
            setting_name,
            value,
            translated,
        )
    return translated


def _translate_bool_alias(value: bool | str, setting_name: str) -> bool:
    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()
    if normalized in _TRUE_BOOL_VALUES:
        logger.warning(
            "[Autonomous][DEPRECATION] %s should be sent as boolean; accepted legacy string '%s'.",
            setting_name,
            value,
        )
        return True
    if normalized in _FALSE_BOOL_VALUES:
        logger.warning(
            "[Autonomous][DEPRECATION] %s should be sent as boolean; accepted legacy string '%s'.",
            setting_name,
            value,
        )
        return False
    return bool(value)


def _build_fallback_diagnostics(
    *,
    branch: str,
    reason: str,
    loop_index: int,
    requested_mode: str,
    resolved_mode: str,
    execution_mode: str,
) -> dict[str, Any]:
    return {
        "branch": branch,
        "reason": reason,
        "loop": loop_index,
        "requested_mode": requested_mode,
        "resolved_mode": resolved_mode,
        "execution_mode": execution_mode,
    }

# Backward-compatible alias for prior examples that used Message(role, text=...).
Message = ChatMessage

mcp = FastMCP("ai-agent-orchestrator")


class ExecutorSuite:
    """Reusable specialized executors for direct tool calls."""

    def __init__(
        self,
        architect: PrincipalArchitect,
        developer: DeveloperAgent,
        qa: QualityAssuranceAgent,
    ) -> None:
        self.architect = architect
        self.developer = developer
        self.qa = qa


@lru_cache(maxsize=1)
def get_executor_suite() -> ExecutorSuite:
    """Create role-specific executors once and reuse for MCP requests."""
    project_endpoint = get_project_endpoint()
    base_deployment = get_base_deployment_name()
    credential = get_credential_for_endpoint(project_endpoint)

    architect_model = resolve_deployment_name(
        "ARCHITECT_MODEL",
        DEFAULT_ARCHITECT_MODEL,
        base_deployment,
    )
    developer_model = resolve_deployment_name(
        "DEVELOPER_MODEL",
        DEFAULT_DEVELOPER_MODEL,
        base_deployment,
    )
    qa_model = resolve_deployment_name(
        "QA_MODEL",
        DEFAULT_QA_MODEL,
        base_deployment,
    )

    logger.info(
        "MCP model routing | architect=%s developer=%s qa=%s",
        architect_model,
        developer_model,
        qa_model,
    )

    architect_client = create_ai_client(project_endpoint, architect_model, credential)
    developer_client = create_ai_client(project_endpoint, developer_model, credential)
    qa_client = create_ai_client(project_endpoint, qa_model, credential)

    return ExecutorSuite(
        architect=PrincipalArchitect(architect_client, id="architect_mcp"),
        developer=DeveloperAgent(developer_client, id="developer_mcp"),
        qa=QualityAssuranceAgent(qa_client, id="qa_mcp"),
    )


async def run_single_executor(executor: Any, prompt: str) -> str:
    """Run one role executor and return text output."""
    request = AgentExecutorRequest(
        messages=[Message("user", text=prompt)],
        should_respond=True,
    )
    response = await executor.agent.run(request.messages, should_respond=request.should_respond)
    return response.text


@mcp.tool()
async def architect_design(task: str, constraints: str = "") -> str:
    """Generate architecture and requirements for a software task."""
    suite = get_executor_suite()
    prompt = (
        f"Task:\n{task}\n\n"
        f"Additional constraints:\n{constraints or 'None provided.'}\n\n"
        "Produce a JSON response with design, requirements, and considerations."
    )
    return await run_single_executor(suite.architect, prompt)


@mcp.tool()
async def developer_implement(task: str, architecture: str, feedback: str = "") -> str:
    """Generate implementation details from architecture and feedback."""
    suite = get_executor_suite()
    prompt = (
        f"Task:\n{task}\n\n"
        f"Architecture:\n{architecture}\n\n"
        f"Feedback to incorporate:\n{feedback or 'No feedback provided.'}\n\n"
        "Produce JSON with implementation, tests, documentation, dependencies, and notes."
    )
    return await run_single_executor(suite.developer, prompt)


@mcp.tool()
async def qa_review(requirements: str, implementation: str) -> str:
    """Review implementation quality, security, and test readiness."""
    suite = get_executor_suite()
    prompt = (
        f"Requirements:\n{requirements}\n\n"
        f"Implementation:\n{implementation}\n\n"
        "Produce JSON with quality_score, security_issues, test_coverage, issues, recommendations, and approved."
    )
    return await run_single_executor(suite.qa, prompt)


@mcp.tool()
async def orchestrate_task(task: str) -> dict[str, Any]:
    """Run the full architect -> developer -> QA feedback loop workflow."""
    workflow = create_orchestrator_workflow()
    outputs: list[str] = []
    statuses: list[str] = []

    async for event in workflow.run_stream([Message("user", text=task)]):
        if isinstance(event, WorkflowOutputEvent):
            outputs.append(str(event.data))
        elif isinstance(event, WorkflowStatusEvent):
            statuses.append(str(event.state))

    return {
        "final_status": statuses[-1] if statuses else "unknown",
        "output_count": len(outputs),
        "outputs": outputs,
    }


@mcp.tool()
def show_model_routing() -> dict[str, str]:
    """Show effective model mapping used by specialized tools."""
    base_deployment = get_base_deployment_name()
    return {
        "architect": resolve_deployment_name("ARCHITECT_MODEL", DEFAULT_ARCHITECT_MODEL, base_deployment),
        "developer": resolve_deployment_name("DEVELOPER_MODEL", DEFAULT_DEVELOPER_MODEL, base_deployment),
        "qa": resolve_deployment_name("QA_MODEL", DEFAULT_QA_MODEL, base_deployment),
        "default_auto_fallback": base_deployment or "<unset>",
    }


# ==================== AUTONOMOUS ORCHESTRATOR TOOLS ====================


async def _collect_autonomous_run(task_prompt: str, execution_order: list[str] | None = None) -> dict[str, Any]:
    """Execute one autonomous workflow run and collect structured telemetry."""
    workflow = create_autonomous_workflow(execution_order=execution_order)
    outputs: list[str] = []
    statuses: list[str] = []
    phases: list[str] = []

    async for event in workflow.run_stream([Message("user", text=task_prompt)]):
        if isinstance(event, WorkflowOutputEvent):
            output = str(event.data)
            outputs.append(output)
            if "Phase:" in output:
                phase = output.split("Phase:")[1].split("\n")[0].strip()
                if phase not in phases:
                    previous_phase = phases[-1] if phases else None
                    phases.append(phase)
                    _log_structured_event(
                        "phase.transition",
                        loop=_AUTONOMOUS_LOOP_INDEX.get(),
                        previous_phase=previous_phase,
                        phase=phase,
                    )
        elif isinstance(event, WorkflowStatusEvent):
            statuses.append(str(event.state))

    final_status = statuses[-1] if statuses else "unknown"
    completed = "COMPLETE" in final_status.upper()

    _log_structured_event(
        "loop.completed",
        loop=_AUTONOMOUS_LOOP_INDEX.get(),
        final_status=final_status,
        completed=completed,
        phase_count=len(phases),
    )

    return {
        "phases_executed": phases,
        "final_status": final_status,
        "iteration_count": len([item for item in outputs if "iteration" in item.lower()]),
        "outputs": outputs,
        "success_indicators": {
            "completed": completed,
            "verified": any("verified" in item.lower() for item in outputs),
        },
    }


@mcp.tool()
def dynamic_plan_preview(
    task: str,
    mode: Literal["auto", "design", "fix_bug", "debug", "implement", "refactor"] = "auto",
) -> dict[str, Any]:
    """Preview dynamic team composition and DAG plan before execution.

    This tool is deterministic and safe to run repeatedly. It allows callers to
    inspect skill discovery, classification, role assignments, and execution DAG
    prior to actually running the autonomous loop.
    """
    mode = _translate_setting_alias(mode, _MODE_ALIASES, "mode")
    planning = build_dynamic_planning_result(task=task, mode=mode, registry=build_default_registry())
    return planning.to_dict()


@mcp.tool()
async def autonomous_execute(
    task: str,
    mode: Literal["auto", "design", "fix_bug", "debug", "implement", "refactor"] = "implement",
    execution_mode: Literal["legacy", "dynamic", "auto"] = "auto",
    max_loops: int = 1,
    enable_legacy_fallback: bool = True,
) -> dict[str, Any]:
    """Execute task using autonomous Plan-Eval-Gather-Execute-Verify loop with self-healing.
    
    This is the recommended tool for:
    - "Design something" requests
    - "Fix this bug" or debugging tasks  
    - Any complex multi-step task requiring iteration
    - Tasks that may need self-correction
    
    The autonomous loop will:
    1. PLAN: Break down task into executable steps
    2. EVALUATE: Assess if we have enough information
    3. GATHER: Research and collect missing context
    4. EXECUTE: Design and implement solution
    5. VERIFY: Test and validate with self-correction
    6. LEARN: Store lessons for future improvements
    
    Args:
        task: The user's request or problem to solve
        mode: Hint for the type of work (auto/design/fix_bug/debug/implement/refactor)
        execution_mode: Orchestration path control (legacy/dynamic/auto)
        max_loops: Maximum recovery loops before returning latest result (1-5)
        enable_legacy_fallback: Fallback to legacy orchestrator when dynamic planning/runtime cannot proceed
    
    Returns:
        Dict with execution history, final output, learnings, and success status
    """
    requested_mode = mode
    mode = _translate_setting_alias(mode, _MODE_ALIASES, "mode")
    execution_mode = _translate_setting_alias(
        execution_mode,
        _EXECUTION_MODE_ALIASES,
        "execution_mode",
    )
    enable_legacy_fallback = _translate_bool_alias(enable_legacy_fallback, "enable_legacy_fallback")

    correlation_id = uuid4().hex
    _AUTONOMOUS_CORRELATION_ID.set(correlation_id)
    _AUTONOMOUS_LOOP_INDEX.set(None)

    logger.info(
        "[Autonomous] Starting execution | correlation_id=%s mode=%s execution_mode=%s loops=%s",
        correlation_id,
        mode,
        execution_mode,
        max_loops,
    )

    loop_count = max(1, min(max_loops, 5))
    loop_telemetry: list[dict[str, float]] = []

    _log_structured_event(
        "autonomous.start",
        requested_mode=requested_mode,
        resolved_mode=mode,
        execution_mode=execution_mode,
        loops_requested=loop_count,
        enable_legacy_fallback=enable_legacy_fallback,
    )

    if execution_mode == "legacy":
        legacy_result = await orchestrate_task(task)
        legacy_status = str(legacy_result.get("final_status", "legacy_unknown"))
        telemetry = _aggregate_telemetry(
            loop_telemetry,
            loops_executed=1,
            fallback_triggered=False,
        )

        memory = MemorySystem()
        recent_learnings = memory.memories[-5:] if memory.memories else []

        _log_structured_event(
            "autonomous.completed",
            effective_mode="legacy",
            loops_executed=1,
            fallback_triggered=False,
            final_status=legacy_status,
        )

        return {
            "mode": mode,
            "effective_mode": "legacy",
            "correlation_id": correlation_id,
            "loops_requested": loop_count,
            "loops_executed": 1,
            "loop_history": [
                {
                    "loop": 1,
                    "resolved_mode": "legacy",
                    "planning": None,
                    "run": {
                        "phases_executed": [],
                        "final_status": str(legacy_result.get("final_status", "legacy_unknown")),
                        "iteration_count": 0,
                        "outputs": legacy_result.get("outputs", []),
                        "success_indicators": {
                            "completed": str(legacy_result.get("final_status", "")).lower() != "unknown",
                            "verified": False,
                        },
                    },
                }
            ],
            "phases_executed": [],
            "final_status": legacy_status,
            "iteration_count": 0,
            "outputs": legacy_result.get("outputs", []),
            "recent_learnings": [
                {"issue": m.issue, "solution": m.solution, "outcome": m.outcome}
                for m in recent_learnings
            ],
            "success_indicators": {
                "completed": str(legacy_result.get("final_status", "")).lower() != "unknown",
                "verified": False,
            },
            "fallback": {
                "triggered": False,
                "reason": "",
                "mode_used": "legacy",
                "legacy_result": legacy_result,
                "diagnostics": None,
            },
            "telemetry": telemetry,
        }

    planning_registry = build_default_registry()
    fallback_allowed = execution_mode == "auto" and enable_legacy_fallback

    loop_history: list[dict[str, Any]] = []
    last_run: dict[str, Any] = {
        "phases_executed": [],
        "final_status": "unknown",
        "iteration_count": 0,
        "outputs": [],
        "success_indicators": {"completed": False, "verified": False},
    }
    last_mode = mode
    fallback: dict[str, Any] = {
        "triggered": False,
        "reason": "",
        "mode_used": "dynamic",
        "legacy_result": None,
        "diagnostics": None,
    }

    for loop_index in range(loop_count):
        planning_started = time.perf_counter()
        planning = build_dynamic_planning_result(task=task, mode=mode, registry=planning_registry)
        planning_latency_ms = (time.perf_counter() - planning_started) * 1000.0
        planning_payload = planning.to_dict()
        effective_mode = planning.team_spec.mode if mode == "auto" else mode
        last_mode = effective_mode

        loop_metric = _build_planning_telemetry(planning_payload, planning_latency_ms)
        loop_telemetry.append(loop_metric)

        _log_structured_event(
            "planning.completed",
            loop=loop_index + 1,
            requested_mode=requested_mode,
            resolved_mode=effective_mode,
            fallback_required=planning.team_spec.fallback_required,
            discovery_success_rate=loop_metric["discovery_success_rate"],
            classification_confidence=loop_metric["classification_confidence"],
            dag_latency_ms=loop_metric["dag_latency_ms"],
        )

        if planning.team_spec.fallback_required and not fallback_allowed:
            logger.warning(
                "[Autonomous][Fallback][planning] Dynamic planning requested fallback but legacy fallback is disabled | execution_mode=%s enable_legacy_fallback=%s reasons=%s",
                execution_mode,
                enable_legacy_fallback,
                planning.team_spec.fallback_reasons,
            )

        if planning.team_spec.fallback_required and fallback_allowed:
            reason = "; ".join(planning.team_spec.fallback_reasons)
            diagnostics = _build_fallback_diagnostics(
                branch="planning",
                reason=reason,
                loop_index=loop_index + 1,
                requested_mode=requested_mode,
                resolved_mode=effective_mode,
                execution_mode=execution_mode,
            )
            logger.warning(
                "[Autonomous][Fallback][planning->legacy] Triggering legacy fallback | diagnostics=%s",
                diagnostics,
            )
            _log_structured_event(
                "fallback.triggered",
                loop=loop_index + 1,
                branch="planning",
                reason=reason,
                mode_used="legacy",
            )

            legacy_result = await orchestrate_task(task)
            legacy_status = str(legacy_result.get("final_status", "legacy_unknown"))
            fallback = {
                "triggered": True,
                "reason": reason,
                "mode_used": "legacy",
                "legacy_result": legacy_result,
                "diagnostics": diagnostics,
            }
            loop_history.append(
                {
                    "loop": loop_index + 1,
                    "resolved_mode": effective_mode,
                    "planning": planning_payload,
                    "telemetry": loop_metric,
                    "run": {
                        "phases_executed": [],
                        "final_status": "legacy_fallback",
                        "iteration_count": 0,
                        "outputs": [],
                        "success_indicators": {"completed": True, "verified": False},
                    },
                }
            )

            # Load memory to show learnings
            memory = MemorySystem()
            recent_learnings = memory.memories[-5:] if memory.memories else []
            telemetry = _aggregate_telemetry(
                loop_telemetry,
                loops_executed=len(loop_history),
                fallback_triggered=True,
            )

            _log_structured_event(
                "autonomous.completed",
                effective_mode="legacy",
                loops_executed=len(loop_history),
                fallback_triggered=True,
                final_status=legacy_status,
            )

            return {
                "mode": mode,
                "effective_mode": "legacy",
                "correlation_id": correlation_id,
                "loops_requested": loop_count,
                "loops_executed": len(loop_history),
                "loop_history": loop_history,
                "phases_executed": [],
                "final_status": legacy_status,
                "iteration_count": 0,
                "outputs": legacy_result.get("outputs", []),
                "recent_learnings": [
                    {"issue": m.issue, "solution": m.solution, "outcome": m.outcome}
                    for m in recent_learnings
                ],
                "success_indicators": {
                    "completed": str(legacy_result.get("final_status", "")).lower() != "unknown",
                    "verified": False,
                },
                "fallback": fallback,
                "telemetry": telemetry,
            }

        # Embed planning context in the prompt so each loop can self-correct.
        task_prompt = (
            f"[MODE: {effective_mode}]\n"
            f"[LOOP: {loop_index + 1}/{loop_count}]\n"
            f"[DAG_ORDER: {', '.join(planning.dag_plan.execution_order)}]\n\n"
            f"{task}"
        )
        _AUTONOMOUS_LOOP_INDEX.set(loop_index + 1)
        try:
            run_result = await _collect_autonomous_run(
                task_prompt,
                execution_order=planning.dag_plan.execution_order,
            )
        except Exception as exc:
            if fallback_allowed:
                reason = f"dynamic runtime failure: {exc}"
                diagnostics = _build_fallback_diagnostics(
                    branch="runtime",
                    reason=reason,
                    loop_index=loop_index + 1,
                    requested_mode=requested_mode,
                    resolved_mode=effective_mode,
                    execution_mode=execution_mode,
                )
                logger.warning(
                    "[Autonomous][Fallback][runtime->legacy] Triggering legacy fallback | diagnostics=%s",
                    diagnostics,
                )
                _log_structured_event(
                    "fallback.triggered",
                    loop=loop_index + 1,
                    branch="runtime",
                    reason=reason,
                    mode_used="legacy",
                )

                legacy_result = await orchestrate_task(task)
                legacy_status = str(legacy_result.get("final_status", "legacy_unknown"))
                fallback = {
                    "triggered": True,
                    "reason": reason,
                    "mode_used": "legacy",
                    "legacy_result": legacy_result,
                    "diagnostics": diagnostics,
                }
                # Load memory to show learnings
                memory = MemorySystem()
                recent_learnings = memory.memories[-5:] if memory.memories else []
                telemetry = _aggregate_telemetry(
                    loop_telemetry,
                    loops_executed=len(loop_history),
                    fallback_triggered=True,
                )

                _log_structured_event(
                    "autonomous.completed",
                    effective_mode="legacy",
                    loops_executed=len(loop_history),
                    fallback_triggered=True,
                    final_status=legacy_status,
                )

                return {
                    "mode": mode,
                    "effective_mode": "legacy",
                    "correlation_id": correlation_id,
                    "loops_requested": loop_count,
                    "loops_executed": len(loop_history),
                    "loop_history": loop_history,
                    "phases_executed": [],
                    "final_status": legacy_status,
                    "iteration_count": 0,
                    "outputs": legacy_result.get("outputs", []),
                    "recent_learnings": [
                        {"issue": m.issue, "solution": m.solution, "outcome": m.outcome}
                        for m in recent_learnings
                    ],
                    "success_indicators": {
                        "completed": str(legacy_result.get("final_status", "")).lower() != "unknown",
                        "verified": False,
                    },
                    "fallback": fallback,
                    "telemetry": telemetry,
                }

            _log_structured_event(
                "loop.error",
                loop=loop_index + 1,
                error=str(exc),
                fallback_allowed=fallback_allowed,
            )
            run_result = {
                "phases_executed": [],
                "final_status": f"dynamic_error: {exc}",
                "iteration_count": 0,
                "outputs": [],
                "success_indicators": {"completed": False, "verified": False},
            }
        last_run = run_result

        loop_history.append(
            {
                "loop": loop_index + 1,
                "resolved_mode": effective_mode,
                "planning": planning_payload,
                "telemetry": loop_metric,
                "run": run_result,
            }
        )

        if run_result["success_indicators"]["completed"]:
            break

    # Load memory to show learnings
    memory = MemorySystem()
    recent_learnings = memory.memories[-5:] if memory.memories else []
    telemetry = _aggregate_telemetry(
        loop_telemetry,
        loops_executed=len(loop_history),
        fallback_triggered=fallback["triggered"],
    )

    _log_structured_event(
        "autonomous.completed",
        effective_mode=last_mode,
        loops_executed=len(loop_history),
        fallback_triggered=fallback["triggered"],
        final_status=last_run["final_status"],
    )

    return {
        "mode": mode,
        "effective_mode": last_mode,
        "correlation_id": correlation_id,
        "loops_requested": loop_count,
        "loops_executed": len(loop_history),
        "loop_history": loop_history,
        "phases_executed": last_run["phases_executed"],
        "final_status": last_run["final_status"],
        "iteration_count": last_run["iteration_count"],
        "outputs": last_run["outputs"],
        "recent_learnings": [
            {"issue": m.issue, "solution": m.solution, "outcome": m.outcome}
            for m in recent_learnings
        ],
        "success_indicators": last_run["success_indicators"],
        "fallback": fallback,
        "telemetry": telemetry,
    }


@mcp.tool()
def get_learnings(task_type: str = "all", limit: int = 10) -> list[dict[str, Any]]:
    """Retrieve past learnings from the agent memory system.
    
    The autonomous orchestrator stores lessons learned from past executions
    to continuously improve and avoid repeating mistakes.
    
    Args:
        task_type: Filter by task type (planning/verification/all)
        limit: Maximum number of learnings to return
    
    Returns:
        List of past learnings with issue, solution, outcome, and confidence
    """
    memory = MemorySystem()
    
    learnings = memory.memories
    if task_type != "all":
        learnings = [m for m in learnings if m.task_type == task_type]
    
    learnings = sorted(learnings, key=lambda m: m.timestamp, reverse=True)[:limit]
    
    return [
        {
            "timestamp": m.timestamp,
            "task_type": m.task_type,
            "issue": m.issue,
            "solution": m.solution,
            "outcome": m.outcome,
            "confidence": m.confidence,
        }
        for m in learnings
    ]


@mcp.tool()
def show_autonomous_capabilities() -> dict[str, Any]:
    """Show what the autonomous orchestrator can do and its agent lineup."""
    dynamic_demo = build_dynamic_planning_result(
        task="Implement secure API endpoint with tests",
        mode="auto",
        registry=build_default_registry(),
    )

    return {
        "description": "Autonomous multi-agent system with self-healing capabilities",
        "execution_loop": [
            "PLAN: Break down tasks into executable steps",
            "EVALUATE: Assess progress and decide next actions",
            "GATHER: Research and collect necessary context",
            "EXECUTE: Design and implement solutions",
            "VERIFY: Test, validate, and self-correct",
            "LEARN: Store lessons for continuous improvement"
        ],
        "specialized_agents": {
            "PlannerAgent": "Strategic planning and task decomposition",
            "EvaluatorAgent": "Progress assessment and decision-making",
            "ResearcherAgent": "Context gathering and solution research",
            "ArchitectAgent": "Solution design and architecture",
            "DeveloperAgent": "Code implementation",
            "VerifierAgent": "Quality assurance and self-correction",
        },
        "self_healing": {
            "enabled": True,
            "description": "Agents learn from mistakes and adapt execution",
            "memory_location": ".orchestrator_memory/lessons_learned.json"
        },
        "use_cases": [
            "Design complex systems",
            "Fix bugs with root cause analysis",
            "Debug issues systematically",
            "Implement features end-to-end",
            "Refactor code with validation"
        ],
        "dynamic_layer": {
            "enabled": True,
            "description": "Builds skill-aware team composition and adaptive DAG per request.",
            "resolved_mode_example": dynamic_demo.team_spec.mode,
            "dag_order_example": dynamic_demo.dag_plan.execution_order,
            "discovered_skill_count": len(dynamic_demo.discovered_skills),
            "preview_tool": "dynamic_plan_preview",
            "legacy_fallback": True,
        },
        "model_routing": {
            "planner": os.getenv("PLANNER_MODEL", DEFAULT_PLANNER_MODEL),
            "evaluator": os.getenv("EVALUATOR_MODEL", DEFAULT_EVALUATOR_MODEL),
            "researcher": os.getenv("RESEARCHER_MODEL", DEFAULT_RESEARCHER_MODEL),
            "architect": os.getenv("ARCHITECT_MODEL", DEFAULT_ARCHITECT_MODEL),
            "developer": os.getenv("DEVELOPER_MODEL", DEFAULT_DEVELOPER_MODEL),
            "verifier": os.getenv("VERIFIER_MODEL", DEFAULT_VERIFIER_MODEL),
        }
    }


def main() -> None:
    """Script entrypoint for `ai-agent-orchestrator` console command."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
