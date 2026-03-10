"""MCP server exposing autonomous and specialized AI orchestration tools to Copilot.

Two modes available:
1. Legacy mode: Direct architect/developer/QA tools
2. Autonomous mode: Self-healing Plan-Eval-Gather-Execute-Verify loop
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Literal

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
                    phases.append(phase)
        elif isinstance(event, WorkflowStatusEvent):
            statuses.append(str(event.state))

    final_status = statuses[-1] if statuses else "unknown"
    completed = "COMPLETE" in final_status.upper()

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
    logger.info(
        "[Autonomous] Starting execution | mode=%s execution_mode=%s loops=%s",
        mode,
        execution_mode,
        max_loops,
    )

    loop_count = max(1, min(max_loops, 5))

    if execution_mode == "legacy":
        legacy_result = await orchestrate_task(task)

        memory = MemorySystem()
        recent_learnings = memory.memories[-5:] if memory.memories else []

        return {
            "mode": mode,
            "effective_mode": "legacy",
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
            "final_status": str(legacy_result.get("final_status", "legacy_unknown")),
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
            },
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
    }

    for loop_index in range(loop_count):
        planning = build_dynamic_planning_result(task=task, mode=mode, registry=planning_registry)
        effective_mode = planning.team_spec.mode if mode == "auto" else mode
        last_mode = effective_mode

        if planning.team_spec.fallback_required and fallback_allowed:
            legacy_result = await orchestrate_task(task)
            fallback = {
                "triggered": True,
                "reason": "; ".join(planning.team_spec.fallback_reasons),
                "mode_used": "legacy",
                "legacy_result": legacy_result,
            }
            loop_history.append(
                {
                    "loop": loop_index + 1,
                    "resolved_mode": effective_mode,
                    "planning": planning.to_dict(),
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

            return {
                "mode": mode,
                "effective_mode": "legacy",
                "loops_requested": loop_count,
                "loops_executed": len(loop_history),
                "loop_history": loop_history,
                "phases_executed": [],
                "final_status": str(legacy_result.get("final_status", "legacy_unknown")),
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
            }

        # Embed planning context in the prompt so each loop can self-correct.
        task_prompt = (
            f"[MODE: {effective_mode}]\n"
            f"[LOOP: {loop_index + 1}/{loop_count}]\n"
            f"[DAG_ORDER: {', '.join(planning.dag_plan.execution_order)}]\n\n"
            f"{task}"
        )
        try:
            run_result = await _collect_autonomous_run(
                task_prompt,
                execution_order=planning.dag_plan.execution_order,
            )
        except Exception as exc:
            if fallback_allowed:
                legacy_result = await orchestrate_task(task)
                fallback = {
                    "triggered": True,
                    "reason": f"dynamic runtime failure: {exc}",
                    "mode_used": "legacy",
                    "legacy_result": legacy_result,
                }
                # Load memory to show learnings
                memory = MemorySystem()
                recent_learnings = memory.memories[-5:] if memory.memories else []

                return {
                    "mode": mode,
                    "effective_mode": "legacy",
                    "loops_requested": loop_count,
                    "loops_executed": len(loop_history),
                    "loop_history": loop_history,
                    "phases_executed": [],
                    "final_status": str(legacy_result.get("final_status", "legacy_unknown")),
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
                }

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
                "planning": planning.to_dict(),
                "run": run_result,
            }
        )

        if run_result["success_indicators"]["completed"]:
            break

    # Load memory to show learnings
    memory = MemorySystem()
    recent_learnings = memory.memories[-5:] if memory.memories else []

    return {
        "mode": mode,
        "effective_mode": last_mode,
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
