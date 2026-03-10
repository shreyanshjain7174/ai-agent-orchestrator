"""
Autonomous Multi-Agent Orchestrator with Plan-Eval-Gather-Execute-Verify Loop

This orchestrator implements a self-healing, self-evolving agent system that:
- Plans: Breaks down tasks into executable steps
- Evaluates: Assesses progress and determines next actions
- Gathers: Researches and collects necessary context
- Executes: Implements solutions using specialized agents
- Verifies: Tests and validates outputs with self-correction
- Learns: Stores lessons for continuous improvement
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    ChatMessage,
    Executor,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    WorkflowStatusEvent,
    handler,
)
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Import base model resolution utilities
from orchestrator import (
    DEFAULT_ARCHITECT_MODEL,
    DEFAULT_DEVELOPER_MODEL,
    DEFAULT_QA_MODEL,
    create_ai_client,
    get_base_deployment_name,
    get_credential_for_endpoint,
    get_project_endpoint,
    resolve_deployment_name,
)

load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Backward-compatible alias for prior examples that used Message(role, text=...).
Message = ChatMessage


# Agent model defaults
DEFAULT_PLANNER_MODEL = "auto"
DEFAULT_EVALUATOR_MODEL = "auto"
DEFAULT_RESEARCHER_MODEL = "auto"
DEFAULT_VERIFIER_MODEL = "auto"


class Phase(str, Enum):
    """Execution phases in the autonomous loop."""
    PLAN = "plan"
    EVALUATE = "evaluate"
    GATHER = "gather"
    EXECUTE = "execute"
    VERIFY = "verify"
    LEARN = "learn"
    COMPLETE = "complete"


@dataclass
class ExecutionPlan:
    """Structured execution plan from Planner."""
    task_id: str
    goal: str
    steps: list[dict[str, Any]]
    success_criteria: list[str]
    assumptions: list[str]
    risks: list[str]
    iteration: int = 0
    context_needed: list[str] = field(default_factory=list)


@dataclass
class EvaluationResult:
    """Assessment from Evaluator."""
    phase: Phase
    success: bool
    confidence: float
    issues: list[str]
    next_action: str
    reasoning: str
    context_gaps: list[str] = field(default_factory=list)


@dataclass
class MemoryEntry:
    """Learning memory for self-improvement."""
    timestamp: str
    task_type: str
    issue: str
    solution: str
    outcome: str
    confidence: float


class MemorySystem:
    """Persistent memory for agent learning and self-evolution."""
    
    def __init__(self, memory_dir: str = ".orchestrator_memory"):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(exist_ok=True)
        self.memory_file = self.memory_dir / "lessons_learned.json"
        self.memories: list[MemoryEntry] = self._load_memories()
    
    def _load_memories(self) -> list[MemoryEntry]:
        """Load existing memories from disk."""
        if not self.memory_file.exists():
            return []
        try:
            with open(self.memory_file, 'r') as f:
                data = json.load(f)
                return [MemoryEntry(**entry) for entry in data]
        except Exception as e:
            logger.warning(f"Failed to load memories: {e}")
            return []
    
    def add_memory(self, task_type: str, issue: str, solution: str, outcome: str, confidence: float = 0.8):
        """Store a new learning for future reference."""
        memory = MemoryEntry(
            timestamp=datetime.now().isoformat(),
            task_type=task_type,
            issue=issue,
            solution=solution,
            outcome=outcome,
            confidence=confidence
        )
        self.memories.append(memory)
        self._save_memories()
        logger.info(f"Stored memory: {task_type} - {issue}")
    
    def _save_memories(self):
        """Persist memories to disk."""
        try:
            with open(self.memory_file, 'w') as f:
                json.dump([vars(m) for m in self.memories], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save memories: {e}")
    
    def get_relevant_memories(self, task_type: str, issue_keywords: list[str]) -> list[MemoryEntry]:
        """Retrieve relevant past learnings."""
        relevant = []
        for memory in self.memories:
            if memory.task_type == task_type:
                for keyword in issue_keywords:
                    if keyword.lower() in memory.issue.lower() or keyword.lower() in memory.solution.lower():
                        relevant.append(memory)
                        break
        return sorted(relevant, key=lambda m: m.confidence, reverse=True)[:5]


class PlannerAgent(Executor):
    """Plans task execution with detailed steps and success criteria."""
    
    agent: Any
    
    def __init__(self, client: AzureOpenAIResponsesClient, memory: MemorySystem, id: str = "planner"):
        self.agent = client.create_agent(
            name="PlannerAgent",
            instructions="""You are an Expert Planning Agent specializing in task decomposition and strategic planning.

