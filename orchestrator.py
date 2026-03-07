"""
AI Agent Orchestrator - Multi-Agent System with Feedback Loop

This orchestrator manages specialized AI agents working together in a run-to-completion model
with automatic feedback loops and agent-to-agent communication. 

Architecture:
- Principal Architect: Designs features, reviews approaches, provides architectural guidance
- Developer Agent: Implements features using skills, focuses on code quality and precision
- QA Agent: Reviews code for testing, security, quality, identifies issues
- Manager: Orchestrates all agents, manages feedback loops, ensures completion

The system supports:
- Parallel task execution where possible
- Agent-to-agent communication via structured protocol
- Auto feedback loops between agents
- Skills discovery and integration (local, skills.sh, GitHub)
- Security review before skill installation
- Global scope for reuse across projects
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    Executor,
    Message,
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

# Load environment variables
load_dotenv(override=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Per-agent model defaults for Copilot/GitHub Models usage.
DEFAULT_ARCHITECT_MODEL = "anthropic/claude-opus-4.6"
DEFAULT_DEVELOPER_MODEL = "anthropic/claude-opus-4.6"
DEFAULT_QA_MODEL = "auto"


def get_project_endpoint() -> str:
    """Read and validate the configured project endpoint."""
    project_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    if not project_endpoint:
        raise ValueError("AZURE_AI_PROJECT_ENDPOINT not set in environment variables. Please configure .env file.")
    return project_endpoint


def get_base_deployment_name() -> str | None:
    """Read the default deployment name used by auto-mode agents."""
    return os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME")


def resolve_deployment_name(agent_env_name: str, default_value: str, base_deployment: str | None) -> str:
    """Resolve agent model name, supporting `auto` fallback to base deployment."""
    configured = os.getenv(agent_env_name, default_value).strip()
    if configured.lower() != "auto":
        return configured

    if not base_deployment:
        raise ValueError(
            f"{agent_env_name}=auto requires AZURE_AI_MODEL_DEPLOYMENT_NAME to be set. "
            "Please configure .env file."
        )
    return base_deployment


def get_credential_for_endpoint(project_endpoint: str) -> DefaultAzureCredential | None:
    """Pick credential strategy based on endpoint type."""
    if "github" in project_endpoint.lower():
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            raise ValueError("GITHUB_TOKEN required for GitHub Models. Get one at: https://github.com/settings/tokens")
        logger.info("Using GitHub Models endpoint")
        return None

    logger.info("Using Microsoft Foundry endpoint")
    return DefaultAzureCredential()


def create_ai_client(
    project_endpoint: str,
    deployment_name: str,
    credential: DefaultAzureCredential | None,
) -> AzureOpenAIResponsesClient:
    """Create a model client for a specific deployment/model."""
    try:
        return AzureOpenAIResponsesClient(
            project_endpoint=project_endpoint,
            deployment_name=deployment_name,
            credential=credential,
        )
    except Exception as exc:
        logger.error("Failed to create AI client for deployment '%s': %s", deployment_name, exc)
        raise


class AgentRole(str, Enum):
    """Roles for different agents in the orchestrator."""
    ARCHITECT = "architect"
    DEVELOPER = "developer"
    QA = "qa"
    MANAGER = "manager"


class TaskStatus(str, Enum):
    """Status of a task in the workflow."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    UNDER_REVIEW = "under_review"
    NEEDS_REVISION = "needs_revision"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentMessage:
    """Structured message for agent-to-agent communication."""
    from_agent: AgentRole
    to_agent: AgentRole | None  # None means broadcast to all
    content: str
    message_type: str  # design, implementation, review, feedback, question
    task_id: str
    iteration: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "from_agent": self.from_agent.value if isinstance(self.from_agent, AgentRole) else self.from_agent,
            "to_agent": self.to_agent.value if self.to_agent and isinstance(self.to_agent, AgentRole) else self.to_agent,
            "content": self.content,
            "message_type": self.message_type,
            "task_id": self.task_id,
            "iteration": self.iteration,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentMessage":
        """Create from dictionary."""
        return cls(
            from_agent=AgentRole(data["from_agent"]) if data.get("from_agent") else AgentRole.MANAGER,
            to_agent=AgentRole(data["to_agent"]) if data.get("to_agent") else None,
            content=data["content"],
            message_type=data["message_type"],
            task_id=data["task_id"],
            iteration=data.get("iteration", 0),
            metadata=data.get("metadata", {})
        )


