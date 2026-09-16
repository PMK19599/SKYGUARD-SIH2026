# SKYGUARD Build Plan

This document outlines the phased milestone roadmap for developing the SKYGUARD decision engine for SIH 2026 (Problem Statement SIH26073).

---

## Milestone Roadmap

```text
M0: Repository Foundation [CURRENT]
  ↓
M1: Virtual AWS Network (Simulator & Ingestion)
  ↓
M2: Command-Center Dashboard (Operational Interface)
  ↓
M3: Physical ESP32 + BME280 Edge Testbed
  ↓
M4: ML Supporting Evidence & Spatial Analysis
  ↓
M5: Demo Hardening & Benchmark Scenarios
```

---

## Detailed Milestone Descriptions

### Milestone 0: Repository Foundation & Architectural Freeze [CURRENT]
- **Goal**: Establish the repository structure, data contracts, state definitions, safety principles, and cross-team development contracts.
- **Deliverables**:
  - Clean modular repository structure.
  - Frozen `ARCHITECTURE.md`, `DATA_CONTRACT.md`, `DECISION_STATES.md`, and `AI_COLLABORATION.md`.
  - Initial baseline commit.
- **Status**: **IN PROGRESS / INITIALIZED** (Architecture frozen; implementation not started).

---

### Milestone 1: Virtual AWS Network & Core Decision Engine
- **Goal**: Implement deterministic physical limit checks and multi-station synthetic data generation.
- **Deliverables**:
  - `simulator/`: Multi-station synthetic network generator with realistic meteorological physics (diurnal cycles, regional fronts) and controlled fault injectors (drift, stuck values, spikes).
  - `backend/`: Core deterministic checks, evidence collector, independence evaluator, and five-state decision engine.
  - Unit tests for all deterministic validation rules.

---

### Milestone 2: Command-Center Dashboard
- **Goal**: Build an intuitive, high-performance operational web dashboard for station operators and meteorologists.
- **Deliverables**:
  - Network overview with station status cards (`NORMAL`, `WORLD`, `SENSOR`, `BOTH`, `UNKNOWN`).
  - Deep-dive station view showing time series, evidence cards, independence verification, and provenance trace.
  - Scenario playback controller to demonstrate real-time fault vs. storm differentiation.
  - *Strict constraint*: Dashboard only visualizes backend decisions and performs zero independent diagnosis.

---

### Milestone 3: Physical ESP32 + BME280 Edge Acquisition Testbed
- **Goal**: Connect a physical IoT edge sensor to demonstrate real-world serial/MQTT data ingestion.
- **Deliverables**:
  - ESP32 firmware reading BME280 temperature, humidity, and barometric pressure.
  - Edge ingestion adapter piping physical observations into the backend decision pipeline.
  - Demonstration of live physical sensor fault induction (e.g., thermal shock, disconnection).

---

### Milestone 4: ML Supporting Evidence & Spatial Analysis
- **Goal**: Introduce contextual machine learning models as investigative evidence generators.
- **Deliverables**:
  - Spatial neighbor anomaly detection models.
  - Multi-variable temporal autoencoders / isolation forests providing hypothesis scoring.
  - Provenance integration ensuring ML scores are wrapped as `SUPPORTED`, `QUALIFIED`, `UNKNOWN`, or `REJECTED` evidence items.

---

### Milestone 5: Demo Hardening & Benchmark Evaluation
- **Goal**: Prepare an end-to-end evaluation suite with reproducible scenario benchmarks.
- **Deliverables**:
  - Benchmark suite testing edge cases (squall line vs. failing thermistor, simultaneous storm + sensor disconnect).
  - Reproducible demo runbook and automated verification scripts.
  - System performance diagnostics and documentation refinement.
