"""Unit and integration tests for SKYGUARD Virtual AWS Network and Scenario Injection."""

import unittest
from typing import Dict, List, Set

from backend.schemas import Observation, Station
from simulator import (
    DEFAULT_STATIONS,
    BaseFault,
    CommunicationFault,
    DriftFault,
    FrozenFault,
    ScenarioEngine,
    ScenarioResult,
    SpikeFault,
    VirtualAWSNetwork,
    create_fault,
)


FORBIDDEN_FIELDS: Set[str] = {
    "scenario",
    "fault_type",
    "diagnosis",
    "expected_state",
    "ground_truth",
    "is_fault",
    "is_world_event",
    "is_sensor_fault",
    "root_cause",
    "label",
    "state",
}


def assert_no_label_leakage(test_case: unittest.TestCase, obs: Observation) -> None:
    """Verify that an Observation contains strictly canonical fields and no leaked metadata."""
    data = obs.model_dump()
    for forbidden in FORBIDDEN_FIELDS:
        test_case.assertNotIn(
            forbidden,
            data,
            f"Observation payload leaked forbidden field: '{forbidden}'",
        )
        if "measurements" in data and isinstance(data["measurements"], dict):
            test_case.assertNotIn(
                forbidden,
                data["measurements"],
                f"Measurements leaked forbidden field: '{forbidden}'",
            )
        if "source" in data and isinstance(data["source"], dict):
            test_case.assertNotIn(
                forbidden,
                data["source"],
                f"Source leaked forbidden field: '{forbidden}'",
            )


class TestVirtualAWSNetwork(unittest.TestCase):
    """Tests validating the Virtual AWS Network abstraction and physics."""

    def test_01_four_stations_generated_with_synthetic_coordinates(self):
        net = VirtualAWSNetwork(seed=42)
        stations = net.get_stations()
        self.assertEqual(len(stations), 4)
        station_ids = [s.station_id for s in stations]
        self.assertEqual(station_ids, ["AWS-01", "AWS-02", "AWS-03", "AWS-04"])

        # Validate that coordinates are neutral synthetic coordinates (e.g. ~20.0 N, 80.0 E)
        for s in stations:
            self.assertIsInstance(s, Station)
            self.assertAlmostEqual(s.location.latitude, 20.0, delta=1.0)
            self.assertAlmostEqual(s.location.longitude, 80.0, delta=1.0)
            self.assertGreater(s.location.elevation_m, 0.0)

    def test_02_every_normal_observation_satisfies_contract(self):
        net = VirtualAWSNetwork(seed=123)
        obs_list = net.generate_sequence(timesteps=5)
        self.assertEqual(len(obs_list), 20)  # 4 stations * 5 steps

        for obs in obs_list:
            self.assertIsInstance(obs, Observation)
            # Re-validate via Pydantic model_validate
            validated = Observation.model_validate(obs.model_dump())
            self.assertEqual(validated.observation_id, obs.observation_id)
            self.assertIn(obs.station_id, ["AWS-01", "AWS-02", "AWS-03", "AWS-04"])
            self.assertIsNotNone(obs.measurements.temperature_c)
            self.assertIsNotNone(obs.measurements.relative_humidity_pct)
            self.assertIsNotNone(obs.measurements.pressure_hpa)
            self.assertEqual(obs.source.type, "SIMULATOR")
            self.assertGreater(obs.sequence, 0)
            assert_no_label_leakage(self, obs)

    def test_03_normal_produces_temporally_continuous_and_varying_values(self):
        """Verify temporal continuity: small step-to-step deltas with non-zero micro-variation."""
        net = VirtualAWSNetwork(seed=999)
        timesteps = 10
        obs_by_station: Dict[str, List[Observation]] = {s: [] for s in ["AWS-01", "AWS-02", "AWS-03", "AWS-04"]}

        for _ in range(timesteps):
            batch = net.step()
            for obs in batch:
                obs_by_station[obs.station_id].append(obs)

        for st_id, seq in obs_by_station.items():
            temps = [o.measurements.temperature_c for o in seq]
            humidities = [o.measurements.relative_humidity_pct for o in seq]
            pressures = [o.measurements.pressure_hpa for o in seq]

            for i in range(len(seq) - 1):
                temp_delta = abs(temps[i + 1] - temps[i])
                hum_delta = abs(humidities[i + 1] - humidities[i])
                pres_delta = abs(pressures[i + 1] - pressures[i])

                # Temporal continuity assertions: step-to-step changes must be physically modest
                self.assertLess(temp_delta, 1.0, f"{st_id} temperature jump too abrupt: {temp_delta}")
                self.assertLess(hum_delta, 3.0, f"{st_id} humidity jump too abrupt: {hum_delta}")
                self.assertLess(pres_delta, 1.0, f"{st_id} pressure jump too abrupt: {pres_delta}")

                # Floating-point variation assertion: readings must not be frozen/identical
                has_variation = (temp_delta > 0.0) or (hum_delta > 0.0) or (pres_delta > 0.0)
                self.assertTrue(has_variation, f"{st_id} appeared frozen during normal simulation at step {i}")


