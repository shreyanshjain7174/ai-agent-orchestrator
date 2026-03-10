# AI Agent Orchestrator

[![MCP Server](https://img.shields.io/badge/MCP-Server-blue)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Smithery](https://img.shields.io/badge/Smithery-MCP_Registry-green)](https://smithery.ai/server/ai-agent-orchestrator)

A sophisticated multi-agent orchestration system that coordinates specialized AI agents to complete complex software development tasks through automatic feedback loops and agent-to-agent communication.

**🚀 Key Features:**
- 🤖 **6 Specialized AI Agents** - Plan, Evaluate, Research, Architect, Develop, Verify
- 🔄 **Self-Healing PEGEV Loop** - Autonomous execution with iterative improvement
- 🧭 **Dynamic Team Planning** - Skill discovery, classification, and adaptive DAG previews
- 🧠 **Persistent Memory** - Learns from mistakes and improves over time
- 🛠️ **GitHub Copilot Integration** - Available as MCP server with 8 tools
- ⚡ **Autonomous Execution** - Handles "design", "fix_bug", "debug", "implement" tasks
- 🔌 **Highly Extensible** - Easy model swapping, custom agents, pluggable memory

## Quick Start

### Install via Smithery (Recommended)

To install AI Agent Orchestrator for Claude Desktop automatically via [Smithery](https://smithery.ai/server/ai-agent-orchestrator):

```bash
npx -y @smithery/cli install ai-agent-orchestrator --client claude
```

> **Note:** When used via GitHub Copilot or Claude Desktop, environment variables are not required. The host application provides model access automatically.

### Manual Installation

1. Clone and setup:
   ```bash
   git clone https://github.com/shreyanshjain7174/ai-agent-orchestrator.git
   cd ai-agent-orchestrator
   python -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```

2. Configure `.env` (only required for standalone usage):
   ```bash
   cp .env.example .env
   # Edit .env with your GitHub token or Azure credentials
   ```

3. Run as MCP server:
   ```bash
   uv run --prerelease=allow --with "mcp[cli]>=1.6.0,<2.0.0" --with-requirements requirements.txt mcp run mcp_server.py
   ```

A sophisticated multi-agent orchestration system that coordinates specialized AI agents to complete complex software development tasks through automatic feedback loops and agent-to-agent communication.

## Overview

This orchestrator manages a team of specialized AI agents working together in a run-to-completion model:

- **Principal Architect**: Designs features, reviews approaches, provides architectural guidance
- **Developer Agent**: Implements features with high code quality, precision, and optimal solutions
- **QA Agent**: Reviews code for testing, security, quality, and identifies issues
- **Orchestrator Manager**: Coordinates all agents, manages feedback loops, ensures task completion

## Architecture

### Legacy Mode (Simple Feedback Loop)

```
User Task
    ↓
Orchestrator Manager
    ↓
Principal Architect (Design)
    ↓
Developer Agent (Implement)
    ↓
QA Agent (Review)
    ↓
Feedback Coordinator
    ↓ (if issues found)
Developer Agent (Revise) → Architect (Review) → QA (Re-review)
    ↓ (approved)
Task Completed
```

### Autonomous Mode (Self-Healing PEGEV Loop) ⚡ NEW

The autonomous orchestrator implements a **Plan-Eval-Gather-Execute-Verify** loop with self-healing and continuous learning:

```
User Task: "Design something" / "Fix this bug" / "Debug this issue"
    ↓
┌─────────────────────────────────────────────────────────┐
│  AUTONOMOUS LOOP (continues until success)              │
│                                                          │
│  1. PLAN      → Planner Agent breaks down task         │
│  2. EVALUATE  → Evaluator assesses if ready            │
│  3. GATHER    → Researcher collects missing context     │
│  4. EXECUTE   → Architect + Developer implement         │
│  5. VERIFY    → Verifier tests & self-corrects         │
│  6. EVALUATE  → Check success criteria                  │
│       ↓ (if failed, loop back to PLAN with learnings)  │
│  7. LEARN     → Store lessons in memory system          │
└─────────────────────────────────────────────────────────┘
    ↓
Task Completed (Verified & Validated)
```

**Autonomous Agents:**
- **PlannerAgent**: Strategic planning, task decomposition, risk assessment
- **EvaluatorAgent**: Progress assessment, decision-making, quality gating
- **ResearcherAgent**: Context gathering, solution research, best practices
- **ArchitectAgent**: Solution design, architecture planning
- **DeveloperAgent**: Code implementation, testing
- **VerifierAgent**: Quality assurance, bug detection, self-correction

**Self-Healing Capabilities:**
- Agents learn from mistakes and store lessons in persistent memory
- Past failures inform future planning and execution
- Automatic retry with improved strategies
- Bug fixes trigger memory updates to prevent recurrence

**When to Use Autonomous Mode:**
- Complex multi-step tasks requiring iteration
- "Design something" requests
- "Fix this bug" or debugging scenarios
- Tasks where requirements may evolve during execution
- Situations requiring self-correction and adaptation

### Key Features

- **Multi-Agent Collaboration**: Specialized agents work together seamlessly
- **Automatic Feedback Loops**: Agents iterate based on feedback until quality standards are met
- **Agent-to-Agent Communication**: Structured protocol for clear communication
- **Parallel Task Execution**: Multiple tasks can be processed concurrently
- **Skills Integration**: Discovers and uses appropriate skills from local libraries or GitHub
- **Security Review**: All skills undergo security review before installation
- **Global Scope**: Reusable across different projects
- **Production-Ready**: HTTP server mode with debugging support

## Prerequisites

    **Python 3.10 or higher** (REQUIRED - [Download here](https://www.python.org/downloads/))
- Azure CLI (for authentication) or GitHub Personal Access Token
- Microsoft Foundry project (recommended) or GitHub Models (free tier)

    > **Important**: Python 3.10+ must be installed and available in your PATH. Verify with `python --version` or `python3 --version`.

## Installation

    **Note**: These instructions assume Python is installed. If you don't have Python, install it first from [python.org](https://www.python.org/downloads/).

1. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   # or
   source .venv/bin/activate  # Linux/Mac
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment:**
   ```bash
   # Copy the example environment file
   copy .env.example .env  # Windows
   # or
   cp .env.example .env  # Linux/Mac
   
   # Edit .env and add your configuration
   ```

4. **(Copilot MCP) Register specialized tools server:**
    ```bash
    uv run --prerelease=allow --with "mcp[cli]>=1.6.0,<2.0.0" --with-requirements requirements.txt mcp run mcp_server.py
    ```
    This exposes specialized tools (`architect_design`, `developer_implement`, `qa_review`, `orchestrate_task`) to MCP clients.

### Configuration Options

#### Dynamic Discovery Controls (optional)

Use these when tuning runtime skill discovery behavior:

```bash
# Optional JSON skill inventory injected at runtime
AI_ORCHESTRATOR_SKILLS_JSON=[{"id":"python-pro","name":"Python Pro","description":"Python coding expert","source":"env","input_schema_summary":"{task: string}","health":"healthy"}]

# Discovery resilience controls
AI_ORCHESTRATOR_DISCOVERY_RETRY_ATTEMPTS=1
AI_ORCHESTRATOR_DISCOVERY_TTL_SECONDS=60

# Classification confidence threshold (0.0-1.0)
AI_ORCHESTRATOR_CLASSIFIER_MIN_CONFIDENCE=0.6

# Dynamic composition guardrail
AI_ORCHESTRATOR_MAX_TEAM_SIZE=6

# DAG planner controls
# dynamic (default): role-aware adaptive dependencies
# static: mode-template dependencies
AI_ORCHESTRATOR_DAG_MODE=dynamic

# Maximum DAG nodes (minimum enforced to 1)
AI_ORCHESTRATOR_MAX_DAG_NODES=24
```

Discovery schema is normalized to: `id`, `name`, `description`, `source`, `input_schema_summary`, and `health`.
If fresh discovery fails, the system gracefully falls back to cached inventory.

#### Migration and Backward Compatibility (Phase 8)

Legacy settings continue to work, but they now emit deprecation warnings and are translated to canonical dynamic settings.

- Migration matrix: `docs/migration-matrix.md`
- Planning/runtime legacy fallback diagnostics are included in `autonomous_execute` response under `fallback.diagnostics`
- Safe rollout recommendation: use `execution_mode=auto` with `enable_legacy_fallback=true`

#### Option 1: GitHub Models (Free Tier - Development)

Get a GitHub Personal Access Token:
1. Go to https://github.com/settings/tokens
2. Generate a new token with appropriate scopes
3. Add to `.env`:
   ```
   GITHUB_TOKEN=your_token_here
   AZURE_AI_PROJECT_ENDPOINT=https://models.github.ai/inference/
   AZURE_AI_MODEL_DEPLOYMENT_NAME=openai/gpt-5.1

    # Specialized model routing for Copilot tools
    ARCHITECT_MODEL=anthropic/claude-opus-4.6
    DEVELOPER_MODEL=anthropic/claude-opus-4.6
    QA_MODEL=auto
   ```

`auto` means that role falls back to `AZURE_AI_MODEL_DEPLOYMENT_NAME`.

#### Option 2: Microsoft Foundry (Recommended - Production)

1. **Explore models in AI Toolkit:**
   - Open VS Code Command Palette (`Ctrl+Shift+P`)
   - Run: `AI Toolkit: View Model Catalog`
   - Filter by `Microsoft Foundry`
   - Browse available models

2. **Deploy models:**
   Recommended models for each agent:
   - **Architect**: `gpt-5.1` (reasoning) or `o3` (advanced reasoning)
   - **Developer**: `gpt-5.1-codex` (coding) or `claude-sonnet-4-5` (coding + agents)
   - **QA**: `claude-opus-4-5` (leader in agents) or `o3` (reasoning)

3. **Get your project endpoint:**
   - From Microsoft Foundry portal
   - Update `.env` with your endpoint and model deployment name

## Usage

### CLI Mode (Testing)

Run the orchestrator with a sample task:

```bash
python orchestrator.py
```

This will process a predefined task through the full agent workflow.

### HTTP Server Mode (Production)

Run as an HTTP server for production use:

```bash
python orchestrator.py --server
```

The server will be available at `http://localhost:8087` by default.

### MCP Server Mode (Copilot Tools)

Run the MCP server for specialized agents:

```bash
uv run --prerelease=allow --with "mcp[cli]>=1.6.0,<2.0.0" --with-requirements requirements.txt mcp run mcp_server.py
```

#### Available MCP Tools

**Legacy Mode (Direct agent calls):**
- `architect_design` - Generate architecture and requirements
- `developer_implement` - Implement from architecture
- `qa_review` - Review code quality and security
- `orchestrate_task` - Run simple feedback loop
- `show_model_routing` - Display model configuration

**Autonomous Mode (Recommended for complex tasks):**
- `autonomous_execute` ⚡ - Run self-healing PEGEV loop
    - Modes: `auto`, `design`, `fix_bug`, `debug`, `implement`, `refactor`
        - Execution paths: `legacy`, `dynamic`, `auto` (default)
            - `legacy`: run legacy `orchestrate_task` directly
            - `dynamic`: dynamic planning/execution only (no legacy fallback)
            - `auto`: dynamic-first with optional legacy fallback
    - Supports bounded loop retries with `max_loops` (1-5)
        - Supports safe legacy fallback with `enable_legacy_fallback=true` when `execution_mode=auto`
  - Auto-iterates until verified success
  - Learns from mistakes and self-corrects
- `dynamic_plan_preview` - Preview dynamic skill classification, team composition, and DAG order before execution
- `get_learnings` - View past learnings from memory
- `show_autonomous_capabilities` - Display system info

**Example Usage in Copilot Chat:**
```
User: "Use autonomous_execute to design a secure user authentication API"
User: "Fix this bug using autonomous_execute mode=fix_bug"
User: "Run autonomous_execute execution_mode=legacy for strict legacy routing"
User: "Run autonomous_execute mode=debug execution_mode=dynamic"
User: "Preview the dynamic team with dynamic_plan_preview mode=auto"
User: "Show me what the agents have learned with get_learnings"
```

### Debugging in VS Code

Press `F5` or go to Run and Debug → `Debug Local Agent/Workflow HTTP Server`

This will:
1. Start the HTTP server with debugging enabled
2. Open the AI Toolkit Agent Inspector for interactive testing
3. Allow you to set breakpoints and debug agent interactions

## Model Recommendations

Based on your needs, here are recommended models for each agent:

### Principal Architect
- **Best**: `gpt-5.1` - Superior reasoning and design capabilities
- **Alternative**: `o3` - Advanced reasoning for complex architectures
- **Premium**: `claude-opus-4-5` - Industry leader for complex agent workflows

### Developer Agent
- **Best**: `gpt-5.1-codex` - Advanced coding with repository awareness
- **Alternative**: `gpt-5.1-codex-max` - Maximum efficiency for complex workflows
- **Premium**: `claude-sonnet-4-5` - Excellent for coding and agent workflows

### QA Agent
- **Best**: `o3` - Advanced reasoning for security and quality analysis
- **Alternative**: `gpt-5.1` - Strong analytical capabilities
- **Premium**: `claude-opus-4-5` - Industry leader in code review and agents

## Workflow Example

```python
# Example task sent to the orchestrator
task = """
Create a REST API endpoint for user authentication with JWT tokens.
Requirements:
- Support login, logout, and token refresh
- Include rate limiting
- Implement proper error handling
- Add comprehensive tests
- Follow security best practices
"""

# Workflow execution:
# 1. Manager receives task
# 2. Architect designs the solution (authentication architecture, JWT strategy)
# 3. Developer implements based on design
# 4. QA reviews for security, quality, testing
# 5. If issues found: Developer revises → Architect reviews → QA re-reviews
# 6. Loop continues until QA approves
# 7. Task completed with high-quality output
```

## Agent Communication Protocol

Agents communicate via structured `AgentMessage` objects:

```python
{
    "from_agent": "architect",
    "to_agent": "developer",
    "content": "Please implement the authentication service...",
    "message_type": "design",  # design, implementation, review, feedback, question
    "task_id": "uuid",
    "iteration": 1,
    "metadata": {
        "priority": "high",
        "requirements": [...]
    }
}
```

## Customization

### Adding New Agents

Create a new agent executor:

```python
class NewAgent(Executor):
    agent: Agent
    
    def __init__(self, client: AzureOpenAIResponsesClient, id: str = "new_agent"):
        self.agent = client.as_agent(
            name="NewAgent",
            instructions="Your agent instructions here..."
        )
        super().__init__(id=id)
    
    @handler
    async def handle(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorResponse]) -> None:
        response = await self.agent.run(request.messages, should_respond=request.should_respond)
        await ctx.send_message(AgentExecutorResponse(agent_response=response, executor_id=self.id))
```

### Modifying Workflow

Update the `create_orchestrator_workflow()` function to adjust agent connections:

```python
workflow = (
    WorkflowBuilder(start_executor=manager)
    .add_edge(manager, architect)
    .add_edge(architect, developer)
    .add_edge(developer, qa_agent)
    .add_edge(qa_agent, new_agent)  # Add your agent
    .build()
)
```

## Skills Integration

The orchestrator supports skills discovery and integration:

1. **Local Skills**: Automatically discovered from installed packages
2. **skills.sh**: Search and install skills from skills.sh catalog
3. **GitHub**: Search and install skills from GitHub repositories

All skills undergo security review before installation.

## Production Deployment

For production deployment to Microsoft Foundry:

1. Ensure HTTP server mode is configured
2. Use the AI Toolkit deployment feature:
   - Open Command Palette (`Ctrl+Shift+P`)
   - Run: `Microsoft Foundry: Deploy Hosted Agent`
   - Follow the deployment wizard

## Troubleshooting

### Common Issues

**Module not found errors:**
```bash
# Ensure virtual environment is activated and dependencies installed
pip install -r requirements.txt
```

**Authentication errors:**
```bash
# For Azure: Login with Azure CLI
az login

# For GitHub: Verify your token in .env file
```

**Model not found:**
- Verify your model deployment name in `.env`
- Check that the model is deployed in your Foundry project
- Use AI Toolkit Model Catalog to browse available models

## Project Structure

```
ai-agent-orchestrator/
├── orchestrator.py          # Main orchestrator implementation
├── autonomous_orchestrator.py  # Autonomous PEGEV workflow
├── dynamic_orchestration.py # Dynamic skill discovery/classification/composition/DAG core
├── mcp_server.py            # MCP tools and loop execution API
├── requirements.txt         # Python dependencies
├── pyproject.toml           # Packaging, scripts, test extras
├── tests/                   # Deterministic unit/integration/failure tests
├── .github/workflows/       # CI validation
├── .env.example            # Environment configuration template
├── .env                    # Your environment configuration (git-ignored)
├── README.md               # This file
├── .vscode/
│   ├── launch.json         # Debug configuration
│   └── tasks.json          # Build tasks
└── .gitignore             # Git ignore rules
```

## Contributing

This orchestrator is designed to be extensible. Feel free to:
- Add new specialized agents
- Improve feedback loop logic
- Enhance skill discovery mechanisms
- Add more sophisticated task routing

## License

This project uses Microsoft Agent Framework which is under Microsoft license terms.

## Support

For issues or questions:
- Check the [Microsoft Agent Framework documentation](https://github.com/microsoft/agent-framework)
- Review AI Toolkit features in VS Code
- Consult Microsoft Foundry documentation

---

**Note**: This orchestrator is currently using Agent Framework preview version (1.0.0b260107). Be sure to pin the version in `requirements.txt` to avoid breaking changes.
