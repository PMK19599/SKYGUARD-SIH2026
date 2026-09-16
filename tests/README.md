# SKYGUARD Test Suite

## Responsibilities

This directory contains automated test suites to ensure data contract enforcement, deterministic quality control verification, independence gating correctness, and decision engine stability.

## Test Categorization

- `unit/`: Tests individual physical bounds checks, evidence evaluators, and independence gate logic in isolation.
- `integration/`: Tests ingestion pipeline flow from raw observation to final five-state output object.
- `scenarios/`: End-to-end regression tests verifying that predefined synthetic scenarios evaluate to their expected operational states (`NORMAL`, `WORLD`, `SENSOR`, `BOTH`, `UNKNOWN`).

## Testing Philosophy

- High test coverage on deterministic safety checks and evidence quality filters.
- Zero reliance on network calls or live hardware during automated unit/integration runs.