class TestFaultTransformations(unittest.TestCase):
    """Tests verifying controlled fault injection classes in simulator/faults.py."""

    def test_08_spike_fault(self):
        net = VirtualAWSNetwork(seed=42)
        step_1_obs = net.step()[0]
        base_temp = step_1_obs.measurements.temperature_c

        spike = SpikeFault(parameter="temperature_c", magnitude=15.0, start_step=2, duration=1)
        # At step 1: no spike
        m1 = spike.transform(1, step_1_obs.measurements)
        self.assertEqual(m1.temperature_c, base_temp)

        # At step 2: spike active
        step_2_obs = net.step()[0]
        m2 = spike.transform(2, step_2_obs.measurements)
        self.assertAlmostEqual(m2.temperature_c, step_2_obs.measurements.temperature_c + 15.0, places=2)

        # At step 3: spike inactive
        step_3_obs = net.step()[0]
        m3 = spike.transform(3, step_3_obs.measurements)
        self.assertEqual(m3.temperature_c, step_3_obs.measurements.temperature_c)

    def test_09_frozen_fault(self):
        net = VirtualAWSNetwork(seed=777)
        frozen = FrozenFault(parameters=["temperature_c", "relative_humidity_pct"], start_step=3)

        readings: List[float] = []
        for step_idx in range(1, 7):
            obs = net.step()[0]
            transformed = frozen.transform(step_idx, obs.measurements)
            readings.append(transformed.temperature_c)

        # Steps 1 and 2 vary naturally
        self.assertNotEqual(readings[0], readings[1])

        # Steps 3, 4, 5, 6 must be strictly identical
        latched_val = readings[2]
        self.assertEqual(readings[3], latched_val)
        self.assertEqual(readings[4], latched_val)
        self.assertEqual(readings[5], latched_val)

    def test_10_communication_fault_channel_null_and_packet_drop(self):
        net = VirtualAWSNetwork(seed=101)

        # Channel null mode: replaces specific channel with None according to contract
        comm_channel = CommunicationFault(mode="channel_null", parameters=["pressure_hpa"], start_step=2)
        obs1 = net.step()[0]
        t1 = comm_channel.transform(1, obs1.measurements)
        self.assertIsNotNone(t1.pressure_hpa)

        obs2 = net.step()[0]
        t2 = comm_channel.transform(2, obs2.measurements)
        self.assertIsNone(t2.pressure_hpa)
        self.assertIsNotNone(t2.temperature_c)

        # Packet drop mode: returns None to omit observation entirely
        comm_drop = CommunicationFault(mode="packet_drop", start_step=3)
        obs3 = net.step()[0]
        t3 = comm_drop.transform(3, obs3.measurements)
        self.assertIsNone(t3)

    def test_11_drift_fault_accumulates_gradual_bias(self):
        net = VirtualAWSNetwork(seed=555)
        drift = DriftFault(parameter="temperature_c", rate=0.5, start_step=2)

        biases: List[float] = []
        for step_idx in range(1, 6):
            obs = net.step()[0]
            raw_val = obs.measurements.temperature_c
            trans = drift.transform(step_idx, obs.measurements)
            biases.append(trans.temperature_c - raw_val)

        # Step 1: no drift
        self.assertAlmostEqual(biases[0], 0.0, places=2)
        # Step 2: 0.5 drift
        self.assertAlmostEqual(biases[1], 0.5, places=2)
        # Step 3: 1.0 drift
        self.assertAlmostEqual(biases[2], 1.0, places=2)
        # Step 4: 1.5 drift
        self.assertAlmostEqual(biases[3], 1.5, places=2)