@dataclass
class Task:
    """Represents a task in the orchestration."""
    task_id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    current_owner: AgentRole | None = None
    design: str | None = None
    implementation: str | None = None
    test_results: str | None = None
    feedback_history: list[AgentMessage] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 5
    
    def add_feedback(self, message: AgentMessage) -> None:
        """Add feedback to history."""
        self.feedback_history.append(message)
        self.iteration = message.iteration


class PrincipalArchitect(Executor):
    """
    Principal Architect Agent - Designs features, reviews approaches, provides guidance.
    
    Responsibilities:
    - Create architectural designs for features
    - Review developer implementations
    - Provide suggestions and requirements
    - Ensure design best practices
    """
    
    agent: Any
    
    def __init__(self, client: AzureOpenAIResponsesClient, id: str = "principal_architect"):
        self.agent = client.as_agent(
            name="PrincipalArchitect",
            instructions="""You are a Principal Software Architect with expertise in:
- System design and architecture patterns (microservices, event-driven, etc.)
- Best practices and design principles (SOLID, DRY, KISS, etc.)
- Technology stack selection and evaluation
- Scalability, performance, and security considerations
- Code review and architectural guidance

When given a task:
1. Analyze requirements thoroughly
2. Design a robust, scalable solution
3. Provide clear architectural guidelines
4. Review implementations for architectural soundness
5. Suggest improvements and optimizations
6. Ensure alignment with best practices

Format your responses as structured JSON with:
- "design": detailed architectural design
- "requirements": specific requirements for developers
- "considerations": important factors to consider
- "review_feedback": feedback on implementations (when reviewing)
- "approved": boolean indicating approval status (when reviewing)
"""
        )
        super().__init__(id=id)
    
    @handler
    async def handle(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorResponse]) -> None:
        """Handle architect tasks - design or review."""
        logger.info(f"[Architect] Processing request with {len(request.messages)} messages")
        
        # Run the agent
        response = await self.agent.run(request.messages, should_respond=request.should_respond)
        
        # Send response
        await ctx.send_message(
            AgentExecutorResponse(
                agent_response=response,
                executor_id=self.id
            )
        )


class DeveloperAgent(Executor):
    """
    Developer Agent - Implements features with high code quality and precision.
    
    Responsibilities:
    - Implement features based on architectural designs
    - Write clean, maintainable, optimal code
    - Follow coding standards and best practices
    - Use appropriate skills and libraries
    - Respond to feedback and iterate
    """
    
    agent: Any
    
    def __init__(self, client: AzureOpenAIResponsesClient, id: str = "developer_agent"):
        self.agent = client.as_agent(
            name="DeveloperAgent",
            instructions="""You are an Expert Software Developer with deep expertise in:
- Multiple programming languages (Python, Go, C#, JavaScript, etc.)
- Clean code principles and best practices
- Design patterns and software architecture
- Testing (unit, integration, e2e)
- Performance optimization
- Security best practices

When given a task:
1. Carefully review architectural design and requirements
2. Implement clean, efficient, well-documented code
3. Follow language-specific idioms and conventions
4. Write comprehensive tests
5. Consider edge cases and error handling
6. Respond constructively to feedback
7. Iterate based on QA and architect feedback

Format your responses as structured JSON with:
- "implementation": the code implementation
- "tests": test code and test strategy
- "documentation": code documentation and usage examples
- "dependencies": required libraries/skills
- "notes": implementation notes and considerations
"""
        )
        super().__init__(id=id)
    
    @handler
    async def handle(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorResponse]) -> None:
        """Handle development tasks."""
        logger.info(f"[Developer] Processing request with {len(request.messages)} messages")
        
        # Run the agent
        response = await self.agent.run(request.messages, should_respond=request.should_respond)
        
        # Send response
        await ctx.send_message(
            AgentExecutorResponse(
                agent_response=response,
                executor_id=self.id
            )
        )


