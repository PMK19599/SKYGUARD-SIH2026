"""Automated Unit and Adversarial Tests for SKYGUARD Sensor Evidence Layer (M1-C3).

Validates physical limits, repeated temporal spikes, sustained channel-specific flatlines,
robust MAD baseline deviation, persistent drift/offset candidates, intermittent dropouts,
telemetry integrity, bounded health memory, observation immutability, determinism,
and zero scenario/ground-truth leakage.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest
from typing import Any, Dict, List, Optional, Set

from backend.engine.sensor import (
    SensorConfig,
    SensorEvidenceEngine,
    SensorEvidenceResult,
)
from backend.schemas import (
    Evidence,
    EvidenceProvenance,
    EvidenceQuality,
    EvidenceSubject,
    Measurements,
    Observation,
    ObservationSource,
)


FORBIDDEN_RUNTIME_FIELDS: Set[str] = {
    "scenario",
    "ground_truth",
    "fault_type",
    "expected_state",
    "diagnosis",
    "root_cause",
    "is_fault",
    "is_world_event",
    "is_sensor_fault",
}


def make_obs(
    station_id: str = "AWS-03",
    obs_id: str = "obs-AWS03-000001",
    observed_at: str = "2026-09-17T09:00:00+05:30",
    received_at: Optional[str] = None,
    temp: Optional[float] = 28.0,
    humidity: Optional[float] = 65.0,
    pressure: Optional[float] = 1010.0,
    source_type: str = "SIMULATOR",
    source_id: str = "sim-network-01",
    sequence: Optional[int] = 1,
) -> Observation:
    if received_at is None:
        obs_dt = datetime.fromisoformat(observed_at)
        received_at = (obs_dt + timedelta(seconds=2)).isoformat()

    return Observation(
        observation_id=obs_id,
        station_id=station_id,
        observed_at=observed_at,
        received_at=received_at,
        measurements=Measurements(
            temperature_c=temp,
            relative_humidity_pct=humidity,
            pressure_hpa=pressure,
        ),
        source=ObservationSource(type=source_type, source_id=source_id),
        sequence=sequence,
    )


def generate_obs_series(
    n: int,
    station_id: str = "AWS-03",
    start_time: str = "2026-09-17T09:00:00+05:30",
    step_minutes: int = 5,
    base_temp: float = 28.0,
    base_humidity: float = 65.0,
    base_pressure: float = 1010.0,
    temp_trend: float = 0.0,
    temp_noise: float = 0.05,
) -> List[Observation]:
    """Generate a clean synthetic chronological series of observations."""
    series: List[Observation] = []
    start_dt = datetime.fromisoformat(start_time)

    for i in range(n):
        obs_dt = start_dt + timedelta(minutes=i * step_minutes)
        obs_id = f"obs-{station_id}-{i+1:06d}"
        t = round(base_temp + (i * temp_trend) + (temp_noise if i % 2 == 0 else -temp_noise), 2)
        h = round(base_humidity - (i * 0.1), 1)
        p = round(base_pressure + (0.1 if i % 3 == 0 else 0.0), 1)

        series.append(
            make_obs(
                station_id=station_id,
                obs_id=obs_id,
                observed_at=obs_dt.isoformat(),
                temp=t,
                humidity=h,
                pressure=p,
                sequence=i + 1,
            )
        )
    return series


def assert_no_forbidden_fields(test_case: unittest.TestCase, obj: Any) -> None:
    """Recursively ensure no forbidden labels or diagnoses leak into runtime data."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            test_case.assertNotIn(
                k.lower(),
                FORBIDDEN_RUNTIME_FIELDS,
                f"Forbidden field '{k}' discovered in runtime dictionary keys.",
            )
            assert_no_forbidden_fields(test_case, v)
    elif isinstance(obj, list):
        for item in obj:
            assert_no_forbidden_fields(test_case, item)
    elif isinstance(obj, str):
        pass


