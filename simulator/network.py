"""Virtual AWS Network for SKYGUARD.

Simulates a generic network of Automatic Weather Stations (AWS) producing
physically plausible, temporally continuous, and spatially correlated observations.
"""

from datetime import datetime, timedelta, timezone
import math
import random
from typing import Dict, List, Optional

from backend.schemas import (
    Location,
    Measurements,
    Observation,
    ObservationSource,
    SensorCapability,
    Station,
)

# -----------------------------------------------------------------------------
# Default Virtual Stations (Synthetic / Neutral Test Grid)
# -----------------------------------------------------------------------------

DEFAULT_STATIONS: List[Station] = [
    Station(
        station_id="AWS-01",
        name="Virtual Station 01 (Reference)",
        location=Location(latitude=20.0000, longitude=80.0000, elevation_m=100.0),
        sensors=[
            SensorCapability(type="temperature", unit="celsius"),
            SensorCapability(type="relative_humidity", unit="percent"),
            SensorCapability(type="pressure", unit="hpa"),
        ],
    ),
    Station(
        station_id="AWS-02",
        name="Virtual Station 02 (North-East)",
        location=Location(latitude=20.0200, longitude=80.0200, elevation_m=105.0),
        sensors=[
            SensorCapability(type="temperature", unit="celsius"),
            SensorCapability(type="relative_humidity", unit="percent"),
            SensorCapability(type="pressure", unit="hpa"),
        ],
    ),
    Station(
        station_id="AWS-03",
        name="Virtual Station 03 (South-West)",
        location=Location(latitude=20.0000, longitude=80.0400, elevation_m=98.0),
        sensors=[
            SensorCapability(type="temperature", unit="celsius"),
            SensorCapability(type="relative_humidity", unit="percent"),
            SensorCapability(type="pressure", unit="hpa"),
        ],
    ),
    Station(
        station_id="AWS-04",
        name="Virtual Station 04 (East)",
        location=Location(latitude=20.0300, longitude=80.0100, elevation_m=102.0),
        sensors=[
            SensorCapability(type="temperature", unit="celsius"),
            SensorCapability(type="relative_humidity", unit="percent"),
            SensorCapability(type="pressure", unit="hpa"),
        ],
    ),
]


class StationState:
    """Internal continuous physical state for a single virtual station."""

    def __init__(
        self,
        station: Station,
        base_temp: float = 28.0,
        base_humidity: float = 65.0,
        base_pressure: float = 1010.0,
    ) -> None:
        self.station = station
        # Physical micro-offsets based on elevation and spatial separation
        elevation_delta = station.location.elevation_m - 100.0
        # Standard lapse rate: ~-0.0065°C/m, pressure lapse: ~-0.12 hPa/m
        self.temp_offset = -0.0065 * elevation_delta
        self.pressure_offset = -0.12 * elevation_delta
        self.humidity_offset = 0.05 * elevation_delta

        # Current continuous state
        self.current_temp = base_temp + self.temp_offset
        self.current_humidity = base_humidity + self.humidity_offset
        self.current_pressure = base_pressure + self.pressure_offset
        self.sequence_number = 0


