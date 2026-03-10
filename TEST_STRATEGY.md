# Test Strategy: Dynamic-Skill Orchestrator Architecture

**Version:** 1.0  
**Created:** 2026-03-10  
**Target:** ai-agent-orchestrator Python codebase  
**CI Requirement:** Zero real LLM/MCP calls - all mocked/deterministic

---

## 1. Test Layers

### 1.1 Unit Tests (`tests/unit/`)
**Purpose:** Validate individual components in isolation  
**Coverage Target:** >85%  
**Execution Time:** <5s total

**What Each Validates:**

- **Agent Classes** (`test_agents.py`)
  - Message formatting and instruction injection
  - Handler invocation mechanics
  - Response parsing and error handling
  - Agent state management (if stateful)
  
- **Memory System** (`test_memory.py`)
  - Entry creation, retrieval, filtering
  - Disk persistence (using temp dirs)
  - JSON serialization/deserialization
  - Memory scoring and relevance ranking
  
- **Workflow Builders** (`test_workflow_builders.py`)
  - Executor graph construction
  - Message routing logic
  - Context propagation
  - Workflow termination conditions
  
- **Data Structures** (`test_models.py`)
  - ExecutionPlan serialization
  - EvaluationResult validation
  - MemoryEntry schema compliance
  - Phase enum transitions

### 1.2 Integration Tests (`tests/integration/`)
**Purpose:** Validate multi-component interactions with fakes  
**Coverage Target:** >75%  
**Execution Time:** <30s total

**What Each Validates:**

- **Orchestrator Workflows** (`test_orchestrator_workflow.py`)
  - Architect → Developer → QA flow with fake agents
  - Feedback loop iterations (1-3 cycles)
  - Message passing between agents
  - Final output aggregation
  
- **Autonomous Loop** (`test_autonomous_loop.py`)
  - Plan → Eval → Gather → Execute → Verify cycle
  - Phase transition logic
  - Self-healing retry mechanisms
  - Memory integration in planning
  
- **MCP Server Integration** (`test_mcp_server.py`)
  - Tool registration and discovery
  - Request/response serialization
  - Model routing resolution
  - Error handling in tool calls
  
- **Cross-Agent Communication** (`test_agent_communication.py`)
  - Message protocol compliance
  - Context sharing between phases
  - Output event streaming
  - Status event propagation

### 1.3 E2E-Lite Tests (`tests/e2e/`)
**Purpose:** Validate complete workflows end-to-end with golden outputs  
**Coverage Target:** >60% (critical paths only)  
**Execution Time:** <60s total

**What Each Validates:**

- **Golden Path Scenarios** (`test_golden_paths.py`)
  - "Design a REST API" → full specialized flow
  - "Fix bug in authentication" → autonomous fix_bug mode
  - "Refactor database layer" → autonomous refactor mode
  - All produce deterministic, verified outputs
  
- **Mode Switching** (`test_mode_execution.py`)
  - Legacy orchestrator selection
  - Autonomous mode selection by task type
  - Model routing per agent/mode
  
- **Memory Evolution** (`test_memory_evolution.py`)
  - Task execution creates memories
  - Subsequent similar tasks use memories
  - Confidence scoring improves over time

---

## 2. Mock/Fake Components to Build

### 2.1 Core Fakes (`tests/fakes/`)

#### `FakeAzureOpenAIClient`
```python
class FakeAzureOpenAIClient:
    """Deterministic LLM response generator - zero API calls."""
    
    def __init__(self, response_map: Dict[str, str]):
        self.response_map = response_map
        self.call_count = 0
        self.call_history = []
    
    def create_agent(self, name: str, instructions: str):
        return FakeAgent(self, name, instructions)
    
    async def generate_response(self, messages, model):
        # Match on last message content hash
        key = hash(messages[-1].text) % 1000
        response = self.response_map.get(str(key), DEFAULT_RESPONSES[model])
        self.call_count += 1
        self.call_history.append((messages, model))
        return FakeResponse(response)
```

**Usage:** Inject deterministic responses per agent type  
**Golden Responses:** Pre-crafted JSON for Planner, Evaluator, Developer, QA

#### `FakeAgent`
```python
class FakeAgent:
    """Fake agent executor with configurable behavior."""
    
    def __init__(self, client, name, instructions, response_delay=0):
        self.client = client
        self.name = name
        self.instructions = instructions
        self.response_delay = response_delay
        self.invocation_count = 0
    
    async def run(self, messages, should_respond=True):
        self.invocation_count += 1
        await asyncio.sleep(self.response_delay)  # Simulate latency
        return await self.client.generate_response(messages, self.name)
```