Your responsibilities:
1. Analyze user tasks and break them into executable steps
2. Define clear success criteria and validation points
3. Identify required context, resources, and dependencies
4. Anticipate risks and create mitigation strategies
5. Learn from past executions to improve planning

When creating a plan, provide JSON with:
{
  "goal": "clear statement of the end goal",
  "steps": [
    {
      "id": 1,
      "action": "specific action to take",
      "agent": "which specialized agent should execute",
      "inputs": ["what information is needed"],
      "outputs": ["what will be produced"],
      "validation": "how to verify success"
    }
  ],
  "success_criteria": ["measurable criteria for task completion"],
  "assumptions": ["what we assume to be true"],
  "risks": ["potential issues and mitigation"],
  "context_needed": ["information we need to gather first"]
}

Consider past learnings provided in context to avoid repeating mistakes."""
        )
        self.memory = memory
        super().__init__(id=id)
    
    @handler
    async def handle(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        logger.info(f"[Planner] Creating execution plan")
        
        # Enhance prompt with relevant memories
        original_prompt = request.messages[-1].text
        memories = self.memory.get_relevant_memories("planning", [])
        
        if memories:
            memory_context = "\n\nPast Learnings:\n" + "\n".join([
                f"- {m.issue}: {m.solution} (outcome: {m.outcome})"
                for m in memories
            ])
            enhanced_prompt = original_prompt + memory_context
            request.messages[-1] = Message("user", text=enhanced_prompt)
        
        response = await self.agent.run(request.messages, should_respond=request.should_respond)
        await ctx.send_message(
            AgentExecutorRequest(
                messages=[Message("user", text=response.text)],
                should_respond=True,
            )
        )


class EvaluatorAgent(Executor):
    """Evaluates progress and decides next actions in the autonomous loop."""
    
    agent: Any
    
    def __init__(self, client: AzureOpenAIResponsesClient, id: str = "evaluator"):
        self.agent = client.create_agent(
            name="EvaluatorAgent",
            instructions="""You are an Expert Evaluation Agent specializing in progress assessment and decision-making.

Your responsibilities:
1. Assess if current phase achieved its objectives
2. Evaluate output quality and completeness
3. Identify gaps, issues, or missing context
4. Decide the optimal next action in the execution loop
5. Maintain high quality standards while avoiding infinite loops

Respond with JSON:
{
  "phase": "current phase being evaluated",
  "success": true/false,
  "confidence": 0.0-1.0,
  "issues": ["specific problems found"],
  "next_action": "CONTINUE|GATHER_MORE|REVISE|COMPLETE",
  "reasoning": "detailed explanation of decision",
  "context_gaps": ["missing information needed"]
}

Be pragmatic: Don't demand perfection, but ensure quality standards are met.
If stuck in loops, escalate or suggest alternative approaches."""
        )
        super().__init__(id=id)
    
    @handler
    async def handle(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        logger.info(f"[Evaluator] Assessing progress")
        response = await self.agent.run(request.messages, should_respond=request.should_respond)
        await ctx.send_message(
            AgentExecutorRequest(
                messages=[Message("user", text=response.text)],
                should_respond=True,
            )
        )


class ResearcherAgent(Executor):
    """Gathers context, researches solutions, and fills knowledge gaps."""
    
    agent: Any
    
    def __init__(self, client: AzureOpenAIResponsesClient, id: str = "researcher"):
        self.agent = client.create_agent(
            name="ResearcherAgent",
            instructions="""You are an Expert Research Agent specializing in information gathering and analysis.

Your responsibilities:
1. Collect relevant context for the current task
2. Research best practices and patterns
3. Identify potential solutions and approaches
4. Analyze codebases and documentation
5. Fill knowledge gaps identified by other agents

Respond with JSON:
{
  "findings": [
    {
      "topic": "what was researched",
      "information": "detailed findings",
      "sources": ["where information came from"],
      "relevance": "why this matters for the task"
    }
  ],
  "recommendations": ["actionable suggestions based on research"],
  "confidence": 0.0-1.0,
  "gaps_remaining": ["what still needs to be researched"]
}

