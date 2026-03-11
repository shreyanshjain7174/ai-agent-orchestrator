# Performance Baseline

Deterministic baseline for Issue #11 generated with offline stubs and no external network calls.

## Methodology

- Imported mcp_server through deterministic stubs matching integration contract tests.
- Benchmarked autonomous_execute across execution_mode values: legacy, dynamic, auto.
- Recorded latency mean/median/p95, loops_executed, fallback_rate, execution_order_valid_ratio.
- Ran concurrent load scenarios using asyncio gather with deterministic request prompts.
- Sampled memory trends with tracemalloc while scaling loop_count and task complexity.

## Execution Mode Results

| execution_mode | iterations | latency_mean_ms | latency_median_ms | latency_p95_ms | loops_executed_mean | fallback_rate | execution_order_valid_ratio |
| --- | --- | --- | --- | --- | --- | --- | --- |
| legacy | 30 | 0.1317 | 0.1202 | 0.1749 | 1.00 | 0.0000 | n/a |
| dynamic | 30 | 0.4686 | 0.4358 | 0.8306 | 1.00 | 0.0000 | 0.7500 |
| auto | 30 | 0.4508 | 0.4314 | 0.5258 | 1.00 | 0.0000 | 0.7500 |

## Concurrent Load Results

| scenario | requests | throughput_rps | latency_mean_ms | latency_p95_ms | fallback_rate |
| --- | --- | --- | --- | --- | --- |
| legacy:p2 | 4 | 21942.9376 | 0.0179 | 0.0217 | 0.0000 |
| legacy:p4 | 8 | 32487.1775 | 0.0174 | 0.0240 | 0.0000 |
| dynamic:p2 | 4 | 2721.3957 | 0.3415 | 0.3951 | 0.0000 |
| dynamic:p4 | 8 | 3055.6219 | 0.3138 | 0.3232 | 0.0000 |
| auto:p2 | 4 | 2912.2679 | 0.3151 | 0.3215 | 0.0000 |
| auto:p4 | 8 | 2651.5677 | 0.3615 | 0.6427 | 0.0000 |

## Memory Trend Results

| scenario | loop_count | task_words | loops_executed_mean | current_kib | peak_kib |
| --- | --- | --- | --- | --- | --- |
| small_l1 | 1 | 5 | 1.00 | 17.8311 | 28.9727 |
| medium_l1 | 1 | 40 | 1.00 | 18.2686 | 29.7021 |
| medium_l3 | 3 | 40 | 3.00 | 36.3506 | 47.7686 |
| large_l5 | 5 | 80 | 5.00 | 54.5029 | 66.2490 |

Memory summary: peak_kib_min=28.9727, peak_kib_max=66.2490, peak_growth_ratio=2.2866.

## Optimization Recommendations

1. **Cache dynamic planning artifacts per normalized task signature**
   Observation: Dynamic median latency is higher than legacy, indicating recurring planner and classification overhead on repeated prompts.
   Action: Memoize build_dynamic_planning_result outputs using task hash + mode + registry version with short TTL to reduce repeated planning latency without changing execution semantics.

2. **Trim prompt payload growth across loop retries**
   Observation: Peak memory grows across loop_count/task complexity scenarios, showing prompt expansion is a primary allocation driver.
   Action: Store structured loop context separately and pass compact prompt references (mode/loop/order IDs) instead of repeatedly embedding full task text.

3. **Bound concurrent autonomous_execute fan-out with semaphore control**
   Observation: Concurrent scenarios increase p95 latency compared with single-request runs as request fan-out grows.
   Action: Introduce a lightweight per-process semaphore for high parallelism paths and expose queue depth in telemetry to keep throughput stable under burst load.

4. **Split telemetry payload assembly from hot execution path**
   Observation: Every loop currently builds full telemetry dictionaries even in deterministic success paths where fallback is not triggered.
   Action: Collect hot-path counters first and build expanded telemetry payloads only once at response assembly, reducing per-loop object churn.

## Reproduce

- python3 scripts/profile_execution_paths.py --iterations 30 --output docs/performance-baseline.json --report docs/performance-baseline.md
