# Migration Matrix

This document describes backward-compatible translation from legacy orchestration settings to canonical dynamic orchestration settings.

Phase 8 guarantees:
- Existing legacy configuration continues to run.
- Legacy aliases emit deprecation warnings.
- Dynamic planning/runtime fallback to legacy emits explicit diagnostics.

## Environment Variable Matrix

| Canonical variable | Deprecated legacy alias(es) | Default | Notes |
| --- | --- | --- | --- |
| `AI_ORCHESTRATOR_SKILLS_JSON` | `ORCHESTRATOR_SKILLS_JSON`, `SKILLS_JSON` | unset | Optional JSON inventory for env-backed skills. |
| `AI_ORCHESTRATOR_ENABLE_SKILL_DISCOVERY` | `ORCHESTRATOR_ENABLE_SKILL_DISCOVERY`, `ENABLE_SKILL_DISCOVERY` | `true` | Controls whether env-backed discovery is enabled. Static built-ins always remain available. |
| `AI_ORCHESTRATOR_DISCOVERY_RETRY_ATTEMPTS` | `ORCHESTRATOR_DISCOVERY_RETRY_ATTEMPTS`, `DISCOVERY_RETRY_ATTEMPTS` | `1` | Discovery retry attempts. |
| `AI_ORCHESTRATOR_DISCOVERY_TTL_SECONDS` | `ORCHESTRATOR_DISCOVERY_TTL_SECONDS`, `DISCOVERY_TTL_SECONDS` | `60` | Discovery cache TTL in seconds. |
| `AI_ORCHESTRATOR_CLASSIFIER_MIN_CONFIDENCE` | `ORCHESTRATOR_CLASSIFIER_MIN_CONFIDENCE`, `CLASSIFIER_MIN_CONFIDENCE` | `0.6` | Minimum classifier confidence threshold. |
| `AI_ORCHESTRATOR_MAX_TEAM_SIZE` | `ORCHESTRATOR_MAX_TEAM_SIZE`, `MAX_TEAM_SIZE` | `6` | Maximum dynamic team assignment size. |
| `AI_ORCHESTRATOR_DAG_MODE` | `ORCHESTRATOR_DAG_MODE`, `DAG_MODE` | `dynamic` | `dynamic` or `static` DAG edge policy. |
| `AI_ORCHESTRATOR_MAX_DAG_NODES` | `ORCHESTRATOR_MAX_DAG_NODES`, `MAX_DAG_NODES` | `24` | Upper bound on generated DAG nodes. |

## Runtime Settings Matrix

| Canonical setting | Deprecated alias(es) | Scope |
| --- | --- | --- |
| `mode=fix_bug` | `mode=bugfix`, `mode=bug_fix` | `dynamic_plan_preview`, `autonomous_execute` |
| `mode=implement` | `mode=implementation` | `dynamic_plan_preview`, `autonomous_execute` |
| `execution_mode=legacy` | `execution_mode=static`, `execution_mode=classic` | `autonomous_execute` |
| `execution_mode=auto` | `execution_mode=hybrid`, `execution_mode=adaptive` | `autonomous_execute` |
| `execution_mode=dynamic` | `execution_mode=dynamic_only` | `autonomous_execute` |
| `enable_legacy_fallback=<bool>` | string booleans (`"true"`, `"false"`, `"1"`, `"0"`) | `autonomous_execute` |

## Fallback Diagnostics

When dynamic execution falls back to legacy in `execution_mode=auto`, the response includes:

- `fallback.triggered = true`
- `fallback.mode_used = "legacy"`
- `fallback.reason`
- `fallback.diagnostics`:
  - `branch`: `planning` or `runtime`
  - `reason`
  - `loop`
  - `requested_mode`
  - `resolved_mode`
  - `execution_mode`

Warning logs are emitted for both fallback branches:
- planning fallback: `[Autonomous][Fallback][planning->legacy]`
- runtime fallback: `[Autonomous][Fallback][runtime->legacy]`

## Safe Upgrade Steps

1. Keep existing environment variables and runtime flags unchanged.
2. Upgrade to Phase 8 and deploy normally; backward compatibility is preserved.
3. Monitor logs for deprecation warnings indicating translated legacy aliases.
4. Replace deprecated aliases with canonical variables/settings from the matrix above.
5. Re-run migration smoke tests:
   - `python3 -m pytest tests/unit/test_dynamic_orchestration_compat.py -q`
   - `python3 -m pytest tests/integration/test_migration_docs_smoke.py -q`
6. Keep `execution_mode=auto` with `enable_legacy_fallback=true` during rollout to preserve legacy fallback safety.
