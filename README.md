# SKYGUARD — Weather Data Trust & Sensor Health Decision Engine

> **"When weather data looks wrong, determine whether the world changed—or the sensor did."**

[![SIH 2026](https://img.shields.io/badge/SIH%202026-Problem%20SIH26073-blue.svg)](https://www.sih.gov.in/)
[![Theme](https://img.shields.io/badge/Theme-Disaster%20Management-orange.svg)](#)
[![Ministry](https://img.shields.io/badge/Organization-MoES%20%2F%20IMD-green.svg)](#)
[![Status](https://img.shields.io/badge/Status-M1--A%20Contract%20Freeze-lightgrey.svg)](docs/BUILD_PLAN.md)

---

## 📌 Problem Statement & Context

- **Event**: Smart India Hackathon (SIH) 2026
- **Problem Statement ID**: SIH26073
- **Title**: AI/ML-Based Intelligent Anomaly Detection for Automatic Weather Stations (AWS)
- **Category**: Software
- **Theme**: Disaster Management
- **Organization**: Ministry of Earth Sciences (MoES) / India Meteorological Department (IMD)
- **Team**: Axiom Forge

---

## 🎯 Positioning & What SKYGUARD Is

> **SKYGUARD is a weather-data trust and sensor-health decision engine that helps determine whether an unusual AWS observation reflects a genuine environmental change, a sensor issue, both, or insufficient evidence.**

We are **NOT** building a generic anomaly detector that merely flags outliers. Standard anomaly detectors produce binary alarms without distinguishing whether a sudden 15°C temperature drop is a severe microburst (environmental event) or a failing thermistor (sensor failure).

SKYGUARD serves as an **attribution and decision-support layer** for Automatic Weather Station observations, resolving the central operational question:

> *"Did the world change, did the sensor change, did both change, or do we simply not have enough evidence to know?"*

---

## 🚦 The Five Operational States

Every evaluated observation is attributed to exactly one of five operational states:

| Operational State | Meaning | Prescribed Action |
|---|---|---|
| **`NORMAL`** | No sufficient evidence of abnormality. | `Continue observation.` |
| **`WORLD`** | Environmental change is supported by independent evidence. | `Observe/continue with event context.` |
| **`SENSOR`** | Station behavior is inconsistent with available world evidence. | `Inspect/validate sensor.` |
| **`BOTH`** | Independent evidence supports environmental change **AND** sensor issue. | `Handle event + inspect sensor.` |
| **`UNKNOWN`** | Cause cannot be independently established (evidence is insufficient, conflicting, stale, missing, or non-independent). | `Human review.` |

*Note: These are operational states designed for actionable decision-support under uncertainty, not claims of infallible causal omniscience.*

---

## 🛡️ Core Safety Principle & AI Role

> **"The intelligence path may degrade. The safety path must remain."**

- **AI is NOT the final judge**: AI/ML models act as investigative tools that extract contextual features and formulate hypotheses (labeled as `SUPPORTED`, `QUALIFIED`, `UNKNOWN`, or `REJECTED`).
- **Deterministic Decision Core**: The deterministic decision engine retains final authority for assigning operational states, ensuring predictable, auditable, and fail-safe operation even if ML services are offline.
- **Strict Dashboard Role**: The command-center dashboard is an observational and presentation layer. It **never** invents or independently determines a diagnostic state.

---

## 🔬 Hardware Testbed Context

Physical edge hardware (ESP32 microcontroller with BME280 sensor suite) is utilized within SKYGUARD as a **demonstration and edge acquisition testbed** rather than a system dependency. SKYGUARD is designed to integrate seamlessly across physical microcontrollers, synthetic AWS network streams, and standard meteorological telemetry feeds.

---

## 🏗️ Repository Architecture

```text
SKYGUARD-SIH2026/
│
├── backend/          # Deterministic decision engine, physical QC, and API layer
├── frontend/         # Command-center visualization & scenario inspection dashboard
├── ml/               # Contextual feature extraction & supporting evidence models
├── simulator/        # Multi-station virtual AWS network & scenario fault injection
├── edge/             # ESP32 + BME280 testbed firmware and ingestion adapter
├── data/             # Benchmark traces, station metadata, and synthetic datasets
├── tests/            # Contract tests, deterministic QC tests, and scenario suites
├── scripts/          # Developer automation, generation, and evaluation scripts
├── docs/             # Frozen architectural and collaboration specifications
│   ├── ARCHITECTURE.md
│   ├── DATA_CONTRACT.md
│   ├── DECISION_STATES.md
│   ├── BUILD_PLAN.md
│   └── AI_COLLABORATION.md
├── .env.example      # Environment configuration template
├── .gitignore        # Git ignore rules
└── README.md         # Root project overview
```

For complete architectural details, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/DATA_CONTRACT.md`](docs/DATA_CONTRACT.md).

---

## ⚙️ Development Philosophy & Boundaries

In Team Axiom Forge, we prioritize engineering rigor, explainability, and epistemic honesty over inflated claims:

- We do **NOT** claim production accuracy, 99% real-world accuracy, 100% fault detection, or zero false positives.
- We do **NOT** claim government deployment readiness or autonomous field maintenance.
- We do **NOT** claim AI superiority over traditional QC or replacement of existing IMD quality-control systems.
- Benchmark evaluations are strictly reported against documented synthetic testbeds.

---

## 📊 Current Project Status

- **M0 — Repository Foundation**: `COMPLETE`
- **M1-A — Contract Freeze**: `COMPLETE AFTER REVIEW`
- **M1-B — Virtual AWS Network**: `NOT STARTED`
- **M1-C — Decision Engine**: `NOT STARTED`
- **M2 — Command-Center Dashboard**: `NOT STARTED`
- **M3 — Physical ESP32 + BME280 Edge Testbed**: `NOT STARTED`
- **M4 — ML Supporting Evidence**: `NOT STARTED`
- **M5 — Demo Hardening**: `NOT STARTED`
