# SKYGUARD Backend Subsystem

## Responsibilities

The backend subsystem hosts the core deterministic decision engine, observation ingestion pipeline, physical validity checks, evidence synthesis, independence evaluation, and REST/WebSocket API endpoints.

## Architectural Principles

1. **Deterministic Authority**: The final decision state (`NORMAL`, `WORLD`, `SENSOR`, `BOTH`, `UNKNOWN`) is evaluated deterministically based on verified evidence and independence gates.
2. **Safety First**: Clearly invalid observations are handled by deterministic physical limits.
3. **Decoupled Evidence**: Evidence collectors produce structured evidence objects with provenance before final decision attribution.

## Key Modules (To Be Implemented in M1)

- `ingestion/`: Ingests and validates incoming station observations.
- `qc/`: Deterministic range, step, and persistence checks.
- `evidence/`: Evaluators for world evidence (spatial neighbor correlation, multi-parameter coupling) and sensor evidence (stuck values, electrical noise, baseline drift).
- `engine/`: Decision arbitration core mapping evidence into the 5 operational states.
- `api/`: FastAPI routing and streaming endpoints for dashboard consumption.