class VirtualAWSNetwork:
    """Virtual network of Automatic Weather Stations.
    
    Produces temporally continuous and spatially coherent observations
    conforming strictly to the frozen SKYGUARD Observation contract.
    """

    def __init__(
        self,
        stations: Optional[List[Station]] = None,
        seed: Optional[int] = None,
        start_time: Optional[datetime] = None,
        step_minutes: int = 5,
        source_id: str = "sim-network-01",
        base_temp: float = 28.0,
        base_humidity: float = 65.0,
        base_pressure: float = 1010.0,
    ) -> None:
        self._seed = seed
        self._rng = random.Random(seed)
        self.stations = stations if stations is not None else [s.model_copy() for s in DEFAULT_STATIONS]
        self.source_id = source_id
        self.step_minutes = step_minutes
        self.base_temp = base_temp
        self.base_humidity = base_humidity
        self.base_pressure = base_pressure

        if start_time is None:
            # Default reference start time with timezone
            self.start_time = datetime(2026, 9, 17, 9, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        else:
            self.start_time = start_time

        self.current_time = self.start_time
        self.step_count = 0
        self._init_station_states()

    def _init_station_states(self) -> None:
        self.station_states: Dict[str, StationState] = {}
        for s in self.stations:
            state = StationState(
                station=s,
                base_temp=self.base_temp,
                base_humidity=self.base_humidity,
                base_pressure=self.base_pressure,
            )
            # Add small static microclimate jitter per station
            state.current_temp += self._rng.uniform(-0.15, 0.15)
            state.current_humidity += self._rng.uniform(-0.3, 0.3)
            state.current_pressure += self._rng.uniform(-0.1, 0.1)
            self.station_states[s.station_id] = state

    def reset(self, seed: Optional[int] = None) -> None:
        """Reset the network state to initial conditions."""
        if seed is not None:
            self._seed = seed
        self._rng = random.Random(self._seed)
        self.current_time = self.start_time
        self.step_count = 0
        self._init_station_states()

    def get_stations(self) -> List[Station]:
        """Return the list of station definitions in this virtual network."""
        return [s.model_copy() for s in self.stations]

    def step(
        self,
        world_deltas: Optional[Dict[str, Dict[str, float]]] = None,
        global_world_delta: Optional[Dict[str, float]] = None,
    ) -> List[Observation]:
        """Advance the simulation by one timestep and return observations.
        
        Args:
            world_deltas: Optional per-station external environmental shift,
                e.g. {"AWS-01": {"temperature": -2.0}}.
            global_world_delta: Optional network-wide environmental shift,
                e.g. {"temperature": -5.0, "pressure": 2.5, "humidity": 12.0}.
        
        Returns:
            List of valid Observation objects for all stations in this step.
        """
        self.step_count += 1
        self.current_time += timedelta(minutes=self.step_minutes)
        timestamp_str = self.current_time.isoformat()
        # Received time is slightly after capture time
        received_str = (self.current_time + timedelta(seconds=2)).isoformat()

        # Diurnal solar cycle progression: small smooth drift over time
        elapsed_hours = (self.step_count * self.step_minutes) / 60.0
        # Peak warmth around 14:00 (5 hours after 09:00 start)
        diurnal_temp_shift = 3.0 * math.sin((elapsed_hours / 12.0) * math.pi)
        diurnal_humidity_shift = -4.0 * math.sin((elapsed_hours / 12.0) * math.pi)

        observations: List[Observation] = []

        for station in self.stations:
            state = self.station_states[station.station_id]
            state.sequence_number += 1

            # Base target regional climate
            target_t = self.base_temp + state.temp_offset + diurnal_temp_shift
            target_h = self.base_humidity + state.humidity_offset + diurnal_humidity_shift
            target_p = self.base_pressure + state.pressure_offset

            # Apply global world events
            if global_world_delta:
                target_t += global_world_delta.get("temperature", 0.0)
                target_h += global_world_delta.get("humidity", 0.0)
                target_p += global_world_delta.get("pressure", 0.0)

            # Apply station-specific world events (e.g. spatial propagation delays)
            if world_deltas and station.station_id in world_deltas:
                st_delta = world_deltas[station.station_id]
                target_t += st_delta.get("temperature", 0.0)
                target_h += st_delta.get("humidity", 0.0)
                target_p += st_delta.get("pressure", 0.0)

            # Continuous mean-reverting progression with non-zero stochastic micro-variation
            # This ensures normal values fluctuate continuously without rounding to identical constants
            theta = 0.25  # Mean reversion rate toward target
            noise_t = self._rng.gauss(0.0, 0.08)
            noise_h = self._rng.gauss(0.0, 0.15)
            noise_p = self._rng.gauss(0.0, 0.05)

            state.current_temp += theta * (target_t - state.current_temp) + noise_t
            state.current_humidity += theta * (target_h - state.current_humidity) + noise_h
            state.current_pressure += theta * (target_p - state.current_pressure) + noise_p

            # Clamp to physical atmospheric bounds
            state.current_humidity = max(5.0, min(99.5, state.current_humidity))
            state.current_temp = max(-30.0, min(55.0, state.current_temp))
            state.current_pressure = max(800.0, min(1080.0, state.current_pressure))

            obs_id = f"obs-{station.station_id.replace('-', '')}-{state.sequence_number:06d}"
            measurements = Measurements(
                temperature_c=round(state.current_temp, 2),
                relative_humidity_pct=round(state.current_humidity, 2),
                pressure_hpa=round(state.current_pressure, 2),
            )
            source = ObservationSource(
                type="SIMULATOR",
                source_id=self.source_id,
            )

            obs = Observation(
                observation_id=obs_id,
                station_id=station.station_id,
                observed_at=timestamp_str,
                received_at=received_str,
                measurements=measurements,
                source=source,
                sequence=state.sequence_number,
            )
            observations.append(obs)

        return observations

    def generate_sequence(
        self,
        timesteps: int,
        world_deltas_per_step: Optional[List[Dict[str, Dict[str, float]]]] = None,
        global_world_deltas_per_step: Optional[List[Dict[str, float]]] = None,
    ) -> List[Observation]:
        """Generate a series of observations across multiple timesteps.
        
        Returns:
            Flat list of observations in chronological sequence.
        """
        all_obs: List[Observation] = []
        for i in range(timesteps):
            st_delta = world_deltas_per_step[i] if world_deltas_per_step and i < len(world_deltas_per_step) else None
            gl_delta = global_world_deltas_per_step[i] if global_world_deltas_per_step and i < len(global_world_deltas_per_step) else None
            obs_batch = self.step(world_deltas=st_delta, global_world_delta=gl_delta)
            all_obs.extend(obs_batch)
        return all_obs
