"""Comprehensive automated tests for SKYGUARD Data Quality and Deterministic Safety Layer.

Verifies deterministic QC checks, canonical Evidence generation, independence grouping,
protection against discretization flatlines, immutability, zero label leakage,
and processing of real M1-B simulator streams.
"""

from copy import deepcopy
from datetime import datetime, timedelta
import unittest
from typing import Any, Dict, List, Optional, Set

from backend.engine.quality import (
    DataQualityChecker,
    QualityCheckDetail,
    QualityConfig,
    QualityResult,
)
from backend.schemas import (
    Evidence,
    Measurements,
    Observation,
    ObservationSource,
)
from simulator.scenario_engine import ScenarioEngine


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
    station_id: str = "AWS-01",
    obs_id: str = "obs-AWS01-000001",
    observed_at: str = "2026-09-17T09:05:00+05:30",
    received_at: Optional[str] = None,
    temp: Optional[float] = 28.5,
    humidity: Optional[float] = 65.0,
    pressure: Optional[float] = 1010.0,
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
        source=ObservationSource(type="SIMULATOR", source_id="sim-network-01"),
        sequence=sequence,
    )


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


class TestDataQualityChecker(unittest.TestCase):
    """Unit tests validating the deterministic QC evidence engine."""

    def setUp(self):
        self.checker = DataQualityChecker()

    # 1. Valid normal observation passes quality checks
    def test_01_valid_normal_observation_passes(self):
        obs = make_obs()
        result = self.checker.check(obs)

        self.assertEqual(result.status, "VALID")
        self.assertEqual(result.station_id, "AWS-01")
        self.assertEqual(result.observation_id, "obs-AWS01-000001")
        self.assertEqual(len(result.evidence), 0)
        self.assertIn("passed", result.summary)
        assert_no_forbidden_fields(self, result.model_dump())

    # 2. Impossible/out-of-range temperature generates appropriate evidence
    def test_02_out_of_range_temperature_emits_physical_evidence(self):
        obs = make_obs(temp=85.0)  # > 55.0 max
        result = self.checker.check(obs)

        self.assertEqual(result.status, "INVALID")
        self.assertEqual(len(result.evidence), 1)

        ev = result.evidence[0]
        self.assertEqual(ev.type, "PHYSICAL_LIMIT")
        self.assertEqual(ev.relation, "SUPPORTS")
        self.assertEqual(ev.hypothesis, "SENSOR")
        self.assertIn("Temperature 85.0°C", ev.description)
        self.assertEqual(ev.provenance.source_id, "quality-range-v1")
        self.assertEqual(ev.independence_group, "sensor-range-temperature")

    # 3. Impossible/out-of-range humidity generates appropriate evidence
    def test_03_out_of_range_humidity_emits_physical_evidence(self):
        # Configure custom bounds to test boundary logic
        cfg = QualityConfig(humidity_min_pct=10.0, humidity_max_pct=90.0)
        checker = DataQualityChecker(config=cfg)
        obs = make_obs(humidity=95.0)
        result = checker.check(obs)

        self.assertEqual(result.status, "INVALID")
        self.assertEqual(len(result.evidence), 1)
        ev = result.evidence[0]
        self.assertEqual(ev.type, "PHYSICAL_LIMIT")
        self.assertEqual(ev.hypothesis, "SENSOR")
        self.assertEqual(ev.independence_group, "sensor-range-humidity")

    # 4. Impossible/out-of-range pressure generates appropriate evidence
    def test_04_out_of_range_pressure_emits_physical_evidence(self):
        obs = make_obs(pressure=650.0)  # < 850.0 min
        result = self.checker.check(obs)

        self.assertEqual(result.status, "INVALID")
        self.assertEqual(len(result.evidence), 1)
        ev = result.evidence[0]
        self.assertEqual(ev.type, "PHYSICAL_LIMIT")
        self.assertEqual(ev.hypothesis, "SENSOR")
        self.assertEqual(ev.independence_group, "sensor-range-pressure")

    # 5. Missing temperature is detected as incomplete/degraded (no SENSOR hypothesis)
    def test_05_missing_temperature_detected_as_degraded(self):
        obs = make_obs(temp=None)
        result = self.checker.check(obs)

        self.assertEqual(result.status, "DEGRADED")
        # Invariant: Missing data alone does NOT emit an Evidence with hypothesis="SENSOR"
        self.assertEqual(len(result.evidence), 0)
        completeness_checks = [c for c in result.checks if c.check_name == "completeness"]
        self.assertEqual(len(completeness_checks), 1)
        self.assertEqual(completeness_checks[0].status, "DEGRADED")
        self.assertIn("temperature_c", completeness_checks[0].description)

    # 6. Missing humidity is detected
    def test_06_missing_humidity_detected(self):
        obs = make_obs(humidity=None)
        result = self.checker.check(obs)

        self.assertEqual(result.status, "DEGRADED")
        self.assertEqual(len(result.evidence), 0)
        completeness_check = next(c for c in result.checks if c.check_name == "completeness")
        self.assertIn("relative_humidity_pct", completeness_check.description)

    # 7. Missing pressure is detected
    def test_07_missing_pressure_detected(self):
        obs = make_obs(pressure=None)
        result = self.checker.check(obs)

        self.assertEqual(result.status, "DEGRADED")
        completeness_check = next(c for c in result.checks if c.check_name == "completeness")
        self.assertIn("pressure_hpa", completeness_check.description)

    # 8. Invalid timestamp ordering is detected (observed_at > received_at)
    def test_08_invalid_timestamp_ordering_detected(self):
        # Inverted: observed in the future relative to received
        obs = make_obs(
            observed_at="2026-09-17T09:05:30+05:30",
            received_at="2026-09-17T09:05:00+05:30",  # 30s before observed
        )
        result = self.checker.check(obs)

        self.assertEqual(result.status, "INVALID")
        self.assertTrue(any(ev.independence_group == "station-telemetry-timestamp" for ev in result.evidence))

    # 9. Sequence regression is detected
    def test_09_sequence_regression_detected(self):
        obs1 = make_obs(obs_id="obs-01", sequence=10)
        obs2 = make_obs(obs_id="obs-02", sequence=8)  # decreased from 10 to 8

        self.checker.check(obs1)
        result2 = self.checker.check(obs2)

        self.assertEqual(result2.status, "INVALID")
        ev = next(ev for ev in result2.evidence if ev.independence_group == "station-telemetry-sequence")
        self.assertEqual(ev.type, "TEMPORAL")
        self.assertEqual(ev.hypothesis, "SENSOR")
        self.assertIn("regressed", ev.description)

    # 10. Duplicate sequence is detected
    def test_10_duplicate_sequence_detected(self):
        obs1 = make_obs(obs_id="obs-01", sequence=5)
        obs2 = make_obs(obs_id="obs-02", sequence=5)  # duplicate 5

        self.checker.check(obs1)
        result2 = self.checker.check(obs2)

        self.assertEqual(result2.status, "DEGRADED")
        ev = next(ev for ev in result2.evidence if ev.independence_group == "station-telemetry-sequence")
        self.assertIn("Duplicate", ev.description)

    # 11. Rapid temperature change generates temporal evidence
    def test_11_rapid_temperature_change_generates_temporal_evidence(self):
        obs1 = make_obs(obs_id="obs-01", observed_at="2026-09-17T09:00:00+05:30", temp=25.0, sequence=1)
        # 5 minutes later: jumped to 38.0°C (13°C change in 5 min = 2.6°C/min > 1.5 threshold)
        obs2 = make_obs(obs_id="obs-02", observed_at="2026-09-17T09:05:00+05:30", temp=38.0, sequence=2)

        self.checker.check(obs1)
        result2 = self.checker.check(obs2)

        self.assertEqual(result2.status, "DEGRADED")
        ev = next(ev for ev in result2.evidence if ev.independence_group == "station-temporal-temperature")
        self.assertEqual(ev.type, "TEMPORAL")
        self.assertEqual(ev.hypothesis, "SENSOR")
        self.assertEqual(ev.provenance.source_id, "quality-temporal-v1")
        self.assertIn("Temperature rate of change", ev.description)

    # 12. Rapid humidity change generates temporal evidence
    def test_12_rapid_humidity_change_generates_temporal_evidence(self):
        obs1 = make_obs(obs_id="obs-01", observed_at="2026-09-17T09:00:00+05:30", humidity=40.0, sequence=1)
        # 5 minutes later: jumped to 85.0% (45% change in 5 min = 9.0%/min > 6.0 threshold)
        obs2 = make_obs(obs_id="obs-02", observed_at="2026-09-17T09:05:00+05:30", humidity=85.0, sequence=2)

        self.checker.check(obs1)
        result2 = self.checker.check(obs2)

        self.assertEqual(result2.status, "DEGRADED")
        ev = next(ev for ev in result2.evidence if ev.independence_group == "station-temporal-humidity")
        self.assertIn("humidity rate of change", ev.description.lower())

    # 13. Rapid pressure change generates temporal evidence
    def test_13_rapid_pressure_change_generates_temporal_evidence(self):
        obs1 = make_obs(obs_id="obs-01", observed_at="2026-09-17T09:00:00+05:30", pressure=1010.0, sequence=1)
        # 5 minutes later: plummeted to 998.0 hPa (12 hPa in 5 min = 2.4 hPa/min > 1.5 threshold)
        obs2 = make_obs(obs_id="obs-02", observed_at="2026-09-17T09:05:00+05:30", pressure=998.0, sequence=2)

        self.checker.check(obs1)
        result2 = self.checker.check(obs2)

        self.assertEqual(result2.status, "DEGRADED")
        ev = next(ev for ev in result2.evidence if ev.independence_group == "station-temporal-pressure")
        self.assertIn("Pressure rate of change", ev.description)

    # 14. Short normal flatline (2-3 identical values) does NOT produce SENSOR evidence
    def test_14_short_flatline_does_not_produce_evidence(self):
        """Verify that 2-3 repeated values (e.g. pressure rounding) do not trigger false flatline alarms."""
        # 3 observations with exact identical pressure
        for i in range(3):
            obs = make_obs(
                obs_id=f"obs-{i+1}",
                observed_at=f"2026-09-17T09:{i*5:02d}:00+05:30",
                pressure=1010.42,
                temp=28.0 + (i * 0.1),
                humidity=65.0 - (i * 0.2),
                sequence=i + 1,
            )
            res = self.checker.check(obs)
            # Must remain VALID with zero flatline evidence
            flatline_ev = [ev for ev in res.evidence if "flatline" in ev.evidence_id]
            self.assertEqual(len(flatline_ev), 0, f"False positive flatline emitted at step {i+1}")

    # 15. Sustained frozen values produce flatline evidence
    def test_15_sustained_frozen_values_produce_flatline_evidence(self):
        """Verify that 5 consecutive identical values trigger flatline evidence."""
        res = None
        for i in range(5):
            obs = make_obs(
                obs_id=f"obs-{i+1}",
                observed_at=f"2026-09-17T09:{i*5:02d}:00+05:30",
                temp=28.45,  # locked
                humidity=65.0 - (i * 0.1),
                pressure=1010.0 + (i * 0.05),
                sequence=i + 1,
            )
            res = self.checker.check(obs)

        self.assertIsNotNone(res)
        self.assertEqual(res.status, "DEGRADED")
        ev = next(ev for ev in res.evidence if ev.independence_group == "station-persistence-temperature")
        self.assertEqual(ev.type, "TEMPORAL")
        self.assertEqual(ev.hypothesis, "SENSOR")
        self.assertIn("Sustained flatline", ev.description)
        self.assertEqual(len(ev.subject.observation_ids), 5)

    # 16. Normal simulator data does not produce excessive false quality failures
    def test_16_normal_simulator_data_produces_no_false_alarms(self):
        engine = ScenarioEngine(seed=42)
        normal_res = engine.normal(timesteps=15)
        checker = DataQualityChecker()

        invalid_count = 0
        evidence_count = 0
        for obs in normal_res.observations:
            res = checker.check(obs)
            if res.status == "INVALID":
                invalid_count += 1
            evidence_count += len(res.evidence)

        # Normal simulation should be 100% physically clean with zero invalid observations
        self.assertEqual(invalid_count, 0, "Normal simulator observations triggered INVALID status.")
        self.assertEqual(evidence_count, 0, "Normal simulator observations generated false SENSOR evidence.")

    # 17. Evidence hypothesis is ONLY WORLD or SENSOR
    def test_17_evidence_hypothesis_strictly_world_or_sensor(self):
        obs = make_obs(temp=99.0)
        res = self.checker.check(obs)
        for ev in res.evidence:
            self.assertIn(ev.hypothesis, ["WORLD", "SENSOR"])

    # 18. Evidence does not use NORMAL/BOTH/UNKNOWN as hypothesis
    def test_18_evidence_hypothesis_never_decision_states(self):
        obs = make_obs(temp=-60.0)
        res = self.checker.check(obs)
        forbidden_hypotheses = {"NORMAL", "BOTH", "UNKNOWN"}
        for ev in res.evidence:
            self.assertNotIn(ev.hypothesis, forbidden_hypotheses)

    # 19. Evidence has explicit provenance
    def test_19_evidence_has_explicit_provenance(self):
        obs = make_obs(pressure=1200.0)
        res = self.checker.check(obs)
        self.assertGreater(len(res.evidence), 0)
        for ev in res.evidence:
            self.assertEqual(ev.provenance.source_type, "DETERMINISTIC_QC")
            self.assertTrue(ev.provenance.source_id.startswith("quality-"))
            self.assertIn(obs.observation_id, ev.provenance.derived_from)

    # 20. Evidence independence groups are present and sensible
    def test_20_evidence_independence_groups_are_parameter_specific(self):
        obs1 = make_obs(obs_id="obs-01", observed_at="2026-09-17T09:00:00+05:30", temp=20.0, pressure=1010.0, sequence=1)
        obs2 = make_obs(obs_id="obs-02", observed_at="2026-09-17T09:05:00+05:30", temp=45.0, pressure=900.0, sequence=2)  # dual temporal jumps
        self.checker.check(obs1)
        res2 = self.checker.check(obs2)

        groups = {ev.independence_group for ev in res2.evidence}
        # Distinct mechanism-specific groups
        self.assertIn("station-temporal-temperature", groups)
        self.assertIn("station-temporal-pressure", groups)

    # 21. Observation objects are never mutated
    def test_21_observation_immutability(self):
        obs = make_obs(temp=105.0)
        original_dict = deepcopy(obs.model_dump())
        self.checker.check(obs)
        after_dict = obs.model_dump()
        self.assertEqual(original_dict, after_dict, "Observation was mutated during quality check.")

    # 22. No scenario/ground-truth fields appear in any runtime evidence or quality result
    def test_22_zero_scenario_leakage_in_quality_result(self):
        obs = make_obs(temp=110.0)
        res = self.checker.check(obs)
        assert_no_forbidden_fields(self, res.model_dump())

    # 23. Same observation analyzed independently produces deterministic output
    def test_23_deterministic_reproducibility(self):
        obs = make_obs(temp=80.0)
        res1 = DataQualityChecker().check(obs)
        res2 = DataQualityChecker().check(obs)

        self.assertEqual(res1.status, res2.status)
        self.assertEqual(len(res1.evidence), len(res2.evidence))
        self.assertEqual(res1.evidence[0].evidence_id, res2.evidence[0].evidence_id)
        self.assertEqual(res1.evidence[0].description, res2.evidence[0].description)

    # 24. Thresholds are configurable
    def test_24_configurable_thresholds(self):
        # Strict config where 32°C is considered an out-of-range limit
        strict_config = QualityConfig(temp_max_c=32.0)
        strict_checker = DataQualityChecker(config=strict_config)

        obs = make_obs(temp=34.0)
        # Standard checker: 34°C is nominal (< 55°C)
        res_default = self.checker.check(obs)
        self.assertEqual(res_default.status, "VALID")

        # Strict checker: 34°C breaches 32°C bound
        res_strict = strict_checker.check(obs)
        self.assertEqual(res_strict.status, "INVALID")
        self.assertEqual(len(res_strict.evidence), 1)