**Modes:**
- Fast mode: 0 delay
- Realistic mode: 0.1s delay per call
- Failure mode: raises exception on 3rd call

#### `FakeMemorySystem`
```python
class FakeMemorySystem:
    """In-memory ephemeral memory for tests."""
    
    def __init__(self, initial_memories=None):
        self.memories = initial_memories or []
        self.add_calls = []
        self.get_calls = []
    
    def add_memory(self, task_type, issue, solution, outcome, confidence=0.8):
        entry = MemoryEntry(...)  # Create entry
        self.memories.append(entry)
        self.add_calls.append((task_type, issue))
    
    def get_relevant_memories(self, task_type, keywords):
        self.get_calls.append((task_type, keywords))
        # Return pre-configured relevant memories
        return [m for m in self.memories if m.task_type == task_type][:5]
```

**Features:**
- No disk I/O
- Inspectable call history
- Pre-seedable with golden memories

#### `FakeWorkflowContext`
```python
class FakeWorkflowContext:
    """Capture workflow events without agent framework runtime."""
    
    def __init__(self):
        self.messages_sent = []
        self.events_emitted = []
        self.status_changes = []
    
    async def send_message(self, request):
        self.messages_sent.append(request)
        
    async def emit_event(self, event):
        self.events_emitted.append(event)
```

**Validation:** Assert on message flow without real workflow execution

### 2.2 Fixture Builders (`tests/fixtures/`)

#### `ResponseFixtures`
Golden LLM responses for deterministic testing:

```python
GOLDEN_RESPONSES = {
    "architect": {
        "simple_api": """{"design": {...}, "requirements": [...]}""",
        "complex_system": """{"design": {...}, "requirements": [...]}""",
    },
    "developer": {
        "simple_implementation": """{"code": "...", "tests": "..."}""",
        "with_dependencies": """{"code": "...", "dependencies": [...]}""",
    },
    "qa": {
        "passing_review": """{"approved": true, "quality_score": 95}""",
        "failing_review": """{"approved": false, "issues": [...]}""",
    },
    "planner": {
        "three_step_plan": """{"goal": "...", "steps": [{...}]}""",
    },
    "evaluator": {
        "phase_complete": """{"success": true, "next_action": "proceed"}""",
        "needs_retry": """{"success": false, "next_action": "retry"}""",
    },
}
```

#### `TaskFixtures`
Pre-defined test tasks:

```python
GOLDEN_TASKS = {
    "simple_design": "Design a REST API for user management",
    "complex_refactor": "Refactor the database layer to use async operations",
    "bug_fix": "Fix the authentication timeout issue in login flow",
    "edge_case": "Task with invalid characters: <script>alert('xss')</script>",
    "long_description": "..." * 1000,  # Test token limits
}
```

#### `MemoryFixtures`
Pre-seeded learning memories:

```python
GOLDEN_MEMORIES = [
    {
        "task_type": "refactor",
        "issue": "Database connection pool exhaustion",
        "solution": "Implemented connection pooling with max_connections=20",
        "outcome": "success",
        "confidence": 0.95
    },
    # ... 10 more golden memories
]
```

---

## 3. Deterministic Fixtures & Golden Cases

### 3.1 Golden Cases (`tests/golden/`)

#### File Structure:
```
tests/golden/
├── inputs/
│   ├── design_simple_api.json
│   ├── fix_auth_bug.json
│   └── refactor_db_layer.json
├── expected_outputs/
│   ├── design_simple_api_output.json
│   ├── fix_auth_bug_output.json
│   └── refactor_db_layer_output.json
└── memory_snapshots/
    ├── after_successful_refactor.json
    └── after_failed_attempt.json
```

#### Input Format:
```json
{
  "task": "Design a REST API for user management",
  "mode": "design",
  "injected_responses": {
    "planner": "golden/responses/planner_design.json",
    "architect": "golden/responses/architect_design.json"
  },
  "initial_memory": "golden/memory_snapshots/empty.json"
}
```

#### Expected Output Format:
```json
{
  "final_phase": "complete",
  "iterations": 2,
  "execution_plan": {"goal": "...", "steps": [...]},
  "final_output": "...",
  "memory_entries_created": 1,
  "status_events": ["plan", "evaluate", "execute", "verify", "complete"]
}
```