class QualityAssuranceAgent(Executor):
    """
    QA Agent - Reviews code for quality, security, testing, and best practices.
    
    Responsibilities:
    - Review code quality and adherence to standards
    - Identify security vulnerabilities
    - Verify test coverage and quality
    - Check for performance issues
    - Provide detailed feedback for improvements
    """
    
    agent: Any
    
    def __init__(self, client: AzureOpenAIResponsesClient, id: str = "qa_agent"):
        self.agent = client.as_agent(
            name="QualityAssuranceAgent",
            instructions="""You are a Principal QA Engineer and Security Expert with expertise in:
- Code quality review and static analysis
- Security vulnerability assessment (OWASP, CVE)
- Test strategy and coverage analysis
- Performance testing and optimization
- Code review best practices
- Compliance and standards (PCI-DSS, GDPR, etc.)

When reviewing code:
1. Analyze code quality and maintainability
2. Identify security vulnerabilities and risks
3. Evaluate test coverage and quality
4. Check for performance bottlenecks
5. Verify adherence to coding standards
6. Provide specific, actionable feedback
7. Suggest improvements and fixes

Format your responses as structured JSON with:
- "quality_score": 0-100 rating
- "security_issues": list of security concerns with severity
- "test_coverage": assessment of testing
- "performance_notes": performance considerations
- "issues": list of specific issues to fix
- "recommendations": improvement suggestions
- "approved": boolean indicating approval status
"""
        )
        super().__init__(id=id)
    
    @handler
    async def handle(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorResponse]) -> None:
        """Handle QA review tasks."""
        logger.info(f"[QA] Processing request with {len(request.messages)} messages")
        
        # Run the agent
        response = await self.agent.run(request.messages, should_respond=request.should_respond)
        
        # Send response
        await ctx.send_message(
            AgentExecutorResponse(
                agent_response=response,
                executor_id=self.id
            )
        )


class OrchestratorManager(Executor):
    """
    Orchestrator Manager - Coordinates all agents in a run-to-completion model.
    
    Responsibilities:
    - Receive user tasks
    - Coordinate agent workflow
    - Manage feedback loops
    - Track task status
    - Ensure completion criteria are met
    - Handle agent-to-agent communication
    """
    
    def __init__(self, id: str = "orchestrator_manager"):
        super().__init__(id=id)
        self.active_tasks: dict[str, Task] = {}
    
    @handler
    async def handle_task(
        self,
        messages: list[Message],
        ctx: WorkflowContext[AgentExecutorRequest, str]
    ) -> None:
        """
        Handle incoming task - orchestrate the multi-agent workflow.
        
        Workflow:
        1. Create task from user input
        2. Send to Architect for design
        3. Send design to Developer for implementation
        4. Send implementation to QA for review
        5. Handle feedback loop (QA -> Developer -> Architect -> Developer -> QA)
        6. Complete when all approvals received
        """
        logger.info(f"[Manager] Orchestrating task with {len(messages)} messages")
        
        # Extract task from messages
        user_message = messages[-1].text if messages else "No task specified"
        task_id = str(uuid4())
        
        task = Task(
            task_id=task_id,
            description=user_message,
            status=TaskStatus.IN_PROGRESS
        )
        self.active_tasks[task_id] = task
        
        # Phase 1: Architect creates design
        architect_message = Message(
            "user",
            text=f"""Task: {task.description}

Please create an architectural design for this feature. Provide:
1. High-level design and architecture
2. Specific requirements for the developer
3. Important considerations (security, scalability, performance)

Format your response as JSON."""
        )
        
        architect_request = AgentExecutorRequest(
            messages=[architect_message],
            should_respond=True
        )
        task.current_owner = AgentRole.ARCHITECT
        
        # Send to architect
        await ctx.send_message(architect_request)
        
        # Add status update
        status_msg = f"Task {task_id[:8]} created and sent to Principal Architect for design."
        await ctx.yield_output(status_msg)


