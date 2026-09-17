"""
SKYGUARD Backend Data Models

Defines Pydantic data schemas following docs/DATA_CONTRACT.md and docs/AI_COLLABORATION.md.
"""

from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field, model_validator


class IngestionPayload(BaseModel):
    """
    Flexible Ingestion Payload schema that accepts both flat docs/DATA_CONTRACT.md schema
    and nested telemetry structures, normalizing to canonical fields.
    """
    station_id: str
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    timestamp: Optional[str] = None

    # Nested fields for extended ingestion formats
    observation_id: Optional[str] = None
    observed_at: Optional[str] = None
    received_at: Optional[str] = None
    measurements: Optional[Dict[str, Optional[float]]] = None
    source: Optional[Any] = None
    sequence: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # Normalize timestamp
        if not data.get("timestamp"):
            if data.get("observed_at"):
                data["timestamp"] = data["observed_at"]
            elif data.get("received_at"):
                data["timestamp"] = data["received_at"]

        # Normalize nested measurements if present
        measurements = data.get("measurements")
        if isinstance(measurements, dict):
            if data.get("temperature") is None:
                data["temperature"] = measurements.get("temperature_c", measurements.get("temperature"))
            if data.get("humidity") is None:
                data["humidity"] = measurements.get("relative_humidity_pct", measurements.get("humidity"))
            if data.get("pressure") is None:
                data["pressure"] = measurements.get("pressure_hpa", measurements.get("pressure"))

        return data


class RawObservation(BaseModel):
    """
    Canonical Station Observation Schema as defined in docs/DATA_CONTRACT.md Section 1.
    Missing values must remain None/null and NEVER be replaced with zero.
    """
    station_id: str = Field(..., description="Unique identifier of the weather station")
    temperature: Optional[float] = Field(None, description="Ambient air temperature in °C")
    humidity: Optional[float] = Field(None, description="Relative humidity in %")
    pressure: Optional[float] = Field(None, description="Barometric pressure in hPa")
    timestamp: str = Field(..., description="Observation timestamp in ISO 8601 format")


class ProvenanceInfo(BaseModel):
    source_stations: List[str] = Field(default_factory=list)
    computed_at: str
    method: str


class EvidenceItem(BaseModel):
    """
    Internal Evidence Object Schema (docs/DATA_CONTRACT.md Section 4).
    Labels must be one of: SUPPORTED, QUALIFIED, UNKNOWN, REJECTED (docs/AI_COLLABORATION.md).
    """
    evidence_id: str
    source_type: str  # e.g., SPATIAL_NEIGHBOR, DRIFT_CHECK, STUCK_VALUE, NOISE_CHECK
    label: str  # SUPPORTED | QUALIFIED | UNKNOWN | REJECTED
    description: str
    quality_score: float = Field(..., ge=0.0, le=1.0)
    provenance: Dict[str, Any] = Field(default_factory=dict)


class DecisionObject(BaseModel):
    """
    Final Decision Object Schema (docs/DATA_CONTRACT.md Section 2).
    Operational State must be one of: NORMAL, WORLD, SENSOR, BOTH, UNKNOWN.
    """
    station_id: str
    timestamp: str
    state: str  # NORMAL | WORLD | SENSOR | BOTH | UNKNOWN
    confidence: float = Field(0.0, description="Algorithmic scoring metric (not calibrated probability)")
    world_evidence: List[EvidenceItem] = Field(default_factory=list)
    sensor_evidence: List[EvidenceItem] = Field(default_factory=list)
    evidence_quality: Dict[str, Any] = Field(default_factory=dict)
    provenance: List[Dict[str, Any]] = Field(default_factory=list)
    independence: Dict[str, Any] = Field(default_factory=dict)
    reason: str
    action: str


class StationInfo(BaseModel):
    station_id: str
    name: str
    status: str = "ONLINE"  # ONLINE | OFFLINE | STALE
    latitude: float
    longitude: float
    last_observed_at: Optional[str] = None
    latest_reading: Optional[RawObservation] = None


class StationHistoryResponse(BaseModel):
    station_id: str
    history: List[RawObservation]
    total_records: int


class NetworkStatus(BaseModel):
    total_stations: int
    online_stations: int
    offline_stations: int
    state_distribution: Dict[str, int]
    last_updated: str


class ScenarioRequest(BaseModel):
    scenario: str  # NORMAL | WORLD | SENSOR | BOTH | UNKNOWN
    station_id: Optional[str] = "AWS-03"
    mode: Optional[str] = None