### 3.2 Determinism Techniques

1. **Seeded Randomness:** If any UUIDs/timestamps, use fixed seeds
2. **Clock Mocking:** `freezegun` for timestamp determinism
3. **Hash-Based Response Selection:** Hash input → select golden response
4. **Ordered Execution:** No concurrency in tests unless explicitly testing it

---

## 4. Failure-Mode Tests

### 4.1 Missing Skills (`test_missing_skills.py`)
```python
async def test_missing_researcher_skill():
    """Autonomous mode requests researcher but skill unavailable."""
    fake_client = FakeAzureOpenAIClient({})
    # Only provide planner, evaluator - no researcher
    workflow = create_autonomous_workflow_partial(
        planner=PlannerAgent(fake_client),
        evaluator=EvaluatorAgent(fake_client),
        researcher=None,  # Missing!
    )
    
    result = await workflow.run([Message("user", "Design API")])
    
    # Should fallback gracefully or fail explicitly
    assert "researcher unavailable" in result.error.lower()
    # OR assert fallback to legacy architect
```

**Variants:**
- Missing single agent (researcher, verifier)
- Missing entire mode (no autonomous agents available)
- Missing memory system

### 4.2 Bad Classification (`test_classification_failures.py`)
```python
async def test_ambiguous_task_routing():
    """Task could be 'design' or 'implement' - misclassified."""
    task = "Create user authentication"  # Ambiguous intent
    
    # Mock evaluator to select wrong mode initially
    fake_evaluator = FakeAgent(responses={
        "initial": '{"next_action": "gather"}',  # Wrong - should plan
    })
    
    result = await autonomous_execute(task, mode="design")
    
    # Should recover via eval feedback or timeout
    assert result.iterations <= 5  # Max retry limit
    assert result.final_phase in ["complete", "failed"]
```

**Variants:**
- Mode mismatch (task says "fix bug" but mode="design")
- Evaluator keeps saying "retry" infinitely
- Classifier returns non-existent mode

### 4.3 Retry Loops (`test_retry_behavior.py`)
```python
async def test_max_retry_limit():
    """Evaluator never approves - hits retry ceiling."""
    fake_evaluator = FakeEvaluatorAgent(
        always_return='{"success": false, "next_action": "retry"}'
    )
    
    result = await autonomous_execute("Design API", max_iterations=3)
    
    assert result.iterations == 3
    assert result.final_phase == "failed"
    assert "max iterations reached" in result.error
```

**Variants:**
- Retry with context gaps (each iteration adds new gap)
- Retry with degrading confidence
- Retry with memory lookup failures

### 4.4 Partial Failures (`test_partial_failures.py`)
```python
async def test_qa_fails_after_developer_succeeds():
    """Developer completes but QA rejects - what happens?"""
    fake_developer = FakeAgent(responses={
        "implement": '{"code": "...", "tests": "..."}'
    })
    fake_qa = FakeAgent(responses={
        "review": '{"approved": false, "issues": ["security flaw"]}'
    })
    
    result = await orchestrate_workflow(
        developer=fake_developer,
        qa=fake_qa
    )
    
    # Should trigger feedback loop
    assert result.feedback_iterations >= 1
    assert "security flaw" in result.feedback_history
```

**Variants:**
- Plan succeeds but gather fails
- Execute succeeds but verify fails
- Memory save fails mid-workflow

### 4.5 Timeout Handling (`test_timeout_scenarios.py`)
```python
async def test_agent_response_timeout():
    """Agent takes too long to respond."""
    slow_agent = FakeAgent(response_delay=10.0)  # 10s delay
    
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            orchestrate_workflow(architect=slow_agent),
            timeout=5.0
        )
```

**Variants:**
- Individual agent timeout
- Workflow total timeout
- Memory I/O timeout

### 4.6 Fallback to Legacy (`test_legacy_fallback.py`)
```python
async def test_autonomous_unavailable_fallback():
    """Autonomous mode fails - should fallback to legacy orchestrator."""
    # Simulate autonomous workflow failure
    autonomous_unavailable = True
    
    result = await execute_task_with_fallback(
        task="Design API",
        preferred_mode="autonomous",
        fallback_mode="legacy"
    )
    
    assert result.mode_used == "legacy"
    assert all(agent in result.agents_used for agent in ["architect", "developer", "qa"])
```

