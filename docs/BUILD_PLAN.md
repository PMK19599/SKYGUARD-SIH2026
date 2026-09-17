# SKYGUARD Build Plan

This document outlines the phased milestone roadmap for developing the SKYGUARD decision engine for SIH 2026 (Problem Statement SIH26073).

---

## Milestone Roadmap

```text
M0: Repository Foundation [COMPLETE]
  ↓
M1-A: Contract Freeze [COMPLETE AFTER REVIEW]
  ↓
M1-B: Virtual AWS Network (Simulator & Ingestion) [NOT STARTED]
  ↓
M1-C: Decision Engine (Deterministic Core & Attribution) [NOT STARTED]
  ↓
M2: Command-Center Dashboard (Operational Interface) [NOT STARTED]
  ↓
M3: Physical ESP32 + BME280 Edge Testbed [NOT STARTED]
  ↓
M4: ML Supporting Evidence & Spatial Analysis [NOT STARTED]
  ↓
M5: Demo Hardening & Benchmark Scenarios [NOT STARTED]
```

---

## Detailed Milestone Descriptions

### Milestone 0: Repository Foundation [COMPLETE]
- Clean modular repository structure.
- Baseline documentation and architectural guidelines.
- Git repository initialization and baseline architecture commit.

---

### Milestone 1-A: Contract Freeze [COMPLETE AFTER REVIEW]
- **Goal**: Freeze canonical data contracts, schemas, API definitions, and architectural invariants.
- **Deliverables**:
  - Authoritative Station, Observation, Evidence, Decision, and API schemas.
  - Causal hypothesis modeling (`WORLD` vs. `SENSOR`).
  - Strict observation integrity rules (no embedded diagnosis, null missing data handling).
  - Pydantic v2 type contracts and automated unit test suite.

---

### Milestone 1-B: Virtual AWS Network (Simulator & Ingestion) [NOT STARTED]
- **Goal**: Implement multi-station synthetic data generation and realistic meteorological physics.
- **Deliverables**:
  - `simulator/`: Multi-station synthetic network generator with diurnal solar cycles, regional storm fronts, and controlled fault injectors (drift, stuck values, spikes).
  - Ingestion adapter piping synthetic observations into the pipeline via `POST /ingest`.
  - Scenario generation harnesses for reproducible evaluation.

---

### Milestone 1-C: Decision Engine (Deterministic Core) [NOT STARTED]
- **Goal**: Implement deterministic physical limit checks, evidence collectors, independence gating, and five-state decision engine.
- **Deliverables**:
  - `backend/qc/`: Deterministic physical range, step, and persistence checks.
  - `backend/evidence/`: Spatial neighbor correlation, temporal gradient, and sensor noise evaluators.
  - `backend/engine/`: Deterministic decision engine arbitrating evidence into `NORMAL`, `WORLD`, `SENSOR`, `BOTH`, or `UNKNOWN`.
  - Full automated scenario test suite verifying invariant adherence.

---

### Milestone 2: Command-Center Dashboard [NOT STARTED]
- **Goal**: Build an intuitive, high-performance operational web dashboard for station operators and meteorologists.
- **Deliverables**:
  - Network overview with station status cards (`NORMAL`, `WORLD`, `SENSOR`, `BOTH`, `UNKNOWN`).
  - Deep-dive station view showing time series, evidence cards, independence verification, and provenance trace.
  - Scenario playback controller to demonstrate real-time fault vs. storm differentiation.
  - *Strict constraint*: Dashboard only visualizes backend decisions and performs zero independent diagnosis.

---

### Milestone 3: Physical ESP32 + BME280 Edge Acquisition Testbed [NOT STARTED]
- **Goal**: Connect a physical IoT edge sensor to demonstrate real-world serial/MQTT data ingestion.
- **Deliverables**:
  - ESP32 firmware reading BME280 temperature, humidity, and barometric pressure.
  - Edge ingestion adapter piping physical observations into the backend decision pipeline.
  - Demonstration of live physical sensor fault induction (e.g., thermal shock, disconnection).

---

### Milestone 4: ML Supporting Evidence & Spatial Analysis [NOT STARTED]
- **Goal**: Introduce contextual machine learning models as investigative evidence generators.
- **Deliverables**:
  - Spatial neighbor anomaly detection models.
  - Multi-variable temporal autoencoders / isolation forests providing hypothesis scoring.
  - Provenance integration ensuring ML scores are wrapped as `SUPPORTED`, `QUALIFIED`, `UNKNOWN`, or `REJECTED` evidence items.

---

### Milestone 5: Demo Hardening & Benchmark Evaluation [NOT STARTED]
- **Goal**: Prepare an end-to-end evaluation suite with reproducible scenario benchmarks.
- **Deliverables**:
  - Benchmark suite testing edge cases (squall line vs. failing thermistor, simultaneous storm + sensor disconnect).
  - Reproducible demo runbook and automated verification scripts.
  - System performance diagnostics and documentation refinement.
