# Implement Comprehensive Test Suite for Dynamic-Skill Orchestrator

## Overview
Implement a production-ready test suite for the ai-agent-orchestrator with **zero real LLM/MCP calls** in CI. All tests use deterministic mocks and golden fixtures for fast, reliable, cost-free execution.

## Context
Current state: Integration tests exist (`backtest_suite.py`) but require real LLM calls. We need unit, integration, and E2E tests that run in CI without external dependencies.

Reference: See `TEST_STRATEGY.md` for complete specification.

## Objectives
1. **Unit tests** (<5s total) - individual component validation
2. **Integration tests** (<30s total) - multi-component workflows with fakes
3. **E2E-lite tests** (<60s total) - golden path scenarios
4. **Failure mode tests** - retry loops, timeouts, partial failures, fallbacks
5. **CI integration** - GitHub Actions with coverage reporting (target >75%)

## Implementation Phases

### Phase 1: Test Foundation (Week 1)
**Goal:** Build mock infrastructure and unit tests

**Tasks:**
- [ ] Create test directory structure (`tests/{unit,integration,e2e,failure_modes,fakes,fixtures,golden}`)
- [ ] Implement `tests/fakes/fake_client.py` - `FakeAzureOpenAIClient` with deterministic responses
- [ ] Implement `tests/fakes/fake_agent.py` - `FakeAgent` with configurable delays/failures
- [ ] Implement `tests/fakes/fake_memory.py` - `FakeMemorySystem` with in-memory storage
- [ ] Implement `tests/fakes/fake_workflow.py` - `FakeWorkflowContext` for event capture
- [ ] Create `tests/fixtures/response_fixtures.py` - golden LLM responses for each agent type
- [ ] Create `tests/conftest.py` - pytest fixtures and configuration
- [ ] Write `tests/unit/test_memory.py` - MemorySystem tests (add, retrieve, persist, score)
- [ ] Write `tests/unit/test_models.py` - ExecutionPlan, EvaluationResult, MemoryEntry tests
- [ ] Configure `pytest.ini` with markers and coverage settings

**Acceptance Criteria:**
- [ ] Unit tests run in <5s
- [ ] Zero external API calls (verify with network mocking)
- [ ] MemorySystem coverage >85%
- [ ] All fakes have usage examples in docstrings

---

### Phase 2: Integration Tests (Week 2)
**Goal:** Validate multi-agent workflows with fakes

**Tasks:**
- [ ] Write `tests/integration/test_orchestrator_workflow.py`
  - [ ] Test Architect → Developer → QA flow
  - [ ] Test feedback loop (1-3 iterations)
  - [ ] Test message passing protocol
- [ ] Write `tests/integration/test_autonomous_loop.py`
  - [ ] Test Plan → Eval → Gather → Execute → Verify cycle
  - [ ] Test all 5 modes (design, fix_bug, debug, implement, refactor)
  - [ ] Test self-healing retry logic
- [ ] Write `tests/integration/test_mcp_server.py`
  - [ ] Test tool registration and discovery
  - [ ] Test model routing resolution
  - [ ] Test request/response serialization
- [ ] Write `tests/integration/test_agent_communication.py`
  - [ ] Test context sharing between phases
  - [ ] Test output event streaming
  - [ ] Test status event propagation
- [ ] Create `tests/fixtures/task_fixtures.py` - golden input tasks
- [ ] Create `tests/fixtures/memory_fixtures.py` - pre-seeded memories

**Acceptance Criteria:**
- [ ] Integration tests run in <30s
- [ ] All agent-to-agent handoffs tested
- [ ] Phase transitions validated with state assertions
- [ ] Memory integration in planning verified

---

### Phase 3: E2E & Failure Modes (Week 3)
**Goal:** Golden path validation and chaos engineering

**Tasks:**
- [ ] Create golden test cases in `tests/golden/`
  - [ ] `inputs/design_simple_api.json` + expected output
  - [ ] `inputs/fix_auth_bug.json` + expected output
  - [ ] `inputs/refactor_db_layer.json` + expected output
- [ ] Write `tests/e2e/test_golden_paths.py`
  - [ ] "Design a REST API" → full specialized flow
  - [ ] "Fix authentication bug" → autonomous fix_bug mode
  - [ ] "Refactor database layer" → autonomous refactor mode
- [ ] Write `tests/e2e/test_mode_execution.py`
  - [ ] Legacy orchestrator selection logic
  - [ ] Autonomous mode selection by task type
- [ ] Write `tests/e2e/test_memory_evolution.py`
  - [ ] Execute task → creates memory
  - [ ] Similar task → uses past memory
- [ ] Write `tests/failure_modes/test_missing_skills.py`
  - [ ] Missing researcher agent → graceful degradation
  - [ ] Missing verifier agent → fallback behavior
- [ ] Write `tests/failure_modes/test_classification_failures.py`
  - [ ] Ambiguous task routing
  - [ ] Mode mismatch recovery
- [ ] Write `tests/failure_modes/test_retry_behavior.py`
  - [ ] Max retry limit enforcement
  - [ ] Infinite retry loop prevention
- [ ] Write `tests/failure_modes/test_partial_failures.py`
  - [ ] Developer succeeds, QA fails → feedback loop
  - [ ] Plan succeeds, gather fails → error handling
