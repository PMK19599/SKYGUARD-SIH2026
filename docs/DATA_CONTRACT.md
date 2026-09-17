# SKYGUARD Data Contract

This document defines the authoritative, frozen schemas and interfaces across the SKYGUARD pipeline.

---

## Architectural Invariants for Data Flow

- **Observation ≠ Interpretation**: Observations are immutable raw physical facts. They contain zero diagnosis, scores, or states.
- **Evidence ≠ Decision**: Evidence items support or contradict a specific causal hypothesis (`WORLD` or `SENSOR`). They do not assign operational states.
- **AI ≠ Judge**: AI/ML models output supporting hypotheses and evidence scores; the deterministic decision engine retains final authority.
- **Outlier ≠ Fault**: An extreme reading may be a severe meteorological event (`WORLD`), an instrument malfunction (`SENSOR`), or both.
- **Agreement ≠ Independence**: Corroborating sources must be verified as statistically and physically independent before evidence fusion.
- **Correlation ≠ Independence**: Spatial or physical correlation does not imply independent sensor channels.
- **`BOTH` Requires Independent Support**: Assigning `BOTH` strictly requires independent evidence corroborating both an environmental event and a sensor issue.
- **`UNKNOWN` is Deliberate**: When evidence is missing, conflicting, stale, or non-independent, `UNKNOWN` is the correct safety outcome.
- **Dashboard Never Diagnoses**: The dashboard is strictly a consumer and renderer of backend decision objects.
- **Scenario Labels Never Enter Decision Logic**: Scenario metadata is used strictly for offline validation and must never leak into runtime decision paths.

---

## 1. Canonical Station Schema

Stations represent static identity, geographical location, and sensor capabilities. Station entities do **not** contain dynamic health or diagnosis fields; operational health is evaluated downstream by the decision engine.

```json
{
  "station_id": "AWS-03",
  "name": "AWS-03",
  "location": {
    "latitude": 12.9716,
    "longitude": 77.5946,
    "elevation_m": 920
  },
  "sensors": [
    {"type": "temperature", "unit": "celsius"},
    {"type": "relative_humidity", "unit": "percent"},
    {"type": "pressure", "unit": "hpa"}
  ]
}
```

### Field Definitions

| Field | Type | Description |
|---|---|---|
| `station_id` | `string` | Unique identifier for the automatic weather station (e.g., `"AWS-03"`). |
| `name` | `string` | Human-readable station designation. |
| `location.latitude` | `number` | Latitude in decimal degrees (-90.0 to 90.0). |
| `location.longitude` | `number` | Longitude in decimal degrees (-180.0 to 180.0). |
| `location.elevation_m` | `number` | Station elevation above sea level in meters. |
| `sensors` | `array` | List of installed sensor instruments and their standard reporting units. |

---

## 2. Canonical Observation Schema

An Observation is an immutable raw measurement payload captured at a specific point in time.

```json
{
  "observation_id": "obs-AWS03-000184",
  "station_id": "AWS-03",
  "observed_at": "2026-09-16T18:30:00+05:30",
  "received_at": "2026-09-16T18:30:02+05:30",
  "measurements": {
    "temperature_c": 31.8,
    "relative_humidity_pct": 68.2,
    "pressure_hpa": 1008.4
  },
  "source": {
    "type": "SIMULATOR",
    "source_id": "sim-network-01"
  },
  "sequence": 184
}
```

### Observation Integrity Rules

1. **`observed_at`**: Timestamp when the physical measurement took place at the station.
2. **`received_at`**: Timestamp when SKYGUARD ingestion received the observation.
3. **Missing Data Handling**: If a sensor fails to report or a channel is dropped, the field remains `null` or omitted. **Never replace missing data with `0` or placeholder numbers.**
4. **Immutability**: Raw observations are stored as immutable records of fact.
5. **Zero Interpretation**: An observation must **NOT** contain any of the following fields:
   - `state`
   - `anomaly_score`
   - `sensor_fault`
   - `confidence`
   - `diagnosis`
   - `AI conclusion`

