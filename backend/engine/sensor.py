"""Deterministic Sensor Evidence and Station-Health Evidence Layer for SKYGUARD.

Evaluates whether there is credible evidence that a target station behaves
inconsistently with its own expected physical/statistical behavior or exhibits
sensor/telemetry-specific failure signatures.

Core Architectural Invariants:
1. Observation != Interpretation: Raw observations are never mutated.
2. Evidence != Decision: Generates candidate Evidence only; never assigns final operational states.
3. Outlier != Fault: Extreme readings are evidence of an anomaly, not proof of sensor failure.
4. Trend != Drift: Environmental trends are distinguished from persistent station-specific residual bias.
5. Missing != Fault: Incomplete data or missing channels do not automatically prove sensor hardware failure.
6. Telemetry != Hardware: Sequence or communication glitches are telemetry anomalies, not guaranteed physical faults.
7. Memory != Verdict: Health history is an evidence accumulator with decay/recovery, not a reputation blacklist.
8. Zero Scenario Awareness: No simulation or ground truth labels are imported or accessed.
"""

from datetime import datetime, timezone
import statistics
from typing import Any, Dict, List, Optional, Set, Union
from pydantic import BaseModel, Field

from backend.schemas import (
    Evidence,
    EvidenceProvenance,
    EvidenceQuality,
    EvidenceSubject,
    Observation,
)


def _to_utc_datetime(ts: Union[datetime, str]) -> datetime:
    """Convert ISO 8601 string or datetime object to timezone-aware UTC datetime."""
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _clean_param(param: str) -> str:
    """Clean parameter names for standard evidence IDs and independence groups."""
    return param.replace("_c", "").replace("_pct", "").replace("_hpa", "").replace("relative_", "")


class SensorConfig(BaseModel):
    """Configuration thresholds for deterministic sensor evidence generation."""

    # Configured terrestrial surface physical plausibility bounds (heuristic screening ranges)
    temp_min_c: float = Field(-40.0, description="Minimum configured physical plausibility bound for ambient temperature (°C)")
    temp_max_c: float = Field(55.0, description="Maximum configured physical plausibility bound for ambient temperature (°C)")
    humidity_min_pct: float = Field(0.0, ge=0.0, description="Minimum configured physical plausibility bound for relative humidity (%)")
    humidity_max_pct: float = Field(100.0, le=100.0, description="Maximum configured physical plausibility bound for relative humidity (%)")
    pressure_min_hpa: float = Field(850.0, description="Minimum configured physical plausibility bound for barometric pressure (hPa)")
    pressure_max_hpa: float = Field(1080.0, description="Maximum configured physical plausibility bound for barometric pressure (hPa)")

    # Spike detection parameters (step threshold)
    spike_threshold_temp_c: float = Field(4.0, description="Minimum abrupt step for temperature spike candidate (°C)")
    spike_threshold_humidity_pct: float = Field(15.0, description="Minimum abrupt step for humidity spike candidate (%)")
    spike_threshold_pressure_hpa: float = Field(3.0, description="Minimum abrupt step for pressure spike candidate (hPa)")
    spike_recurrence_min_count: int = Field(2, ge=2, description="Consecutive/recurring spikes required for candidate recurrence")

    # Flatline / Persistence parameters
    # Note: Pressure rounding repetitions (2-3) are natural and must not trigger flatline.
    flatline_persistence_count: int = Field(5, ge=4, description="Consecutive identical readings required for flatline")

    # Baseline & MAD parameters
    baseline_window_size: int = Field(15, ge=5, description="Number of historical observations for rolling baseline")
    mad_threshold_sigma: float = Field(3.5, ge=2.0, description="MAD multiplier threshold for baseline deviation")
    min_mad_noise_floor_temp_c: float = Field(0.3, description="Minimum MAD noise floor for temperature (°C)")
    min_mad_noise_floor_humidity_pct: float = Field(1.5, description="Minimum MAD noise floor for humidity (%)")
    min_mad_noise_floor_pressure_hpa: float = Field(0.4, description="Minimum MAD noise floor for pressure (hPa)")

    # Drift / Persistent Offset parameters
    drift_min_persistence_count: int = Field(4, ge=3, description="Consecutive timesteps required for persistent offset")
    drift_min_offset_temp_c: float = Field(1.5, description="Minimum persistent offset for temperature drift candidate (°C)")
    drift_min_offset_humidity_pct: float = Field(10.0, description="Minimum persistent offset for humidity drift candidate (%)")
    drift_min_offset_pressure_hpa: float = Field(1.2, description="Minimum persistent offset for pressure drift candidate (hPa)")

    # Intermittent failure parameters
    intermittent_window_size: int = Field(10, ge=4, description="Sliding window to evaluate intermittent transitions")
    intermittent_min_transitions: int = Field(2, ge=2, description="Minimum dropouts or toggles to flag intermittency")

    # Telemetry anomaly parameters
    telemetry_anomaly_threshold: int = Field(2, ge=2, description="Minimum sequence/timestamp anomalies for telemetry evidence")

    # Health history accumulator parameters (bounded derivation from input window)
    health_history_buffer_size: int = Field(30, ge=3, description="Maximum historical observations evaluated in health history window")
    health_recovery_clean_steps: int = Field(5, ge=2, description="Clean observations required to clear temporary anomaly status")


class SensorEvidenceResult(BaseModel):
    """Result of deterministic sensor evidence evaluation for a target station."""

    station_id: str
    target_observation_id: str
    evidence: List[Evidence]
    evaluated_observations: List[str]
    mechanism_summary: Dict[str, Any]
    health_history_summary: Dict[str, Any]
    provenance: EvidenceProvenance
    warnings: List[str]
    summary: str