- [ ] Write `tests/failure_modes/test_timeout_scenarios.py`
  - [ ] Individual agent timeout
  - [ ] Workflow total timeout
- [ ] Write `tests/failure_modes/test_legacy_fallback.py`
  - [ ] Autonomous unavailable → legacy orchestrator

**Acceptance Criteria:**
- [ ] E2E tests run in <60s
- [ ] All golden cases produce deterministic outputs
- [ ] All 6 failure categories covered (missing skills, classification, retry, partial, timeout, fallback)
- [ ] No flaky tests (100 consecutive runs pass)

---

### Phase 4: CI Integration & Polish (Week 4)
**Goal:** Production-ready CI pipeline

**Tasks:**
- [ ] Create `.github/workflows/test.yml`
  - [ ] Matrix strategy for Python 3.10, 3.11, 3.12
  - [ ] Separate jobs for unit/integration/e2e/failure_modes
  - [ ] Coverage upload to Codecov
- [ ] Add test dependencies to `pyproject.toml`
  - [ ] pytest, pytest-asyncio, pytest-cov, pytest-timeout
  - [ ] freezegun for time mocking
  - [ ] faker for test data generation
- [ ] Update `README.md` with test running instructions
- [ ] Create `docs/TESTING.md` with:
  - [ ] Architecture overview of test layers
  - [ ] How to add new tests
  - [ ] How to update golden responses
  - [ ] Troubleshooting flaky tests
- [ ] Configure `.coveragerc` with exclusions
- [ ] Set up pre-commit hooks for test running
- [ ] Create performance benchmark suite (optional)

**Acceptance Criteria:**
- [ ] CI runs full suite in <2 minutes
- [ ] Coverage >75% overall (unit >85%, integration >75%, e2e >60%)
- [ ] All platforms (ubuntu, macos, windows) pass (optional)
- [ ] Dependabot integration for test dependencies

---

## File Structure (Final State)
```
ai-agent-orchestrator/
├── .github/workflows/test.yml
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_agents.py
│   │   ├── test_memory.py
│   │   ├── test_workflow_builders.py
│   │   └── test_models.py
│   ├── integration/
│   │   ├── test_orchestrator_workflow.py
│   │   ├── test_autonomous_loop.py
│   │   ├── test_mcp_server.py
│   │   └── test_agent_communication.py
│   ├── e2e/
│   │   ├── test_golden_paths.py
│   │   ├── test_mode_execution.py
│   │   └── test_memory_evolution.py
│   ├── failure_modes/
│   │   ├── test_missing_skills.py
│   │   ├── test_classification_failures.py
│   │   ├── test_retry_behavior.py
│   │   ├── test_partial_failures.py
│   │   ├── test_timeout_scenarios.py
│   │   └── test_legacy_fallback.py
│   ├── fakes/
│   │   ├── fake_client.py
│   │   ├── fake_agent.py
│   │   ├── fake_memory.py
│   │   └── fake_workflow.py
│   ├── fixtures/
│   │   ├── response_fixtures.py
│   │   ├── task_fixtures.py
│   │   └── memory_fixtures.py
│   └── golden/
│       ├── inputs/
│       ├── expected_outputs/
│       └── memory_snapshots/
├── pytest.ini
├── .coveragerc
└── TEST_STRATEGY.md  ✅ Already created
```

## Success Metrics
- [ ] **Zero CI failures** due to LLM rate limits or costs
- [ ] **<2 min total CI time** for full test suite
- [ ] **>75% code coverage** with detailed HTML reports
- [ ] **100% deterministic** - same inputs always produce same outputs
- [ ] **Zero flakiness** - no random failures over 100 runs
- [ ] **Fast feedback** - unit tests give instant developer feedback

## Technical Constraints
1. **No Real API Calls:** All LLM interactions mocked via `FakeAzureOpenAIClient`
2. **No Network I/O:** Memory uses temp directories, no external persistence
3. **Deterministic Execution:** Seeded randomness, mocked timestamps
4. **Async Testing:** Full support via `pytest-asyncio`
5. **Coverage Requirements:** Unit >85%, Integration >75%, E2E >60%

## Resources
- **Test Strategy:** `/TEST_STRATEGY.md` (comprehensive 800+ line spec)
- **Existing Backtest:** `backtest_suite.py` (reference for integration patterns)
- **Agent Framework Docs:** [Azure AI Agent Framework](https://learn.microsoft.com/azure/ai-services/agents/)

## Dependencies
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

## Getting Started
1. Read `TEST_STRATEGY.md` for complete architecture
2. Start with Phase 1 - implement fakes and unit tests
3. Use `pytest -v` locally to validate each phase
4. Open draft PRs for early feedback on test patterns

## Questions?
- **Test Strategy Unclear?** See `TEST_STRATEGY.md` Section X
- **How to Mock Workflows?** See `tests/fakes/fake_workflow.py` example
- **Golden Responses?** See `tests/fixtures/response_fixtures.py`
- **Failure Mode Examples?** See `TEST_STRATEGY.md` Section 4

---

**Labels:** `testing`, `infrastructure`, `ci/cd`, `priority:high`, `good-first-issue` (for Phase 1 tasks)
**Assignees:** TBD
**Milestone:** v1.1 - Production Test Suite