class TestAdversarialQualityCases(unittest.TestCase):
    """Adversarial testing: boundary conditions, subtle vs. moderate steps, and real simulator data."""

    def setUp(self):
        self.checker = DataQualityChecker()

    def test_subtle_and_moderate_temperature_steps(self):
        """Subtle (+1.0°C/5min) should NOT trigger temporal evidence; moderate (+4.0°C/5min) should NOT either."""
        obs1 = make_obs(obs_id="obs-01", observed_at="2026-09-17T09:00:00+05:30", temp=28.0, sequence=1)
        # Moderate front step (+4.0°C in 5 min = 0.8°C/min, below 1.5 threshold)
        obs2 = make_obs(obs_id="obs-02", observed_at="2026-09-17T09:05:00+05:30", temp=32.0, sequence=2)

        self.checker.check(obs1)
        res2 = self.checker.check(obs2)
        # Should be VALID, not falsely flagged
        self.assertEqual(res2.status, "VALID")
        self.assertEqual(len(res2.evidence), 0)

    def test_valid_extreme_physical_boundaries(self):
        """Near-limit valid readings should pass without alarms."""
        # 54.5°C is hot desert ambient, but valid under 55.0°C limit
        obs_hot = make_obs(obs_id="obs-hot", station_id="AWS-01", temp=54.5, humidity=12.0, pressure=1005.0, sequence=1)
        res = self.checker.check(obs_hot)
        self.assertEqual(res.status, "VALID")

        # 99.0% humidity is near saturation, valid under 100.0%
        obs_fog = make_obs(obs_id="obs-fog", station_id="AWS-02", temp=18.0, humidity=99.0, pressure=1012.0, sequence=1)
        res2 = self.checker.check(obs_fog)
        self.assertEqual(res2.status, "VALID")

    def test_all_channels_missing_triggers_invalid_status(self):
        """When all three channels are null, status is INVALID without false SENSOR hypothesis."""
        obs_empty = make_obs(temp=None, humidity=None, pressure=None)
        res = self.checker.check(obs_empty)
        self.assertEqual(res.status, "INVALID")
        self.assertEqual(len(res.evidence), 0)
        check = next(c for c in res.checks if c.check_name == "completeness")
        self.assertIn("All measurement channels are null", check.description)

    def test_real_simulator_world_scenario_processing(self):
        """Process cold front scenario from M1-B: should pass cleanly as valid physical data."""
        engine = ScenarioEngine(seed=999)
        world_res = engine.world(timesteps=10, event_type="cold_front")

        checker = DataQualityChecker()
        invalid_obs = 0
        for obs in world_res.observations:
            res = checker.check(obs)
            if res.status == "INVALID":
                invalid_obs += 1

        # Real cold front has rapid, but physically plausible cooling
        self.assertEqual(invalid_obs, 0, "Cold front world scenario was falsely rejected as INVALID.")

    def test_real_simulator_sensor_spike_detection(self):
        """Process sensor spike scenario from M1-B: spike station must generate temporal evidence."""
        engine = ScenarioEngine(seed=777)
        # Spike on AWS-03 at step 4
        sensor_res = engine.sensor(timesteps=6, target_station="AWS-03", fault_type="spike", magnitude=20.0, start_step=4)

        checker = DataQualityChecker()
        aws03_ev_count = 0
        peer_ev_count = 0

        for obs in sensor_res.observations:
            res = checker.check(obs)
            if obs.station_id == "AWS-03":
                aws03_ev_count += len(res.evidence)
            else:
                peer_ev_count += len(res.evidence)

        self.assertGreater(aws03_ev_count, 0, "Spike on AWS-03 was not detected by temporal/range QC.")
        self.assertEqual(peer_ev_count, 0, "Peer stations falsely generated sensor evidence.")

    def test_conservative_multivariate_screening(self):
        """Atypical joint heat/humidity condition generates candidate evidence only."""
        obs_atypical = make_obs(temp=52.0, humidity=98.0, pressure=1010.0)
        res = self.checker.check(obs_atypical)
        self.assertEqual(res.status, "INVALID")
        ev = next(e for e in res.evidence if e.type == "MULTIVARIATE")
        self.assertEqual(ev.relation, "SUPPORTS")
        self.assertEqual(ev.hypothesis, "SENSOR")
        self.assertIn("Candidate evidence", ev.description)
        self.assertEqual(ev.independence_group, "station-multivariate-thermodynamic")


if __name__ == "__main__":
    unittest.main()
