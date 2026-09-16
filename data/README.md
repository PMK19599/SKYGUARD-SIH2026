# SKYGUARD Data Subsystem

## Responsibilities

This directory manages dataset storage, sample scenario recordings, station metadata registries, and synthetic benchmarks for offline evaluation.

## Directory Layout

- `raw/`: Raw telemetry logs and uncleaned observations (ignored by git, preserved locally).
- `processed/`: Validated observations, curated scenario benchmark traces, and feature matrices.
- `metadata/`: Static station metadata (station IDs, coordinates, sensor types, elevation).

## Data Integrity Guidelines

- All dataset artifacts used for formal benchmarks must have documented origin timestamps and generation parameters.
- Raw synthetic scenario traces must never include runtime decision engine state overrides.
