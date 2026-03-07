---
title: Building an Autonomous Multi-Agent System with Self-Healing Capabilities
published: false
description: How I built an autonomous AI agent orchestrator with Plan-Eval-Gather-Execute-Verify loop, persistent memory learning, and GitHub Copilot integration
tags: ai, agents, opensource, automation, python
cover_image: https://dev-to-uploads.s3.amazonaws.com/uploads/articles/[your-image].png
---

# Building an Autonomous Multi-Agent System with Self-Healing Capabilities

## The Problem

As someone working with AI agents, I kept running into the same issues:
- Complex tasks need multiple specialized agents working together
- Agents don't learn from their mistakes
- Manual orchestration is tedious and error-prone
- No good way to iterate until a task is truly complete

I wanted a system that could handle requests like "Design a REST API for user authentication" or "Fix this performance bug" **autonomously** - planning, researching, implementing, testing, and learning from failures.

## The Solution: PEGEV Loop

I built **AI Agent Orchestrator** - an autonomous multi-agent system that coordinates 6 specialized AI agents in a Plan-Eval-Gather-Execute-Verify loop:

```
User Task: "Design something" / "Fix this bug"
    ↓
┌─────────────────────────────────────────────┐
│  AUTONOMOUS LOOP (until success)            │
│                                             │
│  1. PLAN      → Break down task            │
│  2. EVALUATE  → Assess readiness           │
│  3. GATHER    → Research & collect context │
│  4. EXECUTE   → Design & implement         │
│  5. VERIFY    → Test & self-correct        │
│  6. EVALUATE  → Check success criteria     │
│       ↓ (if failed, loop with learnings)   │
│  7. LEARN     → Store lessons in memory    │
└─────────────────────────────────────────────┘
```

## The Agents

### 1. PlannerAgent
Strategic planning and task decomposition. Creates execution plans, identifies risks, defines success criteria.

```python
class PlannerAgent(Executor):
    def __init__(self, client, memory):
        self.agent = client.as_agent(
            name="PlannerAgent",
            instructions="""Break down tasks into executable steps.
            Define success criteria. Learn from past executions."""
        )
        self.memory = memory  # Accesses past learnings
```

### 2. EvaluatorAgent
Progress assessment and decision-making. Determines if we should continue, gather more context, or complete.

```python
# Responds with:
{
  "success": true/false,
  "confidence": 0.9,
  "next_action": "CONTINUE|GATHER_MORE|REVISE|COMPLETE",
  "context_gaps": ["missing info needed"]
}
```

### 3. ResearcherAgent
Context gathering and solution research. Fills knowledge gaps identified by other agents.

### 4. ArchitectAgent
Solution design and architecture planning. Plans robust, scalable implementations.

### 5. DeveloperAgent
Code implementation with comprehensive tests and documentation.

### 6. VerifierAgent
**The key to self-healing.** Tests implementation, finds bugs, provides fix instructions, and **stores lessons learned.**

```python
# When VerifierAgent finds an issue:
{
  "issue": "Missing input validation on login endpoint",
  "severity": "high",
  "fix": "Add validation for email format and password strength",
  "lesson": "Auth APIs need input validation from start"
}

# This gets stored in persistent memory!
self.memory.add_memory(
    task_type="verification",
    issue=issue["issue"],
    solution=issue["fix"],
    confidence=0.9
)
```

## The Self-Healing Magic

Here's what makes it truly autonomous:

### Example: Building an Auth API (First Time)

**Iteration 1:**
1. Planner creates plan
2. Evaluator approves
3. Developer implements
4. **Verifier finds**: Missing input validation
5. Lesson stored: "Auth APIs need input validation"

**Iteration 2:**
1. Planner incorporates feedback
2. Developer adds validation
3. Verifier approves ✅

### Next Auth API Task

**Iteration 1:**
1. Planner **loads past learnings from memory**
2. Plan **includes input validation from the start**
3. Developer implements correctly
4. Verifier approves immediately ✅

**The agent learned!** Future tasks benefit from past mistakes.

## Memory System

Persistent storage of learnings:

```python
class MemorySystem:
    def __init__(self, memory_dir=".orchestrator_memory"):
        self.memory_file = Path(memory_dir) / "lessons_learned.json"
    
    def add_memory(self, task_type, issue, solution, outcome):
        memory = MemoryEntry(
            timestamp=datetime.now().isoformat(),
            task_type=task_type,
            issue=issue,
            solution=solution,
            outcome=outcome,
            confidence=0.8
        )
        self.memories.append(memory)
        self._save_memories()
    
    def get_relevant_memories(self, task_type, keywords):
        # Returns top 5 most relevant past learnings
        return sorted_relevant_memories[:5]
```

Stored in `.orchestrator_memory/lessons_learned.json`:

```json
[
  {
    "timestamp": "2026-03-07T10:30:00",
    "task_type": "verification",
    "issue": "Missing input validation on auth endpoint",
    "solution": "Add email format and password strength validation",
    "outcome": "Severity: high",
    "confidence": 0.9
  }
]
```

## GitHub Copilot Integration

Available as an MCP (Model Context Protocol) server with 8 tools:

```bash
# Install via Smithery
npx -y @smithery/cli install ai-agent-orchestrator --client claude
```

**MCP Tools exposed:**

1. **`autonomous_execute`** ⚡ - Main autonomous loop
   - Modes: design, fix_bug, debug, implement, refactor
   - Auto-iterates until verified success

2. **`get_learnings`** - View past lessons from memory

3. **`show_autonomous_capabilities`** - System info

