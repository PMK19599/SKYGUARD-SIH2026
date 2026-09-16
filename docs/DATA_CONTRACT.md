# SKYGUARD Data Contract

This document defines the core data schemas and interfaces exchanged across the SKYGUARD pipeline, including ingestion payloads, internal evidence structures, and final decision payloads.

---

## 1. Raw Station Observation Schema

Observations arriving from physical edge nodes (ESP32), virtual network simulators, or weather telemetry streams adhere to the following schema:

```json
{
  "station_id": "AWS-03",
  "temperature": 31.8,
  "humidity": 68.2,
  "pressure": 1008.4,
  "timestamp": "2026-09-16T18:30:00+05:30"
}
```

### Field Definitions

| Field | Type | Description | Units / Format |
|---|---|---|---|
| `station_id` | `string` | Unique identifier of the weather station | e.g. `"AWS-01"` |
| `temperature` | `number` | Ambient air temperature | Degrees Celsius (°C) |
| `humidity` | `number` | Relative humidity | Percentage (0.0 to 100.0%) |
| `pressure` | `number` | Atmospheric barometric pressure | Hectopascals (hPa) |
| `timestamp` | `string` | Observation timestamp | ISO 8601 with timezone offset |

---

## 2. Final Decision Object Schema

The decision engine produces a single structured output for every evaluated observation:

```json
{
  "station_id": "AWS-03",
  "timestamp": "2026-09-16T18:30:00+05:30",
  "state": "SENSOR",
  "confidence": 0.0,
  "world_evidence": [],
  "sensor_evidence": [],
  "evidence_quality": {},
  "provenance": [],
  "independence": {},
  "reason": "",
  "action": ""
}
```

### Field Definitions

| Field | Type | Description |
|---|---|---|
| `station_id` | `string` | Target station identifier |
| `timestamp` | `string` | Evaluation timestamp (ISO 8601) |
| `state` | `string` | Operational state: `NORMAL`, `WORLD`, `SENSOR`, `BOTH`, `UNKNOWN` |
| `confidence` | `number` | Algorithmic scoring metric (see Confidence Disclaimer below) |
| `world_evidence` | `array` | List of validated world-evidence items (spatial, physical, contextual) |
| `sensor_evidence` | `array` | List of validated sensor-fault evidence items (noise, drift, stuck) |
| `evidence_quality` | `object` | Quality metrics assessed for each contributing evidence item |
| `provenance` | `array` | Origin, sensor IDs, algorithm versions, and pipeline trace |
| `independence` | `object` | Independence verification metrics between evidence sources |
| `reason` | `string` | Concise human-readable explanation of why the state was selected |
| `action` | `string` | Prescribed operational procedure for station maintainers / forecasters |

---

## 3. Confidence Disclaimer & Safety Rule

> [!IMPORTANT]
> **Confidence Metric Handling**:
> The `confidence` field is an internal heuristic and algorithmic scoring metric. It **must NOT** be presented or interpreted as a calibrated statistical probability unless empirical calibration has been rigorously validated on real-world datasets.
> 
> High confidence never overrides missing independence, conflicting evidence, or basic deterministic sanity checks.

---

## 4. Evidence Object Schema (Internal)

Individual evidence items contained within `world_evidence` and `sensor_evidence` follow this internal structure:

```json
{
  "evidence_id": "EV-NEIGHBOR-CORR-01",
  "source_type": "SPATIAL_NEIGHBOR",
  "label": "SUPPORTED",
  "description": "3 nearest neighbor stations within 15km show consistent 3.5°C drop over the same 10-minute window.",
  "quality_score": 0.88,
  "provenance": {
    "source_stations": ["AWS-01", "AWS-02", "AWS-04"],
    "computed_at": "2026-09-16T18:30:02+05:30",
    "method": "spatial_gradient_check_v1"
  }
}
```