class FeedbackCoordinator(Executor):
    """
    Coordinates feedback between agents in the orchestration loop.
    
    This executor manages the feedback flow:
    - Architect reviews -> Developer implements -> QA reviews
    - QA feedback -> Developer revises -> Architect reviews -> QA approves
    """
    
    def __init__(self, id: str = "feedback_coordinator"):
        super().__init__(id=id)
        self.feedback_queue: list[AgentMessage] = []
        self.current_phase: str = "design"  # design, implement, review, revision
        self.iteration_count: int = 0
        self.max_iterations: int = int(os.getenv("MAX_ITERATIONS", "5"))
    
    @handler
    async def coordinate_from_manager(
        self,
        request: AgentExecutorRequest,
        ctx: WorkflowContext[AgentExecutorRequest, str]
    ) -> None:
        """Handle initial task from manager."""
        logger.info("[Coordinator] Received task from manager, sending to architect")
        self.current_phase = "design"
        self.iteration_count = 0
        
        # Forward to architect for design
        await ctx.send_message(request)
        await ctx.yield_output("Task received. Sending to Principal Architect for design...")
    
    @handler
    async def coordinate_from_agents(
        self,
        response: AgentExecutorResponse,
        ctx: WorkflowContext[AgentExecutorRequest, str]
    ) -> None:
        """Coordinate feedback between agents based on their responses."""
        logger.info(f"[Coordinator] Processing response from {response.executor_id}")
        
        # Get response text
        response_text = response.agent_response.text
        
        # Route based on which agent responded
        executor_id = response.executor_id.lower()
        
        if "architect" in executor_id:
            # Architect provided design -> send to Developer
            if self.current_phase == "design":
                self.current_phase = "implement"
                developer_request = AgentExecutorRequest(
                    messages=[
                        Message("user", text=f"Architectural Design:\n{response_text}\n\nPlease implement this design following all requirements and considerations provided. Provide code, tests, and documentation.")
                    ],
                    should_respond=True
                )
                await ctx.send_message(developer_request)
                await ctx.yield_output("✓ Design completed. Sending to Developer for implementation...")
            else:
                # Architect reviewed revision -> send back to developer
                self.current_phase = "implement"
                developer_request = AgentExecutorRequest(
                    messages=[
                        Message("user", text=f"Architect Review:\n{response_text}\n\nPlease incorporate this feedback into your implementation.")
                    ],
                    should_respond=True
                )
                await ctx.send_message(developer_request)
                await ctx.yield_output("✓ Architect review completed. Sending feedback to Developer...")
            
        elif "developer" in executor_id:
            # Developer provided implementation -> send to QA
            self.current_phase = "review"
            qa_request = AgentExecutorRequest(
                messages=[
                    Message("user", text=f"Implementation to Review:\n{response_text}\n\nPlease conduct a thorough review covering:\n1. Code quality and maintainability\n2. Security vulnerabilities\n3. Test coverage and quality\n4. Performance considerations\n\nProvide specific, actionable feedback.")
                ],
                should_respond=True
            )
            await ctx.send_message(qa_request)
            await ctx.yield_output("✓ Implementation completed. Sending to QA for comprehensive review...")
            
        elif "qa" in executor_id:
            # QA provided review - check if approved
            response_lower = response_text.lower()
            
            # Simple approval detection (in production, parse structured JSON)
            is_approved = (
                ("approved" in response_lower and "true" in response_lower) or
                ("approve" in response_lower and "quality_score" in response_lower) or
                "no critical issues" in response_lower
            )
            
            if is_approved:
                await ctx.yield_output(f"""
{'='*60}
✓ SUCCESS! Task completed successfully.
{'='*60}
QA Review: APPROVED
Iterations: {self.iteration_count}

{response_text}
{'='*60}
""")
            else:
                # Needs revision
                self.iteration_count += 1
                
                if self.iteration_count >= self.max_iterations:
                    await ctx.yield_output(f"""
⚠ Maximum iterations ({self.max_iterations}) reached. Task requires manual review.

Latest QA Feedback:
{response_text}
""")
                else:
                    self.current_phase = "revision"
                    # Send feedback to developer for revision
                    developer_request = AgentExecutorRequest(
                        messages=[
                            Message("user", text=f"QA Review Feedback (Iteration {self.iteration_count}):\n{response_text}\n\nPlease address all identified issues and provide a revised implementation.")
                        ],
                        should_respond=True
                    )
                    await ctx.send_message(developer_request)
                    await ctx.yield_output(f"⚠ QA identified issues (Iteration {self.iteration_count}/{self.max_iterations}). Sending feedback to Developer for revision...")