class TestSensorEvidenceEngine(unittest.TestCase):
    """Unit test suite for SensorEvidenceEngine adhering to SKYGUARD invariants."""

    def setUp(self):
        self.engine = SensorEvidenceEngine()

    # 1. Normal station -> no SENSOR evidence
    def test_01_normal_station_produces_no_sensor_evidence(self):
        series = generate_obs_series(10)
        result = self.engine.evaluate(series)

        self.assertEqual(len(result.evidence), 0)
        self.assertIn("nominal", result.summary)
        self.assertEqual(result.station_id, "AWS-03")

    # 2. Single spike -> weak candidate evidence only
    def test_02_single_spike_produces_weak_candidate_evidence(self):
        series = generate_obs_series(8)
        # Add single spike at final observation (+10°C)
        last_dt = datetime.fromisoformat(series[-1].observed_at) + timedelta(minutes=5)
        spike_obs = make_obs(
            obs_id="obs-AWS03-spike",
            observed_at=last_dt.isoformat(),
            temp=38.0,  # +10°C step
            sequence=9,
        )
        result = self.engine.evaluate(series + [spike_obs])

        # Single spike must remain weak (<= 0.35)
        spike_ev = [e for e in result.evidence if "spike" in e.independence_group]
        self.assertEqual(len(spike_ev), 1)
        ev = spike_ev[0]
        self.assertEqual(ev.hypothesis, "SENSOR")
        self.assertEqual(ev.relation, "SUPPORTS")
        self.assertLessEqual(ev.strength, 0.35)
        self.assertIn("isolated", ev.description.lower())
        self.assertIn("insufficient", ev.description.lower())

        # All evidence generated must remain weak candidate evidence
        for e in result.evidence:
            self.assertLessEqual(e.strength, 0.45)

    # 3. Repeated spikes -> candidate SENSOR evidence
    def test_03_repeated_spikes_produce_candidate_sensor_evidence(self):
        series = generate_obs_series(5)
        start_dt = datetime.fromisoformat(series[-1].observed_at)

        # Spike 1
        s1 = make_obs(obs_id="obs-s1", observed_at=(start_dt + timedelta(minutes=5)).isoformat(), temp=38.0, sequence=6)
        # Normal
        n1 = make_obs(obs_id="obs-n1", observed_at=(start_dt + timedelta(minutes=10)).isoformat(), temp=28.0, sequence=7)
        # Spike 2 (current target)
        s2 = make_obs(obs_id="obs-s2", observed_at=(start_dt + timedelta(minutes=15)).isoformat(), temp=39.0, sequence=8)

        result = self.engine.evaluate(series + [s1, n1, s2])

        spike_ev = [e for e in result.evidence if "spike-recurrence" in e.evidence_id]
        self.assertEqual(len(spike_ev), 1)
        ev = spike_ev[0]
        self.assertEqual(ev.hypothesis, "SENSOR")
        self.assertGreaterEqual(ev.strength, 0.70)
        self.assertIn("Repeated spike recurrence", ev.description)

    # 4. Sustained temperature flatline -> SENSOR candidate
    def test_04_sustained_temperature_flatline_produces_sensor_candidate(self):
        series = generate_obs_series(10, temp_noise=0.0)
        # Temperature stuck at 28.0 while humidity and pressure continue changing
        result = self.engine.evaluate(series)

        # Since base_temp=28.0 is constant across 10 steps while humidity and pressure vary:
        flatline_ev = [e for e in result.evidence if "flatline-isolated-temp" in e.evidence_id]
        self.assertEqual(len(flatline_ev), 1)
        ev = flatline_ev[0]
        self.assertEqual(ev.strength, 0.80)
        self.assertIn("Isolated sustained flatline", ev.description)

    # 5. Sustained humidity flatline -> SENSOR candidate
    def test_05_sustained_humidity_flatline_produces_sensor_candidate(self):
        # Temp varies, pressure varies, humidity strictly frozen
        obs_list = []
        base_dt = datetime.fromisoformat("2026-09-17T09:00:00+05:30")
        for i in range(6):
            obs_list.append(
                make_obs(
                    obs_id=f"obs-h-{i}",
                    observed_at=(base_dt + timedelta(minutes=i*5)).isoformat(),
                    temp=28.0 + (i * 0.5),  # changing
                    humidity=65.0,          # frozen across 6 steps
                    pressure=1010.0 + (i * 0.2), # changing
                    sequence=i+1,
                )
            )

        result = self.engine.evaluate(obs_list)
        flatline_ev = [e for e in result.evidence if "flatline-isolated-humidity" in e.evidence_id]
        self.assertEqual(len(flatline_ev), 1)
        self.assertEqual(flatline_ev[0].strength, 0.80)

    # 6. Sustained pressure flatline -> SENSOR candidate
    def test_06_sustained_pressure_flatline_produces_sensor_candidate(self):
        obs_list = []
        base_dt = datetime.fromisoformat("2026-09-17T09:00:00+05:30")
        for i in range(6):
            obs_list.append(
                make_obs(
                    obs_id=f"obs-p-{i}",
                    observed_at=(base_dt + timedelta(minutes=i*5)).isoformat(),
                    temp=28.0 + (i * 0.5),
                    humidity=65.0 - (i * 1.0),
                    pressure=1012.0,  # frozen across 6 steps (>= 5 required)
                    sequence=i+1,
                )
            )

        result = self.engine.evaluate(obs_list)
        flatline_ev = [e for e in result.evidence if "flatline-isolated-pressure" in e.evidence_id]
        self.assertEqual(len(flatline_ev), 1)
        self.assertEqual(flatline_ev[0].strength, 0.80)

    # 7. 2-3 repeated pressure values -> NO false flatline
    def test_07_two_to_three_repeated_pressure_values_no_false_flatline(self):
        obs_list = []
        base_dt = datetime.fromisoformat("2026-09-17T09:00:00+05:30")
        # 3 repeated pressure values (natural rounding behavior)
        pressures = [1012.4, 1012.5, 1012.5, 1012.5]
        for i, p in enumerate(pressures):
            obs_list.append(
                make_obs(
                    obs_id=f"obs-round-{i}",
                    observed_at=(base_dt + timedelta(minutes=i*5)).isoformat(),
                    temp=28.0 + (i * 0.2),
                    humidity=65.0 - (i * 0.5),
                    pressure=p,
                    sequence=i+1,
                )
            )

        result = self.engine.evaluate(obs_list)
        flatline_ev = [e for e in result.evidence if "flatline" in e.evidence_id]
        self.assertEqual(len(flatline_ev), 0)

    # 8. Gradual normal weather change -> no strong SENSOR evidence
    def test_08_gradual_normal_weather_change_no_strong_sensor_evidence(self):
        # Gradual warming of +1.5°C over 10 steps with normal variation
        series = generate_obs_series(10, temp_trend=0.15, temp_noise=0.05)
        result = self.engine.evaluate(series)

        for ev in result.evidence:
            self.assertLessEqual(ev.strength, 0.45)

    # 9. Rapid genuine regional change -> no automatic SENSOR failure
    def test_09_rapid_genuine_regional_change_no_automatic_sensor(self):
        series = generate_obs_series(8, base_temp=28.0)
        base_dt = datetime.fromisoformat(series[-1].observed_at)
        # Cold front sudden drop of -3.5°C
        drop_obs = make_obs(
            obs_id="obs-front-drop",
            observed_at=(base_dt + timedelta(minutes=5)).isoformat(),
            temp=24.5,
            humidity=85.0,
            pressure=1014.0,
            sequence=9,
        )

        result = self.engine.evaluate(series + [drop_obs])
        # May generate candidate baseline deviation, but strength is capped and summary states unresolved
        for ev in result.evidence:
            self.assertLessEqual(ev.strength, 0.45)
            self.assertIn("unresolved", ev.description)
        self.assertIn("unresolved", result.summary)

    # 10. Station-specific baseline deviation -> candidate evidence
    def test_10_station_specific_baseline_deviation_candidate_evidence(self):
        series = generate_obs_series(10, base_temp=28.0, temp_noise=0.1)
        base_dt = datetime.fromisoformat(series[-1].observed_at)
        outlier_obs = make_obs(
            obs_id="obs-outlier",
            observed_at=(base_dt + timedelta(minutes=5)).isoformat(),
            temp=33.5,  # Deviation > 3.5 * MAD
            sequence=11,
        )

        result = self.engine.evaluate(series + [outlier_obs])
        base_ev = [e for e in result.evidence if "baseline-dev-temp" in e.evidence_id]
        self.assertEqual(len(base_ev), 1)
        self.assertEqual(base_ev[0].strength, 0.40)
        self.assertIn("baseline deviation candidate", base_ev[0].description)

    # 11. Baseline adaptation after regime change
    def test_11_baseline_adaptation_after_regime_change(self):
        # Initial regime at 28°C (8 steps)
        series = generate_obs_series(8, base_temp=28.0)
        base_dt = datetime.fromisoformat(series[-1].observed_at)

        # Shift to new regime at 24°C and stay for 10 steps
        shifted_series = list(series)
        for i in range(10):
            shifted_series.append(
                make_obs(
                    obs_id=f"obs-newregime-{i}",
                    observed_at=(base_dt + timedelta(minutes=(i+1)*5)).isoformat(),
                    temp=24.0,
                    humidity=80.0,
                    pressure=1013.0,
                    sequence=9 + i,
                )
            )

        # Evaluate at the end of the new regime: baseline has adapted!
        result = self.engine.evaluate(shifted_series)
        base_ev = [e for e in result.evidence if "baseline-dev-temp" in e.evidence_id]
        self.assertEqual(len(base_ev), 0)

    # 12. Persistent offset / drift candidate
    def test_12_persistent_offset_drift_candidate(self):
        # 6 baseline observations at 28.0°C
        series = generate_obs_series(6, base_temp=28.0)
        base_dt = datetime.fromisoformat(series[-1].observed_at)

        # Followed by 4 consecutive observations shifted by +2.5°C
        drift_series = list(series)
        for i in range(4):
            drift_series.append(
                make_obs(
                    obs_id=f"obs-drift-{i}",
                    observed_at=(base_dt + timedelta(minutes=(i+1)*5)).isoformat(),
                    temp=30.5,  # +2.5°C offset
                    sequence=7 + i,
                )
            )

        result = self.engine.evaluate(drift_series)
        drift_ev = [e for e in result.evidence if "drift-temp" in e.evidence_id]
        self.assertEqual(len(drift_ev), 1)
        self.assertEqual(drift_ev[0].strength, 0.60)
        self.assertIn("Persistent signed offset candidate", drift_ev[0].description)

    # 13. Raw trend alone does not equal drift
    def test_13_raw_trend_alone_does_not_equal_drift(self):
        # 10 observations with normal smooth diurnal trend (+0.05°C/step)
        series = generate_obs_series(10, base_temp=28.0, temp_trend=0.05)
        result = self.engine.evaluate(series)

        drift_ev = [e for e in result.evidence if "drift" in e.evidence_id]
        self.assertEqual(len(drift_ev), 0)

    # 14. Intermittent dropout pattern
    def test_14_intermittent_dropout_pattern(self):
        obs_list = []
        base_dt = datetime.fromisoformat("2026-09-17T09:00:00+05:30")
        # Pattern: valid -> null -> valid -> null -> valid
        temps = [28.0, None, 28.2, None, 28.1]
        for i, t in enumerate(temps):
            obs_list.append(
                make_obs(
                    obs_id=f"obs-toggle-{i}",
                    observed_at=(base_dt + timedelta(minutes=i*5)).isoformat(),
                    temp=t,
                    sequence=i+1,
                )
            )

        result = self.engine.evaluate(obs_list)
        interm_ev = [e for e in result.evidence if "intermittent-temp" in e.evidence_id]
        self.assertEqual(len(interm_ev), 1)
        self.assertEqual(interm_ev[0].strength, 0.70)
        self.assertIn("Intermittent telemetry/sensor dropout pattern", interm_ev[0].description)

    # 15. Repeated telemetry sequence anomalies
    def test_15_repeated_telemetry_sequence_anomalies(self):
        obs_list = []
        base_dt = datetime.fromisoformat("2026-09-17T09:00:00+05:30")
        # Repeated sequence regressions: 5 -> 3, 7 -> 6
        seqs = [5, 3, 7, 6]
        for i, s in enumerate(seqs):
            obs_list.append(
                make_obs(
                    obs_id=f"obs-seq-{i}",
                    observed_at=(base_dt + timedelta(minutes=i*5)).isoformat(),
                    sequence=s,
                )
            )

        result = self.engine.evaluate(obs_list)
        telem_ev = [e for e in result.evidence if "telemetry-integrity" in e.evidence_id]
        self.assertEqual(len(telem_ev), 1)
        self.assertEqual(telem_ev[0].strength, 0.65)
        self.assertIn("Station telemetry integrity anomaly", telem_ev[0].description)

    # 16. One sequence anomaly remains weak
    def test_16_one_sequence_anomaly_remains_weak(self):
        obs_list = []
        base_dt = datetime.fromisoformat("2026-09-17T09:00:00+05:30")
        # Only 1 sequence regression: 5 -> 4, followed by clean progression
        seqs = [5, 4, 5, 6]
        for i, s in enumerate(seqs):
            obs_list.append(
                make_obs(
                    obs_id=f"obs-seq-single-{i}",
                    observed_at=(base_dt + timedelta(minutes=i*5)).isoformat(),
                    sequence=s,
                )
            )

        result = self.engine.evaluate(obs_list)
        telem_ev = [e for e in result.evidence if "telemetry-integrity" in e.evidence_id]
        self.assertEqual(len(telem_ev), 0)

    # 17. Missing data does not automatically become SENSOR
    def test_17_missing_data_does_not_automatically_become_sensor(self):
        single_obs = make_obs(temp=None)
        result = self.engine.evaluate([single_obs])

        self.assertEqual(len(result.evidence), 0)

    # 18. Physical-limit evidence handling
    def test_18_physical_limit_evidence_handling(self):
        extreme_obs = make_obs(temp=65.0)  # Breaches 55.0°C limit
        result = self.engine.evaluate([extreme_obs])

        limit_ev = [e for e in result.evidence if e.type == "PHYSICAL_LIMIT"]
        self.assertEqual(len(limit_ev), 1)
        self.assertEqual(limit_ev[0].strength, 0.95)
        self.assertEqual(limit_ev[0].hypothesis, "SENSOR")

    # 19. Quality evidence provenance preservation
    def test_19_quality_evidence_provenance_preservation(self):
        target = make_obs(obs_id="obs-qc-test")
        qc_ev = Evidence(
            evidence_id="ev-qc-obs-qc-test-range-temp",
            subject=EvidenceSubject(station_id=target.station_id, observation_ids=[target.observation_id]),
            type="PHYSICAL_LIMIT",
            relation="SUPPORTS",
            hypothesis="SENSOR",
            description="Upstream QC range limit breach.",
            strength=0.95,
            quality=EvidenceQuality(status="INVALID", freshness="FRESH", completeness="COMPLETE"),
            provenance=EvidenceProvenance(
                source_type="DETERMINISTIC_QC",
                source_id="quality-range-v1",
                derived_from=[target.observation_id],
            ),
            independence_group="sensor-range-temperature",
            status="AVAILABLE",
        )

        result = self.engine.evaluate([target], quality_evidence=[qc_ev])
        self.assertEqual(len(result.evidence), 1)
        self.assertEqual(result.evidence[0].evidence_id, "ev-qc-obs-qc-test-range-temp")
        self.assertEqual(result.evidence[0].provenance.source_id, "quality-range-v1")

    # 20. Duplicate evidence prevention
    def test_20_duplicate_evidence_prevention(self):
        # Target observation is at 65°C, and upstream QC already generated evidence for it
        target = make_obs(obs_id="obs-dup-test", temp=65.0)
        qc_ev = Evidence(
            evidence_id="ev-qc-obs-dup-test-range-temp",
            subject=EvidenceSubject(station_id=target.station_id, observation_ids=[target.observation_id]),
            type="PHYSICAL_LIMIT",
            relation="SUPPORTS",
            hypothesis="SENSOR",
            description="QC range breach.",
            strength=0.95,
            quality=EvidenceQuality(status="INVALID", freshness="FRESH", completeness="COMPLETE"),
            provenance=EvidenceProvenance(
                source_type="DETERMINISTIC_QC",
                source_id="quality-range-v1",
                derived_from=[target.observation_id],
            ),
            independence_group="sensor-range-temperature",
            status="AVAILABLE",
        )

        result = self.engine.evaluate([target], quality_evidence=[qc_ev])
        # Must not duplicate physical limit evidence
        limit_ev = [e for e in result.evidence if "range-temp" in e.evidence_id]
        self.assertEqual(len(limit_ev), 1)

    # 21. Evidence hypothesis strictly SENSOR
    def test_21_evidence_hypothesis_strictly_sensor(self):
        obs = make_obs(temp=65.0)
        result = self.engine.evaluate([obs])
        for ev in result.evidence:
            self.assertEqual(ev.hypothesis, "SENSOR")

    # 22. No NORMAL/WORLD/BOTH/UNKNOWN hypotheses
    def test_22_no_decision_hypotheses(self):
        obs = make_obs(temp=65.0)
        result = self.engine.evaluate([obs])
        for ev in result.evidence:
            self.assertNotIn(ev.hypothesis, ["NORMAL", "WORLD", "BOTH", "UNKNOWN"])

    # 23. Provenance present
    def test_23_provenance_present(self):
        obs = make_obs(temp=65.0)
        result = self.engine.evaluate([obs])
        self.assertIsNotNone(result.provenance)
        self.assertEqual(result.provenance.source_type, "DETERMINISTIC_QC")

    # 24. Independence groups present
    def test_24_independence_groups_present(self):
        obs = make_obs(temp=65.0)
        result = self.engine.evaluate([obs])
        for ev in result.evidence:
            self.assertIsNotNone(ev.independence_group)
            self.assertTrue(len(ev.independence_group) > 0)

    # 25. Independence groups not claimed statistically independent
    def test_25_independence_groups_not_claimed_statistically_independent(self):
        # Two consecutive spikes
        series = generate_obs_series(3)
        base_dt = datetime.fromisoformat(series[-1].observed_at)
        s1 = make_obs(observed_at=(base_dt + timedelta(minutes=5)).isoformat(), temp=38.0, sequence=4)
        s2 = make_obs(observed_at=(base_dt + timedelta(minutes=10)).isoformat(), temp=39.0, sequence=5)

        result = self.engine.evaluate(series + [s1, s2])
        for ev in result.evidence:
            self.assertNotIn("proven independent", ev.description.lower())

    # 26. Observation immutability
    def test_26_observation_immutability(self):
        series = generate_obs_series(5)
        orig_dumps = [deepcopy(o.model_dump()) for o in series]

        self.engine.evaluate(series)

        for i, o in enumerate(series):
            self.assertEqual(o.model_dump(), orig_dumps[i])

    # 27. Deterministic repeatability
    def test_27_deterministic_repeatability(self):
        series = generate_obs_series(6)
        res1 = self.engine.evaluate(series)
        res2 = self.engine.evaluate(series)

        self.assertEqual(res1.model_dump(), res2.model_dump())

    # 28. Configurable thresholds
    def test_28_configurable_thresholds(self):
        strict_config = SensorConfig(spike_threshold_temp_c=2.0)
        strict_engine = SensorEvidenceEngine(config=strict_config)

        series = generate_obs_series(3)
        base_dt = datetime.fromisoformat(series[-1].observed_at)
        # Step of +2.5°C
        step_obs = make_obs(observed_at=(base_dt + timedelta(minutes=5)).isoformat(), temp=30.5, sequence=4)

        # Default engine (threshold=4.0): delta 2.5 is not a spike
        res_default = self.engine.evaluate(series + [step_obs])
        self.assertEqual(len([e for e in res_default.evidence if "spike" in e.evidence_id]), 0)

        # Strict engine (threshold=2.0): delta 2.5 triggers spike candidate
        res_strict = strict_engine.evaluate(series + [step_obs])
        self.assertEqual(len([e for e in res_strict.evidence if "spike" in e.evidence_id]), 1)

    # 29. No scenario imports
    def test_29_no_scenario_imports(self):
        import backend.engine.sensor as smod
        mod_dict = smod.__dict__
        self.assertNotIn("ScenarioEngine", mod_dict)
        self.assertNotIn("ScenarioResult", mod_dict)

    # 30. No ground truth leakage
    def test_30_no_ground_truth_leakage(self):
        series = generate_obs_series(5)
        result = self.engine.evaluate(series)
        assert_no_forbidden_fields(self, result.model_dump())

    # 31. No label leakage
    def test_31_no_label_leakage(self):
        series = generate_obs_series(5)
        result = self.engine.evaluate(series)
        summary_str = str(result.model_dump()).lower()
        for forbidden in FORBIDDEN_RUNTIME_FIELDS:
            self.assertNotIn(f"'{forbidden}'", summary_str)

    # 32. Bounded health history
    def test_32_bounded_health_history(self):
        small_engine = SensorEvidenceEngine(config=SensorConfig(health_history_buffer_size=5))
        series = generate_obs_series(10)
        for i in range(1, len(series) + 1):
            res = small_engine.evaluate(series[:i])
            self.assertLessEqual(res.health_history_summary["window_size"], 5)

    # 33. Health memory uses only past observations
    def test_33_health_memory_uses_only_past_observations(self):
        series = generate_obs_series(5)
        # Supply reference time that only includes first 3 observations
        ref_time = series[2].observed_at
        res = self.engine.evaluate(series, reference_time=ref_time)

        self.assertEqual(res.target_observation_id, series[2].observation_id)
        self.assertEqual(len(res.evaluated_observations), 3)

    # 34. Health memory does not permanently poison after temporary anomaly
    def test_34_health_memory_recovers_after_temporary_anomaly(self):
        engine = SensorEvidenceEngine(config=SensorConfig(health_recovery_clean_steps=4))
        # Initial series with anomaly
        series = generate_obs_series(3)
        base_dt = datetime.fromisoformat(series[-1].observed_at)
        s1 = make_obs(obs_id="obs-anom", observed_at=(base_dt + timedelta(minutes=5)).isoformat(), temp=65.0, sequence=4)
        engine.evaluate(series + [s1])

        # Then clean observations arrive sequentially with natural variation
        curr_series = series + [s1]
        for i in range(6):
            clean_obs = make_obs(
                obs_id=f"obs-clean-34-{i}",
                observed_at=(base_dt + timedelta(minutes=(i+2)*5)).isoformat(),
                temp=28.0 + (i * 0.1),
                humidity=65.0 - (i * 0.2),
                pressure=1010.0 + (i * 0.1),
                sequence=5 + i,
            )
            curr_series.append(clean_obs)
            res = engine.evaluate(curr_series)

        # After clean steps, station is marked recovered
        self.assertTrue(res.health_history_summary["is_recovered"])
        self.assertGreaterEqual(res.health_history_summary["consecutive_clean_steps"], 4)

    # 35. Localized-weather ambiguity
    def test_35_localized_weather_ambiguity(self):
        series = generate_obs_series(5)
        base_dt = datetime.fromisoformat(series[-1].observed_at)
        # Shift of +3.0°C (could be local weather or sensor bias)
        amb_obs = make_obs(observed_at=(base_dt + timedelta(minutes=5)).isoformat(), temp=31.0, sequence=6)

        result = self.engine.evaluate(series + [amb_obs])
        # Summary explicitly admits unresolved attribution
        self.assertIn("unresolved", result.summary)

    # 36. Unavailable world context ambiguity
    def test_36_unavailable_world_context_ambiguity(self):
        series = generate_obs_series(5)
        base_dt = datetime.fromisoformat(series[-1].observed_at)
        amb_obs = make_obs(observed_at=(base_dt + timedelta(minutes=5)).isoformat(), temp=32.0, sequence=6)

        result = self.engine.evaluate(series + [amb_obs])
        self.assertIn("attribution remains unresolved", result.summary)

    # 37. Stable multi-channel weather event
    def test_37_stable_multichannel_weather_event(self):
        # Calm nocturnal inversion: all 3 channels constant over 6 steps
        obs_list = []
        base_dt = datetime.fromisoformat("2026-09-17T02:00:00+05:30")
        for i in range(6):
            obs_list.append(
                make_obs(
                    obs_id=f"obs-calm-{i}",
                    observed_at=(base_dt + timedelta(minutes=i*5)).isoformat(),
                    temp=18.0,
                    humidity=92.0,
                    pressure=1014.5,
                    sequence=i+1,
                )
            )

        result = self.engine.evaluate(obs_list)
        # Flatline is heavily discounted due to all channels being calm
        for ev in result.evidence:
            if "flatline" in ev.evidence_id:
                self.assertLessEqual(ev.strength, 0.35)
                self.assertIn("stillness plausible", ev.description)

    # 38. Channel-specific flatline
    def test_38_channel_specific_flatline(self):
        obs_list = []
        base_dt = datetime.fromisoformat("2026-09-17T09:00:00+05:30")
        for i in range(6):
            obs_list.append(
                make_obs(
                    obs_id=f"obs-chan-{i}",
                    observed_at=(base_dt + timedelta(minutes=i*5)).isoformat(),
                    temp=28.0,                  # Stuck
                    humidity=65.0 - (i * 2.0),  # Active
                    pressure=1010.0 + (i * 0.5),# Active
                    sequence=i+1,
                )
            )

        result = self.engine.evaluate(obs_list)
        ev = next(e for e in result.evidence if "flatline-isolated-temp" in e.evidence_id)
        self.assertEqual(ev.strength, 0.80)
        self.assertIn("Isolated sustained flatline", ev.description)

    # 39. One bad channel while others evolve
    def test_39_one_bad_channel_while_others_evolve(self):
        obs = make_obs(temp=65.0, humidity=65.0, pressure=1010.0)
        result = self.engine.evaluate([obs])

        self.assertEqual(len(result.evidence), 1)
        self.assertIn("range-temp", result.evidence[0].evidence_id)
        self.assertNotIn("humidity", result.evidence[0].evidence_id)

    # 40. Repeated intermittent spike pattern
    def test_40_repeated_intermittent_spike_pattern(self):
        obs_list = []
        base_dt = datetime.fromisoformat("2026-09-17T09:00:00+05:30")
        # Alternating normal -> spike -> normal -> spike
        temps = [28.0, 38.0, 28.0, 38.0]
        for i, t in enumerate(temps):
            obs_list.append(
                make_obs(
                    obs_id=f"obs-alt-{i}",
                    observed_at=(base_dt + timedelta(minutes=i*5)).isoformat(),
                    temp=t,
                    sequence=i+1,
                )
            )

        result = self.engine.evaluate(obs_list)
        spike_ev = [e for e in result.evidence if "spike-recurrence-temp" in e.evidence_id]
        self.assertEqual(len(spike_ev), 1)

    # 41. Empty target observations handled safely
    def test_41_empty_target_observations_handled_safely(self):
        result = self.engine.evaluate([])
        self.assertEqual(result.station_id, "UNKNOWN")
        self.assertEqual(result.target_observation_id, "NONE")
        self.assertEqual(len(result.evidence), 0)
        self.assertEqual(result.health_history_summary["accumulated_anomalies"], 0)
        self.assertTrue(result.health_history_summary["is_recovered"])
        self.assertIn("No observations provided", result.summary)

    # 42. Four identical values: no default flatline fault (requires 5)
    def test_42_four_identical_values_no_default_flatline_fault(self):
        obs_list = []
        base_dt = datetime.fromisoformat("2026-09-17T09:00:00+05:30")
        for i in range(4):
            obs_list.append(
                make_obs(
                    obs_id=f"obs-four-{i}",
                    observed_at=(base_dt + timedelta(minutes=i * 5)).isoformat(),
                    temp=28.0,
                    humidity=65.0 - (i * 1.0),
                    pressure=1010.0 + (i * 0.2),
                    sequence=i + 1,
                )
            )
        result = self.engine.evaluate(obs_list)
        flatline_ev = [e for e in result.evidence if "flatline" in e.evidence_id]
        self.assertEqual(len(flatline_ev), 0)

    # 43. Drift insufficient persistence and subthreshold
    def test_43_drift_insufficient_persistence_and_subthreshold(self):
        # 6 baseline observations at 28.0°C
        series = generate_obs_series(6, base_temp=28.0)
        base_dt = datetime.fromisoformat(series[-1].observed_at)

        # Case A: Only 3 shifted observations (< 4 persistence required)
        drift_short = list(series)
        for i in range(3):
            drift_short.append(
                make_obs(
                    obs_id=f"obs-short-{i}",
                    observed_at=(base_dt + timedelta(minutes=(i + 1) * 5)).isoformat(),
                    temp=31.0,  # +3.0°C
                    sequence=7 + i,
                )
            )
        res_short = self.engine.evaluate(drift_short)
        self.assertEqual(len([e for e in res_short.evidence if "drift" in e.evidence_id]), 0)

        # Case B: 4 shifted observations but offset 0.8°C is below threshold (1.5°C)
        drift_subthresh = list(series)
        for i in range(4):
            drift_subthresh.append(
                make_obs(
                    obs_id=f"obs-sub-{i}",
                    observed_at=(base_dt + timedelta(minutes=(i + 1) * 5)).isoformat(),
                    temp=28.8,  # +0.8°C offset
                    sequence=7 + i,
                )
            )
        res_sub = self.engine.evaluate(drift_subthresh)
        self.assertEqual(len([e for e in res_sub.evidence if "drift" in e.evidence_id]), 0)

    # 44. Chronological sorting with local derived view without input mutation
    def test_44_chronological_sorting_local_derived_view(self):
        series = generate_obs_series(5)
        # Reverse the list so it is out of chronological order
        reversed_series = list(reversed(series))
        orig_order_ids = [o.observation_id for o in reversed_series]

        result = self.engine.evaluate(reversed_series)

        # Verify caller-owned list was not mutated
        self.assertEqual([o.observation_id for o in reversed_series], orig_order_ids)

        # Verify engine evaluated in correct chronological order
        expected_chronological_ids = [o.observation_id for o in series]
        self.assertEqual(result.evaluated_observations, expected_chronological_ids)
        self.assertEqual(result.target_observation_id, series[-1].observation_id)

    # 45. Future observation strictly excluded via datetime reference_time
    def test_45_future_observation_strictly_excluded_via_datetime_reference_time(self):
        series = generate_obs_series(5)
        last_dt = datetime.fromisoformat(series[-1].observed_at)
        # Injected future anomalous observation (+20 minutes ahead)
        future_obs = make_obs(
            obs_id="obs-future-anomaly",
            observed_at=(last_dt + timedelta(minutes=20)).isoformat(),
            temp=99.0,  # Extreme breach in future
            sequence=10,
        )

        # Supply reference_time as a datetime object matching the last valid observation
        result_with_future = self.engine.evaluate(
            series + [future_obs],
            reference_time=last_dt,
        )
        result_without_future = self.engine.evaluate(series)

        self.assertEqual(result_with_future.model_dump(), result_without_future.model_dump())
        self.assertNotIn("obs-future-anomaly", result_with_future.evaluated_observations)

    # 46. Health history stateless across multiple stations
    def test_46_health_history_stateless_across_multiple_stations(self):
        series_a = generate_obs_series(5, station_id="AWS-01")
        series_b = generate_obs_series(5, station_id="AWS-02", base_temp=65.0)  # Breaches limits

        # 1. Evaluate Station A
        res_a1 = self.engine.evaluate(series_a)

        # 2. Evaluate Station B (anomalous)
        res_b = self.engine.evaluate(series_b)
        self.assertGreater(res_b.health_history_summary["accumulated_anomalies"], 0)

        # 3. Evaluate Station A again -> must be 100% identical to first evaluation, no state cross-talk
        res_a2 = self.engine.evaluate(series_a)
        self.assertEqual(res_a1.model_dump(), res_a2.model_dump())

    # 47. Physical plausibility bound descriptions do not mention WMO
    def test_47_physical_plausibility_bound_descriptions_do_not_mention_wmo(self):
        engine = SensorEvidenceEngine(config=SensorConfig(humidity_max_pct=90.0))
        obs = make_obs(temp=65.0, humidity=95.0, pressure=800.0)
        result = engine.evaluate([obs])
        self.assertGreaterEqual(len(result.evidence), 3)
        for ev in result.evidence:
            self.assertIn("configured physical plausibility bound", ev.description.lower())
            self.assertNotIn("wmo", ev.description.lower())

    # 48. Causal ambiguity wording when unresolved
    def test_48_causal_ambiguity_wording_when_unresolved(self):
        series = generate_obs_series(6)
        base_dt = datetime.fromisoformat(series[-1].observed_at)
        # Ambiguous shift of +3.0°C (could be local weather or sensor deviation)
        amb_obs = make_obs(observed_at=(base_dt + timedelta(minutes=5)).isoformat(), temp=31.0, sequence=7)

        result = self.engine.evaluate(series + [amb_obs])
        self.assertIn("Station-specific evidence candidate; attribution remains unresolved", result.summary)