### Field Definitions

| Field | Type | Description | Units / Format |
|---|---|---|---|
| `observation_id` | `string` | Unique identifier of the observation record | e.g. `"obs-AWS03-000184"` |
| `station_id` | `string` | Identifier of reporting station | e.g. `"AWS-03"` |
| `observed_at` | `string` | Measurement capture time | ISO 8601 with timezone |
| `received_at` | `string` | System ingestion time | ISO 8601 with timezone |
| `measurements.temperature_c` | `number \| null` | Ambient air temperature | Degrees Celsius (°C) |
| `measurements.relative_humidity_pct` | `number \| null` | Relative humidity | Percentage (0.0 to 100.0%) |
| `measurements.pressure_hpa` | `number \| null` | Atmospheric pressure | Hectopascals (hPa) |
| `source.type` | `string` | Origin stream (`"EDGE"`, `"SIMULATOR"`, `"IMD_TELEMETRY"`) | String enum |
| `source.source_id` | `string` | Identifier of ingestion agent/simulator instance | e.g. `"sim-network-01"` |
| `sequence` | `integer \| null` | Optional monotonically increasing sequence number per station | Positive integer |

---

## 3. Canonical Evidence Schema

Evidence represents a single verified analytical finding produced by a deterministic QC check, spatial comparator, temporal evaluator, or ML hypothesis generator. Evidence is **NOT** a final operational decision; it supports or contradicts a specific causal hypothesis (`WORLD` or `SENSOR`).

```json
{
  "evidence_id": "ev-000184",
  "subject": {
    "station_id": "AWS-03",
    "observation_ids": ["obs-AWS03-000184"]
  },
  "type": "TEMPORAL",
  "relation": "SUPPORTS",
  "hypothesis": "SENSOR",
  "description": "Temperature changed by 23.2°C within 5 minutes.",
  "strength": 0.91,
  "quality": {
    "status": "VALID",
    "freshness": "FRESH",
    "completeness": "COMPLETE"
  },
  "provenance": {
    "source_type": "DERIVED",
    "source_id": "temporal-detector-v1",
    "derived_from": ["obs-AWS03-000184"]
  },
  "independence_group": "station-temporal",
  "status": "AVAILABLE"
}
```

### Evidential Hypothesis Modeling

- **Causal Hypotheses (`WORLD`, `SENSOR`)**: Evidence strictly investigates whether an anomaly is attributed to an environmental phenomenon (`WORLD`) or an instrument/telemetry fault (`SENSOR`).
- **Why `BOTH` is not an evidence hypothesis**: `BOTH` is a composite decision state issued only when there is independent evidence supporting both `WORLD` and `SENSOR`.
- **Why `NORMAL` is not an evidence hypothesis**: `NORMAL` is the null operational state when neither `WORLD` nor `SENSOR` hypotheses are supported (or when evidence actively contradicts them).
- **`strength` Interpretation**: Normalized support score (0.0 to 1.0) indicating evidence weight. It is **NOT** a calibrated statistical probability.

### Evidence Field Definitions

| Field | Type | Description |
|---|---|---|
| `evidence_id` | `string` | Unique identifier for the evidence artifact. |
| `subject.station_id` | `string` | Target station under evaluation. |
| `subject.observation_ids` | `array[string]` | Observation IDs evaluated to construct this evidence. |
| `type` | `string` | Method category: `"TEMPORAL"`, `"SPATIAL"`, `"PHYSICAL_LIMIT"`, `"MULTIVARIATE"`, `"ML_HYPOTHESIS"`. |
| `relation` | `string` | Relationship to hypothesis: `"SUPPORTS"`, `"CONTRADICTS"`. |
| `hypothesis` | `string` | Target causal hypothesis: `"WORLD"`, `"SENSOR"`. |
| `description` | `string` | Human-readable explanation of the quantitative finding. |
| `strength` | `number` | Normalized support score (0.0 to 1.0). *Not a calibrated probability.* |
| `quality.status` | `string` | Data quality status (`"VALID"`, `"DEGRADED"`, `"INVALID"`). |
| `quality.freshness` | `string` | Freshness rating (`"FRESH"`, `"STALE"`, `"EXPIRED"`). |
| `quality.completeness` | `string` | Signal completeness (`"COMPLETE"`, `"PARTIAL"`, `"INTERPOLATED"`). |
| `provenance.source_type` | `string` | Origin tier (`"DETERMINISTIC_QC"`, `"DERIVED"`, `"ML_MODEL"`). |
| `provenance.source_id` | `string` | Specific algorithm / detector version. |
| `provenance.derived_from` | `array[string]` | Source observations or parent evidence IDs. |
| `independence_group` | `string` | Identifier grouping non-independent channels (e.g. `"station-temporal"`, `"bus-01"`). |
| `status` | `string` | Lifecycle status (`"AVAILABLE"`, `"SUPPRESSED"`, `"EXPIRED"`). |