class TestScenarioEngine(unittest.TestCase):
    """Tests for ScenarioEngine generating NORMAL, WORLD, SENSOR, BOTH, and UNKNOWN scenarios."""

    def setUp(self):
        self.engine = ScenarioEngine(seed=42)

    def test_04_world_changes_multiple_stations_coherently(self):
        """WORLD scenario should show coherent meteorological trends across all stations."""
        result = self.engine.world(timesteps=8, event_type="cold_front")
        self.assertIsInstance(result, ScenarioResult)
        self.assertEqual(result.ground_truth, "WORLD")

        # Check observations
        obs_by_station: Dict[str, List[Observation]] = {s.station_id: [] for s in DEFAULT_STATIONS}
        for obs in result.observations:
            obs_by_station[obs.station_id].append(obs)
            assert_no_label_leakage(self, obs)

        # In cold_front: all stations should experience drop from step 1 to step 8
        for st_id, seq in obs_by_station.items():
            start_temp = seq[0].measurements.temperature_c
            end_temp = seq[-1].measurements.temperature_c
            temp_drop = start_temp - end_temp
            # Network-wide drop should be substantial (> 3.5°C)
            self.assertGreater(
                temp_drop,
                3.5,
                f"Station {st_id} did not experience coherent cold front temperature drop (drop={temp_drop})",
            )
            # Pressure should surge coherently
            start_pres = seq[0].measurements.pressure_hpa
            end_pres = seq[-1].measurements.pressure_hpa
            self.assertGreater(
                end_pres - start_pres,
                1.0,
                f"Station {st_id} did not experience coherent cold front pressure surge",
            )

    def test_05_sensor_changes_only_selected_station(self):
        """SENSOR scenario should affect only the target station while peers remain normal."""
        target = "AWS-03"
        result = self.engine.sensor(timesteps=8, target_station=target, fault_type="spike", magnitude=20.0, start_step=4)
        self.assertEqual(result.ground_truth, "SENSOR")

        obs_by_station: Dict[str, List[Observation]] = {s.station_id: [] for s in DEFAULT_STATIONS}
        for obs in result.observations:
            obs_by_station[obs.station_id].append(obs)
            assert_no_label_leakage(self, obs)

        # Target station AWS-03 must exhibit the spike at step 4
        target_seq = obs_by_station[target]
        pre_spike = target_seq[2].measurements.temperature_c  # step 3
        at_spike = target_seq[3].measurements.temperature_c   # step 4
        self.assertGreater(at_spike - pre_spike, 15.0)

        # Peer stations AWS-01, AWS-02, AWS-04 must NOT exhibit any spike
        for peer_id in ["AWS-01", "AWS-02", "AWS-04"]:
            peer_seq = obs_by_station[peer_id]
            peer_step3 = peer_seq[2].measurements.temperature_c
            peer_step4 = peer_seq[3].measurements.temperature_c
            self.assertLess(abs(peer_step4 - peer_step3), 1.0)

    def test_06_both_contains_independent_world_event_and_sensor_fault(self):
        """BOTH scenario should demonstrate independent network event and independent sensor fault."""
        target = "AWS-03"
        result = self.engine.both(
            timesteps=8,
            target_station=target,
            event_type="cold_front",
            fault_type="spike",
            magnitude=25.0,
            start_step=5,
        )
        self.assertEqual(result.ground_truth, "BOTH")

        obs_by_station: Dict[str, List[Observation]] = {s.station_id: [] for s in DEFAULT_STATIONS}
        for obs in result.observations:
            obs_by_station[obs.station_id].append(obs)
            assert_no_label_leakage(self, obs)

        # 1. Peer stations experience cold front (world event)
        for peer_id in ["AWS-01", "AWS-02", "AWS-04"]:
            peer_seq = obs_by_station[peer_id]
            drop = peer_seq[0].measurements.temperature_c - peer_seq[-1].measurements.temperature_c
            self.assertGreater(drop, 3.0, f"Peer {peer_id} failed to exhibit world cold front drop in BOTH scenario")

        # 2. Target station AWS-03 independently experiences the spike fault at step 5
        target_seq = obs_by_station[target]
        step4_t = target_seq[3].measurements.temperature_c
        step5_t = target_seq[4].measurements.temperature_c
        self.assertGreater(step5_t - step4_t, 18.0)

    def test_07_unknown_produces_causally_ambiguous_condition(self):
        """UNKNOWN scenario must create genuine causal ambiguity and incomplete/conflicting evidence."""
        target = "AWS-03"
        result = self.engine.unknown(timesteps=8, target_station=target)
        self.assertEqual(result.ground_truth, "UNKNOWN")
        self.assertIn("condition", result.metadata)

        obs_by_station: Dict[str, List[Observation]] = {s.station_id: [] for s in DEFAULT_STATIONS}
        for obs in result.observations:
            obs_by_station[obs.station_id].append(obs)
            assert_no_label_leakage(self, obs)

        # Verification of ambiguous evidence structure:
        # 1. Target AWS-03 experiences an ambiguous gradual shift (+1.5 to +2.5°C)
        target_seq = obs_by_station[target]
        delta_target = target_seq[-1].measurements.temperature_c - target_seq[0].measurements.temperature_c
        self.assertGreater(delta_target, 1.0)
        self.assertLess(delta_target, 3.5)  # Borderline, not an obvious +20°C hardware spike

        # 2. AWS-01 exhibits weak ambiguous correlation
        aws01_seq = obs_by_station["AWS-01"]
        delta_01 = aws01_seq[-1].measurements.temperature_c - aws01_seq[0].measurements.temperature_c
        self.assertGreaterEqual(delta_01, 0.4)

        # 3. AWS-02 stays flat, conflicting with a regional warming hypothesis
        aws02_seq = obs_by_station["AWS-02"]
        delta_02 = abs(aws02_seq[-1].measurements.temperature_c - aws02_seq[0].measurements.temperature_c)
        self.assertLess(delta_02, 1.0)

        # 4. AWS-04 suffers dropped packets starting at step 5
        aws04_seq = obs_by_station["AWS-04"]
        self.assertEqual(len(aws04_seq), 4)  # steps 1-4 present, steps 5-8 omitted

    def test_12_and_13_no_label_leakage_across_all_scenarios(self):
        """Verify strict absence of scenario labels, diagnoses, and forbidden fields in Observation."""
        scenarios = [
            self.engine.normal(timesteps=5),
            self.engine.world(timesteps=5),
            self.engine.sensor(timesteps=5, fault_type="spike"),
            self.engine.sensor(timesteps=5, fault_type="drift"),
            self.engine.sensor(timesteps=5, fault_type="frozen"),
            self.engine.sensor(timesteps=5, fault_type="communication"),
            self.engine.both(timesteps=5),
            self.engine.unknown(timesteps=5),
        ]

        for scn in scenarios:
            self.assertIsInstance(scn.ground_truth, str)
            for obs in scn.observations:
                assert_no_label_leakage(self, obs)
                dump = obs.model_dump()
                # Verify exact allowable keys in observation
                allowable_keys = {
                    "observation_id",
                    "station_id",
                    "observed_at",
                    "received_at",
                    "measurements",
                    "source",
                    "sequence",
                }
                self.assertEqual(set(dump.keys()), allowable_keys)

    def test_14_reproducibility_same_seed_produces_identical_output(self):
        """Verify deterministic reproducibility using random seed."""
        eng1 = ScenarioEngine(seed=4242)
        res1 = eng1.world(timesteps=6, event_type="cold_front")

        eng2 = ScenarioEngine(seed=4242)
        res2 = eng2.world(timesteps=6, event_type="cold_front")

        self.assertEqual(len(res1.observations), len(res2.observations))
        for o1, o2 in zip(res1.observations, res2.observations):
            self.assertEqual(o1.observation_id, o2.observation_id)
            self.assertEqual(o1.station_id, o2.station_id)
            self.assertEqual(o1.observed_at, o2.observed_at)
            self.assertEqual(o1.measurements.temperature_c, o2.measurements.temperature_c)
            self.assertEqual(o1.measurements.relative_humidity_pct, o2.measurements.relative_humidity_pct)
            self.assertEqual(o1.measurements.pressure_hpa, o2.measurements.pressure_hpa)

    def test_15_different_seeds_produce_differing_valid_sequences(self):
        """Verify that different seeds produce distinct synthetic series."""
        eng1 = ScenarioEngine(seed=1001)
        res1 = eng1.normal(timesteps=5)

        eng2 = ScenarioEngine(seed=9999)
        res2 = eng2.normal(timesteps=5)

        # Observations should differ
        temps1 = [o.measurements.temperature_c for o in res1.observations]
        temps2 = [o.measurements.temperature_c for o in res2.observations]
        self.assertNotEqual(temps1, temps2)


if __name__ == "__main__":
    unittest.main()
