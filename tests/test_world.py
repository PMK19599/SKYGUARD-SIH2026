"""Comprehensive automated tests for SKYGUARD World Evidence / Neighbor Coherence Layer.

Verifies spatial neighbor coherence, regional common movement, external world evidence,
source cluster tracking, target self-contamination protection, and non-consensus invariants.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest
from typing import Any, Dict, List, Optional, Set

from backend.engine.world import (
    ExternalWorldEvidence,
    WorldConfig,
    WorldEvidenceEngine,
    WorldEvidenceResult,
)
from backend.schemas import (
    Evidence,
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
    station_id: str = "AWS-01",
    obs_id: str = "obs-AWS01-000001",
    observed_at: str = "2026-09-17T09:05:00+05:30",
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


class TestWorldEvidenceEngine(unittest.TestCase):
    """Unit and adversarial test suite for WorldEvidenceEngine."""

    def setUp(self):
        self.engine = WorldEvidenceEngine()

    # 1. Single target with no neighbors
    def test_01_single_target_no_neighbors_produces_no_world_evidence(self):
        target = make_obs(station_id="AWS-03", temp=31.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0)

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[],
        )

        self.assertEqual(len(result.evidence), 0)
        self.assertEqual(len(result.corroborating_stations), 0)
        self.assertIn("No sufficient independent WORLD corroboration", result.summary)
        # CRITICAL: No SENSOR evidence emitted
        for ev in result.evidence:
            self.assertNotEqual(ev.hypothesis, "SENSOR")

    # 2. Target + one coherent neighbor
    def test_02_target_plus_one_coherent_neighbor_produces_weak_candidate_evidence(self):
        # Both drop -2.5°C
        target = make_obs(station_id="AWS-03", temp=25.5)
        prev_target = make_obs(station_id="AWS-03", temp=28.0)

        n1 = make_obs(station_id="AWS-01", temp=25.6, source_id="gw-01")
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0, source_id="gw-01")

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n1],
            prev_neighbor_obs=[prev_n1],
        )

        # 1 neighbor -> candidate evidence, insufficient alone for full corroboration
        self.assertEqual(len(result.corroborating_stations), 1)
        self.assertEqual(len(result.evidence), 1)
        ev = result.evidence[0]
        self.assertEqual(ev.hypothesis, "WORLD")
        self.assertEqual(ev.relation, "SUPPORTS")
        self.assertLessEqual(ev.strength, 0.40)  # Weak candidate score
        self.assertIn("Single neighbor", ev.description)
        self.assertIn("insufficient for independent corroboration", ev.description)

    # 3. Target + multiple coherent neighbors across distinct sources
    def test_03_target_plus_multiple_coherent_neighbors_distinct_sources(self):
        target = make_obs(station_id="AWS-03", temp=25.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0)

        n1 = make_obs(station_id="AWS-01", temp=25.2, source_id="gw-alpha")
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0, source_id="gw-alpha")

        n2 = make_obs(station_id="AWS-02", temp=25.1, source_id="gw-beta")
        prev_n2 = make_obs(station_id="AWS-02", temp=28.0, source_id="gw-beta")

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n1, n2],
            prev_neighbor_obs=[prev_n1, prev_n2],
        )

        self.assertEqual(len(result.corroborating_stations), 2)
        ev = next(e for e in result.evidence if "temperature" in e.description.lower())
        self.assertEqual(ev.hypothesis, "WORLD")
        self.assertEqual(ev.relation, "SUPPORTS")
        self.assertGreaterEqual(ev.strength, 0.75)
        self.assertIn("distinct source clusters", ev.description)

    # 4. Regional coherent movement
    def test_04_regional_coherent_movement(self):
        target = make_obs(station_id="AWS-03", temp=24.0, pressure=1013.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0, pressure=1010.0)

        n1 = make_obs(station_id="AWS-01", temp=24.2, pressure=1012.8, source_id="src-1")
        prev_n1 = make_obs(station_id="AWS-01", temp=28.1, pressure=1010.1, source_id="src-1")

        n2 = make_obs(station_id="AWS-02", temp=23.9, pressure=1013.2, source_id="src-2")
        prev_n2 = make_obs(station_id="AWS-02", temp=28.0, pressure=1010.0, source_id="src-2")

        n3 = make_obs(station_id="AWS-04", temp=24.1, pressure=1012.9, source_id="src-3")
        prev_n3 = make_obs(station_id="AWS-04", temp=27.9, pressure=1009.9, source_id="src-3")

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n1, n2, n3],
            prev_neighbor_obs=[prev_n1, prev_n2, prev_n3],
        )

        self.assertEqual(len(result.corroborating_stations), 3)
        self.assertGreater(len(result.evidence), 1)
        for ev in result.evidence:
            self.assertEqual(ev.hypothesis, "WORLD")

    # 5. Isolated target movement
    def test_05_isolated_target_movement_produces_no_world_evidence(self):
        # Target spikes +4.0°C while neighbors stay flat (+0.1°C)
        target = make_obs(station_id="AWS-03", temp=32.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0)

        n1 = make_obs(station_id="AWS-01", temp=28.1)
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0)

        n2 = make_obs(station_id="AWS-02", temp=28.0)
        prev_n2 = make_obs(station_id="AWS-02", temp=28.0)

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n1, n2],
            prev_neighbor_obs=[prev_n1, prev_n2],
        )

        # Isolated target movement -> no corroborating stations -> NO WORLD evidence
        self.assertEqual(len(result.corroborating_stations), 0)
        self.assertEqual(len(result.evidence), 0)
        self.assertIn("No sufficient independent WORLD corroboration", result.summary)

    # 6. Opposite-direction neighbors
    def test_06_opposite_direction_neighbors_generates_contradiction(self):
        # Target drops -3.0°C; neighbors warm up +2.5°C
        target = make_obs(station_id="AWS-03", temp=25.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0)

        n1 = make_obs(station_id="AWS-01", temp=30.5)
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0)

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n1],
            prev_neighbor_obs=[prev_n1],
        )

        self.assertEqual(len(result.contradicting_stations), 1)
        self.assertEqual(len(result.evidence), 1)
        ev = result.evidence[0]
        self.assertEqual(ev.relation, "CONTRADICTS")
        self.assertEqual(ev.hypothesis, "WORLD")
        self.assertIn("Spatial contradiction", ev.description)

    # 7. Missing neighbor
    def test_07_missing_neighbor_is_not_counted(self):
        target = make_obs(station_id="AWS-03", temp=26.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0)

        # Neighbor has None for temperature
        n1 = make_obs(station_id="AWS-01", temp=None)
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0)

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n1],
            prev_neighbor_obs=[prev_n1],
        )

        self.assertEqual(len(result.corroborating_stations), 0)
        self.assertEqual(len(result.evidence), 0)

    # 8. Stale neighbor
    def test_08_stale_neighbor_excluded_from_active_corroboration(self):
        target = make_obs(station_id="AWS-03", observed_at="2026-09-17T10:00:00+05:30", temp=25.0)
        prev_target = make_obs(station_id="AWS-03", observed_at="2026-09-17T09:55:00+05:30", temp=28.0)

        # Neighbor observed 45 minutes ago (> 30 min stale threshold)
        n_stale = make_obs(station_id="AWS-01", observed_at="2026-09-17T09:15:00+05:30", temp=25.0)
        prev_n_stale = make_obs(station_id="AWS-01", observed_at="2026-09-17T09:10:00+05:30", temp=28.0)

        ref_time = datetime.fromisoformat("2026-09-17T10:00:00+05:30")
        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n_stale],
            prev_neighbor_obs=[prev_n_stale],
            reference_time=ref_time,
        )

        self.assertIn("AWS-01", result.stale_stations)
        self.assertEqual(len(result.corroborating_stations), 0)
        self.assertEqual(len(result.evidence), 0)

    # 9. Conflicting neighbors (some agree, others contradict -> NO majority vote)
    def test_09_conflicting_neighbors_heavily_weakened_and_flagged(self):
        target = make_obs(station_id="AWS-03", temp=25.0)  # -3.0
        prev_target = make_obs(station_id="AWS-03", temp=28.0)

        # n1 agrees (-2.8°C)
        n1 = make_obs(station_id="AWS-01", temp=25.2)
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0)

        # n2 contradicts (+2.0°C)
        n2 = make_obs(station_id="AWS-02", temp=30.0)
        prev_n2 = make_obs(station_id="AWS-02", temp=28.0)

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n1, n2],
            prev_neighbor_obs=[prev_n1, prev_n2],
        )

        self.assertEqual(len(result.corroborating_stations), 1)
        self.assertEqual(len(result.contradicting_stations), 1)
        ev = result.evidence[0]
        self.assertIn("Spatial conflict detected", ev.description)
        self.assertLessEqual(ev.strength, 0.30)  # Heavily discounted

    # 10. Duplicate neighbor observation
    def test_10_duplicate_neighbor_observation_is_deduplicated(self):
        target = make_obs(station_id="AWS-03", temp=25.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0)

        # Same station AWS-01 provided twice
        n1_a = make_obs(station_id="AWS-01", obs_id="obs-1a", observed_at="2026-09-17T09:05:00+05:30", temp=25.1)
        n1_b = make_obs(station_id="AWS-01", obs_id="obs-1b", observed_at="2026-09-17T09:05:00+05:30", temp=25.1)
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0)

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n1_a, n1_b],
            prev_neighbor_obs=[prev_n1],
        )

        # Must count AWS-01 only once
        self.assertEqual(len(result.corroborating_stations), 1)
        self.assertEqual(result.corroborating_stations, ["AWS-01"])

    # 11. Target self-contamination attempt
    def test_11_target_self_contamination_strictly_rejected(self):
        target = make_obs(station_id="AWS-03", temp=25.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0)

        # Caller accidentally/adversarially passes target itself as a neighbor
        target_clone = make_obs(station_id="AWS-03", obs_id="obs-clone", temp=25.0)

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[target_clone],
        )

        self.assertEqual(len(result.corroborating_stations), 0)
        self.assertEqual(len(result.evidence), 0)

    # 12. Same-source neighbors
    def test_12_same_source_neighbors_clustered_without_independence_claim(self):
        target = make_obs(station_id="AWS-03", temp=25.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0)

        # Both neighbors share source_id="cluster-gateway-01"
        n1 = make_obs(station_id="AWS-01", temp=25.1, source_id="cluster-gateway-01")
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0, source_id="cluster-gateway-01")

        n2 = make_obs(station_id="AWS-02", temp=25.2, source_id="cluster-gateway-01")
        prev_n2 = make_obs(station_id="AWS-02", temp=28.0, source_id="cluster-gateway-01")

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n1, n2],
            prev_neighbor_obs=[prev_n1, prev_n2],
        )

        self.assertEqual(len(result.corroborating_stations), 2)
        ev = result.evidence[0]
        self.assertIn("Single provenance cluster", ev.description)
        self.assertIn("statistical independence not established", ev.description)
        self.assertLessEqual(ev.strength, 0.55)  # Constrained due to shared telemetry source

    # 13. Different-source neighbors
    def test_13_different_source_neighbors_recorded(self):
        target = make_obs(station_id="AWS-03", temp=25.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0)

        n1 = make_obs(station_id="AWS-01", temp=25.1, source_id="gw-east")
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0, source_id="gw-east")

        n2 = make_obs(station_id="AWS-02", temp=25.2, source_id="gw-west")
        prev_n2 = make_obs(station_id="AWS-02", temp=28.0, source_id="gw-west")

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n1, n2],
            prev_neighbor_obs=[prev_n1, prev_n2],
        )

        self.assertEqual(len(result.source_clusters), 2)
        self.assertIn("gw-east", result.source_clusters)
        self.assertIn("gw-west", result.source_clusters)

    # 14. Temporal misalignment
    def test_14_temporal_misalignment_discarded(self):
        target = make_obs(station_id="AWS-03", observed_at="2026-09-17T09:05:00+05:30", temp=25.0)
        prev_target = make_obs(station_id="AWS-03", observed_at="2026-09-17T09:00:00+05:30", temp=28.0)

        # Neighbor observed 15 minutes away (> 10 min misalignment threshold)
        n_misaligned = make_obs(station_id="AWS-01", observed_at="2026-09-17T09:20:00+05:30", temp=25.0)
        prev_n = make_obs(station_id="AWS-01", observed_at="2026-09-17T09:15:00+05:30", temp=28.0)

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n_misaligned],
            prev_neighbor_obs=[prev_n],
        )

        self.assertEqual(len(result.corroborating_stations), 0)
        self.assertEqual(len(result.evidence), 0)

    # 15. Magnitude mismatch
    def test_15_magnitude_mismatch_fails_similarity_check(self):
        # Target changes -5.0°C; neighbor changes only -0.8°C (difference 4.2°C > 2.0°C tolerance)
        target = make_obs(station_id="AWS-03", temp=23.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0)

        n1 = make_obs(station_id="AWS-01", temp=27.2)
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0)

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n1],
            prev_neighbor_obs=[prev_n1],
        )

        self.assertEqual(len(result.corroborating_stations), 0)
        self.assertEqual(len(result.evidence), 0)

    # 16. Gradual coherent change
    def test_16_gradual_coherent_change(self):
        target = make_obs(station_id="AWS-03", temp=27.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0)

        n1 = make_obs(station_id="AWS-01", temp=27.1, source_id="s1")
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0, source_id="s1")

        n2 = make_obs(station_id="AWS-02", temp=26.9, source_id="s2")
        prev_n2 = make_obs(station_id="AWS-02", temp=28.0, source_id="s2")

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n1, n2],
            prev_neighbor_obs=[prev_n1, prev_n2],
        )

        self.assertEqual(len(result.corroborating_stations), 2)
        self.assertEqual(len(result.evidence), 1)

    # 17. Pressure regional movement
    def test_17_pressure_regional_movement(self):
        target = make_obs(station_id="AWS-03", pressure=1014.0)  # +3.0 hPa
        prev_target = make_obs(station_id="AWS-03", pressure=1011.0)

        n1 = make_obs(station_id="AWS-01", pressure=1013.8, source_id="s1")
        prev_n1 = make_obs(station_id="AWS-01", pressure=1011.0, source_id="s1")

        n2 = make_obs(station_id="AWS-02", pressure=1014.2, source_id="s2")
        prev_n2 = make_obs(station_id="AWS-02", pressure=1011.0, source_id="s2")

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n1, n2],
            prev_neighbor_obs=[prev_n1, prev_n2],
        )

        self.assertEqual(len(result.corroborating_stations), 2)
        ev = next(e for e in result.evidence if "pressure" in e.description.lower())
        self.assertEqual(ev.relation, "SUPPORTS")
        self.assertEqual(ev.hypothesis, "WORLD")

    # 18. Humidity regional movement
    def test_18_humidity_regional_movement(self):
        target = make_obs(station_id="AWS-03", humidity=80.0)  # +15%
        prev_target = make_obs(station_id="AWS-03", humidity=65.0)

        n1 = make_obs(station_id="AWS-01", humidity=82.0, source_id="s1")
        prev_n1 = make_obs(station_id="AWS-01", humidity=65.0, source_id="s1")

        n2 = make_obs(station_id="AWS-02", humidity=78.0, source_id="s2")
        prev_n2 = make_obs(station_id="AWS-02", humidity=65.0, source_id="s2")

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n1, n2],
            prev_neighbor_obs=[prev_n1, prev_n2],
        )

        self.assertEqual(len(result.corroborating_stations), 2)
        ev = next(e for e in result.evidence if "humidity" in e.description.lower())
        self.assertEqual(ev.relation, "SUPPORTS")

    # 19. Missing target channel
    def test_19_missing_target_channel_handled_gracefully(self):
        target = make_obs(station_id="AWS-03", temp=None, pressure=1010.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0, pressure=1010.0)

        n1 = make_obs(station_id="AWS-01", temp=25.0, pressure=1010.0)
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0, pressure=1010.0)

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n1],
            prev_neighbor_obs=[prev_n1],
        )

        # Does not crash; temperature skipped, pressure evaluated
        self.assertIsInstance(result, WorldEvidenceResult)

    # 20. Invalid target observation
    def test_20_invalid_target_observation_generates_no_ungrounded_evidence(self):
        target = make_obs(station_id="AWS-03", temp=None, humidity=None, pressure=None)
        result = self.engine.evaluate(target_obs=target, neighbor_obs=[])
        self.assertEqual(len(result.evidence), 0)

    # 21. Evidence hypothesis restriction (strictly "WORLD")
    def test_21_evidence_hypothesis_strictly_world(self):
        target = make_obs(station_id="AWS-03", temp=25.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0)
        n1 = make_obs(station_id="AWS-01", temp=25.0)
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0)

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n1],
            prev_neighbor_obs=[prev_n1],
        )

        for ev in result.evidence:
            self.assertEqual(ev.hypothesis, "WORLD")
            self.assertNotIn(ev.hypothesis, ["NORMAL", "SENSOR", "BOTH", "UNKNOWN"])

    # 22. Evidence provenance
    def test_22_evidence_explicit_provenance(self):
        target = make_obs(station_id="AWS-03", temp=25.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0)
        n1 = make_obs(station_id="AWS-01", temp=25.1)
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0)

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n1],
            prev_neighbor_obs=[prev_n1],
        )

        for ev in result.evidence:
            self.assertEqual(ev.provenance.source_type, "DERIVED")
            self.assertEqual(ev.provenance.source_id, "world-spatial-v1")
            self.assertIn(target.observation_id, ev.provenance.derived_from)

    # 23. Independence-group preservation
    def test_23_independence_group_preservation(self):
        target = make_obs(station_id="AWS-03", temp=25.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0)
        n1 = make_obs(station_id="AWS-01", temp=25.1, source_id="gw-1")
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0, source_id="gw-1")

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n1],
            prev_neighbor_obs=[prev_n1],
        )

        for ev in result.evidence:
            self.assertIsNotNone(ev.independence_group)
            self.assertTrue(ev.independence_group.startswith("spatial-"))

    # 24. Observation immutability
    def test_24_observation_immutability(self):
        target = make_obs(station_id="AWS-03", temp=25.0)
        orig_dict = deepcopy(target.model_dump())
        n1 = make_obs(station_id="AWS-01", temp=25.1)
        orig_n1_dict = deepcopy(n1.model_dump())

        self.engine.evaluate(target_obs=target, neighbor_obs=[n1])

        self.assertEqual(target.model_dump(), orig_dict)
        self.assertEqual(n1.model_dump(), orig_n1_dict)

    # 25. No scenario/ground-truth leakage
    def test_25_zero_scenario_leakage(self):
        target = make_obs(station_id="AWS-03", temp=25.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0)
        n1 = make_obs(station_id="AWS-01", temp=25.1)
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0)

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n1],
            prev_neighbor_obs=[prev_n1],
        )

        assert_no_forbidden_fields(self, result.model_dump())

    # 26. Deterministic repeatability
    def test_26_deterministic_repeatability(self):
        target = make_obs(station_id="AWS-03", temp=25.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0)
        n1 = make_obs(station_id="AWS-01", temp=25.1)
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0)

        res1 = self.engine.evaluate(target, prev_target, [n1], [prev_n1])
        res2 = self.engine.evaluate(target, prev_target, [n1], [prev_n1])

        self.assertEqual(res1.model_dump(), res2.model_dump())

    # 27. Configurable thresholds
    def test_27_configurable_thresholds(self):
        # Strict config with 0.5°C tolerance
        strict_engine = WorldEvidenceEngine(config=WorldConfig(temp_similarity_tolerance_c=0.5))

        target = make_obs(station_id="AWS-03", temp=25.0)  # delta = -3.0
        prev_target = make_obs(station_id="AWS-03", temp=28.0)

        n1 = make_obs(station_id="AWS-01", temp=26.2)  # delta = -1.8 (diff = 1.2 > 0.5)
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0)

        # Default engine (tol = 2.0): 1.2 <= 2.0 -> matches
        res_default = self.engine.evaluate(target, prev_target, [n1], [prev_n1])
        self.assertEqual(len(res_default.corroborating_stations), 1)

        # Strict engine (tol = 0.5): 1.2 > 0.5 -> fails
        res_strict = strict_engine.evaluate(target, prev_target, [n1], [prev_n1])
        self.assertEqual(len(res_strict.corroborating_stations), 0)

    # 28. External evidence VALID
    def test_28_external_evidence_valid_produces_evidence(self):
        target = make_obs(station_id="AWS-03", temp=25.0)
        ext = ExternalWorldEvidence(
            source_id="radar-doppler-01",
            source_type="RADAR",
            observed_at="2026-09-17T09:05:00+05:30",
            event_detected=True,
            event_description="Cold front gust line reflectivity",
            status="VALID",
        )

        result = self.engine.evaluate(target_obs=target, external_evidence=[ext])

        self.assertTrue(result.has_external_corroboration)
        ev = next(e for e in result.evidence if "RADAR" in e.description)
        self.assertEqual(ev.hypothesis, "WORLD")
        self.assertEqual(ev.relation, "SUPPORTS")
        self.assertEqual(ev.independence_group, "external-source-radar-radar-doppler-01")

    # 29. External evidence MISSING
    def test_29_external_evidence_missing_produces_no_strong_evidence(self):
        target = make_obs(station_id="AWS-03", temp=25.0)
        ext = ExternalWorldEvidence(
            source_id="radar-doppler-01",
            source_type="RADAR",
            observed_at="2026-09-17T09:05:00+05:30",
            event_detected=True,
            status="MISSING",
        )

        result = self.engine.evaluate(target_obs=target, external_evidence=[ext])
        self.assertFalse(result.has_external_corroboration)
        self.assertEqual(len(result.evidence), 0)

    # 30. External evidence STALE
    def test_30_external_evidence_stale_discounted(self):
        target = make_obs(station_id="AWS-03", observed_at="2026-09-17T10:00:00+05:30", temp=25.0)
        ext = ExternalWorldEvidence(
            source_id="radar-doppler-01",
            source_type="RADAR",
            observed_at="2026-09-17T09:10:00+05:30",  # 50 min old
            event_detected=True,
            status="VALID",
        )

        ref_time = datetime.fromisoformat("2026-09-17T10:00:00+05:30")
        result = self.engine.evaluate(target_obs=target, external_evidence=[ext], reference_time=ref_time)

        self.assertFalse(result.has_external_corroboration)
        ev = result.evidence[0]
        self.assertEqual(ev.quality.freshness, "STALE")
        self.assertEqual(ev.status, "SUPPRESSED")
        self.assertLessEqual(ev.strength, 0.20)

    # 31. External evidence CONFLICTING
    def test_31_external_evidence_conflicting_produces_contradiction(self):
        target = make_obs(station_id="AWS-03", temp=25.0)
        ext = ExternalWorldEvidence(
            source_id="radar-doppler-01",
            source_type="RADAR",
            observed_at="2026-09-17T09:05:00+05:30",
            event_detected=False,
            event_description="Clear air baseline, zero frontal activity",
            status="CONFLICTING",
        )

        result = self.engine.evaluate(target_obs=target, external_evidence=[ext])
        ev = result.evidence[0]
        self.assertEqual(ev.relation, "CONTRADICTS")
        self.assertEqual(ev.hypothesis, "WORLD")

    # 32. Local weather ambiguity: target uncorroborated does NOT become SENSOR
    def test_32_local_weather_ambiguity_never_becomes_sensor(self):
        # Target changes +2.0°C; 2 neighbors stay flat
        target = make_obs(station_id="AWS-03", temp=30.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0)

        n1 = make_obs(station_id="AWS-01", temp=28.0)
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0)

        n2 = make_obs(station_id="AWS-02", temp=28.0)
        prev_n2 = make_obs(station_id="AWS-02", temp=28.0)

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n1, n2],
            prev_neighbor_obs=[prev_n1, prev_n2],
        )

        self.assertEqual(len(result.corroborating_stations), 0)
        # CRITICAL INVARIANT: Never emit SENSOR evidence from lack of corroboration
        for ev in result.evidence:
            self.assertNotEqual(ev.hypothesis, "SENSOR")

    # 33. Same-source neighbor cluster does not masquerade as independent corroboration
    def test_33_same_source_cluster_does_not_masquerade_as_independent(self):
        target = make_obs(station_id="AWS-03", temp=25.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0)

        # 3 neighbors all sharing the exact same source path
        n1 = make_obs(station_id="AWS-01", temp=25.0, source_id="common-gw")
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0, source_id="common-gw")

        n2 = make_obs(station_id="AWS-02", temp=25.1, source_id="common-gw")
        prev_n2 = make_obs(station_id="AWS-02", temp=28.0, source_id="common-gw")

        n3 = make_obs(station_id="AWS-04", temp=25.0, source_id="common-gw")
        prev_n3 = make_obs(station_id="AWS-04", temp=28.0, source_id="common-gw")

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n1, n2, n3],
            prev_neighbor_obs=[prev_n1, prev_n2, prev_n3],
        )

        self.assertEqual(len(result.source_clusters), 1)
        ev = result.evidence[0]
        self.assertIn("Single provenance cluster", ev.description)
        self.assertIn("statistical independence not established", ev.description)
        # Strength must be capped, not elevated to high confidence
        self.assertLessEqual(ev.strength, 0.50)

    # 34. Target is never counted as its own neighbor
    def test_34_target_never_counted_as_own_neighbor(self):
        target = make_obs(station_id="AWS-03", temp=25.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0)

        # Neighbor list contains target itself and one peer
        n_self = make_obs(station_id="AWS-03", temp=25.0)
        n_peer = make_obs(station_id="AWS-01", temp=25.0)
        prev_peer = make_obs(station_id="AWS-01", temp=28.0)

        result = self.engine.evaluate(
            target_obs=target,
            prev_target_obs=prev_target,
            neighbor_obs=[n_self, n_peer],
            prev_neighbor_obs=[prev_peer],
        )

        self.assertNotIn("AWS-03", result.corroborating_stations)
        self.assertEqual(result.corroborating_stations, ["AWS-01"])


class TestAdversarialWorldCases(unittest.TestCase):
    """Specific adversarial attacks mandated by user review."""

    def setUp(self):
        self.engine = WorldEvidenceEngine()

    # Case A: TARGET + 2 NEIGHBORS (same direction, but all 3 share same source path)
    def test_adversarial_target_and_two_neighbors_shared_source_path(self):
        target = make_obs(station_id="AWS-03", temp=25.0, source_id="shared-bus")
        prev_target = make_obs(station_id="AWS-03", temp=28.0, source_id="shared-bus")

        n1 = make_obs(station_id="AWS-01", temp=25.2, source_id="shared-bus")
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0, source_id="shared-bus")

        n2 = make_obs(station_id="AWS-02", temp=25.1, source_id="shared-bus")
        prev_n2 = make_obs(station_id="AWS-02", temp=28.0, source_id="shared-bus")

        result = self.engine.evaluate(target, prev_target, [n1, n2], [prev_n1, prev_n2])

        # Should NOT masquerade as independent corroboration
        self.assertEqual(len(result.source_clusters), 1)
        ev = result.evidence[0]
        self.assertIn("Single provenance cluster", ev.description)
        self.assertIn("independence not established", ev.description)
        self.assertLessEqual(ev.strength, 0.50)

    # Case B: TARGET + 2 NEIGHBORS (same direction, different provenance)
    def test_adversarial_target_and_two_neighbors_different_provenance(self):
        target = make_obs(station_id="AWS-03", temp=25.0, source_id="src-target")
        prev_target = make_obs(station_id="AWS-03", temp=28.0, source_id="src-target")

        n1 = make_obs(station_id="AWS-01", temp=25.2, source_id="src-alpha")
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0, source_id="src-alpha")

        n2 = make_obs(station_id="AWS-02", temp=25.1, source_id="src-beta")
        prev_n2 = make_obs(station_id="AWS-02", temp=28.0, source_id="src-beta")

        result = self.engine.evaluate(target, prev_target, [n1, n2], [prev_n1, prev_n2])

        # Candidate WORLD evidence produced; independence still marked unverified
        self.assertEqual(len(result.corroborating_stations), 2)
        ev = result.evidence[0]
        self.assertEqual(ev.hypothesis, "WORLD")
        self.assertEqual(ev.relation, "SUPPORTS")
        self.assertIn("physical independence subject to downstream verification", ev.description)

    # Case C: TARGET + 2 NEIGHBORS (target moves 3°C, neighbors move 0.2°C)
    def test_adversarial_target_moves_large_neighbors_move_minimal(self):
        target = make_obs(station_id="AWS-03", temp=31.0)  # delta = +3.0
        prev_target = make_obs(station_id="AWS-03", temp=28.0)

        n1 = make_obs(station_id="AWS-01", temp=28.2)  # delta = +0.2
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0)

        n2 = make_obs(station_id="AWS-02", temp=28.1)  # delta = +0.1
        prev_n2 = make_obs(station_id="AWS-02", temp=28.0)

        result = self.engine.evaluate(target, prev_target, [n1, n2], [prev_n1, prev_n2])

        # Neighbors did not move with target -> no strong WORLD evidence
        self.assertEqual(len(result.corroborating_stations), 0)
        self.assertEqual(len(result.evidence), 0)

    # Case D: TARGET + 2 NEIGHBORS (one agrees, one strongly contradicts)
    def test_adversarial_target_and_two_neighbors_one_agrees_one_contradicts(self):
        target = make_obs(station_id="AWS-03", temp=25.0)  # delta = -3.0
        prev_target = make_obs(station_id="AWS-03", temp=28.0)

        n1 = make_obs(station_id="AWS-01", temp=25.2)  # delta = -2.8 (agrees)
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0)

        n2 = make_obs(station_id="AWS-02", temp=31.0)  # delta = +3.0 (strongly contradicts)
        prev_n2 = make_obs(station_id="AWS-02", temp=28.0)

        result = self.engine.evaluate(target, prev_target, [n1, n2], [prev_n1, prev_n2])

        # Active spatial conflict -> evidence severely weakened
        self.assertEqual(len(result.corroborating_stations), 1)
        self.assertEqual(len(result.contradicting_stations), 1)
        ev = result.evidence[0]
        self.assertIn("Spatial conflict detected", ev.description)
        self.assertLessEqual(ev.strength, 0.30)

    # Case E: TARGET + 3 NEIGHBORS (two agree, one contradicts -> do NOT use naive majority vote)
    def test_adversarial_target_and_three_neighbors_two_agree_one_contradicts(self):
        target = make_obs(station_id="AWS-03", temp=25.0)  # -3.0
        prev_target = make_obs(station_id="AWS-03", temp=28.0)

        n1 = make_obs(station_id="AWS-01", temp=25.1)  # -2.9 (agrees)
        prev_n1 = make_obs(station_id="AWS-01", temp=28.0)

        n2 = make_obs(station_id="AWS-02", temp=25.2)  # -2.8 (agrees)
        prev_n2 = make_obs(station_id="AWS-02", temp=28.0)

        n3 = make_obs(station_id="AWS-04", temp=31.0)  # +3.0 (contradicts)
        prev_n3 = make_obs(station_id="AWS-04", temp=28.0)

        result = self.engine.evaluate(target, prev_target, [n1, n2, n3], [prev_n1, prev_n2, prev_n3])

        # Even with 2 against 1, the presence of active contradiction flags spatial conflict and weakens evidence
        self.assertEqual(len(result.contradicting_stations), 1)
        ev = result.evidence[0]
        self.assertIn("Spatial conflict detected", ev.description)
        self.assertLessEqual(ev.strength, 0.30)  # Must NOT be treated as unanimous or strong consensus

    # Case F: TARGET + no neighbors -> absolutely NO SENSOR evidence
    def test_adversarial_target_plus_no_neighbors_emits_no_sensor_evidence(self):
        target = make_obs(station_id="AWS-03", temp=42.0)
        prev_target = make_obs(station_id="AWS-03", temp=28.0)

        result = self.engine.evaluate(target, prev_target, [])

        self.assertEqual(len(result.evidence), 0)
        self.assertIn("No sufficient independent WORLD corroboration", result.summary)
        # Verify no SENSOR evidence is created anywhere
        for ev in result.evidence:
            self.assertNotEqual(ev.hypothesis, "SENSOR")


if __name__ == "__main__":
    unittest.main()
