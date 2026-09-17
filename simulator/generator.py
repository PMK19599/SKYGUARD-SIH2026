"""
SKYGUARD Multi-Station Network Scenario Simulator

Generates synthetic observation events for fault/weather scenario testing.
Rule: Scenario injection MUST pass through the canonical ingestion pipeline.
Ground truth scenario labels MUST NEVER be passed directly into the decision engine.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timezone
from backend.models import IngestionPayload, DecisionObject
from backend.store import store


def execute_scenario(scenario: str, station_id: str = "AWS-03", mode: Optional[str] = None) -> DecisionObject:
    """
    Simulates weather/sensor conditions by creating and ingesting observations into the canonical pipeline.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    target_sid = station_id if station_id in store.stations else "AWS-03"

    scenario_upper = scenario.upper()

    if scenario_upper == "NORMAL":
        # Nominal Weather: All stations report consistent diurnal readings
        for sid in store.stations:
            store.ingest_observation(IngestionPayload(
                station_id=sid,
                temperature=28.0,
                humidity=75.0,
                pressure=1011.0,
                timestamp=now_iso
            ))

    elif scenario_upper == "WORLD":
        # Cold Front / Squall Line: Regional temperature drop + humidity surge + pressure jump across ALL neighbor stations
        for sid in store.stations:
            store.ingest_observation(IngestionPayload(
                station_id=sid,
                temperature=19.5,  # Drop from 28°C
                humidity=89.0,    # Surge
                pressure=1016.5,  # Surge
                timestamp=now_iso
            ))

    elif scenario_upper == "SENSOR":
        # Failing Thermistor / Electrical Noise: Target station experiences extreme spike/out-of-bounds reading
        # while surrounding neighbor stations remain nominal (28°C)
        for sid in store.stations:
            if sid == target_sid:
                store.ingest_observation(IngestionPayload(
                    station_id=sid,
                    temperature=58.2,  # Sudden unphysical isolated spike
                    humidity=75.0,
                    pressure=1011.0,
                    timestamp=now_iso
                ))
            else:
                store.ingest_observation(IngestionPayload(
                    station_id=sid,
                    temperature=28.0,
                    humidity=75.0,
                    pressure=1011.0,
                    timestamp=now_iso
                ))

    elif scenario_upper == "BOTH":
        # Storm Event + Sensor Failure: Active cold front (world event) AND target station thermistor stuck frozen
        for sid in store.stations:
            if sid == target_sid:
                # Inject physical bounds error / stuck value during severe storm
                store.ingest_observation(IngestionPayload(
                    station_id=sid,
                    temperature=-65.0,  # Physical limit violation during front
                    humidity=90.0,
                    pressure=1016.0,
                    timestamp=now_iso
                ))
            else:
                store.ingest_observation(IngestionPayload(
                    station_id=sid,
                    temperature=19.0,
                    humidity=88.0,
                    pressure=1016.0,
                    timestamp=now_iso
                ))

    elif scenario_upper == "UNKNOWN":
        # Ambiguous / Conflicting Evidence / Stale Data: Missing measurements or conflicting neighbor reports
        for sid in store.stations:
            if sid == target_sid:
                store.ingest_observation(IngestionPayload(
                    station_id=sid,
                    temperature=None,  # Missing temperature value
                    humidity=None,     # Missing humidity value
                    pressure=1011.0,
                    timestamp=now_iso
                ))
            else:
                # Conflicting neighbors
                store.ingest_observation(IngestionPayload(
                    station_id=sid,
                    temperature=15.0 if sid in ["AWS-01", "AWS-02"] else 38.0,
                    humidity=60.0,
                    pressure=1005.0,
                    timestamp=now_iso
                ))

    else:
        # Default fallback: nominal ingestion
        store.ingest_observation(IngestionPayload(
            station_id=target_sid,
            temperature=28.0,
            humidity=75.0,
            pressure=1011.0,
            timestamp=now_iso
        ))

    # Return the actual resulting decision from the backend engine
    return store.get_decision(target_sid)