Be thorough but focused. Prioritize practical, actionable information."""
        )
        super().__init__(id=id)
    
    @handler
    async def handle(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        logger.info(f"[Researcher] Gathering context")
        response = await self.agent.run(request.messages, should_respond=request.should_respond)
        await ctx.send_message(
            AgentExecutorRequest(
                messages=[Message("user", text=response.text)],
                should_respond=True,
            )
        )


class ArchitectAgent(Executor):
    """Designs solutions based on plans and gathered context."""
    
    agent: Any
    
    def __init__(self, client: AzureOpenAIResponsesClient, id: str = "architect"):
        self.agent = client.create_agent(
            name="ArchitectAgent",
            instructions="""You are a Principal Software Architect.

Design robust, scalable solutions following the execution plan and research findings.

Provide JSON:
{
  "design": "detailed architecture",
  "components": ["key components and their responsibilities"],
  "patterns": ["design patterns used"],
  "trade_offs": ["decisions made and why"],
  "implementation_guidance": ["specific instructions for developers"],
  "risks_mitigated": ["how identified risks are addressed"]
}"""
        )
        super().__init__(id=id)
    
    @handler
    async def handle(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        logger.info(f"[Architect] Designing solution")
        response = await self.agent.run(request.messages, should_respond=request.should_respond)
        await ctx.send_message(
            AgentExecutorRequest(
                messages=[Message("user", text=response.text)],
                should_respond=True,
            )
        )


class DeveloperAgent(Executor):
    """Implements solutions based on architecture and plan."""
    
    agent: Any
    
    def __init__(self, client: AzureOpenAIResponsesClient, id: str = "developer"):
        self.agent = client.create_agent(
            name="DeveloperAgent",
            instructions="""You are an Expert Software Developer.

Implement clean, well-tested code following the architecture and plan.

Provide JSON:
{
  "implementation": "complete code",
  "tests": "comprehensive test suite",
  "documentation": "usage docs and comments",
  "edge_cases_handled": ["specific edge cases addressed"],
  "assumptions": ["any assumptions made during implementation"]
}"""
        )
        super().__init__(id=id)
    
    @handler
    async def handle(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        logger.info(f"[Developer] Implementing solution")
        response = await self.agent.run(request.messages, should_respond=request.should_respond)
        await ctx.send_message(
            AgentExecutorRequest(
                messages=[Message("user", text=response.text)],
                should_respond=True,
            )
        )


class VerifierAgent(Executor):
    """Verifies implementation against success criteria with self-correction."""
    
    agent: Any
    memory: MemorySystem
    
    def __init__(self, client: AzureOpenAIResponsesClient, memory: MemorySystem, id: str = "verifier"):
        self.agent = client.create_agent(
            name="VerifierAgent",
            instructions="""You are an Expert Verification and Quality Assurance Agent.

Responsibilities:
1. Validate implementation against success criteria
2. Test functionality thoroughly
3. Identify bugs and security issues
4. Provide specific, actionable fix instructions
5. Learn from issues to prevent recurrence

Respond with JSON:
{
  "verified": true/false,
  "test_results": [
    {"test": "what was tested", "passed": true/false, "details": "specifics"}
  ],
  "issues_found": [
    {
      "severity": "critical|high|medium|low",
      "issue": "description",
      "location": "where the issue is",
      "fix": "how to fix it",
      "lesson": "what to learn from this"
    }
  ],
  "quality_score": 0-100,
  "security_score": 0-100,
  "pass_criteria_met": ["which success criteria are satisfied"],
  "recommendations": ["improvements beyond requirements"]
}

