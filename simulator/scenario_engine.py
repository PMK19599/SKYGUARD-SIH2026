"""Scenario Engine and Injection Controller for SKYGUARD.

Orchestrates controlled synthetic weather scenarios and sensor fault injections:
- NORMAL: Healthy network, continuous nominal weather.
- WORLD: Coherent regional environmental shift across stations.
- SENSOR: Injected sensor anomaly isolated to a single station.
- BOTH: Independent regional world event AND independent sensor fault.
- UNKNOWN: Genuine causal ambiguity with conflicting/insufficient independent evidence.

CRITICAL INVARIANT:
Ground truth is strictly isolated in the test container ScenarioResult.
Generated Observation instances NEVER contain scenario labels, fault labels,
or causal diagnostic fields.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import random

from backend.schemas import Observation, Station
from simulator.faults import (
    BaseFault,
    CommunicationFault,
    DriftFault,
    FrozenFault,
    SpikeFault,
    create_fault,
)
from simulator.network import DEFAULT_STATIONS, VirtualAWSNetwork


@dataclass
class ScenarioResult:
    """Test-only container exposing observations alongside simulation ground truth.
    
    CRITICAL: Only `observations` must be forwarded into downstream ingestion pipelines.
    `ground_truth` and `metadata` are reserved strictly for offline validation test harnesses.
    """
    observations: List[Observation]
    ground_truth: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class ScenarioEngine:
    """Controls the generation of synthetic meteorological and fault injection scenarios."""

    def __init__(
        self,
        seed: Optional[int] = None,
        stations: Optional[List[Station]] = None,
        source_id: str = "sim-network-01",
    ) -> None:
        self.seed = seed
        self._rng = random.Random(seed)
        self.stations = stations if stations is not None else [s.model_copy() for s in DEFAULT_STATIONS]
        self.source_id = source_id

    def _create_network(self, seed: Optional[int] = None) -> VirtualAWSNetwork:
        net_seed = seed if seed is not None else (self._rng.randint(0, 1000000) if self.seed is not None else None)
        return VirtualAWSNetwork(
            stations=[s.model_copy() for s in self.stations],
            seed=net_seed,
            source_id=self.source_id,
        )

    def normal(self, timesteps: int = 10, seed: Optional[int] = None) -> ScenarioResult:
        """Generate a healthy network sequence with nominal continuous weather.
        
        No sensor faults are injected.
        """
        run_seed = seed if seed is not None else self.seed
        net = self._create_network(run_seed)
        observations = net.generate_sequence(timesteps=timesteps)

        return ScenarioResult(
            observations=observations,
            ground_truth="NORMAL",
            metadata={
                "timesteps": timesteps,
                "seed": run_seed,
                "station_count": len(self.stations),
                "injected_fault": None,
                "world_event": None,
            },
        )

    def world(
        self,
        timesteps: int = 10,
        event_type: str = "cold_front",
        seed: Optional[int] = None,
    ) -> ScenarioResult:
        """Generate a coherent environmental event affecting multiple stations.
        
        No sensor faults are injected. All stations report genuine environmental dynamics.
        """
        run_seed = seed if seed is not None else self.seed
        net = self._create_network(run_seed)

        # Plan world progression across timesteps
        # Cold front: starting at step 4, rapid temperature drop, pressure surge, humidity climb
        global_deltas: List[Dict[str, float]] = []
        for step in range(1, timesteps + 1):
            if event_type == "cold_front":
                if step < 4:
                    global_deltas.append({})
                else:
                    # Evolving cold front impact
                    severity = min(1.0, (step - 3) / 3.0)
                    global_deltas.append({
                        "temperature": -7.0 * severity,
                        "pressure": 3.5 * severity,
                        "humidity": 18.0 * severity,
                    })
            elif event_type == "heat_surge":
                if step < 4:
                    global_deltas.append({})
                else:
                    severity = min(1.0, (step - 3) / 3.0)
                    global_deltas.append({
                        "temperature": 5.5 * severity,
                        "pressure": -2.0 * severity,
                        "humidity": -14.0 * severity,
                    })
            else:
                global_deltas.append({})

        observations = net.generate_sequence(
            timesteps=timesteps,
            global_world_deltas_per_step=global_deltas,
        )

        return ScenarioResult(
            observations=observations,
            ground_truth="WORLD",
            metadata={
                "timesteps": timesteps,
                "event_type": event_type,
                "seed": run_seed,
                "station_count": len(self.stations),
                "injected_fault": None,
            },
        )

    def sensor(
        self,
        timesteps: int = 10,
        target_station: str = "AWS-03",
        fault_type: str = "spike",
        seed: Optional[int] = None,
        **fault_kwargs: Any,
    ) -> ScenarioResult:
        """Generate nominal network weather with one isolated sensor fault on target_station."""
        run_seed = seed if seed is not None else self.seed
        net = self._create_network(run_seed)

        # Instantiate designated fault
        if "fault" in fault_kwargs and isinstance(fault_kwargs["fault"], BaseFault):
            fault: BaseFault = fault_kwargs["fault"]
        else:
            fault = create_fault(fault_type, **fault_kwargs)

        observations: List[Observation] = []
        for step_idx in range(1, timesteps + 1):
            step_obs = net.step()
            for obs in step_obs:
                if obs.station_id == target_station:
                    new_measurements = fault.transform(step_idx, obs.measurements)
                    if new_measurements is not None:
                        modified_obs = obs.model_copy(update={"measurements": new_measurements})
                        observations.append(modified_obs)
                    # If None, the packet was dropped, so no observation is appended
                else:
                    observations.append(obs)

        return ScenarioResult(
            observations=observations,
            ground_truth="SENSOR",
            metadata={
                "timesteps": timesteps,
                "target_station": target_station,
                "fault_type": fault_type,
                "seed": run_seed,
                "injected_fault": type(fault).__name__,
            },
        )

    def both(
        self,
        timesteps: int = 10,
        target_station: str = "AWS-03",
        event_type: str = "cold_front",
        fault_type: str = "drift",
        seed: Optional[int] = None,
        **fault_kwargs: Any,
    ) -> ScenarioResult:
        """Generate two independent phenomena:
        
        1. A coherent regional environmental event affecting the whole network.
        2. An independent sensor fault affecting target_station.
        """
        run_seed = seed if seed is not None else self.seed
        net = self._create_network(run_seed)

        # 1. Independent world event dynamics
        global_deltas: List[Dict[str, float]] = []
        for step in range(1, timesteps + 1):
            if step < 4:
                global_deltas.append({})
            else:
                severity = min(1.0, (step - 3) / 3.0)
                global_deltas.append({
                    "temperature": -6.5 * severity,
                    "pressure": 3.0 * severity,
                    "humidity": 15.0 * severity,
                })

        # 2. Independent sensor fault
        if "fault" in fault_kwargs and isinstance(fault_kwargs["fault"], BaseFault):
            fault: BaseFault = fault_kwargs["fault"]
        else:
            fault = create_fault(fault_type, **fault_kwargs)

        observations: List[Observation] = []
        for step_idx in range(1, timesteps + 1):
            gl_delta = global_deltas[step_idx - 1] if step_idx - 1 < len(global_deltas) else None
            step_obs = net.step(global_world_delta=gl_delta)
            for obs in step_obs:
                if obs.station_id == target_station:
                    new_measurements = fault.transform(step_idx, obs.measurements)
                    if new_measurements is not None:
                        modified_obs = obs.model_copy(update={"measurements": new_measurements})
                        observations.append(modified_obs)
                else:
                    observations.append(obs)

        return ScenarioResult(
            observations=observations,
            ground_truth="BOTH",
            metadata={
                "timesteps": timesteps,
                "target_station": target_station,
                "event_type": event_type,
                "fault_type": fault_type,
                "seed": run_seed,
                "injected_fault": type(fault).__name__,
            },
        )

    def unknown(
        self,
        timesteps: int = 10,
        target_station: str = "AWS-03",
        seed: Optional[int] = None,
    ) -> ScenarioResult:
        """Generate an observation sequence with genuine causal ambiguity.
        
        Creates conditions where available evidence is conflicting, incomplete,
        or insufficient to decisively distinguish WORLD from SENSOR:
        - Target station AWS-03 exhibits an intermediate, borderline deviation (+2.2°C)
          that could plausibly be a localized convective pocket OR gradual sensor bias.
        - Multivariate coupling is inconclusive (pressure is unchanged, humidity shifts slightly).
        - Peer stations provide conflicting/degraded independent evidence:
          * AWS-01 shows weak correlation (+0.8°C).
          * AWS-02 remains nominal (+0.1°C), contradicting regional warming.
          * AWS-04 suffers communication packet loss during the event window.
        
        CRITICAL: The scenario records ground_truth="UNKNOWN" in ScenarioResult,
        but zero diagnostic/causal labels are encoded in Observation objects.
        """
        run_seed = seed if seed is not None else self.seed
        net = self._create_network(run_seed)

        # Ambiguous subtle shift on AWS-03 starting at step 5
        target_drift = DriftFault(parameter="temperature_c", rate=0.45, start_step=5)
        # AWS-04 telemetry drop starting at step 5
        aws04_comm = CommunicationFault(mode="packet_drop", start_step=5)

        observations: List[Observation] = []
        for step_idx in range(1, timesteps + 1):
            # AWS-01 exhibits a weak ambiguous localized micro-fluctuation at step >= 5
            st_deltas: Dict[str, Dict[str, float]] = {}
            if step_idx >= 5:
                st_deltas["AWS-01"] = {"temperature": 0.8, "humidity": -1.2}

            step_obs = net.step(world_deltas=st_deltas)
            for obs in step_obs:
                if obs.station_id == target_station:
                    new_measurements = target_drift.transform(step_idx, obs.measurements)
                    if new_measurements is not None:
                        modified_obs = obs.model_copy(update={"measurements": new_measurements})
                        observations.append(modified_obs)
                elif obs.station_id == "AWS-04":
                    new_measurements = aws04_comm.transform(step_idx, obs.measurements)
                    if new_measurements is not None:
                        modified_obs = obs.model_copy(update={"measurements": new_measurements})
                        observations.append(modified_obs)
                else:
                    observations.append(obs)

        return ScenarioResult(
            observations=observations,
            ground_truth="UNKNOWN",
            metadata={
                "timesteps": timesteps,
                "target_station": target_station,
                "seed": run_seed,
                "condition": "causal_ambiguity_conflicting_and_missing_peer_evidence",
                "description": (
                    "Borderline temperature deviation on AWS-03 with conflicting peer trends "
                    "(AWS-01 slight rise, AWS-02 flat) and missing peer AWS-04 telemetry."
                ),
            },
        )
