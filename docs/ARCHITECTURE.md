# SKYGUARD System Architecture

## Overview

SKYGUARD is an attribution and decision-support layer designed for Automatic Weather Station (AWS) networks. The fundamental architectural objective is answering a single critical question:

> *"When weather data looks wrong, determine whether the world changed—or the sensor did."*

SKYGUARD sits between raw sensor ingestion and downstream operational systems, providing deterministic safety checks, independent evidence synthesis, and explainable decision states.

---

## Architectural Invariants

The SKYGUARD architecture is governed by ten fundamental invariants:

1. **Observation ≠ Interpretation**: Observations are immutable raw physical facts. They contain zero diagnosis, scores, or states.
2. **Evidence ≠ Decision**: Evidence supports or contradicts a hypothesis. It never independently sets an operational state.
3. **AI ≠ Judge**: AI/ML models act as investigators producing supporting evidence; the deterministic decision engine retains final authority.
4. **Outlier ≠ Fault**: An unusual reading may be an environmental extreme (`WORLD`), a malfunction (`SENSOR`), or both.
5. **Agreement ≠ Independence**: Corroborating sources must be structurally independent; mere agreement is insufficient.
6. **Correlation ≠ Independence**: Spatial or cross-sensor correlation does not establish independent evidence channels.
7. **`BOTH` Requires Independent Support**: Assigning `BOTH` strictly requires independent evidence corroborating both an environmental event and a sensor issue.
8. **`UNKNOWN` is Deliberate**: When evidence is missing, conflicting, stale, or non-independent, `UNKNOWN` is the deliberate, safe outcome.
9. **Dashboard Never Diagnoses**: The dashboard is strictly an observational and presentation layer; it computes zero diagnostic logic.
10. **Scenario Labels Never Enter Decision Logic**: Ground-truth scenario labels are strictly offline validation metadata and never reach runtime decision logic.

---

## Conceptual Pipeline

```text
AWS / Simulator / Edge
        ↓
   Data Quality
        ↓
Deterministic Checks
        ↓
World Evidence ─────┐
                    ├── Evidence Quality
Sensor Evidence ────┘
        ↓
   Provenance
        ↓
Independence Gate
        ↓
 Decision Engine
        ↓
NORMAL / WORLD / SENSOR / BOTH / UNKNOWN
        ↓
Action + Explanation
        ↓
    Dashboard
```

---

## Pipeline Stages

1. **Ingestion Layer (AWS / Simulator / Edge)**
   - Ingests canonical observation payloads (`observation_id`, `station_id`, `observed_at`, `received_at`, `measurements`, `source`, `sequence`).
   - Ingestion sources can be physical hardware testbeds (ESP32 + BME280), simulated AWS networks, or meteorological telemetry feeds.

2. **Data Quality & Physical Validation**
   - Applies deterministic physical limit checks (e.g., climatological limits, rate-of-change thresholds, sensor operating bounds).
   - Flags immediately impossible values (e.g., negative Kelvin, 120% relative humidity, sudden 50°C jumps in 1 second).

3. **Deterministic Checks**
   - Evaluates basic physical and temporal consistency without requiring ML or complex heuristics.
   - Ensures the safety baseline is preserved even if higher-level intelligence components degrade.

4. **Evidence Collection (World vs. Sensor)**
   - **World Evidence**: Spatial neighbor consistency, regional gradient alignment, multi-variable physical co-variation (e.g., temperature drop coinciding with pressure surge and humidity spike during a cold front).
   - **Sensor Evidence**: Electrical noise signatures, stuck-value counters, drift against co-located/adjacent baselines, packet drop rates, calibration anomalies.

5. **Evidence Quality Evaluation**
   - Before fusing any evidence, its quality is scored based on latency, freshness, completeness, and spatial proximity. Stale or degraded evidence is flagged or down-weighted.

6. **Provenance Tracking**
   - Every piece of evidence maintains strict provenance: origin source, timestamp, computation method, and source observation IDs.

7. **Independence Gate**
   - Checks whether supporting sources are truly independent.
   - Correlated sensors on the same tower or common power supply cannot be counted as independent corroborating witnesses.

8. **Decision Engine**
   - Purely deterministic arbitration core that maps verified evidence and independence conditions into exactly one of the five operational states: `NORMAL`, `WORLD`, `SENSOR`, `BOTH`, or `UNKNOWN`.

9. **Action + Explanation Generation**
   - Generates unambiguous recommended actions and human-readable causal explanations tailored to operational personnel.

10. **Visualization / Dashboard**
    - Presents the engine's final decision state, evidence cards, provenance trails, and recommended actions to operators.

---

## Scenario Lab & Injection Architecture

The Scenario Lab provides controlled synthetic meteorological dynamics and sensor fault injection to validate the decision engine.

```text
┌─────────────────────────────────────────────────────────────┐
│                        SCENARIO LAB                         │
│                                                             │
│   [Scenario Generator] ──(Injects synthetic observations)   │
│            │                                                │
│            ▼                                                │
│      POST /ingest                                           │
│            │                                                │
│            ▼                                                │
│  [Standard Ingestion Pipeline]                              │
│            │                                                │
│            ▼                                                │
│  [Deterministic Decision Engine]                            │
│            │                                                │
│            ▼                                                │
│  [Decision Output] ◄── [Ground Truth Evaluator (Offline)]   │
└─────────────────────────────────────────────────────────────┘
```

### Scenario Rules:
- Scenario injection modifies observations through the standard ingestion pipeline.
- Scenario ground-truth labels are stored in the validation harness only.
- The decision engine never has access to scenario metadata.