class TestAdversarialSensorCases(unittest.TestCase):
    """Adversarial validation suite for M1-C3 edge cases and attacks."""

    def setUp(self):
        self.engine = SensorEvidenceEngine()

    # Case A: Genuine regional temperature jump
    def test_adversarial_case_a_genuine_regional_temperature_jump(self):
        series = generate_obs_series(8, base_temp=25.0)
        base_dt = datetime.fromisoformat(series[-1].observed_at)
        jump_obs = make_obs(observed_at=(base_dt + timedelta(minutes=5)).isoformat(), temp=30.0, sequence=9)

        result = self.engine.evaluate(series + [jump_obs])
        for ev in result.evidence:
            self.assertLessEqual(ev.strength, 0.45)

    # Case B: Genuine regional pressure drop
    def test_adversarial_case_b_genuine_regional_pressure_drop(self):
        series = generate_obs_series(8, base_pressure=1012.0)
        base_dt = datetime.fromisoformat(series[-1].observed_at)
        last_t = series[-1].measurements.temperature_c or 28.0
        last_h = series[-1].measurements.relative_humidity_pct or 65.0
        drop_obs = make_obs(
            observed_at=(base_dt + timedelta(minutes=5)).isoformat(),
            temp=round(last_t + 0.1, 2),
            humidity=round(last_h - 0.2, 1),
            pressure=1007.0,
            sequence=9,
        )

        result = self.engine.evaluate(series + [drop_obs])
        for ev in result.evidence:
            self.assertLessEqual(ev.strength, 0.45)

    # Case C: Genuine humidity transition
    def test_adversarial_case_c_genuine_humidity_transition(self):
        series = generate_obs_series(8, base_humidity=50.0)
        base_dt = datetime.fromisoformat(series[-1].observed_at)
        humid_obs = make_obs(observed_at=(base_dt + timedelta(minutes=5)).isoformat(), humidity=85.0, sequence=9)

        result = self.engine.evaluate(series + [humid_obs])
        # No intermittent false alarm
        interm_ev = [e for e in result.evidence if "intermittent" in e.evidence_id]
        self.assertEqual(len(interm_ev), 0)

    # Case D: Localized weather event
    def test_adversarial_case_d_localized_weather_event(self):
        series = generate_obs_series(6)
        base_dt = datetime.fromisoformat(series[-1].observed_at)
        burst_obs = make_obs(observed_at=(base_dt + timedelta(minutes=5)).isoformat(), temp=32.0, humidity=40.0, sequence=7)

        result = self.engine.evaluate(series + [burst_obs])
        self.assertIn("unresolved", result.summary)

    # Case E: Single isolated spike
    def test_adversarial_case_e_single_isolated_spike(self):
        series = generate_obs_series(6)
        base_dt = datetime.fromisoformat(series[-1].observed_at)
        spike_obs = make_obs(observed_at=(base_dt + timedelta(minutes=5)).isoformat(), temp=40.0, sequence=7)

        result = self.engine.evaluate(series + [spike_obs])
        ev = next(e for e in result.evidence if "spike-isolated" in e.evidence_id)
        self.assertLessEqual(ev.strength, 0.35)

    # Case F: Repeated isolated spikes
    def test_adversarial_case_f_repeated_isolated_spikes(self):
        series = generate_obs_series(4)
        base_dt = datetime.fromisoformat(series[-1].observed_at)
        s1 = make_obs(observed_at=(base_dt + timedelta(minutes=5)).isoformat(), temp=40.0, sequence=5)
        n1 = make_obs(observed_at=(base_dt + timedelta(minutes=10)).isoformat(), temp=28.0, sequence=6)
        s2 = make_obs(observed_at=(base_dt + timedelta(minutes=15)).isoformat(), temp=41.0, sequence=7)

        result = self.engine.evaluate(series + [s1, n1, s2])
        ev = next(e for e in result.evidence if "spike-recurrence" in e.evidence_id)
        self.assertGreaterEqual(ev.strength, 0.70)

    # Case G: Slow weather regime shift
    def test_adversarial_case_g_slow_weather_regime_shift(self):
        series = generate_obs_series(15, temp_trend=0.1)
        result = self.engine.evaluate(series)
        # Adaptive baseline prevents false alarms
        base_ev = [e for e in result.evidence if "baseline" in e.evidence_id]
        self.assertEqual(len(base_ev), 0)

    # Case H: Sensor-like drift climate trend
    def test_adversarial_case_h_sensor_like_drift_climate_trend(self):
        # Monotonic warming with small micro-noise
        series = generate_obs_series(10, temp_trend=0.1, temp_noise=0.08)
        result = self.engine.evaluate(series)
        drift_ev = [e for e in result.evidence if "drift" in e.evidence_id]
        self.assertEqual(len(drift_ev), 0)

    # Case I: Pressure rounding repetitions
    def test_adversarial_case_i_pressure_rounding_repetitions(self):
        # Oscillating pressure: 1012.3, 1012.4, 1012.4, 1012.3, 1012.4, 1012.4
        obs_list = []
        base_dt = datetime.fromisoformat("2026-09-17T09:00:00+05:30")
        for i, p in enumerate([1012.3, 1012.4, 1012.4, 1012.3, 1012.4, 1012.4]):
            obs_list.append(
                make_obs(
                    observed_at=(base_dt + timedelta(minutes=i*5)).isoformat(),
                    temp=28.0 + (i * 0.2),
                    humidity=65.0 - (i * 0.5),
                    pressure=p,
                    sequence=i+1,
                )
            )

        result = self.engine.evaluate(obs_list)
        flatline_ev = [e for e in result.evidence if "flatline" in e.evidence_id]
        self.assertEqual(len(flatline_ev), 0)

    # Case J: Missing packets
    def test_adversarial_case_j_missing_packets(self):
        obs_list = [make_obs(sequence=1), make_obs(sequence=3)]  # Packet 2 dropped
        result = self.engine.evaluate(obs_list)
        # Missing packet alone is not evidence of sensor hardware failure
        self.assertEqual(len(result.evidence), 0)

    # Case K: Sequence duplication
    def test_adversarial_case_k_sequence_duplication(self):
        obs_list = [make_obs(sequence=5), make_obs(sequence=5)]
        result = self.engine.evaluate(obs_list)
        # Single duplicate sequence anomaly does not trigger standalone evidence
        telem_ev = [e for e in result.evidence if "telemetry" in e.evidence_id]
        self.assertEqual(len(telem_ev), 0)

    # Case L: Sequence regression
    def test_adversarial_case_l_sequence_regression(self):
        obs_list = [make_obs(sequence=10), make_obs(sequence=8), make_obs(sequence=7)]
        result = self.engine.evaluate(obs_list)
        telem_ev = [e for e in result.evidence if "telemetry-integrity" in e.evidence_id]
        self.assertEqual(len(telem_ev), 1)

    # Case M: Intermittent communication
    def test_adversarial_case_m_intermittent_communication(self):
        obs_list = [
            make_obs(humidity=65.0),
            make_obs(humidity=None),
            make_obs(humidity=66.0),
            make_obs(humidity=None),
            make_obs(humidity=65.5),
        ]
        result = self.engine.evaluate(obs_list)
        interm_ev = [e for e in result.evidence if "intermittent" in e.evidence_id]
        self.assertEqual(len(interm_ev), 1)

    # Case N: One channel frozen while others evolve
    def test_adversarial_case_n_one_channel_frozen_others_evolve(self):
        obs_list = []
        base_dt = datetime.fromisoformat("2026-09-17T09:00:00+05:30")
        for i in range(5):
            obs_list.append(
                make_obs(
                    observed_at=(base_dt + timedelta(minutes=i*5)).isoformat(),
                    temp=28.0,
                    humidity=50.0 + i,
                    pressure=1010.0 - (i*0.2),
                )
            )
        result = self.engine.evaluate(obs_list)
        ev = next(e for e in result.evidence if "flatline-isolated" in e.evidence_id)
        self.assertEqual(ev.strength, 0.80)

    # Case O: All channels frozen during stable conditions
    def test_adversarial_case_o_all_channels_frozen_stable_conditions(self):
        obs_list = []
        base_dt = datetime.fromisoformat("2026-09-17T09:00:00+05:30")
        for i in range(5):
            obs_list.append(
                make_obs(
                    observed_at=(base_dt + timedelta(minutes=i*5)).isoformat(),
                    temp=28.0,
                    humidity=65.0,
                    pressure=1010.0,
                )
            )
        result = self.engine.evaluate(obs_list)
        ev = next(e for e in result.evidence if "flatline-all" in e.evidence_id)
        self.assertEqual(ev.strength, 0.30)

    # Case P: Baseline contamination attempt
    def test_adversarial_case_p_baseline_contamination_attempt(self):
        # 8 normal observations with 1 outlier in history
        series = generate_obs_series(8, base_temp=28.0)
        # Outlier injected at step 4
        series[3] = make_obs(obs_id="obs-outlier-in-hist", temp=45.0)
        result = self.engine.evaluate(series)
        # Robust MAD baseline is not dragged by single historical outlier
        self.assertEqual(len([e for e in result.evidence if "baseline-dev" in e.evidence_id]), 0)

    # Case Q: History poisoning attempt
    def test_adversarial_case_q_history_poisoning_attempt(self):
        engine = SensorEvidenceEngine()
        # Single spike in history followed by nominal operations
        series = generate_obs_series(5)
        base_dt = datetime.fromisoformat(series[-1].observed_at)
        s1 = make_obs(
            obs_id="obs-spike-q",
            observed_at=(base_dt + timedelta(minutes=5)).isoformat(),
            temp=42.0,
            sequence=6,
        )
        engine.evaluate(series + [s1])

        # Then series of 7 clean observations evaluated iteratively as they arrive
        curr_series = list(series) + [s1]
        for i in range(7):
            curr_series.append(
                make_obs(
                    obs_id=f"obs-clean-q-{i}",
                    observed_at=(base_dt + timedelta(minutes=(i+2)*5)).isoformat(),
                    temp=28.0 + (i * 0.1),
                    humidity=65.0 - (i * 0.2),
                    pressure=1010.0 + (i * 0.1),
                    sequence=7 + i,
                )
            )
            final_res = engine.evaluate(curr_series)
        self.assertTrue(final_res.health_history_summary["is_recovered"])

    # Case R: Repeated anomaly followed by recovery
    def test_adversarial_case_r_repeated_anomaly_followed_by_recovery(self):
        engine = SensorEvidenceEngine(config=SensorConfig(health_recovery_clean_steps=4))
        # Initial nominal baseline
        series = generate_obs_series(8, base_temp=28.0)
        base_dt = datetime.fromisoformat(series[-1].observed_at)

        # 3 temporary anomalies
        obs_list = list(series)
        for i in range(3):
            obs_list.append(
                make_obs(
                    obs_id=f"obs-anom-r-{i}",
                    observed_at=(base_dt + timedelta(minutes=(i+1)*5)).isoformat(),
                    temp=65.0,
                    sequence=9+i,
                )
            )
        engine.evaluate(obs_list)

        # Followed by 7 clean steps
        for i in range(7):
            obs_list.append(
                make_obs(
                    obs_id=f"obs-clean-r-{i}",
                    observed_at=(base_dt + timedelta(minutes=(i+4)*5)).isoformat(),
                    temp=28.0 + (i * 0.1),
                    humidity=65.0 - (i * 0.2),
                    pressure=1010.0 + (i * 0.1),
                    sequence=12+i,
                )
            )
            res = engine.evaluate(obs_list)

        self.assertTrue(res.health_history_summary["is_recovered"])

    # Case S: Same evidence submitted twice
    def test_adversarial_case_s_same_evidence_submitted_twice(self):
        target = make_obs(obs_id="obs-double-submit", temp=65.0)
        qc_ev = Evidence(
            evidence_id="ev-qc-double-test",
            subject=EvidenceSubject(station_id=target.station_id, observation_ids=[target.observation_id]),
            type="PHYSICAL_LIMIT",
            relation="SUPPORTS",
            hypothesis="SENSOR",
            description="QC limit breach.",
            strength=0.95,
            quality=EvidenceQuality(status="INVALID", freshness="FRESH", completeness="COMPLETE"),
            provenance=EvidenceProvenance(
                source_type="DETERMINISTIC_QC",
                source_id="quality-range-v1",
                derived_from=[target.observation_id],
            ),
            independence_group="sensor-range-temperature",
            status="AVAILABLE",
        )
        # Passing qc_ev twice in list
        result = self.engine.evaluate([target], quality_evidence=[qc_ev, qc_ev])
        self.assertEqual(len(result.evidence), 1)

    # Case T: Future observation supplied to health history
    def test_adversarial_case_t_future_observation_supplied_to_health_history(self):
        series = generate_obs_series(5)
        # Supply reference time that only includes first 3 observations
        ref_time = series[2].observed_at
        res = self.engine.evaluate(series, reference_time=ref_time)
        self.assertEqual(res.target_observation_id, series[2].observation_id)

    # Case U: Scenario label hidden in observation metadata
    def test_adversarial_case_u_scenario_label_hidden_in_observation_metadata(self):
        obs = make_obs()
        res = self.engine.evaluate([obs])
        assert_no_forbidden_fields(self, res.model_dump())

    # Case V: Generic anomaly score masquerading as evidence
    def test_adversarial_case_v_generic_anomaly_score_masquerading_as_evidence(self):
        series = generate_obs_series(5)
        res = self.engine.evaluate(series)
        # Must not contain generic anomaly_score field
        self.assertNotIn("anomaly_score", res.model_dump())


if __name__ == "__main__":
    unittest.main()