---

## 5. Minimal File/Test Structure

```
ai-agent-orchestrator/
├── tests/
│   ├── __init__.py
│   ├── conftest.py                    # Pytest fixtures, config
│   │
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_agents.py              # Agent class tests
│   │   ├── test_memory.py              # MemorySystem tests
│   │   ├── test_workflow_builders.py   # Workflow construction
│   │   └── test_models.py              # Data structure tests
│   │
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_orchestrator_workflow.py
│   │   ├── test_autonomous_loop.py
│   │   ├── test_mcp_server.py
│   │   └── test_agent_communication.py
│   │
│   ├── e2e/
│   │   ├── __init__.py
│   │   ├── test_golden_paths.py
│   │   ├── test_mode_execution.py
│   │   └── test_memory_evolution.py
│   │
│   ├── failure_modes/
│   │   ├── __init__.py
│   │   ├── test_missing_skills.py
│   │   ├── test_classification_failures.py
│   │   ├── test_retry_behavior.py
│   │   ├── test_partial_failures.py
│   │   ├── test_timeout_scenarios.py
│   │   └── test_legacy_fallback.py
│   │
│   ├── fakes/
│   │   ├── __init__.py
│   │   ├── fake_client.py              # FakeAzureOpenAIClient
│   │   ├── fake_agent.py               # FakeAgent
│   │   ├── fake_memory.py              # FakeMemorySystem
│   │   └── fake_workflow.py            # FakeWorkflowContext
│   │
│   ├── fixtures/
│   │   ├── __init__.py
│   │   ├── response_fixtures.py        # GOLDEN_RESPONSES
│   │   ├── task_fixtures.py            # GOLDEN_TASKS
│   │   └── memory_fixtures.py          # GOLDEN_MEMORIES
│   │
│   └── golden/
│       ├── inputs/
│       │   ├── design_simple_api.json
│       │   ├── fix_auth_bug.json
│       │   └── refactor_db_layer.json
│       ├── expected_outputs/
│       │   ├── design_simple_api_output.json
│       │   ├── fix_auth_bug_output.json
│       │   └── refactor_db_layer_output.json
│       └── memory_snapshots/
│           ├── empty.json
│           ├── after_successful_refactor.json
│           └── after_failed_attempt.json
│
├── pytest.ini                          # Pytest configuration
├── .coveragerc                         # Coverage settings
└── pyproject.toml                      # Add test dependencies

```

### Key Files Content:

#### `pytest.ini`
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --strict-markers
    --tb=short
    --cov=.
    --cov-report=term-missing
    --cov-report=html
    --cov-fail-under=75
    --asyncio-mode=auto
markers =
    unit: Unit tests
    integration: Integration tests
    e2e: End-to-end tests
    failure_mode: Failure scenario tests
    slow: Slow-running tests
asyncio_mode = auto
```

#### `tests/conftest.py`
```python
import pytest
from tests.fakes.fake_client import FakeAzureOpenAIClient
from tests.fakes.fake_memory import FakeMemorySystem
from tests.fixtures.response_fixtures import GOLDEN_RESPONSES
from tests.fixtures.memory_fixtures import GOLDEN_MEMORIES

@pytest.fixture
def fake_client():
    """Provide fake LLM client with golden responses."""
    return FakeAzureOpenAIClient(GOLDEN_RESPONSES)

@pytest.fixture
def fake_memory():
    """Provide fake memory system."""
    return FakeMemorySystem(initial_memories=GOLDEN_MEMORIES[:3])

@pytest.fixture
def temp_memory_dir(tmp_path):
    """Provide temporary directory for memory persistence tests."""
    memory_dir = tmp_path / "test_memory"
    memory_dir.mkdir()
    return memory_dir