4-8. Legacy tools: `architect_design`, `developer_implement`, `qa_review`, `orchestrate_task`, `show_model_routing`

**Usage in VS Code:**

```
User in Copilot Chat: "Use autonomous_execute to design a secure REST API for user authentication"
```

The autonomous loop runs in the background:
- Plans the implementation
- Researches JWT best practices
- Designs the architecture
- Implements with tests
- Verifies security
- Learns from any issues found

## Extensibility

### Swap Models Instantly

Just edit `.env`:

```bash
# Budget mode - fast models
PLANNER_MODEL=openai/gpt-4o
EVALUATOR_MODEL=openai/gpt-4o

# Power mode - best models
PLANNER_MODEL=openai/o3-mini
ARCHITECT_MODEL=anthropic/claude-opus-4.6
DEVELOPER_MODEL=anthropic/claude-opus-4.6
VERIFIER_MODEL=openai/o3
```

No code changes needed!

### Add Custom Agents

20 lines to add a SecurityAgent:

```python
class SecurityAgent(Executor):
    agent: Any
    
    def __init__(self, client, id="security"):
        self.agent = client.as_agent(
            name="SecurityAgent",
            instructions="Scan for security vulnerabilities..."
        )
        super().__init__(id=id)
    
    @handler
    async def handle(self, request, ctx):
        response = await self.agent.run(request.messages)
        await ctx.send_message(
            AgentExecutorResponse(
                agent_response=response,
                executor_id=self.id
            )
        )

# Add to workflow
.add_edge(verifier, security)  # Insert in pipeline
```

### Custom Memory Backends

Currently uses JSON, but designed for swapping:

```python
# PostgreSQL backend
class PostgresMemory(MemorySystem):
    def __init__(self, connection_string):
        self.conn = psycopg2.connect(connection_string)
    
    def add_memory(self, ...):
        # Store in your database
        pass

# Redis backend
class RedisMemory(MemorySystem):
    def __init__(self, redis_url):
        self.redis = Redis.from_url(redis_url)
    
    # Your implementation...
```

## Real-World Example

**Task:** "Debug why the login endpoint is returning 500 errors"

**Execution:**

1. **PLAN** (PlannerAgent)
   - Check error logs
   - Review login endpoint code
   - Test authentication flow
   - Identify root cause

2. **EVALUATE** (EvaluatorAgent)
   - Gap: Need access to error logs
   - Decision: GATHER_MORE

3. **GATHER** (ResearcherAgent)
   - Retrieves recent error logs
   - Finds stack trace: "NullPointerException in validateToken()"

4. **EXECUTE** (Architect + Developer)
   - Architect: Token validation logic has null check issue
   - Developer: Implements fix with null safety

5. **VERIFY** (VerifierAgent)
   - Tests login with valid token ✅
   - Tests login with null token ✅
   - Tests login with expired token ✅
   - **Stores lesson**: "Token validation must handle null/expired cases"

6. **EVALUATE**
   - All tests pass
   - Decision: COMPLETE ✅

7. **LEARN**
   - Next time debugging auth issues, agent will check token validation first!

## Technical Stack

- **Python 3.10+**
- **Microsoft Agent Framework** for agent coordination
- **MCP SDK** for Copilot integration
- **Azure AI / GitHub Models** for LLM access
- **Async/await** for parallel execution
- **Type hints** throughout

## Performance Characteristics

- **Iteration limit**: Configurable (default 10)
- **Model costs**: Optimized with "auto" fallback
- **Memory growth**: Linear with task count (prunable)
- **Latency**: ~30-60s per iteration depending on models

## Open Source & Contributing

**GitHub:** https://github.com/shreyanshjain7174/ai-agent-orchestrator

**License:** MIT

**Contributions welcome!**
- Add new specialized agents (Security, Docs, Performance)
- Alternative memory backends (Vector DB, SQLite, Redis)
- Workflow optimizations
- Additional MCP tools

## Try It Now

### Install via Smithery (easiest):
```bash
npx -y @smithery/cli install ai-agent-orchestrator --client claude
```

### Or manual setup:
```bash
git clone https://github.com/shreyanshjain7174/ai-agent-orchestrator
cd ai-agent-orchestrator
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # Add your API keys

# Run as MCP server
uv run --prerelease=allow --with "mcp[cli]>=1.6.0,<2.0.0" \
  --with-requirements requirements.txt mcp run mcp_server.py
```

## What's Next?

Ideas I'm exploring:
- **Vector search for memory** - Find similar past issues semantically
- **Agent performance metrics** - Track which agents are most effective
- **Multi-repo context** - Research across multiple codebases
- **Parallel agent execution** - Run multiple agents simultaneously
- **Web UI** - Visual monitoring of the PEGEV loop

## Conclusion

Building an autonomous multi-agent system taught me that:

1. **Memory is crucial** - Agents that don't learn from mistakes are just expensive loops
2. **Evaluation gates prevent infinite loops** - EvaluatorAgent is the key to pragmatism
3. **Structured communication matters** - JSON responses enable reliable agent handoffs
4. **Extensibility from day one** - Configuration-driven design pays off immediately

The PEGEV loop pattern generalizes beyond software tasks - imagine applying it to data analysis, research, content creation, or business processes.

If you're building with AI agents, I'd love to hear your thoughts! What specialized agents would you add? How would you improve the self-healing loop?

**Star the repo** ⭐ if this resonates, and contributions are very welcome!

---

*This project is MIT licensed and built with Microsoft Agent Framework. Special thanks to the MCP community for inspiration.*
