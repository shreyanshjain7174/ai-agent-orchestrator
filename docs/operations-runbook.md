# Operations Runbook

This runbook covers rollout, rollback, and troubleshooting for dynamic orchestration telemetry/logging additions.

## Scope

- autonomous_execute additive telemetry fields
- structured logs with correlation IDs and phase transitions
- backtest operational comparison output
- deterministic performance baseline and CI smoke regression budget checks

## Pre-Deployment Checklist

1. Run deterministic contract and smoke tests.
2. Confirm docs are present and linked from README.
3. Validate no external telemetry service dependencies are required.
4. Verify additive-only API contract changes.

Required checks:

- python3 scripts/profile_execution_paths.py --iterations 30 --output docs/performance-baseline.json --report docs/performance-baseline.md
- python3 -m pytest tests/integration/test_performance_smoke.py -q
- python3 -m pytest tests/integration/test_mcp_server_contracts.py -q
- python3 -m pytest tests/integration/test_migration_docs_smoke.py -q
- python3 -m pytest tests/e2e/test_dynamic_golden_paths.py -q
- python3 -m pytest -q
- python3 -m compileall mcp_server.py backtest_suite.py dynamic_orchestration.py autonomous_orchestrator.py

## Performance Baseline Procedure

1. Generate/update deterministic baseline artifacts:
   - python3 scripts/profile_execution_paths.py --iterations 30 --output docs/performance-baseline.json --report docs/performance-baseline.md
2. Confirm the JSON includes:
   - execution_modes latency and control-path metrics
   - concurrent load scenarios
   - memory trend summary and soft_budgets
3. Run CI-safe smoke benchmark:
   - python3 -m pytest tests/integration/test_performance_smoke.py -q
4. If smoke fails, compare current measurements against `docs/performance-baseline.md` and investigate execution-mode-specific regressions first.

## Rollout Plan

1. Deploy with execution_mode=auto and enable_legacy_fallback=true for safety.
2. Observe structured logs for:
   - autonomous.start
   - planning.completed
   - phase.transition
   - fallback.triggered
   - autonomous.completed
3. Confirm telemetry fields are present in autonomous_execute responses.
4. Monitor fallback_rate trends and investigate sustained increases.

## Rollback Plan

If regression is detected:

1. Force execution_mode=legacy at caller level to bypass dynamic execution.
2. Keep enable_legacy_fallback=true during rollback window.
3. Re-run contract tests to ensure legacy stability.
4. Revert deployment to previous artifact if legacy-only mode is insufficient.

## Troubleshooting

### Symptom: telemetry missing in autonomous_execute response

Checks:

- Verify response includes correlation_id and telemetry keys.
- Ensure code path is mcp_server autonomous_execute (not direct legacy orchestrate_task call).
- Run integration contract tests locally.

### Symptom: repeated runtime fallback

Checks:

- Filter logs by correlation_id.
- Inspect fallback.triggered events for branch=runtime.
- Compare planning.completed and loop.error events in same correlation_id.

Actions:

- Temporarily force execution_mode=legacy.
- Capture failing task prompt and loop index for deterministic reproduction.

### Symptom: no phase.transition logs

Checks:

- Verify workflow output includes Phase: marker strings.
- Confirm _collect_autonomous_run is being used in execution path.

### Symptom: operational comparison shows no legacy coverage

Expected when no legacy backtest cases were executed. The report returns legacy_coverage=false with explanatory notes.

## Log Correlation Workflow

1. Capture correlation_id from response payload.
2. Search logs for that correlation_id.
3. Reconstruct run sequence:
   - autonomous.start
   - planning.completed per loop
   - phase.transition entries
   - fallback.triggered if present
   - autonomous.completed

## SLO-Oriented Watchpoints

Suggested thresholds for review:

- fallback_rate > 0.20 over stable traffic window
- sustained dag_latency_ms growth above baseline
- declining classification_confidence coupled with increased fallback

## Post-Incident Actions

1. Add deterministic regression coverage for the incident path.
2. Record a short summary in docs if operational guidance changed.
3. Re-run full test suite before re-enabling dynamic auto routing.
