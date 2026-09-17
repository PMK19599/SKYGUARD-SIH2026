"""Canonical Pydantic Data Contracts for SKYGUARD (SIH26073).

These models define the frozen data contracts for Station, Observation,
Evidence, and Decision entities.
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# 1. Canonical Station Schema
# -----------------------------------------------------------------------------

class Location(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees")
    elevation_m: float = Field(..., description="Station elevation in meters above sea level")


class SensorCapability(BaseModel):
    type: str = Field(..., description="Sensor parameter type, e.g. temperature, relative_humidity, pressure")
    unit: str = Field(..., description="Standard reporting unit, e.g. celsius, percent, hpa")


class Station(BaseModel):
    station_id: str = Field(..., description="Unique station identifier, e.g. AWS-03")
    name: str = Field(..., description="Human-readable station designation")
    location: Location
    sensors: List[SensorCapability]


# -----------------------------------------------------------------------------
# 2. Canonical Observation Schema
# -----------------------------------------------------------------------------

class Measurements(BaseModel):
    temperature_c: Optional[float] = Field(None, description="Ambient air temperature in Celsius")
    relative_humidity_pct: Optional[float] = Field(None, ge=0.0, le=100.0, description="Relative humidity percentage")
    pressure_hpa: Optional[float] = Field(None, description="Barometric pressure in hPa")


class ObservationSource(BaseModel):
    type: Literal["EDGE", "SIMULATOR", "IMD_TELEMETRY"] = Field(..., description="Origin stream category")
    source_id: str = Field(..., description="Identifier of source device/simulator")


class Observation(BaseModel):
    observation_id: str = Field(..., description="Unique observation identifier")
    station_id: str = Field(..., description="Reporting station identifier")
    observed_at: str = Field(..., description="ISO 8601 timestamp of measurement")
    received_at: str = Field(..., description="ISO 8601 timestamp of system ingestion")
    measurements: Measurements
    source: ObservationSource
    sequence: Optional[int] = Field(None, ge=0, description="Optional monotonically increasing sequence number")


# -----------------------------------------------------------------------------
# 3. Canonical Evidence Schema
# -----------------------------------------------------------------------------

CausalHypothesis = Literal["WORLD", "SENSOR"]


class EvidenceSubject(BaseModel):
    station_id: str
    observation_ids: List[str]


class EvidenceQuality(BaseModel):
    status: Literal["VALID", "DEGRADED", "INVALID"]
    freshness: Literal["FRESH", "STALE", "EXPIRED"]
    completeness: Literal["COMPLETE", "PARTIAL", "INTERPOLATED"]


class EvidenceProvenance(BaseModel):
    source_type: Literal["DETERMINISTIC_QC", "DERIVED", "ML_MODEL"]
    source_id: str
    derived_from: List[str]


class Evidence(BaseModel):
    evidence_id: str
    subject: EvidenceSubject
    type: Literal["TEMPORAL", "SPATIAL", "PHYSICAL_LIMIT", "MULTIVARIATE", "ML_HYPOTHESIS"]
    relation: Literal["SUPPORTS", "CONTRADICTS"]
    hypothesis: CausalHypothesis
    description: str
    strength: float = Field(..., ge=0.0, le=1.0, description="Normalized support score; NOT calibrated probability")
    quality: EvidenceQuality
    provenance: EvidenceProvenance
    independence_group: str
    status: Literal["AVAILABLE", "SUPPRESSED", "EXPIRED"]


# -----------------------------------------------------------------------------
# 4. Canonical Decision Schema
# -----------------------------------------------------------------------------

OperationalState = Literal["NORMAL", "WORLD", "SENSOR", "BOTH", "UNKNOWN"]


class DecisionEvidenceQuality(BaseModel):
    overall: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT"]


class DecisionIndependence(BaseModel):
    status: Literal["ESTABLISHED", "PARTIAL", "UNVERIFIED", "FAILED"]


class Decision(BaseModel):
    decision_id: str
    station_id: str
    timestamp: str
    state: OperationalState
    confidence: float = Field(..., ge=0.0, le=1.0, description="Engine score; NOT calibrated probability")
    world_evidence: List[str]
    sensor_evidence: List[str]
    evidence_quality: DecisionEvidenceQuality
    independence: DecisionIndependence
    reason: str
    action: str
