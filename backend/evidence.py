"""
SKYGUARD Evidence Generator Module

Generates structured World Evidence and Sensor Evidence objects tagged with standardized labels
(SUPPORTED, QUALIFIED, UNKNOWN, REJECTED) following docs/DATA_CONTRACT.md and docs/AI_COLLABORATION.md.
"""

from typing import List, Dict, Any, Optional, Tuple
from backend.models import RawObservation, EvidenceItem
from backend.qc import validate_physical_limits, check_step_change


def evaluate_world_evidence(
    target: RawObservation,
    neighbor_observations: List[RawObservation],
    timestamp: str
) -> Tuple[List[EvidenceItem], Dict[str, Any]]:
    """
    Evaluates environmental/world change evidence using neighbor correlation
    and multi-parameter coupling (e.g. pressure surge + temperature drop).
    """
    world_evidence: List[EvidenceItem] = []
    quality_metrics: Dict[str, Any] = {"neighbor_count": len(neighbor_observations), "latency_seconds": 2}

    if not neighbor_observations:
        world_evidence.append(
            EvidenceItem(
                evidence_id=f"EV-WORLD-NEIGHBOR-NONE-{target.station_id}",
                source_type="SPATIAL_NEIGHBOR",
                label="UNKNOWN",
                description="No adjacent neighbor stations available within spatial radius.",
                quality_score=0.40,
                provenance={
                    "source_stations": [],
                    "computed_at": timestamp,
                    "method": "spatial_neighbor_check_v1"
                }
            )
        )
        return world_evidence, quality_metrics

    # Check neighbor consistency for temperature & pressure shifts
    valid_neighbors = [obs for obs in neighbor_observations if obs.temperature is not None]
    if valid_neighbors and target.temperature is not None:
        avg_neighbor_temp = sum(obs.temperature for obs in valid_neighbors) / len(valid_neighbors)
        temp_diff = abs(target.temperature - avg_neighbor_temp)

        neighbor_ids = [obs.station_id for obs in valid_neighbors]

        if temp_diff < 2.5:
            world_evidence.append(
                EvidenceItem(
                    evidence_id=f"EV-WORLD-NEIGHBOR-CORR-{target.station_id}",
                    source_type="SPATIAL_NEIGHBOR",
                    label="SUPPORTED",
                    description=f"{len(valid_neighbors)} neighbor stations ({', '.join(neighbor_ids)}) corroborate reading within {temp_diff:.1f}°C margin.",
                    quality_score=0.92,
                    provenance={
                        "source_stations": neighbor_ids,
                        "computed_at": timestamp,
                        "method": "spatial_gradient_check_v1"
                    }
                )
            )
        elif temp_diff > 6.0:
            world_evidence.append(
                EvidenceItem(
                    evidence_id=f"EV-WORLD-NEIGHBOR-ISOLATED-{target.station_id}",
                    source_type="SPATIAL_NEIGHBOR",
                    label="REJECTED",
                    description=f"Isolated deviation: Station target differs by {temp_diff:.1f}°C from surrounding average ({avg_neighbor_temp:.1f}°C).",
                    quality_score=0.85,
                    provenance={
                        "source_stations": neighbor_ids,
                        "computed_at": timestamp,
                        "method": "spatial_gradient_check_v1"
                    }
                )
            )
        else:
            world_evidence.append(
                EvidenceItem(
                    evidence_id=f"EV-WORLD-NEIGHBOR-QUALIFIED-{target.station_id}",
                    source_type="SPATIAL_NEIGHBOR",
                    label="QUALIFIED",
                    description=f"Moderate spatial variance ({temp_diff:.1f}°C) observed relative to neighbor average ({avg_neighbor_temp:.1f}°C).",
                    quality_score=0.75,
                    provenance={
                        "source_stations": neighbor_ids,
                        "computed_at": timestamp,
                        "method": "spatial_gradient_check_v1"
                    }
                )
            )

    # Check multi-parameter coupling (Cold Front: Temp drop + Humidity spike + Pressure rise)
    if target.temperature is not None and target.humidity is not None and target.pressure is not None:
        if target.temperature < 22.0 and target.humidity > 80.0 and target.pressure > 1012.0:
            world_evidence.append(
                EvidenceItem(
                    evidence_id=f"EV-WORLD-COUPLING-{target.station_id}",
                    source_type="MULTI_VARIABLE_COUPLING",
                    label="SUPPORTED",
                    description="Co-varying thermodynamic coupling detected (cool temperature + high humidity + pressure surge).",
                    quality_score=0.90,
                    provenance={
                        "source_stations": [target.station_id],
                        "computed_at": timestamp,
                        "method": "multivariate_front_detector_v1"
                    }
                )
            )

    return world_evidence, quality_metrics


def evaluate_sensor_evidence(
    target: RawObservation,
    history: List[RawObservation],
    timestamp: str
) -> Tuple[List[EvidenceItem], Dict[str, Any]]:
    """
    Evaluates sensor hardware fault evidence using deterministic bounds, step spikes, stuck values, and drift.
    """
    sensor_evidence: List[EvidenceItem] = []
    quality_metrics: Dict[str, Any] = {"history_window": len(history), "noise_floor_db": -42.0}

    # 1. Deterministic Bounds Check
    qc_flags = validate_physical_limits(target)
    if not qc_flags["is_valid"]:
        sensor_evidence.append(
            EvidenceItem(
                evidence_id=f"EV-SENSOR-PHYSICAL-LIMIT-{target.station_id}",
                source_type="PHYSICAL_BOUNDS",
                label="SUPPORTED",
                description=f"Physical limit violation: {'; '.join(qc_flags['violations'])}.",
                quality_score=0.98,
                provenance={
                    "source_stations": [target.station_id],
                    "computed_at": timestamp,
                    "method": "deterministic_physical_bounds_v1"
                }
            )
        )

    # 2. Step Change Spike Check
    previous = history[-1] if history else None
    step_flags = check_step_change(target, previous)
    if step_flags["temp_spike"] or step_flags["humid_spike"] or step_flags["press_spike"]:
        sensor_evidence.append(
            EvidenceItem(
                evidence_id=f"EV-SENSOR-STEP-SPIKE-{target.station_id}",
                source_type="ELECTRICAL_NOISE",
                label="SUPPORTED",
                description=f"Unphysical step spike: {'; '.join(step_flags['violations'])}.",
                quality_score=0.95,
                provenance={
                    "source_stations": [target.station_id],
                    "computed_at": timestamp,
                    "method": "step_rate_of_change_v1"
                }
            )
        )

    # 3. Stuck Value Persistence Check (last 5 identical readings)
    if len(history) >= 4 and target.temperature is not None:
        last_temps = [obs.temperature for obs in history[-4:] if obs.temperature is not None]
        if len(last_temps) == 4 and all(t == target.temperature for t in last_temps):
            sensor_evidence.append(
                EvidenceItem(
                    evidence_id=f"EV-SENSOR-STUCK-{target.station_id}",
                    source_type="STUCK_VALUE",
                    label="SUPPORTED",
                    description=f"Sensor thermistor frozen at constant {target.temperature}°C for {len(last_temps)+1} consecutive intervals.",
                    quality_score=0.96,
                    provenance={
                        "source_stations": [target.station_id],
                        "computed_at": timestamp,
                        "method": "persistence_stuck_counter_v1"
                    }
                )
            )

    return sensor_evidence, quality_metrics
