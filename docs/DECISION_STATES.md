# SKYGUARD Decision States

## Operational State Taxonomy

SKYGUARD classifies every evaluated station observation into one of five mutually exclusive operational states. These states guide operational actions for meteorologists, field technicians, and automated data pipelines.

> [!NOTE]
> **Operational Scope**:
> These are **operational states** designed for actionable decision support under uncertainty, **not** philosophical claims of infallible or omniscient causal identification.

---

## The Five Operational States

```
┌─────────────────────────────────────────────────────────────┐
│                      SKYGUARD STATES                        │
├─────────────┬───────────────────────────────────────────────┤
│   NORMAL    │ No sufficient evidence of abnormality         │
│   WORLD     │ Environmental change supported by evidence    │
│   SENSOR    │ Station behavior inconsistent with world data │
│    BOTH     │ Environmental change AND sensor issue present │
│   UNKNOWN   │ Evidence insufficient, conflicting, or stale  │
└─────────────┴───────────────────────────────────────────────┘
```

---

### 1. `NORMAL`

- **Definition**: The observation passes all deterministic physical validity tests, and there is no statistically or physically significant evidence indicating an anomaly in either the environment or the instrument.
- **Operational Meaning**: Data stream is nominal and within expected climatological and diurnal variation.
- **Default Action**: `Continue observation.`

---

### 2. `WORLD`

- **Definition**: An anomalous or rapid change is detected, but independent corroborating evidence (e.g., neighbor stations, multi-variable meteorological coupling such as gust + pressure surge, satellite/radar context) confirms that a genuine atmospheric event is occurring.
- **Operational Meaning**: The sensor is accurately reporting real physical weather dynamics (e.g., squall lines, microbursts, sea breeze front).
- **Default Action**: `Observe/continue with event context.` (Tag data as high-significance meteorological event; preserve in downstream forecasting pipelines).

---

### 3. `SENSOR`

- **Definition**: The observation deviates significantly from expected physical limits or regional baselines, and available independent world evidence does *not* support an environmental shift (e.g., isolated spike with normal neighbors, frozen constant values, electrical noise spikes).
- **Operational Meaning**: The reading is most likely an artifact of hardware degradation, power fluctuations, calibration drift, or bio-fouling.
- **Default Action**: `Inspect/validate sensor.` (Flag sensor telemetry as suspect, down-weight in numerical weather prediction ingestion, trigger field validation ticket).

---

### 4. `BOTH`

- **Definition**: Independent evidence confirms that a significant environmental event is taking place, *and* independent diagnostic evidence confirms that the sensor is simultaneously experiencing a fault or degraded operation (e.g., a lightning surge causing calibration shift during an active storm).
- **Operational Meaning**: A real weather event is underway, but this specific instrument is misrepresenting the magnitude or failing to capture it accurately.
- **Default Action**: `Handle event + inspect sensor.` (Escalate meteorological alert while dispatching urgent hardware diagnostics/calibration review).
- **Critical Invariant**: Assigning `BOTH` strictly requires independent, verified evidence supporting BOTH `WORLD` and `SENSOR`. It cannot be assigned based on conjecture.

---

### 5. `UNKNOWN`

- **Definition**: The root cause cannot be established with acceptable confidence because evidence is insufficient, conflicting, stale, missing, non-independent, or causally ambiguous.
- **Operational Meaning**: The system explicitly admits epistemic uncertainty rather than forcing an ungrounded classification.
- **Default Action**: `Human review.` (Route flagged observation to a meteorological data analyst for manual triage and review).
- **Critical Invariant**: `UNKNOWN` is a deliberate, first-class safety outcome, not a system failure.

---

## State Transition & Attribution Matrix

| World Evidence | Sensor Fault Evidence | Independence Verified | Resulting State | Default Action |
|---|---|---|---|---|
| Absent / Nominal | Absent / Nominal | Yes | **`NORMAL`** | Continue observation |
| Strong & Corroborated | Absent | Yes | **`WORLD`** | Observe/continue with event context |
| Absent / Contradicted | Strong & Identified | Yes | **`SENSOR`** | Inspect/validate sensor |
| Strong & Corroborated | Strong & Identified | Yes | **`BOTH`** | Handle event + inspect sensor |
| Weak / Conflicting / Stale | Any / Conflicting | No / Partial | **`UNKNOWN`** | Human review |
