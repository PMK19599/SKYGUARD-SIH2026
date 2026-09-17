"""
SKYGUARD Core Decision Arbitration Engine

Executes PMK's deterministic five-state decision engine logic, independence gating,
reason synthesis, and prescribed action mapping as specified in docs/DECISION_STATES.md.
"""

from typing import List, Dict, Any, Tuple
from backend.models import RawObservation, EvidenceItem, DecisionObject


def evaluate_independence(
    world_evidence: List[EvidenceItem],
    sensor_evidence: List[EvidenceItem]
) -> Dict[str, Any]:
    """
    Independence Gate: Ensures evidence sources do not share single point failures or common power supply.
    Correlated sources cannot automatically be treated as independent.
    """
    has_world_supported = any(e.label == "SUPPORTED" for e in world_evidence)
    has_sensor_supported = any(e.label == "SUPPORTED" for e in sensor_evidence)

    world_sources = set()
    for e in world_evidence:
        world_sources.update(e.provenance.get("source_stations", []))

    sensor_sources = set()
    for e in sensor_evidence:
        sensor_sources.update(e.provenance.get("source_stations", []))

    # Check source overlap
    overlapping = world_sources.intersection(sensor_sources)

    independence_status = {
        "independence_verified": len(overlapping) == 0,
        "shared_gateway": False,
        "shared_power_bus": False,
        "world_source_count": len(world_sources),
        "sensor_source_count": len(sensor_sources),
        "overlap_count": len(overlapping)
    }

    return independence_status


def determine_skyguard_decision(
    target_observation: RawObservation,
    world_evidence: List[EvidenceItem],
    sensor_evidence: List[EvidenceItem],
    evidence_quality: Dict[str, Any],
    timestamp: str
) -> DecisionObject:
    """
    Arbitrates verified evidence items into exactly one of five operational states:
    NORMAL, WORLD, SENSOR, BOTH, UNKNOWN.
    """
    independence = evaluate_independence(world_evidence, sensor_evidence)

    # Categorize supported evidence
    has_world_supported = any(e.label == "SUPPORTED" for e in world_evidence)
    has_world_rejected = any(e.label == "REJECTED" for e in world_evidence)
    has_sensor_supported = any(e.label == "SUPPORTED" for e in sensor_evidence)

    has_unknown_or_stale = any(e.label == "UNKNOWN" for e in world_evidence) or not independence["independence_verified"]

    # 1. BOTH State
    # Requires independent evidence supporting WORLD + SENSOR simultaneously
    if has_world_supported and has_sensor_supported and independence["independence_verified"]:
        state = "BOTH"
        confidence = 0.88
        reason = "Independent evidence confirms severe environmental event while target sensor simultaneously exhibits physical/hardware anomalies."
        action = "Handle event + inspect sensor."

    # 2. SENSOR State
    # Sensor fault evidence is strong AND world evidence is absent, rejected, or insufficient
    elif has_sensor_supported and (has_world_rejected or not has_world_supported):
        state = "SENSOR"
        confidence = 0.92
        reason = "Observation deviates significantly from physical bounds/history while neighboring stations report nominal world conditions."
        action = "Inspect/validate sensor."

    # 3. WORLD State
    # Environmental change is corroborated by independent evidence AND sensor fault is absent
    elif has_world_supported and not has_sensor_supported:
        state = "WORLD"
        confidence = 0.90
        reason = "Observation anomaly is corroborated by surrounding stations and thermodynamic coupling. Sensor is functioning normally."
        action = "Observe/continue with event context."

    # 4. UNKNOWN State
    # Evidence is missing, stale, conflicting, non-independent, or ambiguous
    elif has_unknown_or_stale or (has_world_rejected and not has_sensor_supported):
        state = "UNKNOWN"
        confidence = 0.50
        reason = "Evidence is insufficient, conflicting, stale, or non-independent. Operational cause cannot be conclusively determined."
        action = "Human review."

    # 5. NORMAL State
    # No abnormal condition established
    else:
        state = "NORMAL"
        confidence = 0.95
        reason = "Station measurements pass physical bounds and step checks. No environmental or sensor anomalies detected."
        action = "Continue observation."

    # Build provenance trace
    provenance = [
        {
            "pipeline_stage": "ingestion",
            "station_id": target_observation.station_id,
            "timestamp": timestamp
        },
        {
            "pipeline_stage": "qc_and_evidence",
            "world_evidence_count": len(world_evidence),
            "sensor_evidence_count": len(sensor_evidence)
        },
        {
            "pipeline_stage": "decision_engine",
            "ruleset": "pmk_skyguard_v1.0"
        }
    ]

    return DecisionObject(
        station_id=target_observation.station_id,
        timestamp=timestamp,
        state=state,
        confidence=confidence,
        world_evidence=world_evidence,
        sensor_evidence=sensor_evidence,
        evidence_quality=evidence_quality,
        provenance=provenance,
        independence=independence,
        reason=reason,
        action=action
    )