class SensorEvidenceEngine:
    """Deterministic station-health and sensor evidence engine for SKYGUARD."""

    def __init__(self, config: Optional[SensorConfig] = None) -> None:
        self.config = config or SensorConfig()

    def reset(self, station_id: Optional[str] = None) -> None:
        """No-op: Health history is stateless and derived purely from the evaluation window."""
        pass

    def evaluate(
        self,
        target_observations: List[Observation],
        quality_evidence: Optional[List[Evidence]] = None,
        reference_time: Optional[Union[datetime, str]] = None,
    ) -> SensorEvidenceResult:
        """Evaluate chronological observations for a single target station.

        Args:
            target_observations: Chronological list of observations for ONE target station.
                                 The final observation is the current observation under evaluation.
                                 Preceding observations provide historical context.
            quality_evidence: Optional upstream QC evidence from M1-C1 to ingest/preserve without duplication.
            reference_time: Optional reference time (datetime or ISO string) establishing current evaluation boundary.
                            Observations with observed_at > reference_time are strictly excluded.

        Returns:
            SensorEvidenceResult containing candidate SENSOR evidence, mechanism details, and health summary.
        """
        # Step 0: Input validation and defensive handling
        if not target_observations:
            return SensorEvidenceResult(
                station_id="UNKNOWN",
                target_observation_id="NONE",
                evidence=[],
                evaluated_observations=[],
                mechanism_summary={"status": "EMPTY_INPUT"},
                health_history_summary={
                    "window_size": 0,
                    "accumulated_anomalies": 0,
                    "consecutive_clean_steps": 0,
                    "is_recovered": True,
                },
                provenance=EvidenceProvenance(
                    source_type="DETERMINISTIC_QC",
                    source_id="sensor-engine-v1",
                    derived_from=[],
                ),
                warnings=["Empty observation list provided to SensorEvidenceEngine."],
                summary="No observations provided for evaluation.",
            )

        # Single station validation
        target_station_id = target_observations[0].station_id
        for obs in target_observations:
            if obs.station_id != target_station_id:
                raise ValueError(
                    f"SensorEvidenceEngine expects chronological observations for ONE station. "
                    f"Found mixed station IDs: '{obs.station_id}' and '{target_station_id}'."
                )

        # Sort a local derived view chronologically without mutating caller-owned input list
        local_sorted_obs = sorted(target_observations, key=lambda o: _to_utc_datetime(o.observed_at))

        # Determine reference time boundary
        ref_dt: Optional[datetime] = None
        if reference_time is not None:
            ref_dt = _to_utc_datetime(reference_time)
        else:
            # If reference_time is omitted, use latest observation timestamp as evaluation boundary
            ref_dt = _to_utc_datetime(local_sorted_obs[-1].observed_at)

        # Filter strictly: every observation used for evidence generation must satisfy observed_at <= reference_time
        valid_chronological_obs = [o for o in local_sorted_obs if _to_utc_datetime(o.observed_at) <= ref_dt]

        if not valid_chronological_obs:
            return SensorEvidenceResult(
                station_id=target_station_id,
                target_observation_id="NONE",
                evidence=[],
                evaluated_observations=[],
                mechanism_summary={"status": "NO_CAUSAL_OBSERVATIONS"},
                health_history_summary={
                    "window_size": 0,
                    "accumulated_anomalies": 0,
                    "consecutive_clean_steps": 0,
                    "is_recovered": True,
                },
                provenance=EvidenceProvenance(
                    source_type="DETERMINISTIC_QC",
                    source_id="sensor-engine-v1",
                    derived_from=[],
                ),
                warnings=["All observations exceeded reference_time (future timestamp violation)."],
                summary="No valid causal observations available for evaluation at or before reference_time.",
            )

        # The target observation is strictly the final valid observation
        target_obs = valid_chronological_obs[-1]
        evaluated_ids = [o.observation_id for o in valid_chronological_obs]

        evidence_list: List[Evidence] = []
        warnings: List[str] = []
        mechanism_summary: Dict[str, Any] = {}
        ingested_evidence_ids: Set[str] = set()

        # Step 1: Ingest & Preserve Upstream Quality Evidence (M1-C1)
        # CRITICAL: Preserve identity/provenance, no duplication, no amplification into diagnosis
        if quality_evidence:
            for qe in quality_evidence:
                if qe.evidence_id in ingested_evidence_ids:
                    continue
                # Ingest only if relevant to target observation or immediate station context
                if target_obs.observation_id in qe.subject.observation_ids or qe.subject.station_id == target_station_id:
                    # Ingest strictly without mutating
                    evidence_list.append(qe)
                    ingested_evidence_ids.add(qe.evidence_id)

        # Step 2: Physical-Limit Evidence (Heuristic screening bounds; candidate evidence only)
        self._evaluate_physical_limits(target_obs, evidence_list, ingested_evidence_ids, mechanism_summary)

        # Step 3: Repeated Temporal Spikes
        self._evaluate_temporal_spikes(valid_chronological_obs, evidence_list, ingested_evidence_ids, mechanism_summary)

        # Step 4: Sustained Channel-Specific Flatline
        self._evaluate_flatlines(valid_chronological_obs, evidence_list, ingested_evidence_ids, mechanism_summary)

        # Step 5: Station-Specific Baseline Deviation (MAD / Robust Median)
        self._evaluate_baseline_deviation(valid_chronological_obs, evidence_list, ingested_evidence_ids, mechanism_summary)

        # Step 6: Persistent Offset / Drift Candidate
        self._evaluate_drift_candidate(valid_chronological_obs, evidence_list, ingested_evidence_ids, mechanism_summary)

        # Step 7: Intermittent Failure Signatures (Dropouts & Flapping)
        self._evaluate_intermittent_failures(valid_chronological_obs, evidence_list, ingested_evidence_ids, mechanism_summary)

        # Step 8: Telemetry / Sequence Behavior
        self._evaluate_telemetry_integrity(valid_chronological_obs, evidence_list, ingested_evidence_ids, mechanism_summary)

        # Step 9: Bounded Health Memory Accumulator & Decay (Stateless derivation from bounded input window)
        health_summary = self._evaluate_health_history(valid_chronological_obs, evidence_list, quality_evidence)

        # Step 10: Summary & Causal Ambiguity Wording
        # Invariant: If observations have potential ambiguity, do NOT force SENSOR
        if not evidence_list:
            summary = f"Station {target_station_id} telemetry and sensor channels are nominal; no SENSOR evidence."
        elif any(e.type == "PHYSICAL_LIMIT" for e in evidence_list):
            summary = f"Station {target_station_id} breached configured physical plausibility bounds; SENSOR candidate evidence active."
        elif any(e.strength >= 0.70 for e in evidence_list):
            summary = (
                f"Station {target_station_id} exhibits station-specific sensor failure signatures; "
                f"candidate evidence generated; final attribution deferred to M1-C6."
            )
        else:
            summary = (
                f"Station {target_station_id}: Station-specific evidence candidate; "
                f"attribution remains unresolved (weak candidate evidence)."
            )

        return SensorEvidenceResult(
            station_id=target_station_id,
            target_observation_id=target_obs.observation_id,
            evidence=evidence_list,
            evaluated_observations=evaluated_ids,
            mechanism_summary=mechanism_summary,
            health_history_summary=health_summary,
            provenance=EvidenceProvenance(
                source_type="DETERMINISTIC_QC",
                source_id="sensor-engine-v1",
                derived_from=[target_obs.observation_id],
            ),
            warnings=warnings,
            summary=summary,
        )

    # -------------------------------------------------------------------------
    # Mechanism 2: Physical Limits
    # -------------------------------------------------------------------------
    def _evaluate_physical_limits(
        self,
        target_obs: Observation,
        evidence_list: List[Evidence],
        ingested_evidence_ids: Set[str],
        mechanism_summary: Dict[str, Any],
    ) -> None:
        """Inspect measurements against configured physical plausibility bounds without duplicate creation."""
        m = target_obs.measurements
        violations: List[str] = []

        # Temperature
        if m.temperature_c is not None:
            if m.temperature_c < self.config.temp_min_c or m.temperature_c > self.config.temp_max_c:
                violations.append("temperature_c")
                ev_id = f"ev-sensor-{target_obs.observation_id}-range-temp"
                if ev_id not in ingested_evidence_ids and not any(e.type == "PHYSICAL_LIMIT" and "temp" in e.independence_group for e in evidence_list):
                    evidence_list.append(
                        Evidence(
                            evidence_id=ev_id,
                            subject=EvidenceSubject(
                                station_id=target_obs.station_id,
                                observation_ids=[target_obs.observation_id],
                            ),
                            type="PHYSICAL_LIMIT",
                            relation="SUPPORTS",
                            hypothesis="SENSOR",
                            description=(
                                f"Temperature {m.temperature_c}°C breached configured physical plausibility bound "
                                f"[{self.config.temp_min_c}, {self.config.temp_max_c}]°C. Physical-limit anomaly candidate."
                            ),
                            strength=0.95,
                            quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                            provenance=EvidenceProvenance(
                                source_type="DETERMINISTIC_QC",
                                source_id="sensor-physical-limit-v1",
                                derived_from=[target_obs.observation_id],
                            ),
                            independence_group="sensor-range-temperature",
                            status="AVAILABLE",
                        )
                    )
                    ingested_evidence_ids.add(ev_id)

        # Humidity
        if m.relative_humidity_pct is not None:
            if m.relative_humidity_pct < self.config.humidity_min_pct or m.relative_humidity_pct > self.config.humidity_max_pct:
                violations.append("relative_humidity_pct")
                ev_id = f"ev-sensor-{target_obs.observation_id}-range-humidity"
                if ev_id not in ingested_evidence_ids and not any(e.type == "PHYSICAL_LIMIT" and "humidity" in e.independence_group for e in evidence_list):
                    evidence_list.append(
                        Evidence(
                            evidence_id=ev_id,
                            subject=EvidenceSubject(
                                station_id=target_obs.station_id,
                                observation_ids=[target_obs.observation_id],
                            ),
                            type="PHYSICAL_LIMIT",
                            relation="SUPPORTS",
                            hypothesis="SENSOR",
                            description=(
                                f"Relative humidity {m.relative_humidity_pct}% breached configured physical plausibility bound "
                                f"[{self.config.humidity_min_pct}, {self.config.humidity_max_pct}]%. Physical-limit anomaly candidate."
                            ),
                            strength=0.95,
                            quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                            provenance=EvidenceProvenance(
                                source_type="DETERMINISTIC_QC",
                                source_id="sensor-physical-limit-v1",
                                derived_from=[target_obs.observation_id],
                            ),
                            independence_group="sensor-range-humidity",
                            status="AVAILABLE",
                        )
                    )
                    ingested_evidence_ids.add(ev_id)

        # Pressure
        if m.pressure_hpa is not None:
            if m.pressure_hpa < self.config.pressure_min_hpa or m.pressure_hpa > self.config.pressure_max_hpa:
                violations.append("pressure_hpa")
                ev_id = f"ev-sensor-{target_obs.observation_id}-range-pressure"
                if ev_id not in ingested_evidence_ids and not any(e.type == "PHYSICAL_LIMIT" and "pressure" in e.independence_group for e in evidence_list):
                    evidence_list.append(
                        Evidence(
                            evidence_id=ev_id,
                            subject=EvidenceSubject(
                                station_id=target_obs.station_id,
                                observation_ids=[target_obs.observation_id],
                            ),
                            type="PHYSICAL_LIMIT",
                            relation="SUPPORTS",
                            hypothesis="SENSOR",
                            description=(
                                f"Barometric pressure {m.pressure_hpa} hPa breached configured physical plausibility bound "
                                f"[{self.config.pressure_min_hpa}, {self.config.pressure_max_hpa}] hPa. Physical-limit anomaly candidate."
                            ),
                            strength=0.95,
                            quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                            provenance=EvidenceProvenance(
                                source_type="DETERMINISTIC_QC",
                                source_id="sensor-physical-limit-v1",
                                derived_from=[target_obs.observation_id],
                            ),
                            independence_group="sensor-range-pressure",
                            status="AVAILABLE",
                        )
                    )
                    ingested_evidence_ids.add(ev_id)

        mechanism_summary["physical_limits"] = {
            "evaluated": True,
            "violations": violations,
        }

    # -------------------------------------------------------------------------
    # Mechanism 3: Repeated Temporal Spikes
    # -------------------------------------------------------------------------
    def _evaluate_temporal_spikes(
        self,
        observations: List[Observation],
        evidence_list: List[Evidence],
        ingested_evidence_ids: Set[str],
        mechanism_summary: Dict[str, Any],
    ) -> None:
        """Distinguish single transient spike (weak candidate) from repeated spike recurrence (strong candidate)."""
        if len(observations) < 2:
            mechanism_summary["temporal_spikes"] = {"status": "INSUFFICIENT_HISTORY"}
            return

        target_obs = observations[-1]
        spike_summary: Dict[str, Any] = {}

        for param, thresh in [
            ("temperature_c", self.config.spike_threshold_temp_c),
            ("relative_humidity_pct", self.config.spike_threshold_humidity_pct),
            ("pressure_hpa", self.config.spike_threshold_pressure_hpa),
        ]:
            param_clean = _clean_param(param)
            # Extract valid values across window
            series = [(o.observation_id, getattr(o.measurements, param)) for o in observations if getattr(o.measurements, param) is not None]
            if len(series) < 2:
                continue

            # Detect abrupt step transitions in series
            spike_indices: List[int] = []
            for i in range(1, len(series)):
                delta = abs(series[i][1] - series[i - 1][1])
                if delta >= thresh:
                    spike_indices.append(i)

            curr_is_spike = len(spike_indices) > 0 and (spike_indices[-1] == len(series) - 1)
            total_spikes = len(spike_indices)

            spike_summary[param] = {
                "total_spikes_in_window": total_spikes,
                "current_observation_is_spike": curr_is_spike,
            }

            if not curr_is_spike:
                continue

            # Case A: Repeated Spikes (>= 2 distinct spike events in window)
            if total_spikes >= self.config.spike_recurrence_min_count:
                ev_id = f"ev-sensor-{target_obs.observation_id}-spike-recurrence-{param_clean}"
                if ev_id not in ingested_evidence_ids:
                    evidence_list.append(
                        Evidence(
                            evidence_id=ev_id,
                            subject=EvidenceSubject(
                                station_id=target_obs.station_id,
                                observation_ids=[s[0] for s in series[-self.config.spike_recurrence_min_count:]],
                            ),
                            type="TEMPORAL",
                            relation="SUPPORTS",
                            hypothesis="SENSOR",
                            description=(
                                f"Repeated spike recurrence on {param_clean}: {total_spikes} abrupt step transitions "
                                f"(>= {thresh}) observed across window. Station-specific transducer/wiring instability candidate."
                            ),
                            strength=0.75,
                            quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                            provenance=EvidenceProvenance(
                                source_type="DETERMINISTIC_QC",
                                source_id="sensor-spike-v1",
                                derived_from=[target_obs.observation_id],
                            ),
                            independence_group=f"station-spike-{param_clean}",
                            status="AVAILABLE",
                        )
                    )
                    ingested_evidence_ids.add(ev_id)
            else:
                # Case B: Single Isolated Spike -> Explicitly weak candidate, insufficient alone
                ev_id = f"ev-sensor-{target_obs.observation_id}-spike-isolated-{param_clean}"
                if ev_id not in ingested_evidence_ids:
                    evidence_list.append(
                        Evidence(
                            evidence_id=ev_id,
                            subject=EvidenceSubject(
                                station_id=target_obs.station_id,
                                observation_ids=[series[-2][0], series[-1][0]],
                            ),
                            type="TEMPORAL",
                            relation="SUPPORTS",
                            hypothesis="SENSOR",
                            description=(
                                f"Single isolated step change on {param_clean} (delta={abs(series[-1][1] - series[-2][1]):.2f}). "
                                "Candidate evidence only; attribution remains unresolved; isolated transient insufficient for sensor fault attribution."
                            ),
                            strength=0.30,  # Explicitly weak
                            quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="PARTIAL"),
                            provenance=EvidenceProvenance(
                                source_type="DETERMINISTIC_QC",
                                source_id="sensor-spike-v1",
                                derived_from=[target_obs.observation_id],
                            ),
                            independence_group=f"station-spike-{param_clean}",
                            status="AVAILABLE",
                        )
                    )
                    ingested_evidence_ids.add(ev_id)

        mechanism_summary["temporal_spikes"] = spike_summary

    # -------------------------------------------------------------------------
    # Mechanism 4: Sustained Flatline
    # -------------------------------------------------------------------------
    def _evaluate_flatlines(
        self,
        observations: List[Observation],
        evidence_list: List[Evidence],
        ingested_evidence_ids: Set[str],
        mechanism_summary: Dict[str, Any],
    ) -> None:
        """Detect frozen channel readings over configurable persistence windows.

        Critical rule: Differentiates isolated single-channel freeze (strong candidate)
        from all-channel atmospheric calm (discounted candidate).
        Avoids false alarms on 2-3 repeated pressure values due to rounding.
        """
        req_count = self.config.flatline_persistence_count
        if len(observations) < req_count:
            mechanism_summary["flatlines"] = {"status": "INSUFFICIENT_HISTORY"}
            return

        target_obs = observations[-1]
        recent_window = observations[-req_count:]

        channel_run_lengths: Dict[str, int] = {}
        channel_frozen: Dict[str, bool] = {}

        for param in ["temperature_c", "relative_humidity_pct", "pressure_hpa"]:
            vals = [getattr(o.measurements, param) for o in recent_window]
            if any(v is None for v in vals):
                channel_run_lengths[param] = 0
                channel_frozen[param] = False
                continue

            target_v = vals[-1]
            # Count identical readings backwards from target
            run_len = 0
            for v in reversed(vals):
                if v == target_v:
                    run_len += 1
                else:
                    break

            channel_run_lengths[param] = run_len
            channel_frozen[param] = run_len >= req_count

        frozen_params = [p for p, is_froz in channel_frozen.items() if is_froz]
        evolving_params = [p for p, is_froz in channel_frozen.items() if not is_froz and channel_run_lengths[p] < req_count]

        mechanism_summary["flatlines"] = {
            "channel_run_lengths": channel_run_lengths,
            "frozen_channels": frozen_params,
        }

        if not frozen_params:
            return

        # Check if ALL available channels are frozen (e.g. calm atmospheric inversion)
        all_channels_frozen = len(frozen_params) >= 3 or (len(frozen_params) > 0 and len(evolving_params) == 0)

        for param in frozen_params:
            param_clean = _clean_param(param)
            run_len = channel_run_lengths[param]

            if all_channels_frozen:
                # All channels stationary -> atmospheric stillness is plausible
                ev_id = f"ev-sensor-{target_obs.observation_id}-flatline-all-{param_clean}"
                if ev_id not in ingested_evidence_ids and not any(f"flatline" in e.evidence_id and param_clean in e.evidence_id for e in evidence_list):
                    evidence_list.append(
                        Evidence(
                            evidence_id=ev_id,
                            subject=EvidenceSubject(
                                station_id=target_obs.station_id,
                                observation_ids=[o.observation_id for o in recent_window],
                            ),
                            type="TEMPORAL",
                            relation="SUPPORTS",
                            hypothesis="SENSOR",
                            description=(
                                f"Sustained constant values on {param_clean} ({run_len} identical readings), "
                                "but all station channels remain stationary. Atmospheric stillness plausible; attribution unresolved."
                            ),
                            strength=0.30,  # Heavily discounted due to multi-channel calm
                            quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                            provenance=EvidenceProvenance(
                                source_type="DETERMINISTIC_QC",
                                source_id="sensor-flatline-v1",
                                derived_from=[o.observation_id for o in recent_window],
                            ),
                            independence_group=f"station-persistence-{param_clean}",
                            status="AVAILABLE",
                        )
                    )
                    ingested_evidence_ids.add(ev_id)
            else:
                # Isolated channel freeze while other channels evolve -> strong station-specific sensor candidate
                ev_id = f"ev-sensor-{target_obs.observation_id}-flatline-isolated-{param_clean}"
                if ev_id not in ingested_evidence_ids and not any(f"flatline" in e.evidence_id and param_clean in e.evidence_id for e in evidence_list):
                    evidence_list.append(
                        Evidence(
                            evidence_id=ev_id,
                            subject=EvidenceSubject(
                                station_id=target_obs.station_id,
                                observation_ids=[o.observation_id for o in recent_window],
                            ),
                            type="TEMPORAL",
                            relation="SUPPORTS",
                            hypothesis="SENSOR",
                            description=(
                                f"Isolated sustained flatline on {param_clean} ({run_len} identical readings) "
                                f"while other channels ({', '.join([_clean_param(p) for p in evolving_params])}) actively vary. "
                                "Station-specific transducer lockup candidate."
                            ),
                            strength=0.80,  # Strong candidate evidence
                            quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                            provenance=EvidenceProvenance(
                                source_type="DETERMINISTIC_QC",
                                source_id="sensor-flatline-v1",
                                derived_from=[o.observation_id for o in recent_window],
                            ),
                            independence_group=f"station-persistence-{param_clean}",
                            status="AVAILABLE",
                        )
                    )
                    ingested_evidence_ids.add(ev_id)

    # -------------------------------------------------------------------------
    # Mechanism 5: Station-Specific Baseline Deviation (MAD)
    # -------------------------------------------------------------------------
    def _evaluate_baseline_deviation(
        self,
        observations: List[Observation],
        evidence_list: List[Evidence],
        ingested_evidence_ids: Set[str],
        mechanism_summary: Dict[str, Any],
    ) -> None:
        """Evaluate whether a station deviates from its recent rolling baseline using robust MAD."""
        min_hist = 5
        if len(observations) < min_hist:
            mechanism_summary["baseline_deviation"] = {"status": "INSUFFICIENT_HISTORY"}
            return

        target_obs = observations[-1]
        baseline_summary: Dict[str, Any] = {}

        # Use historical observations strictly prior to target for baseline calculation
        hist_window = observations[-self.config.baseline_window_size : -1]
        if not hist_window:
            return

        for param, noise_floor in [
            ("temperature_c", self.config.min_mad_noise_floor_temp_c),
            ("relative_humidity_pct", self.config.min_mad_noise_floor_humidity_pct),
            ("pressure_hpa", self.config.min_mad_noise_floor_pressure_hpa),
        ]:
            param_clean = _clean_param(param)
            target_val = getattr(target_obs.measurements, param)
            if target_val is None:
                continue

            hist_vals = [getattr(o.measurements, param) for o in hist_window if getattr(o.measurements, param) is not None]
            if len(hist_vals) < 4:
                continue

            # Robust Median & MAD
            med = statistics.median(hist_vals)
            abs_devs = [abs(v - med) for v in hist_vals]
            mad = statistics.median(abs_devs)
            effective_scale = max(mad * 1.4826, noise_floor)

            residual = abs(target_val - med)
            z_robust = residual / effective_scale if effective_scale > 0 else 0.0

            baseline_summary[param] = {
                "rolling_median": med,
                "effective_scale": effective_scale,
                "residual": residual,
                "z_robust": z_robust,
            }

            if z_robust >= self.config.mad_threshold_sigma:
                ev_id = f"ev-sensor-{target_obs.observation_id}-baseline-dev-{param_clean}"
                if ev_id not in ingested_evidence_ids:
                    evidence_list.append(
                        Evidence(
                            evidence_id=ev_id,
                            subject=EvidenceSubject(
                                station_id=target_obs.station_id,
                                observation_ids=[target_obs.observation_id],
                            ),
                            type="TEMPORAL",
                            relation="SUPPORTS",
                            hypothesis="SENSOR",
                            description=(
                                f"Station-specific baseline deviation candidate on {param_clean} "
                                f"(residual={residual:.2f}, robust score={z_robust:.1f} >= {self.config.mad_threshold_sigma:.1f}). "
                                "Environmental regime shift plausible; attribution unresolved."
                            ),
                            strength=0.40,  # Capped candidate score; never strong proof
                            quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                            provenance=EvidenceProvenance(
                                source_type="DETERMINISTIC_QC",
                                source_id="sensor-baseline-v1",
                                derived_from=[target_obs.observation_id],
                            ),
                            independence_group=f"station-baseline-{param_clean}",
                            status="AVAILABLE",
                        )
                    )
                    ingested_evidence_ids.add(ev_id)

        mechanism_summary["baseline_deviation"] = baseline_summary

    # -------------------------------------------------------------------------
    # Mechanism 6: Persistent Offset / Drift Candidate
    # -------------------------------------------------------------------------
    def _evaluate_drift_candidate(
        self,
        observations: List[Observation],
        evidence_list: List[Evidence],
        ingested_evidence_ids: Set[str],
        mechanism_summary: Dict[str, Any],
    ) -> None:
        """Detect persistent unilateral residual offset.

        Invariant: Raw trend != degradation. Avoids flagging normal diurnal heating.
        Requires sustained signed residual relative to baseline across >= drift_min_persistence_count.
        """
        req_count = self.config.drift_min_persistence_count
        if len(observations) < req_count + 3:
            mechanism_summary["drift_candidate"] = {"status": "INSUFFICIENT_HISTORY"}
            return

        target_obs = observations[-1]
        drift_summary: Dict[str, Any] = {}

        # Compute baseline from early window observations
        baseline_slice = observations[-(req_count + 8) : -req_count]
        recent_slice = observations[-req_count:]

        if not baseline_slice or not recent_slice:
            return

        for param, min_offset in [
            ("temperature_c", self.config.drift_min_offset_temp_c),
            ("relative_humidity_pct", self.config.drift_min_offset_humidity_pct),
            ("pressure_hpa", self.config.drift_min_offset_pressure_hpa),
        ]:
            param_clean = _clean_param(param)
            base_vals = [getattr(o.measurements, param) for o in baseline_slice if getattr(o.measurements, param) is not None]
            recent_vals = [getattr(o.measurements, param) for o in recent_slice if getattr(o.measurements, param) is not None]

            if len(base_vals) < 3 or len(recent_vals) < req_count:
                continue

            base_med = statistics.median(base_vals)
            residuals = [v - base_med for v in recent_vals]

            # Check for sustained signed bias in one direction
            all_positive = all(r >= min_offset for r in residuals)
            all_negative = all(r <= -min_offset for r in residuals)

            mean_offset = sum(residuals) / len(residuals)
            drift_summary[param] = {
                "base_median": base_med,
                "mean_recent_offset": mean_offset,
                "persistent_unilateral_offset": (all_positive or all_negative),
            }

            if all_positive or all_negative:
                ev_id = f"ev-sensor-{target_obs.observation_id}-drift-{param_clean}"
                if ev_id not in ingested_evidence_ids:
                    evidence_list.append(
                        Evidence(
                            evidence_id=ev_id,
                            subject=EvidenceSubject(
                                station_id=target_obs.station_id,
                                observation_ids=[o.observation_id for o in recent_slice],
                            ),
                            type="TEMPORAL",
                            relation="SUPPORTS",
                            hypothesis="SENSOR",
                            description=(
                                f"Persistent signed offset candidate on {param_clean} holding across {req_count} timesteps "
                                f"(mean offset ~{mean_offset:+.2f}). Candidate sensor drift; "
                                "physical attribution requires multi-station/world arbitration."
                            ),
                            strength=0.60,
                            quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                            provenance=EvidenceProvenance(
                                source_type="DETERMINISTIC_QC",
                                source_id="sensor-drift-v1",
                                derived_from=[o.observation_id for o in recent_slice],
                            ),
                            independence_group=f"station-drift-{param_clean}",
                            status="AVAILABLE",
                        )
                    )
                    ingested_evidence_ids.add(ev_id)

        mechanism_summary["drift_candidate"] = drift_summary

    # -------------------------------------------------------------------------
    # Mechanism 7: Intermittent Failure Signatures
    # -------------------------------------------------------------------------
    def _evaluate_intermittent_failures(
        self,
        observations: List[Observation],
        evidence_list: List[Evidence],
        ingested_evidence_ids: Set[str],
        mechanism_summary: Dict[str, Any],
    ) -> None:
        """Detect intermittent dropouts and signal flapping (valid -> null -> valid -> null)."""
        window = observations[-self.config.intermittent_window_size :]
        if len(window) < 4:
            mechanism_summary["intermittent"] = {"status": "INSUFFICIENT_HISTORY"}
            return

        target_obs = observations[-1]
        intermittent_summary: Dict[str, Any] = {}

        for param in ["temperature_c", "relative_humidity_pct", "pressure_hpa"]:
            param_clean = _clean_param(param)
            validity_pattern = [getattr(o.measurements, param) is not None for o in window]

            # Count toggles between valid (True) and missing (False)
            toggles = 0
            for i in range(1, len(validity_pattern)):
                if validity_pattern[i] != validity_pattern[i - 1]:
                    toggles += 1

            intermittent_summary[param] = {
                "toggle_count": toggles,
                "null_count": validity_pattern.count(False),
            }

            # If flapping repeatedly (at least intermittent_min_transitions toggles and at least 2 dropouts)
            if toggles >= self.config.intermittent_min_transitions and validity_pattern.count(False) >= 2:
                ev_id = f"ev-sensor-{target_obs.observation_id}-intermittent-{param_clean}"
                if ev_id not in ingested_evidence_ids:
                    evidence_list.append(
                        Evidence(
                            evidence_id=ev_id,
                            subject=EvidenceSubject(
                                station_id=target_obs.station_id,
                                observation_ids=[o.observation_id for o in window],
                            ),
                            type="TEMPORAL",
                            relation="SUPPORTS",
                            hypothesis="SENSOR",
                            description=(
                                f"Intermittent telemetry/sensor dropout pattern on {param_clean} "
                                f"({toggles} transitions, {validity_pattern.count(False)} dropouts in window). "
                                "Station-specific intermittent connection or hardware instability candidate."
                            ),
                            strength=0.70,
                            quality=EvidenceQuality(status="DEGRADED", freshness="FRESH", completeness="PARTIAL"),
                            provenance=EvidenceProvenance(
                                source_type="DETERMINISTIC_QC",
                                source_id="sensor-intermittent-v1",
                                derived_from=[o.observation_id for o in window],
                            ),
                            independence_group=f"station-intermittent-{param_clean}",
                            status="AVAILABLE",
                        )
                    )
                    ingested_evidence_ids.add(ev_id)

        mechanism_summary["intermittent"] = intermittent_summary

    # -------------------------------------------------------------------------
    # Mechanism 8: Telemetry / Sequence Integrity
    # -------------------------------------------------------------------------
    def _evaluate_telemetry_integrity(
        self,
        observations: List[Observation],
        evidence_list: List[Evidence],
        ingested_evidence_ids: Set[str],
        mechanism_summary: Dict[str, Any],
    ) -> None:
        """Aggregate repeated sequence anomalies and clock drift as telemetry integrity evidence."""
        if len(observations) < 2:
            mechanism_summary["telemetry_integrity"] = {"status": "INSUFFICIENT_HISTORY"}
            return

        target_obs = observations[-1]
        telemetry_glitches: List[str] = []

        for i in range(1, len(observations)):
            curr_o = observations[i]
            prev_o = observations[i - 1]

            # Sequence regressions / duplicates
            if curr_o.sequence is not None and prev_o.sequence is not None:
                if curr_o.sequence < prev_o.sequence:
                    telemetry_glitches.append(f"seq_regression_{curr_o.observation_id}")
                elif curr_o.sequence == prev_o.sequence:
                    telemetry_glitches.append(f"seq_duplicate_{curr_o.observation_id}")

            # Timestamp inversions
            try:
                c_dt = _to_utc_datetime(curr_o.observed_at)
                p_dt = _to_utc_datetime(prev_o.observed_at)
                if c_dt < p_dt:
                    telemetry_glitches.append(f"ts_inversion_{curr_o.observation_id}")
            except Exception:
                pass

        mechanism_summary["telemetry_integrity"] = {
            "total_glitches_in_window": len(telemetry_glitches),
            "glitch_types": telemetry_glitches,
        }

        # Emits evidence only if repeated (count >= telemetry_anomaly_threshold)
        if len(telemetry_glitches) >= self.config.telemetry_anomaly_threshold:
            ev_id = f"ev-sensor-{target_obs.observation_id}-telemetry-integrity"
            if ev_id not in ingested_evidence_ids:
                evidence_list.append(
                    Evidence(
                        evidence_id=ev_id,
                        subject=EvidenceSubject(
                            station_id=target_obs.station_id,
                            observation_ids=[target_obs.observation_id],
                        ),
                        type="TEMPORAL",
                        relation="SUPPORTS",
                        hypothesis="SENSOR",
                        description=(
                            f"Repeated telemetry sequence/timing anomalies detected ({len(telemetry_glitches)} occurrences). "
                            "Station telemetry integrity anomaly; not guaranteed physical sensor hardware failure."
                        ),
                        strength=0.65,
                        quality=EvidenceQuality(status="DEGRADED", freshness="FRESH", completeness="COMPLETE"),
                        provenance=EvidenceProvenance(
                            source_type="DETERMINISTIC_QC",
                            source_id="sensor-telemetry-v1",
                            derived_from=[target_obs.observation_id],
                        ),
                        independence_group="station-telemetry-integrity",
                        status="AVAILABLE",
                    )
                )
                ingested_evidence_ids.add(ev_id)

    # -------------------------------------------------------------------------
    # Mechanism 9: Bounded Sensor-Health History
    # -------------------------------------------------------------------------
    def _evaluate_health_history(
        self,
        valid_chronological_obs: List[Observation],
        evidence_list: List[Evidence],
        quality_evidence: Optional[List[Evidence]] = None,
    ) -> Dict[str, Any]:
        """Derive bounded causal health history from the supplied chronological window only.

        Guarantees:
        - Bounded window size (max config.health_history_buffer_size, default 30).
        - Derived purely from supplied causal observations; NO hidden mutable instance state.
        - Strictly causal (past and current observations up to reference_time only).
        - Zero scenario awareness; never consumes ground truth or final decision states.
        - Natural recovery: clean steps decay anomaly count; temporary weather events
          do not permanently poison sensor health.
        - Deterministic and idempotent across repeated calls.
        """
        window = valid_chronological_obs[-self.config.health_history_buffer_size :]
        if not window:
            return {
                "window_size": 0,
                "accumulated_anomalies": 0,
                "consecutive_clean_steps": 0,
                "is_recovered": True,
            }

        target_obs = window[-1]
        step_anomalies: List[bool] = []

        for i, obs in enumerate(window):
            if obs.observation_id == target_obs.observation_id:
                # Target observation: check if active SENSOR evidence is present
                has_anom = any(e.hypothesis == "SENSOR" and e.strength >= 0.50 for e in evidence_list)
                step_anomalies.append(has_anom)
            else:
                # Historical observation in the window: check physical bounds, upstream QC, or abrupt spikes
                m = obs.measurements
                phys_breach = False
                if m.temperature_c is not None and (m.temperature_c < self.config.temp_min_c or m.temperature_c > self.config.temp_max_c):
                    phys_breach = True
                if m.relative_humidity_pct is not None and (m.relative_humidity_pct < self.config.humidity_min_pct or m.relative_humidity_pct > self.config.humidity_max_pct):
                    phys_breach = True
                if m.pressure_hpa is not None and (m.pressure_hpa < self.config.pressure_min_hpa or m.pressure_hpa > self.config.pressure_max_hpa):
                    phys_breach = True

                qc_breach = False
                if quality_evidence:
                    for qe in quality_evidence:
                        if (
                            obs.observation_id in qe.subject.observation_ids
                            or (qe.provenance and obs.observation_id in qe.provenance.derived_from)
                        ) and qe.hypothesis == "SENSOR" and qe.strength >= 0.50:
                            qc_breach = True
                            break

                step_spike = False
                if i > 0:
                    pm = window[i - 1].measurements
                    if m.temperature_c is not None and pm.temperature_c is not None and abs(m.temperature_c - pm.temperature_c) >= self.config.spike_threshold_temp_c:
                        step_spike = True
                    elif m.relative_humidity_pct is not None and pm.relative_humidity_pct is not None and abs(m.relative_humidity_pct - pm.relative_humidity_pct) >= self.config.spike_threshold_humidity_pct:
                        step_spike = True
                    elif m.pressure_hpa is not None and pm.pressure_hpa is not None and abs(m.pressure_hpa - pm.pressure_hpa) >= self.config.spike_threshold_pressure_hpa:
                        step_spike = True

                step_anomalies.append(phys_breach or qc_breach or step_spike)

        total_anomalies = sum(1 for a in step_anomalies if a)

        # Count consecutive clean steps from tail
        consecutive_clean_steps = 0
        for a in reversed(step_anomalies):
            if not a:
                consecutive_clean_steps += 1
            else:
                break

        is_recovered = consecutive_clean_steps >= self.config.health_recovery_clean_steps

        # If accumulated anomalies are high AND station has not recovered, emit persistence candidate evidence
        if total_anomalies >= 4 and not is_recovered:
            ev_id = f"ev-sensor-{target_obs.observation_id}-health-recurrence"
            if not any(e.evidence_id == ev_id for e in evidence_list):
                evidence_list.append(
                    Evidence(
                        evidence_id=ev_id,
                        subject=EvidenceSubject(
                            station_id=target_obs.station_id,
                            observation_ids=[target_obs.observation_id],
                        ),
                        type="TEMPORAL",
                        relation="SUPPORTS",
                        hypothesis="SENSOR",
                        description=(
                            f"Recurrent station-specific anomaly history ({total_anomalies} anomalies across last {len(window)} evaluations). "
                            "Historical recurrence candidate; attribution subject to downstream fusion."
                        ),
                        strength=0.55,
                        quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                        provenance=EvidenceProvenance(
                            source_type="DETERMINISTIC_QC",
                            source_id="sensor-health-v1",
                            derived_from=[target_obs.observation_id],
                        ),
                        independence_group="station-health-history",
                        status="AVAILABLE",
                    )
                )

        return {
            "window_size": len(window),
            "accumulated_anomalies": total_anomalies,
            "consecutive_clean_steps": consecutive_clean_steps,
            "is_recovered": is_recovered,
        }
