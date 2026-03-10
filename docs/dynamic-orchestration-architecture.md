# Dynamic Orchestration Architecture

This document describes the production architecture for dynamic autonomous execution introduced in Issue 9.

## Goals

- Preserve current external APIs with additive fields only.
- Keep offline deterministic tests stable.
- Avoid external telemetry dependencies.
- Make fallback behavior observable and safe for phased rollout.

## High-Level Flow

1. Request enters autonomous_execute with mode and execution_mode.
2. Dynamic planning builds discovered skills, classified skills, team composition, and DAG order.
3. Autonomous loop executes PEGEV phases using the DAG order.
4. Runtime or planning fallback may route to legacy orchestrate_task when enabled.
5. Response returns loop history plus additive telemetry and correlation metadata.

## Core Components

- mcp_server.py
  - autonomous_execute: top-level orchestration entrypoint.
  - _collect_autonomous_run: loop runner and phase transition extraction.
  - _build_planning_telemetry: per-loop planning telemetry calculation.
  - _aggregate_telemetry: run-level telemetry rollup.
  - _log_structured_event: JSON structured logging sink.
- dynamic_orchestration.py
  - build_dynamic_planning_result: deterministic discovery/classification/team/DAG planner.
- backtest_suite.py
  - report includes operational comparison payload under operational_comparison.

## Additive Response Contract

autonomous_execute now includes:

- correlation_id: unique identifier per request.
- telemetry:
  - discovery_success_rate: mean of per-loop discovery success rates.
  - classification_confidence: mean classifier confidence across discovered classifications.
  - dag_latency_ms: mean planning latency in milliseconds.
  - dag_latency: same latency in seconds for backward readability.
  - fallback_rate: fallback frequency across executed loops.
  - loop_metrics: per-loop telemetry values.

Existing fields remain unchanged.

## Structured Logging Model

All structured events are emitted as JSON payloads in the existing logger stream:

- autonomous.start
- planning.completed
- phase.transition
- loop.completed
- loop.error
- fallback.triggered
- autonomous.completed

Every structured event includes:

- event
- correlation_id

Loop-specific events include loop and mode/fallback context where applicable.

## Phase Transition Observability

Phase transitions are detected from WorkflowOutputEvent entries that contain Phase:. A phase.transition event is emitted only when the phase changes, to avoid noisy duplicates.

## Fallback Semantics

- Planning fallback branch: triggered when team_spec.fallback_required is true and fallback is allowed.
- Runtime fallback branch: triggered when loop runtime errors and fallback is allowed.
- fallback_rate is additive telemetry and does not alter fallback behavior.

## Operational Notes

- Telemetry is computed in-memory and returned in response payloads.
- No network calls or external metrics services are required.
- Contract remains deterministic under test stubs.
