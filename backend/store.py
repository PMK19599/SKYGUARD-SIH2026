"""
SKYGUARD Thread-Safe In-Memory Station State & History Store

Manages active weather stations, observation history, live ingestion pipelines,
and current state decisions.
"""

from typing import Dict, List, Optional
from datetime import datetime, timezone
import threading

from backend.models import (
    RawObservation, DecisionObject, StationInfo, NetworkStatus, IngestionPayload
)
from backend.evidence import evaluate_world_evidence, evaluate_sensor_evidence
from backend.engine import determine_skyguard_decision


class StationStore:
    def __init__(self):
        self._lock = threading.Lock()
        
        # Default AWS Station Grid
        self.stations: Dict[str, StationInfo] = {
            "AWS-01": StationInfo(station_id="AWS-01", name="Station 01 — Udupi Coast", status="ONLINE", latitude=13.3409, longitude=74.7421),
            "AWS-02": StationInfo(station_id="AWS-02", name="Station 02 — Manipal Ridge", status="ONLINE", latitude=13.3525, longitude=74.7864),
            "AWS-03": StationInfo(station_id="AWS-03", name="Station 03 — Brahmavar AWS", status="ONLINE", latitude=13.4215, longitude=74.7485),
            "AWS-04": StationInfo(station_id="AWS-04", name="Station 04 — Karkala Foothills", status="ONLINE", latitude=13.2167, longitude=74.9967),
            "AWS-05": StationInfo(station_id="AWS-05", name="Station 05 — Kundapura Port", status="ONLINE", latitude=13.6268, longitude=74.6908)
        }

        # History ring buffers (max 50 entries per station)
        self.history: Dict[str, List[RawObservation]] = {sid: [] for sid in self.stations}

        # Current Decision state cache
        self.decisions: Dict[str, DecisionObject] = {}

        # Pre-populate baseline nominal data for all stations
        self._initialize_baseline_data()

    def _initialize_baseline_data(self):
        now_iso = datetime.now(timezone.utc).isoformat()
        baseline_readings = {
            "AWS-01": (28.4, 75.0, 1011.2),
            "AWS-02": (27.8, 77.2, 1010.8),
            "AWS-03": (28.1, 76.0, 1011.0),
            "AWS-04": (27.5, 78.5, 1009.5),
            "AWS-05": (28.6, 74.5, 1011.5),
        }

        for sid, (temp, hum, press) in baseline_readings.items():
            obs = RawObservation(
                station_id=sid,
                temperature=temp,
                humidity=hum,
                pressure=press,
                timestamp=now_iso
            )
            self.history[sid].append(obs)
            self.stations[sid].last_observed_at = now_iso
            self.stations[sid].latest_reading = obs

        # Process initial decisions
        for sid in self.stations:
            self._evaluate_station(sid)

    def _evaluate_station(self, station_id: str) -> DecisionObject:
        """
        Passes the station's latest observation through the SKYGUARD pipeline.
        """
        history = self.history.get(station_id, [])
        if not history:
            now_iso = datetime.now(timezone.utc).isoformat()
            target = RawObservation(station_id=station_id, timestamp=now_iso)
        else:
            target = history[-1]

        # Gather neighbors
        neighbors = [
            self.history[sid][-1] for sid in self.stations
            if sid != station_id and self.history[sid]
        ]

        timestamp = target.timestamp or datetime.now(timezone.utc).isoformat()

        # Evidence evaluation
        world_evidence, world_quality = evaluate_world_evidence(target, neighbors, timestamp)
        sensor_evidence, sensor_quality = evaluate_sensor_evidence(target, history[:-1], timestamp)

        evidence_quality = {**world_quality, **sensor_quality}

        # Decision engine arbitration
        decision = determine_skyguard_decision(
            target, world_evidence, sensor_evidence, evidence_quality, timestamp
        )

        self.decisions[station_id] = decision
        return decision

    def get_all_stations(self) -> List[StationInfo]:
        with self._lock:
            return list(self.stations.values())

    def get_station(self, station_id: str) -> Optional[StationInfo]:
        with self._lock:
            return self.stations.get(station_id)

    def get_history(self, station_id: str) -> List[RawObservation]:
        with self._lock:
            return list(self.history.get(station_id, []))

    def ingest_observation(self, payload: IngestionPayload) -> DecisionObject:
        with self._lock:
            sid = payload.station_id
            if sid not in self.stations:
                # Dynamically register new station if needed
                self.stations[sid] = StationInfo(
                    station_id=sid,
                    name=f"Station {sid}",
                    status="ONLINE",
                    latitude=13.3400,
                    longitude=74.7400
                )
                self.history[sid] = []

            obs = RawObservation(
                station_id=sid,
                temperature=payload.temperature,
                humidity=payload.humidity,
                pressure=payload.pressure,
                timestamp=payload.timestamp or datetime.now(timezone.utc).isoformat()
            )

            # Append to history
            self.history[sid].append(obs)
            if len(self.history[sid]) > 50:
                self.history[sid].pop(0)

            self.stations[sid].last_observed_at = obs.timestamp
            self.stations[sid].latest_reading = obs
            self.stations[sid].status = "ONLINE"

            # Execute pipeline evaluation
            decision = self._evaluate_station(sid)
            return decision

    def get_decision(self, station_id: str) -> Optional[DecisionObject]:
        with self._lock:
            if station_id not in self.decisions:
                if station_id in self.stations:
                    self._evaluate_station(station_id)
            return self.decisions.get(station_id)

    def get_network_status(self) -> NetworkStatus:
        with self._lock:
            total = len(self.stations)
            online = sum(1 for s in self.stations.values() if s.status == "ONLINE")
            offline = total - online

            dist: Dict[str, int] = {"NORMAL": 0, "WORLD": 0, "SENSOR": 0, "BOTH": 0, "UNKNOWN": 0}
            for d in self.decisions.values():
                if d.state in dist:
                    dist[d.state] += 1

            return NetworkStatus(
                total_stations=total,
                online_stations=online,
                offline_stations=offline,
                state_distribution=dist,
                last_updated=datetime.now(timezone.utc).isoformat()
            )


# Global Store Instance
store = StationStore()