---

## 4. Canonical Decision Schema

The decision engine evaluates all active evidence, verifies independence across evidence groups, and deterministically issues a single decision object for the target station:

```json
{
  "decision_id": "dec-000184",
  "station_id": "AWS-03",
  "timestamp": "2026-09-16T18:30:02+05:30",
  "state": "SENSOR",
  "confidence": 0.91,
  "world_evidence": ["ev-001", "ev-002"],
  "sensor_evidence": ["ev-003"],
  "evidence_quality": {
    "overall": "HIGH"
  },
  "independence": {
    "status": "ESTABLISHED"
  },
  "reason": "Station behavior is inconsistent with available independent world evidence.",
  "action": "Inspect and validate AWS-03 sensor."
}
```

### Decision Field Definitions

| Field | Type | Description |
|---|---|---|
| `decision_id` | `string` | Unique decision trace ID. |
| `station_id` | `string` | Target station identifier. |
| `timestamp` | `string` | Evaluation completion timestamp (ISO 8601). |
| `state` | `string` | Operational state: `NORMAL`, `WORLD`, `SENSOR`, `BOTH`, `UNKNOWN`. |
| `confidence` | `number` | Heuristic engine confidence score (0.0 to 1.0). *Must NOT be interpreted as calibrated probability.* |
| `world_evidence` | `array[string]` | Array of evidence IDs supporting the `WORLD` hypothesis. |
| `sensor_evidence` | `array[string]` | Array of evidence IDs supporting the `SENSOR` hypothesis. |
| `evidence_quality.overall` | `string` | Composite quality rating (`"HIGH"`, `"MEDIUM"`, `"LOW"`, `"INSUFFICIENT"`). |
| `independence.status` | `string` | Independence verification status (`"ESTABLISHED"`, `"PARTIAL"`, `"UNVERIFIED"`, `"FAILED"`). |
| `reason` | `string` | Concise human-readable explanation of why this state was assigned. |
| `action` | `string` | Prescribed operational procedure for technicians or forecasters. |

---

## 5. API Endpoints Contract

The backend exposes the following REST API endpoints:

```text
GET  /stations              # List all registered AWS stations and static metadata
GET  /stations/{id}         # Retrieve static metadata for a specific station
GET  /stations/{id}/history # Retrieve recent raw observation timeseries for a station
POST /ingest                # Ingest raw observation payload (Observation schema)
GET  /decision/{station_id} # Retrieve latest operational decision for a station
GET  /evidence/{station_id} # Retrieve active evidence items for a station
POST /scenario              # Inject a controlled scenario event into the simulator
```

### Scenario Lab Integration Rule

The Scenario Lab modifies observations through the normal ingestion pipeline.

```text
[Scenario Generator] ──(Injects synthetic observations)──> POST /ingest ──> [Standard QC & Decision Pipeline]
```

> [!CAUTION]
> **No Bypass Rule**:
> Never implement shortcut decision logic based on scenario labels, such as:
> ```python
> # FORBIDDEN:
> if scenario == "SENSOR":
>     state = "SENSOR"
> ```
> Scenario labels are validation metadata only and must never be accessible to the runtime decision engine.