```

---

## 6. CI Integration

### GitHub Actions Workflow (`.github/workflows/test.yml`)
```yaml
name: Test Suite

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
          pip install pytest pytest-asyncio pytest-cov pytest-timeout
      
      - name: Run unit tests
        run: pytest tests/unit -m unit --timeout=10
      
      - name: Run integration tests
        run: pytest tests/integration -m integration --timeout=30
      
      - name: Run E2E tests
        run: pytest tests/e2e -m e2e --timeout=60
      
      - name: Run failure mode tests
        run: pytest tests/failure_modes -m failure_mode --timeout=30
      
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage.xml
```

---

## 7. Implementation Phases

### Phase 1: Foundation (Week 1)
- [ ] Create test directory structure
- [ ] Implement `FakeAzureOpenAIClient`
- [ ] Implement `FakeAgent`
- [ ] Implement `FakeMemorySystem`
- [ ] Implement `FakeWorkflowContext`
- [ ] Create golden response fixtures
- [ ] Write unit tests for MemorySystem
- [ ] Write unit tests for data models

**Success Criteria:** 
- Unit tests run in <5s
- Zero real API calls
- >80% coverage on memory and models

### Phase 2: Integration (Week 2)
- [ ] Write orchestrator workflow tests (legacy mode)
- [ ] Write autonomous loop tests (all modes)
- [ ] Write agent communication tests
- [ ] Create golden task fixtures
- [ ] Test MCP server tool registration

**Success Criteria:**
- Integration tests run in <30s
- All feedback loops tested
- Phase transitions validated

### Phase 3: E2E & Failure Modes (Week 3)
- [ ] Create golden input/output test cases
- [ ] Implement golden path tests
- [ ] Implement all failure mode tests
- [ ] Test memory evolution over time
- [ ] Test mode switching logic

**Success Criteria:**
- E2E tests run in <60s
- All 6 failure categories covered
- Fallback mechanisms validated

### Phase 4: CI & Documentation (Week 4)
- [ ] Set up GitHub Actions workflow
- [ ] Configure coverage reporting
- [ ] Add test running docs to README
- [ ] Create troubleshooting guide
- [ ] Performance benchmarking suite

**Success Criteria:**
- CI runs full suite in <2min
- Coverage >75% overall
- Zero flaky tests

---

## 8. Test Execution Commands

```bash
# Run all tests
pytest

# Run by layer
pytest tests/unit -m unit
pytest tests/integration -m integration
pytest tests/e2e -m e2e
pytest tests/failure_modes -m failure_mode

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/unit/test_memory.py -v

# Run tests matching pattern
pytest -k "test_retry" -v

# Run with debugging
pytest --pdb -x  # Drop into debugger on first failure

# Performance profiling
pytest --durations=10  # Show 10 slowest tests
```

---

## 9. Maintenance Guidelines

1. **Golden Response Updates:** When agent instructions change, regenerate golden responses
2. **Fixture Versioning:** Tag fixtures with version numbers when breaking changes occur
3. **Flakiness Investigation:** Any test failing >1% of runs gets immediately investigated
4. **Coverage Monitoring:** Weekly review of coverage reports, target any drop below 75%
5. **Performance Budgets:** Unit <5s, Integration <30s, E2E <60s - hard limits

---

## Appendix A: Test Dependencies

Add to `pyproject.toml`:
```toml
[project.optional-dependencies]
test = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "pytest-timeout>=2.2.0",
    "pytest-mock>=3.12.0",
    "freezegun>=1.4.0",
    "faker>=22.0.0",
]
```

## Appendix B: Example Test

```python
# tests/unit/test_memory.py
import pytest
from autonomous_orchestrator import MemorySystem, MemoryEntry

@pytest.mark.unit
def test_memory_persistence(temp_memory_dir):
    """Memories should persist to disk and reload correctly."""
    memory = MemorySystem(str(temp_memory_dir))
    
    # Add memory
    memory.add_memory(
        task_type="refactor",
        issue="slow query",
        solution="added index",
        outcome="success",
        confidence=0.9
    )
    
    # Create new instance (simulates restart)
    memory2 = MemorySystem(str(temp_memory_dir))
    
    # Should load from disk
    assert len(memory2.memories) == 1
    assert memory2.memories[0].issue == "slow query"
    assert memory2.memories[0].confidence == 0.9

@pytest.mark.unit
def test_memory_relevance_scoring(fake_memory):
    """Should return most relevant memories by keyword match."""
    fake_memory.memories = [
        MemoryEntry(timestamp="", task_type="refactor", issue="database slow", 
                   solution="", outcome="", confidence=0.9),
        MemoryEntry(timestamp="", task_type="refactor", issue="frontend lag", 
                   solution="", outcome="", confidence=0.8),
        MemoryEntry(timestamp="", task_type="design", issue="api design", 
                   solution="", outcome="", confidence=0.95),
    ]
    
    results = fake_memory.get_relevant_memories("refactor", ["database", "query"])
    
    assert len(results) <= 5
    assert results[0].issue == "database slow"  # Best match
    assert results[0].confidence == 0.9
```