Be thorough but fair. Provide constructive, actionable feedback."""
        )
        self.memory = memory
        super().__init__(id=id)
    
    @handler
    async def handle(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        logger.info(f"[Verifier] Validating solution")
        response = await self.agent.run(request.messages, should_respond=request.should_respond)
        
        # Extract and store learnings
        try:
            result = json.loads(response.text)
            if "issues_found" in result:
                for issue in result["issues_found"]:
                    if "lesson" in issue and issue.get("severity") in ["critical", "high"]:
                        self.memory.add_memory(
                            task_type="verification",
                            issue=issue["issue"],
                            solution=issue["fix"],
                            outcome=f"Severity: {issue['severity']}",
                            confidence=0.9
                        )
        except Exception as e:
            logger.warning(f"Failed to extract learnings: {e}")
        
        await ctx.send_message(
            AgentExecutorRequest(
                messages=[Message("user", text=response.text)],
                should_respond=True,
            )
        )


class AutonomousOrchestrator(Executor):
    """Orchestrates the Plan-Eval-Gather-Execute-Verify autonomous loop."""
    
    def __init__(self, memory: MemorySystem, id: str = "autonomous_orchestrator"):
        super().__init__(id=id)
        self.memory = memory
        self.max_iterations = int(os.getenv("MAX_AUTONOMOUS_ITERATIONS", "10"))
        self.current_iteration = 0
        self.execution_history: list[dict[str, Any]] = []
    
    @handler
    async def orchestrate(
        self,
        messages: list[Message],
        ctx: WorkflowContext[AgentExecutorRequest, str]
    ) -> None:
        """Run the autonomous PEGEV loop until task completion."""
        logger.info(f"[Orchestrator] Starting autonomous execution loop")
        
        user_task = messages[-1].text if messages else "No task specified"
        task_id = str(uuid4())
        
        # Phase 1: PLAN
        await ctx.yield_output(f"🎯 Task: {user_task}\n{'='*60}\n▶ Phase: PLAN")
        plan_request = AgentExecutorRequest(
            messages=[Message("user", text=f"Create an execution plan for:\n{user_task}")],
            should_respond=True
        )
        await ctx.send_message(plan_request)
        
        # The workflow will continue through other agents
        # This orchestrator monitors and guides the flow


def _build_static_workflow(
    max_supersteps: int,
    orchestrator: AutonomousOrchestrator,
    planner: PlannerAgent,
    evaluator: EvaluatorAgent,
    researcher: ResearcherAgent,
    architect: ArchitectAgent,
    developer: DeveloperAgent,
    verifier: VerifierAgent,
) -> Workflow:
    """Build the original PEGEV flow for backward compatibility."""
    return (
        WorkflowBuilder(max_iterations=max_supersteps)
        .set_start_executor(orchestrator)
        .add_edge(orchestrator, planner)       # Start with planning
        .add_edge(planner, evaluator)          # Evaluate the plan
        .add_edge(evaluator, researcher)       # Gather context
        .add_edge(researcher, architect)       # Design solution
        .add_edge(architect, developer)        # Implement
        .add_edge(developer, verifier)         # Verify
        .add_edge(verifier, evaluator)         # Evaluate results
        # Evaluator decides: complete or loop back to planner
        .build()
    )


def _build_dynamic_workflow(
    max_supersteps: int,
    orchestrator: AutonomousOrchestrator,
    planner: PlannerAgent,
    evaluator: EvaluatorAgent,
    researcher: ResearcherAgent,
    architect: ArchitectAgent,
    developer: DeveloperAgent,
    verifier: VerifierAgent,
    execution_order: list[str],
) -> Workflow:
    """Build a mode-aware workflow from a DAG execution order.

    Unknown roles are ignored, duplicate roles are de-duplicated, and if no
    valid roles are found the caller should fall back to the static workflow.
    """
    role_map: dict[str, Executor] = {
        "planner": planner,
        "evaluator": evaluator,
        "researcher": researcher,
        "architect": architect,
        "developer": developer,
        "verifier": verifier,
    }

    seen: set[str] = set()
    normalized_roles: list[str] = []
    ignored_roles: list[str] = []
    for role in execution_order:
        normalized = role.strip().lower()
        if not normalized or normalized in seen:
            continue
        if normalized not in role_map:
            ignored_roles.append(normalized)
            continue
        seen.add(normalized)
        normalized_roles.append(normalized)

    if ignored_roles:
        logger.warning(
            "Dynamic workflow ignored unsupported roles: %s",
            sorted(set(ignored_roles)),
        )

    if not normalized_roles:
        logger.warning(
            "Dynamic workflow received no valid roles; falling back to static workflow | requested_order=%s",
            execution_order,
        )
        return _build_static_workflow(
            max_supersteps,
            orchestrator,
            planner,
            evaluator,
            researcher,
            architect,
            developer,
            verifier,
        )

    builder = WorkflowBuilder(max_iterations=max_supersteps).set_start_executor(orchestrator)
    builder = builder.add_edge(orchestrator, role_map[normalized_roles[0]])

    for current_role, next_role in zip(normalized_roles, normalized_roles[1:]):
        builder = builder.add_edge(role_map[current_role], role_map[next_role])

    # Keep evaluator as a terminal quality gate if verifier is included but
    # evaluator is omitted from the dynamic order.
    if "verifier" in normalized_roles and "evaluator" not in normalized_roles:
        builder = builder.add_edge(verifier, evaluator)

    return builder.build()


def create_autonomous_workflow(execution_order: list[str] | None = None) -> Workflow:
    """Create the autonomous multi-agent workflow with PEGEV loop."""
    logger.info("Creating autonomous orchestrator workflow...")
    
    # Setup
    project_endpoint = get_project_endpoint()
    base_deployment = get_base_deployment_name()
    credential = get_credential_for_endpoint(project_endpoint)
    memory = MemorySystem()
    
    # Resolve models for each specialized agent
    planner_model = resolve_deployment_name("PLANNER_MODEL", DEFAULT_PLANNER_MODEL, base_deployment)
    evaluator_model = resolve_deployment_name("EVALUATOR_MODEL", DEFAULT_EVALUATOR_MODEL, base_deployment)
    researcher_model = resolve_deployment_name("RESEARCHER_MODEL", DEFAULT_RESEARCHER_MODEL, base_deployment)
    architect_model = resolve_deployment_name("ARCHITECT_MODEL", DEFAULT_ARCHITECT_MODEL, base_deployment)
    developer_model = resolve_deployment_name("DEVELOPER_MODEL", DEFAULT_DEVELOPER_MODEL, base_deployment)
    verifier_model = resolve_deployment_name("VERIFIER_MODEL", DEFAULT_VERIFIER_MODEL, base_deployment)
    
    logger.info(f"Model routing | planner={planner_model} evaluator={evaluator_model} "
                f"researcher={researcher_model} architect={architect_model} "
                f"developer={developer_model} verifier={verifier_model}")
    
    # Create clients
    planner_client = create_ai_client(project_endpoint, planner_model, credential)
    evaluator_client = create_ai_client(project_endpoint, evaluator_model, credential)
    researcher_client = create_ai_client(project_endpoint, researcher_model, credential)
    architect_client = create_ai_client(project_endpoint, architect_model, credential)
    developer_client = create_ai_client(project_endpoint, developer_model, credential)
    verifier_client = create_ai_client(project_endpoint, verifier_model, credential)
    
    # Create agents
    orchestrator = AutonomousOrchestrator(memory, id="orchestrator")
    planner = PlannerAgent(planner_client, memory, id="planner")
    evaluator = EvaluatorAgent(evaluator_client, id="evaluator")
    researcher = ResearcherAgent(researcher_client, id="researcher")
    architect = ArchitectAgent(architect_client, id="architect")
    developer = DeveloperAgent(developer_client, id="developer")
    verifier = VerifierAgent(verifier_client, memory, id="verifier")
    
    max_supersteps = int(os.getenv("MAX_AUTONOMOUS_SUPERSTEPS", "7"))

    if execution_order:
        logger.info("Building dynamic autonomous workflow | order=%s", execution_order)
        workflow = _build_dynamic_workflow(
            max_supersteps,
            orchestrator,
            planner,
            evaluator,
            researcher,
            architect,
            developer,
            verifier,
            execution_order,
        )
    else:
        workflow = _build_static_workflow(
            max_supersteps,
            orchestrator,
            planner,
            evaluator,
            researcher,
            architect,
            developer,
            verifier,
        )
    
    logger.info("Autonomous workflow created successfully")
    return workflow


async def run_autonomous_cli():
    """Run autonomous orchestrator in CLI mode."""
    print("=" * 70)
    print("AUTONOMOUS MULTI-AGENT ORCHESTRATOR")
    print("Plan → Evaluate → Gather → Execute → Verify → Learn Loop")
    print("=" * 70)
    print()
    
    workflow = create_autonomous_workflow()
    
    task = input("Enter your task: ").strip() or """Create a secure user authentication API with:
- JWT token-based auth
- Rate limiting
- Password strength validation
- Comprehensive tests
- Security best practices"""
    
    print(f"\n🚀 Starting autonomous execution...\n")
    
    async for event in workflow.run_stream([Message("user", text=task)]):
        if isinstance(event, WorkflowOutputEvent):
            print(f"{event.data}")
        elif isinstance(event, WorkflowStatusEvent):
            print(f"[Status] {event.state}")


if __name__ == "__main__":
    asyncio.run(run_autonomous_cli())
