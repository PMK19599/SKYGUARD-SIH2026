# SKYGUARD System Architecture

## Overview

SKYGUARD is an attribution and decision-support layer designed for Automatic Weather Station (AWS) networks. The fundamental architectural objective is answering a single critical question:

> *"When weather data looks wrong, determine whether the world changed—or the sensor did."*

SKYGUARD sits between raw sensor ingestion and downstream operational systems, providing deterministic safety checks, independent evidence synthesis, and explainable decision states.

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
   - Ingests high-frequency environmental telemetry (`temperature`, `humidity`, `pressure`, timestamps, station identifiers).
   - Ingestion sources can be physical hardware testbeds (ESP32 + BME280), simulated AWS networks, or historical records.

2. **Data Quality & Physical Validation**
   - Applies deterministic physical limit checks (e.g., climatological limits, rate-of-change thresholds, sensor operating bounds).
   - Flags immediately impossible values (e.g., negative Kelvin, 120% relative humidity, sudden 50°C jumps in 1 second).

3. **Deterministic Checks**
   - Evaluates basic consistency without requiring ML or complex heuristics.
   - Ensures the safety baseline is preserved even if higher-level intelligence components degrade.

4. **Evidence Collection (World vs. Sensor)**
   - **World Evidence**: Spatial neighbor consistency, regional gradient alignment, multi-variable physical co-variation (e.g., temperature drop coinciding with pressure surge and humidity spike during a cold front).
   - **Sensor Evidence**: Electrical noise signatures, stuck-value counters, drift against co-located/adjacent baselines, packet drop rates, calibration anomalies.

5. **Evidence Quality Evaluation**
   - Before fusing any evidence, its quality is scored based on latency, freshness, noise levels, and spatial proximity. Stale or degraded evidence is flagged or down-weighted.

6. **Provenance Tracking**
   - Every piece of evidence maintains strict provenance: origin source, timestamp, computation method, and processing pipeline version.

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

## Core Architectural Rules

1. **Dashboard never diagnoses**: The frontend dashboard is strictly an observational and presentation layer. It must NEVER invent, compute, or independently determine a diagnostic state.
2. **Deterministic checks handle clearly invalid observations**: Base physical bounds and gross corruption are caught deterministically prior to evidence synthesis.
3. **Evidence must have provenance**: No observation, hypothesis, or feature may participate in decision-making without a traceable origin, timestamp, and method signature.
4. **Evidence quality must be evaluated before evidence fusion**: Corrupted, stale, or low-resolution signals must not be weighted equally with high-confidence observations.
5. **Correlated sources cannot automatically be treated as independent**: Spatial proximity alone does not guarantee independence (e.g., shared telemetry gateways or identical calibration drift batches).
6. **`BOTH` requires independent support for both world and sensor causes**: The system will not emit `BOTH` unless clear, separate, and verified evidence exists for both an environmental event and a sensor malfunction.
7. **`UNKNOWN` is a deliberate safety outcome**: When evidence is incomplete, conflicting, stale, or non-independent, `UNKNOWN` is the correct, safe output. It is not an unhandled exception or system failure.
8. **Causal ambiguity is allowed**: When signals do not clearly distinguish environmental dynamics from instrument faults, the engine explicitly acknowledges ambiguity rather than guessing.
9. **Scenario injection must modify observations/evidence through the same pipeline**: Simulated faults or weather events must pass through standard ingestion and verification channels; no bypassing allowed.
10. **Scenario labels must NEVER directly set the final decision state**: Injected ground-truth metadata is used strictly for offline validation/benchmarking and must never leak into the runtime decision engine.
11. **AI produces supporting evidence/hypotheses, not authoritative final states**: AI/ML models act as investigative tools (e.g., finding subtle spatio-temporal anomalies or pattern hypotheses). The deterministic decision engine retains final authority.
