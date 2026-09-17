"""Deterministic Data Quality and Safety QC Layer for SKYGUARD.

Executes physical limits, temporal rate-of-change, persistence/flatline,
timestamp integrity, sequence progression, and completeness checks.
Produces structured QualityResult and canonical Evidence objects.

Architectural Invariants:
1. Observation != Interpretation: Raw observations are never mutated.
2. Evidence != Decision: Generates evidence, never final operational states.
3. Outlier != Fault: Unusual readings create evidence, not final state verdicts.
4. AI != Judge: All checks in this layer are purely deterministic.
5. Zero Scenario Awareness: No simulation or ground truth labels are accessed.

Independence Group Semantics:
Different independence_group values identify distinct evidence mechanisms or
provenance partitions. They do NOT prove statistical independence. Verification
of structural or physical independence is deferred to the downstream Independence Gate.
"""

from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from backend.schemas import (
    Evidence,
    EvidenceProvenance,
    EvidenceQuality,
    EvidenceSubject,
    Observation,
)


class QualityConfig(BaseModel):
    """Configuration for deterministic quality checks and sanity thresholds."""

    # Terrestrial surface physical plausibility bounds
    temp_min_c: float = Field(-40.0, description="Minimum plausible ambient temperature (°C)")
    temp_max_c: float = Field(55.0, description="Maximum plausible ambient temperature (°C)")
    humidity_min_pct: float = Field(0.0, ge=0.0, description="Minimum relative humidity (%)")
    humidity_max_pct: float = Field(100.0, le=100.0, description="Maximum relative humidity (%)")
    pressure_min_hpa: float = Field(850.0, description="Minimum barometric pressure (hPa)")
    pressure_max_hpa: float = Field(1080.0, description="Maximum barometric pressure (hPa)")

    # Temporal rate-of-change thresholds (per minute)
    max_temp_change_per_min: float = Field(1.5, description="Max plausible temperature rate of change (°C/min)")
    max_humidity_change_per_min: float = Field(6.0, description="Max plausible humidity rate of change (%/min)")
    max_pressure_change_per_min: float = Field(1.5, description="Max plausible pressure rate of change (hPa/min)")

    # Persistence / flatline detection window
    # Crucial lesson from M1-B audit: small windows (<4) produce false positives
    # on normal 2-decimal rounded pressure fluctuation.
    flatline_persistence_count: int = Field(5, ge=3, description="Consecutive identical readings required for flatline")

    # Timestamp tolerances
    timestamp_tolerance_seconds: float = Field(5.0, description="Allowed clock drift between observed_at and received_at")
    max_history_buffer: int = Field(20, ge=5, description="Maximum historical observations retained per station")


class QualityCheckDetail(BaseModel):
    """Result of a single deterministic quality check."""

    check_name: str
    status: Literal["VALID", "DEGRADED", "INVALID"]
    description: str
    parameter: Optional[str] = None
    observed_value: Optional[Any] = None
    threshold: Optional[Any] = None


class QualityResult(BaseModel):
    """Comprehensive quality evaluation for a single observation."""

    station_id: str
    observation_id: str
    status: Literal["VALID", "DEGRADED", "INVALID"]
    checks: List[QualityCheckDetail]
    evidence: List[Evidence]
    summary: str
    provenance: EvidenceProvenance