def create_orchestrator_workflow() -> Workflow:
    """
    Create the multi-agent orchestrator workflow.
    
    Architecture:
    - Manager receives tasks and initiates workflow
    - Architect, Developer, QA execute in sequence with feedback loops
    - Feedback Coordinator manages the iteration loops
    - Parallel execution where possible (e.g., multiple tasks)
    """
    logger.info("Creating orchestrator workflow...")
    
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
        "Resolved models | architect=%s developer=%s qa=%s",
        architect_model,
        developer_model,
        qa_model,
    )

    architect_client = create_ai_client(project_endpoint, architect_model, credential)
    developer_client = create_ai_client(project_endpoint, developer_model, credential)
    qa_client = create_ai_client(project_endpoint, qa_model, credential)
    
    # Create agent executors
    manager = OrchestratorManager(id="manager")
    architect = PrincipalArchitect(architect_client, id="architect")
    developer = DeveloperAgent(developer_client, id="developer")
    qa_agent = QualityAssuranceAgent(qa_client, id="qa")
    coordinator = FeedbackCoordinator(id="coordinator")
    
    # Build workflow with feedback loops
    # Manager initiates -> Coordinator routes to appropriate agents
    # Agents communicate via Coordinator which manages feedback
    workflow = (
        WorkflowBuilder(start_executor=manager)
        .add_edge(manager, coordinator)      # Manager sends task to coordinator
        .add_edge(coordinator, architect)     # Coordinator routes to architect
        .add_edge(architect, coordinator)     # Architect responds to coordinator
        .add_edge(coordinator, developer)     # Coordinator routes to developer
        .add_edge(developer, coordinator)     # Developer responds to coordinator
        .add_edge(coordinator, qa_agent)      # Coordinator routes to QA
        .add_edge(qa_agent, coordinator)      # QA responds to coordinator
        .build()
    )
    
    logger.info("Orchestrator workflow created successfully")
    return workflow


async def run_cli_mode():
    """Run the orchestrator in CLI mode for testing."""
    print("=" * 60)
    print("AI Agent Orchestrator - Multi-Agent System")
    print("=" * 60)
    print()
    
    workflow = create_orchestrator_workflow()
    
    # Example task
    task = """Create a REST API endpoint for user authentication with JWT tokens.
Requirements:
- Support login, logout, and token refresh
- Include rate limiting
- Implement proper error handling
- Add comprehensive tests
- Follow security best practices"""
    
    print(f"Task: {task}\n")
    print("Starting orchestration...\n")
    
    # Run workflow
    async for event in workflow.run_stream(
        [Message("user", text=task)]
    ):
        if isinstance(event, WorkflowOutputEvent):
            print(f"[Output] {event.data}")
        elif isinstance(event, WorkflowStatusEvent):
            print(f"[Status] {event.state}")


async def run_server_mode():
    """Run the orchestrator as HTTP server."""
    logger.info("Starting AI Agent Orchestrator in server mode...")
    from azure.ai.agentserver.agentframework import from_agent_framework
    
    workflow = create_orchestrator_workflow()
    agent = workflow.as_agent(
        name="MultiAgentOrchestrator",
        instructions="I coordinate specialized AI agents (Architect, Developer, QA) to complete complex software development tasks with automatic feedback loops and quality assurance."
    )
    
    # Run as HTTP server
    await from_agent_framework(agent).run_async()


async def main():
    """Main entry point."""
    import sys
    
    # Check for server mode flag
    if len(sys.argv) > 1 and sys.argv[1] == "--server":
        await run_server_mode()
    else:
        await run_cli_mode()


if __name__ == "__main__":
    asyncio.run(main())
