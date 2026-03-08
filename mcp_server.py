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


@mcp.tool()
async def autonomous_execute(
    task: str,
    mode: Literal["design", "fix_bug", "debug", "implement", "refactor"] = "implement"
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
        mode: Hint for the type of work (design/fix_bug/debug/implement/refactor)
    
    Returns:
        Dict with execution history, final output, learnings, and success status
    """
    logger.info(f"[Autonomous] Starting for mode={mode}")
    
    # Enhance task description based on mode
    task_prompt = f"[MODE: {mode}]\n\n{task}"
    
    workflow = create_autonomous_workflow()
    outputs: list[str] = []
    statuses: list[str] = []
    phases: list[str] = []

    async for event in workflow.run_stream([Message("user", text=task_prompt)]):
        if isinstance(event, WorkflowOutputEvent):
            output = str(event.data)
            outputs.append(output)
            # Extract phase markers
            if "Phase:" in output:
                phase = output.split("Phase:")[1].split("\n")[0].strip()
                if phase not in phases:
                    phases.append(phase)
        elif isinstance(event, WorkflowStatusEvent):
            statuses.append(str(event.state))

    # Load memory to show learnings
    memory = MemorySystem()
    recent_learnings = memory.memories[-5:] if memory.memories else []
    
    return {
        "mode": mode,
        "phases_executed": phases,
        "final_status": statuses[-1] if statuses else "unknown",
        "iteration_count": len([o for o in outputs if "iteration" in o.lower()]),
        "outputs": outputs,
        "recent_learnings": [
            {"issue": m.issue, "solution": m.solution, "outcome": m.outcome}
            for m in recent_learnings
        ],
        "success_indicators": {
            "completed": "COMPLETE" in statuses[-1] if statuses else False,
            "verified": any("verified" in o.lower() for o in outputs),
        }
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
        "model_routing": {
            "planner": os.getenv("PLANNER_MODEL", DEFAULT_PLANNER_MODEL),
            "evaluator": os.getenv("EVALUATOR_MODEL", DEFAULT_EVALUATOR_MODEL),
            "researcher": os.getenv("RESEARCHER_MODEL", DEFAULT_RESEARCHER_MODEL),
            "architect": os.getenv("ARCHITECT_MODEL", DEFAULT_ARCHITECT_MODEL),
            "developer": os.getenv("DEVELOPER_MODEL", DEFAULT_DEVELOPER_MODEL),
            "verifier": os.getenv("VERIFIER_MODEL", DEFAULT_VERIFIER_MODEL),
        }
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