def _parse_iso(timestamp_str: str) -> datetime:
    """Parse ISO 8601 timestamp with timezone support."""
    dt = datetime.fromisoformat(timestamp_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class DataQualityChecker:
    """Deterministic data quality and physical validation engine."""

    def __init__(self, config: Optional[QualityConfig] = None) -> None:
        self.config = config or QualityConfig()
        self._history: Dict[str, Deque[Observation]] = {}

    def reset(self, station_id: Optional[str] = None) -> None:
        """Reset historical observation buffers."""
        if station_id:
            self._history.pop(station_id, None)
        else:
            self._history.clear()

    def check(self, observation: Observation) -> QualityResult:
        """Process an observation, update station history, and return QualityResult."""
        st_id = observation.station_id
        if st_id not in self._history:
            self._history[st_id] = deque(maxlen=self.config.max_history_buffer)

        history_snapshot = list(self._history[st_id])
        result = self.check_observation(observation, history=history_snapshot)

        # Store observation in history after evaluation (observations remain immutable)
        self._history[st_id].append(observation)
        return result

    def check_observation(
        self,
        obs: Observation,
        history: Optional[List[Observation]] = None,
    ) -> QualityResult:
        """Stateless evaluation of an observation against optional historical observations."""
        checks: List[QualityCheckDetail] = []
        evidence_list: List[Evidence] = []

        prev_obs: Optional[Observation] = history[-1] if history else None

        # 1. Timestamp Integrity
        self._check_timestamp(obs, checks, evidence_list)

        # 2. Sequence Progression
        self._check_sequence(obs, prev_obs, checks, evidence_list)

        # 3. Completeness / Missing Channels
        self._check_completeness(obs, checks)

        # 4. Physical Plausibility Limits
        self._check_physical_limits(obs, checks, evidence_list)

        # 5. Temporal Rate of Change
        if prev_obs is not None:
            self._check_rate_of_change(obs, prev_obs, checks, evidence_list)

        # 6. Flatline / Persistence
        if history:
            full_series = history + [obs]
            self._check_flatline(obs, full_series, checks, evidence_list)

        # 7. Basic Multivariate Consistency
        self._check_multivariate_consistency(obs, checks, evidence_list)

        # Determine overall composite status
        has_invalid = any(c.status == "INVALID" for c in checks)
        has_degraded = any(c.status == "DEGRADED" for c in checks)

        if has_invalid:
            composite_status: Literal["VALID", "DEGRADED", "INVALID"] = "INVALID"
            summary = f"Observation {obs.observation_id} failed deterministic physical/temporal checks."
        elif has_degraded:
            composite_status = "DEGRADED"
            summary = f"Observation {obs.observation_id} exhibited degraded quality or incomplete channels."
        else:
            composite_status = "VALID"
            summary = f"Observation {obs.observation_id} passed all deterministic quality checks."

        provenance = EvidenceProvenance(
            source_type="DETERMINISTIC_QC",
            source_id="quality-checker-v1",
            derived_from=[obs.observation_id],
        )

        return QualityResult(
            station_id=obs.station_id,
            observation_id=obs.observation_id,
            status=composite_status,
            checks=checks,
            evidence=evidence_list,
            summary=summary,
            provenance=provenance,
        )

    # -------------------------------------------------------------------------
    # Internal Deterministic Check Implementations
    # -------------------------------------------------------------------------

    def _check_timestamp(
        self,
        obs: Observation,
        checks: List[QualityCheckDetail],
        evidence_list: List[Evidence],
    ) -> None:
        try:
            obs_dt = _parse_iso(obs.observed_at)
            rec_dt = _parse_iso(obs.received_at)
        except Exception as err:
            checks.append(
                QualityCheckDetail(
                    check_name="timestamp_format",
                    status="INVALID",
                    description=f"Malformed ISO 8601 timestamp: {err}",
                    parameter="timestamps",
                )
            )
            evidence_list.append(
                Evidence(
                    evidence_id=f"ev-qc-{obs.observation_id}-ts-format",
                    subject=EvidenceSubject(station_id=obs.station_id, observation_ids=[obs.observation_id]),
                    type="TEMPORAL",
                    relation="SUPPORTS",
                    hypothesis="SENSOR",
                    description=f"Malformed timestamp format on {obs.observation_id}.",
                    strength=0.95,
                    quality=EvidenceQuality(status="INVALID", freshness="FRESH", completeness="COMPLETE"),
                    provenance=EvidenceProvenance(
                        source_type="DETERMINISTIC_QC",
                        source_id="quality-timestamp-v1",
                        derived_from=[obs.observation_id],
                    ),
                    independence_group="station-telemetry-timestamp",
                    status="AVAILABLE",
                )
            )
            return

        # Check observed_at <= received_at (with small tolerance for network clock drift)
        max_drift_delta = obs_dt.timestamp() - rec_dt.timestamp()
        if max_drift_delta > self.config.timestamp_tolerance_seconds:
            checks.append(
                QualityCheckDetail(
                    check_name="timestamp_ordering",
                    status="INVALID",
                    description=(
                        f"Timestamp inversion: observed_at ({obs.observed_at}) is "
                        f"{max_drift_delta:.1f}s after received_at ({obs.received_at})."
                    ),
                    parameter="timestamps",
                    observed_value=max_drift_delta,
                    threshold=self.config.timestamp_tolerance_seconds,
                )
            )
            evidence_list.append(
                Evidence(
                    evidence_id=f"ev-qc-{obs.observation_id}-ts-inversion",
                    subject=EvidenceSubject(station_id=obs.station_id, observation_ids=[obs.observation_id]),
                    type="TEMPORAL",
                    relation="SUPPORTS",
                    hypothesis="SENSOR",
                    description=(
                        f"Timestamp ordering violation: observed_at is ahead of received_at beyond allowed clock-skew tolerance."
                    ),
                    strength=0.90,
                    quality=EvidenceQuality(status="INVALID", freshness="FRESH", completeness="COMPLETE"),
                    provenance=EvidenceProvenance(
                        source_type="DETERMINISTIC_QC",
                        source_id="quality-timestamp-v1",
                        derived_from=[obs.observation_id],
                    ),
                    independence_group="station-telemetry-timestamp",
                    status="AVAILABLE",
                )
            )
        else:
            checks.append(
                QualityCheckDetail(
                    check_name="timestamp_ordering",
                    status="VALID",
                    description="Timestamp format and telemetry ordering within clock-skew tolerance verified.",
                    parameter="timestamps",
                )
            )

    def _check_sequence(
        self,
        obs: Observation,
        prev_obs: Optional[Observation],
        checks: List[QualityCheckDetail],
        evidence_list: List[Evidence],
    ) -> None:
        if obs.sequence is None:
            checks.append(
                QualityCheckDetail(
                    check_name="sequence_progression",
                    status="VALID",
                    description="Sequence number omitted (optional in canonical contract).",
                    parameter="sequence",
                )
            )
            return

        if prev_obs is not None and prev_obs.sequence is not None:
            if obs.sequence < prev_obs.sequence:
                checks.append(
                    QualityCheckDetail(
                        check_name="sequence_progression",
                        status="INVALID",
                        description=f"Sequence regression: sequence decreased from {prev_obs.sequence} to {obs.sequence}.",
                        parameter="sequence",
                        observed_value=obs.sequence,
                        threshold=prev_obs.sequence,
                    )
                )
                evidence_list.append(
                    Evidence(
                        evidence_id=f"ev-qc-{obs.observation_id}-seq-regression",
                        subject=EvidenceSubject(
                            station_id=obs.station_id,
                            observation_ids=[obs.observation_id, prev_obs.observation_id],
                        ),
                        type="TEMPORAL",
                        relation="SUPPORTS",
                        hypothesis="SENSOR",
                        description=f"Sequence counter regressed from {prev_obs.sequence} to {obs.sequence}.",
                        strength=0.85,
                        quality=EvidenceQuality(status="DEGRADED", freshness="FRESH", completeness="COMPLETE"),
                        provenance=EvidenceProvenance(
                            source_type="DETERMINISTIC_QC",
                            source_id="quality-sequence-v1",
                            derived_from=[obs.observation_id, prev_obs.observation_id],
                        ),
                        independence_group="station-telemetry-sequence",
                        status="AVAILABLE",
                    )
                )
            elif obs.sequence == prev_obs.sequence:
                checks.append(
                    QualityCheckDetail(
                        check_name="sequence_progression",
                        status="DEGRADED",
                        description=f"Duplicate sequence number: {obs.sequence} observed consecutively.",
                        parameter="sequence",
                        observed_value=obs.sequence,
                    )
                )
                evidence_list.append(
                    Evidence(
                        evidence_id=f"ev-qc-{obs.observation_id}-seq-duplicate",
                        subject=EvidenceSubject(
                            station_id=obs.station_id,
                            observation_ids=[obs.observation_id, prev_obs.observation_id],
                        ),
                        type="TEMPORAL",
                        relation="SUPPORTS",
                        hypothesis="SENSOR",
                        description=f"Duplicate sequence counter {obs.sequence} observed consecutively.",
                        strength=0.80,
                        quality=EvidenceQuality(status="DEGRADED", freshness="FRESH", completeness="COMPLETE"),
                        provenance=EvidenceProvenance(
                            source_type="DETERMINISTIC_QC",
                            source_id="quality-sequence-v1",
                            derived_from=[obs.observation_id, prev_obs.observation_id],
                        ),
                        independence_group="station-telemetry-sequence",
                        status="AVAILABLE",
                    )
                )
            else:
                checks.append(
                    QualityCheckDetail(
                        check_name="sequence_progression",
                        status="VALID",
                        description=f"Sequence progression verified ({prev_obs.sequence} -> {obs.sequence}).",
                        parameter="sequence",
                        observed_value=obs.sequence,
                    )
                )

    def _check_completeness(
        self,
        obs: Observation,
        checks: List[QualityCheckDetail],
    ) -> None:
        """Evaluate channel completeness.
        
        CRITICAL ARCHITECTURAL RULE:
        Missing data alone does NOT emit an Evidence supporting SENSOR.
        Communication drops and sensor malfunctions must not be conflated.
        """
        missing_channels: List[str] = []
        if obs.measurements.temperature_c is None:
            missing_channels.append("temperature_c")
        if obs.measurements.relative_humidity_pct is None:
            missing_channels.append("relative_humidity_pct")
        if obs.measurements.pressure_hpa is None:
            missing_channels.append("pressure_hpa")

        if len(missing_channels) == 3:
            checks.append(
                QualityCheckDetail(
                    check_name="completeness",
                    status="INVALID",
                    description="All measurement channels are null/missing.",
                    parameter="measurements",
                )
            )
        elif len(missing_channels) > 0:
            checks.append(
                QualityCheckDetail(
                    check_name="completeness",
                    status="DEGRADED",
                    description=f"Incomplete observation: missing channels [{', '.join(missing_channels)}].",
                    parameter="measurements",
                    observed_value=missing_channels,
                )
            )
        else:
            checks.append(
                QualityCheckDetail(
                    check_name="completeness",
                    status="VALID",
                    description="All canonical measurement channels present.",
                    parameter="measurements",
                )
            )

    def _check_physical_limits(
        self,
        obs: Observation,
        checks: List[QualityCheckDetail],
        evidence_list: List[Evidence],
    ) -> None:
        m = obs.measurements

        # Temperature
        if m.temperature_c is not None:
            if m.temperature_c < self.config.temp_min_c or m.temperature_c > self.config.temp_max_c:
                checks.append(
                    QualityCheckDetail(
                        check_name="physical_limit_temperature",
                        status="INVALID",
                        description=(
                            f"Temperature {m.temperature_c}°C outside physical limits "
                            f"[{self.config.temp_min_c}, {self.config.temp_max_c}]°C."
                        ),
                        parameter="temperature_c",
                        observed_value=m.temperature_c,
                        threshold=[self.config.temp_min_c, self.config.temp_max_c],
                    )
                )
                evidence_list.append(
                    Evidence(
                        evidence_id=f"ev-qc-{obs.observation_id}-range-temp",
                        subject=EvidenceSubject(station_id=obs.station_id, observation_ids=[obs.observation_id]),
                        type="PHYSICAL_LIMIT",
                        relation="SUPPORTS",
                        hypothesis="SENSOR",
                        description=(
                            f"Temperature {m.temperature_c}°C breached physical operating bounds "
                            f"[{self.config.temp_min_c}, {self.config.temp_max_c}]°C."
                        ),
                        strength=0.95,
                        quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                        provenance=EvidenceProvenance(
                            source_type="DETERMINISTIC_QC",
                            source_id="quality-range-v1",
                            derived_from=[obs.observation_id],
                        ),
                        independence_group="sensor-range-temperature",
                        status="AVAILABLE",
                    )
                )
            else:
                checks.append(
                    QualityCheckDetail(
                        check_name="physical_limit_temperature",
                        status="VALID",
                        description="Temperature within physical limits.",
                        parameter="temperature_c",
                        observed_value=m.temperature_c,
                    )
                )

        # Relative Humidity
        if m.relative_humidity_pct is not None:
            if m.relative_humidity_pct < self.config.humidity_min_pct or m.relative_humidity_pct > self.config.humidity_max_pct:
                checks.append(
                    QualityCheckDetail(
                        check_name="physical_limit_humidity",
                        status="INVALID",
                        description=(
                            f"Relative humidity {m.relative_humidity_pct}% outside physical bounds "
                            f"[{self.config.humidity_min_pct}, {self.config.humidity_max_pct}]%."
                        ),
                        parameter="relative_humidity_pct",
                        observed_value=m.relative_humidity_pct,
                        threshold=[self.config.humidity_min_pct, self.config.humidity_max_pct],
                    )
                )
                evidence_list.append(
                    Evidence(
                        evidence_id=f"ev-qc-{obs.observation_id}-range-humidity",
                        subject=EvidenceSubject(station_id=obs.station_id, observation_ids=[obs.observation_id]),
                        type="PHYSICAL_LIMIT",
                        relation="SUPPORTS",
                        hypothesis="SENSOR",
                        description=(
                            f"Humidity {m.relative_humidity_pct}% breached physical bounds "
                            f"[{self.config.humidity_min_pct}, {self.config.humidity_max_pct}]%."
                        ),
                        strength=0.95,
                        quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                        provenance=EvidenceProvenance(
                            source_type="DETERMINISTIC_QC",
                            source_id="quality-range-v1",
                            derived_from=[obs.observation_id],
                        ),
                        independence_group="sensor-range-humidity",
                        status="AVAILABLE",
                    )
                )
            else:
                checks.append(
                    QualityCheckDetail(
                        check_name="physical_limit_humidity",
                        status="VALID",
                        description="Relative humidity within physical limits.",
                        parameter="relative_humidity_pct",
                        observed_value=m.relative_humidity_pct,
                    )
                )

        # Pressure
        if m.pressure_hpa is not None:
            if m.pressure_hpa < self.config.pressure_min_hpa or m.pressure_hpa > self.config.pressure_max_hpa:
                checks.append(
                    QualityCheckDetail(
                        check_name="physical_limit_pressure",
                        status="INVALID",
                        description=(
                            f"Pressure {m.pressure_hpa} hPa outside physical bounds "
                            f"[{self.config.pressure_min_hpa}, {self.config.pressure_max_hpa}] hPa."
                        ),
                        parameter="pressure_hpa",
                        observed_value=m.pressure_hpa,
                        threshold=[self.config.pressure_min_hpa, self.config.pressure_max_hpa],
                    )
                )
                evidence_list.append(
                    Evidence(
                        evidence_id=f"ev-qc-{obs.observation_id}-range-pressure",
                        subject=EvidenceSubject(station_id=obs.station_id, observation_ids=[obs.observation_id]),
                        type="PHYSICAL_LIMIT",
                        relation="SUPPORTS",
                        hypothesis="SENSOR",
                        description=(
                            f"Barometric pressure {m.pressure_hpa} hPa breached physical bounds "
                            f"[{self.config.pressure_min_hpa}, {self.config.pressure_max_hpa}] hPa."
                        ),
                        strength=0.95,
                        quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                        provenance=EvidenceProvenance(
                            source_type="DETERMINISTIC_QC",
                            source_id="quality-range-v1",
                            derived_from=[obs.observation_id],
                        ),
                        independence_group="sensor-range-pressure",
                        status="AVAILABLE",
                    )
                )
            else:
                checks.append(
                    QualityCheckDetail(
                        check_name="physical_limit_pressure",
                        status="VALID",
                        description="Pressure within physical limits.",
                        parameter="pressure_hpa",
                        observed_value=m.pressure_hpa,
                    )
                )

    def _check_rate_of_change(
        self,
        obs: Observation,
        prev_obs: Observation,
        checks: List[QualityCheckDetail],
        evidence_list: List[Evidence],
    ) -> None:
        try:
            curr_dt = _parse_iso(obs.observed_at)
            prev_dt = _parse_iso(prev_obs.observed_at)
            delta_seconds = (curr_dt - prev_dt).total_seconds()
        except Exception:
            return

        if delta_seconds <= 0 or delta_seconds > 3600.0:
            # Skip rate-of-change if delta_t is non-positive or observations are over an hour apart
            return

        delta_minutes = delta_seconds / 60.0

        # Temperature rate of change
        if obs.measurements.temperature_c is not None and prev_obs.measurements.temperature_c is not None:
            delta_t = abs(obs.measurements.temperature_c - prev_obs.measurements.temperature_c)
            rate_t = delta_t / delta_minutes
            if rate_t > self.config.max_temp_change_per_min:
                checks.append(
                    QualityCheckDetail(
                        check_name="rate_of_change_temperature",
                        status="DEGRADED",
                        description=(
                            f"Temperature changed by {delta_t:.2f}°C over {delta_minutes:.1f} min "
                            f"({rate_t:.2f}°C/min), exceeding threshold ({self.config.max_temp_change_per_min:.2f}°C/min)."
                        ),
                        parameter="temperature_c",
                        observed_value=rate_t,
                        threshold=self.config.max_temp_change_per_min,
                    )
                )
                evidence_list.append(
                    Evidence(
                        evidence_id=f"ev-qc-{obs.observation_id}-temporal-temp",
                        subject=EvidenceSubject(
                            station_id=obs.station_id,
                            observation_ids=[obs.observation_id, prev_obs.observation_id],
                        ),
                        type="TEMPORAL",
                        relation="SUPPORTS",
                        hypothesis="SENSOR",
                        description=(
                            f"Temperature rate of change ({rate_t:.2f}°C/min) exceeded configured threshold "
                            f"({self.config.max_temp_change_per_min:.2f}°C/min)."
                        ),
                        strength=0.85,
                        quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                        provenance=EvidenceProvenance(
                            source_type="DETERMINISTIC_QC",
                            source_id="quality-temporal-v1",
                            derived_from=[obs.observation_id, prev_obs.observation_id],
                        ),
                        independence_group="station-temporal-temperature",
                        status="AVAILABLE",
                    )
                )
            else:
                checks.append(
                    QualityCheckDetail(
                        check_name="rate_of_change_temperature",
                        status="VALID",
                        description="Temperature rate of change within nominal limits.",
                        parameter="temperature_c",
                        observed_value=rate_t,
                    )
                )

        # Humidity rate of change
        if obs.measurements.relative_humidity_pct is not None and prev_obs.measurements.relative_humidity_pct is not None:
            delta_h = abs(obs.measurements.relative_humidity_pct - prev_obs.measurements.relative_humidity_pct)
            rate_h = delta_h / delta_minutes
            if rate_h > self.config.max_humidity_change_per_min:
                checks.append(
                    QualityCheckDetail(
                        check_name="rate_of_change_humidity",
                        status="DEGRADED",
                        description=(
                            f"Humidity changed by {delta_h:.2f}% over {delta_minutes:.1f} min "
                            f"({rate_h:.2f}%/min), exceeding threshold ({self.config.max_humidity_change_per_min:.2f}%/min)."
                        ),
                        parameter="relative_humidity_pct",
                        observed_value=rate_h,
                        threshold=self.config.max_humidity_change_per_min,
                    )
                )
                evidence_list.append(
                    Evidence(
                        evidence_id=f"ev-qc-{obs.observation_id}-temporal-humidity",
                        subject=EvidenceSubject(
                            station_id=obs.station_id,
                            observation_ids=[obs.observation_id, prev_obs.observation_id],
                        ),
                        type="TEMPORAL",
                        relation="SUPPORTS",
                        hypothesis="SENSOR",
                        description=(
                            f"Relative humidity rate of change ({rate_h:.2f}%/min) exceeded configured threshold."
                        ),
                        strength=0.80,
                        quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                        provenance=EvidenceProvenance(
                            source_type="DETERMINISTIC_QC",
                            source_id="quality-temporal-v1",
                            derived_from=[obs.observation_id, prev_obs.observation_id],
                        ),
                        independence_group="station-temporal-humidity",
                        status="AVAILABLE",
                    )
                )
            else:
                checks.append(
                    QualityCheckDetail(
                        check_name="rate_of_change_humidity",
                        status="VALID",
                        description="Humidity rate of change within nominal limits.",
                        parameter="relative_humidity_pct",
                        observed_value=rate_h,
                    )
                )

        # Pressure rate of change
        if obs.measurements.pressure_hpa is not None and prev_obs.measurements.pressure_hpa is not None:
            delta_p = abs(obs.measurements.pressure_hpa - prev_obs.measurements.pressure_hpa)
            rate_p = delta_p / delta_minutes
            if rate_p > self.config.max_pressure_change_per_min:
                checks.append(
                    QualityCheckDetail(
                        check_name="rate_of_change_pressure",
                        status="DEGRADED",
                        description=(
                            f"Pressure changed by {delta_p:.2f} hPa over {delta_minutes:.1f} min "
                            f"({rate_p:.2f} hPa/min), exceeding threshold ({self.config.max_pressure_change_per_min:.2f} hPa/min)."
                        ),
                        parameter="pressure_hpa",
                        observed_value=rate_p,
                        threshold=self.config.max_pressure_change_per_min,
                    )
                )
                evidence_list.append(
                    Evidence(
                        evidence_id=f"ev-qc-{obs.observation_id}-temporal-pressure",
                        subject=EvidenceSubject(
                            station_id=obs.station_id,
                            observation_ids=[obs.observation_id, prev_obs.observation_id],
                        ),
                        type="TEMPORAL",
                        relation="SUPPORTS",
                        hypothesis="SENSOR",
                        description=(
                            f"Pressure rate of change ({rate_p:.2f} hPa/min) exceeded configured threshold."
                        ),
                        strength=0.85,
                        quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                        provenance=EvidenceProvenance(
                            source_type="DETERMINISTIC_QC",
                            source_id="quality-temporal-v1",
                            derived_from=[obs.observation_id, prev_obs.observation_id],
                        ),
                        independence_group="station-temporal-pressure",
                        status="AVAILABLE",
                    )
                )
            else:
                checks.append(
                    QualityCheckDetail(
                        check_name="rate_of_change_pressure",
                        status="VALID",
                        description="Pressure rate of change within nominal limits.",
                        parameter="pressure_hpa",
                        observed_value=rate_p,
                    )
                )

    def _check_flatline(
        self,
        obs: Observation,
        full_series: List[Observation],
        checks: List[QualityCheckDetail],
        evidence_list: List[Evidence],
    ) -> None:
        """Check for sustained flatlined / frozen sensor readings across observations.
        
        Requires flatline_persistence_count (default 5) consecutive identical readings.
        Short sequences of 2 or 3 identical readings are considered normal stochastic discretization.
        """
        k = self.config.flatline_persistence_count
        if len(full_series) < k:
            return

        window = full_series[-k:]

        for param in ["temperature_c", "relative_humidity_pct", "pressure_hpa"]:
            vals = [getattr(o.measurements, param) for o in window]
            # Only evaluate if all values in window are present
            if any(v is None for v in vals):
                continue

            first_val = vals[0]
            if all(v == first_val for v in vals):
                param_clean = param.replace("_c", "").replace("_pct", "").replace("_hpa", "")
                checks.append(
                    QualityCheckDetail(
                        check_name=f"flatline_{param_clean}",
                        status="DEGRADED",
                        description=f"{param_clean} value {first_val} sustained identical across {k} consecutive observations.",
                        parameter=param,
                        observed_value=first_val,
                        threshold=k,
                    )
                )
                evidence_list.append(
                    Evidence(
                        evidence_id=f"ev-qc-{obs.observation_id}-flatline-{param_clean}",
                        subject=EvidenceSubject(
                            station_id=obs.station_id,
                            observation_ids=[o.observation_id for o in window],
                        ),
                        type="TEMPORAL",
                        relation="SUPPORTS",
                        hypothesis="SENSOR",
                        description=(
                            f"Sustained flatline: {param_clean} remained frozen at {first_val} across {k} consecutive observations."
                        ),
                        strength=0.90,
                        quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                        provenance=EvidenceProvenance(
                            source_type="DETERMINISTIC_QC",
                            source_id="quality-flatline-v1",
                            derived_from=[o.observation_id for o in window],
                        ),
                        independence_group=f"station-persistence-{param_clean}",
                        status="AVAILABLE",
                    )
                )

    def _check_multivariate_consistency(
        self,
        obs: Observation,
        checks: List[QualityCheckDetail],
        evidence_list: List[Evidence],
    ) -> None:
        """Conservative multivariate plausibility screening.
        
        Performs basic sanity screening on joint parameter combinations without
        claiming to universally prove that a meteorological state is impossible.
        Produces candidate evidence only and never diagnoses sensor failure
        or assigns a final operational state.
        """
        m = obs.measurements
        if m.temperature_c is not None and m.relative_humidity_pct is not None:
            # Conservative joint thermodynamic plausibility screening:
            # Extreme surface heating combined with near-saturation (T > 50°C and RH > 95%)
            # represents a highly atypical joint condition that warrants candidate evidence.
            if m.temperature_c > 50.0 and m.relative_humidity_pct > 95.0:
                checks.append(
                    QualityCheckDetail(
                        check_name="multivariate_heat_humidity",
                        status="INVALID",
                        description=(
                            f"Conservative multivariate screening flagged atypical joint condition: "
                            f"Temperature {m.temperature_c}°C with Relative Humidity {m.relative_humidity_pct}%."
                        ),
                        parameter="multivariate",
                        observed_value=[m.temperature_c, m.relative_humidity_pct],
                    )
                )
                evidence_list.append(
                    Evidence(
                        evidence_id=f"ev-qc-{obs.observation_id}-multi-thermo",
                        subject=EvidenceSubject(station_id=obs.station_id, observation_ids=[obs.observation_id]),
                        type="MULTIVARIATE",
                        relation="SUPPORTS",
                        hypothesis="SENSOR",
                        description=(
                            "Conservative multivariate screening: Highly atypical joint thermodynamic condition "
                            f"(Temperature {m.temperature_c}°C and RH {m.relative_humidity_pct}%). "
                            "Candidate evidence supporting SENSOR hypothesis for further multi-station corroboration."
                        ),
                        strength=0.85,
                        quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                        provenance=EvidenceProvenance(
                            source_type="DETERMINISTIC_QC",
                            source_id="quality-multivariate-v1",
                            derived_from=[obs.observation_id],
                        ),
                        independence_group="station-multivariate-thermodynamic",
                        status="AVAILABLE",
                    )
                )
            else:
                checks.append(
                    QualityCheckDetail(
                        check_name="multivariate_consistency",
                        status="VALID",
                        description="Conservative multivariate plausibility screening nominal.",
                        parameter="multivariate",
                    )
                )
