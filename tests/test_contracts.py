"""Unit tests validating canonical data contracts for SKYGUARD."""

import json
import unittest
from backend.schemas import Station, Observation, Evidence, Decision


class TestCanonicalContracts(unittest.TestCase):

    def test_canonical_station(self):
        payload = {
            "station_id": "AWS-03",
            "name": "AWS-03",
            "location": {
                "latitude": 12.9716,
                "longitude": 77.5946,
                "elevation_m": 920
            },
            "sensors": [
                {"type": "temperature", "unit": "celsius"},
                {"type": "relative_humidity", "unit": "percent"},
                {"type": "pressure", "unit": "hpa"}
            ]
        }
        station = Station.model_validate(payload)
        self.assertEqual(station.station_id, "AWS-03")
        self.assertEqual(station.location.elevation_m, 920)
        self.assertEqual(len(station.sensors), 3)

    def test_canonical_observation(self):
        payload = {
            "observation_id": "obs-AWS03-000184",
            "station_id": "AWS-03",
            "observed_at": "2026-09-16T18:30:00+05:30",
            "received_at": "2026-09-16T18:30:02+05:30",
            "measurements": {
                "temperature_c": 31.8,
                "relative_humidity_pct": 68.2,
                "pressure_hpa": 1008.4
            },
            "source": {
                "type": "SIMULATOR",
                "source_id": "sim-network-01"
            },
            "sequence": 184
        }
        obs = Observation.model_validate(payload)
        self.assertEqual(obs.observation_id, "obs-AWS03-000184")
        self.assertEqual(obs.measurements.temperature_c, 31.8)
        self.assertEqual(obs.source.type, "SIMULATOR")
        self.assertEqual(obs.sequence, 184)

    def test_canonical_observation_missing_data_remains_null(self):
        payload = {
            "observation_id": "obs-AWS03-000185",
            "station_id": "AWS-03",
            "observed_at": "2026-09-16T18:31:00+05:30",
            "received_at": "2026-09-16T18:31:02+05:30",
            "measurements": {
                "temperature_c": 31.9,
                "relative_humidity_pct": None,
                "pressure_hpa": 1008.3
            },
            "source": {
                "type": "EDGE",
                "source_id": "esp32-node-03"
            }
        }
        obs = Observation.model_validate(payload)
        self.assertIsNone(obs.measurements.relative_humidity_pct)
        self.assertEqual(obs.source.type, "EDGE")
        self.assertIsNone(obs.sequence)

    def test_canonical_evidence(self):
        payload = {
            "evidence_id": "ev-000184",
            "subject": {
                "station_id": "AWS-03",
                "observation_ids": ["obs-AWS03-000184"]
            },
            "type": "TEMPORAL",
            "relation": "SUPPORTS",
            "hypothesis": "SENSOR",
            "description": "Temperature changed by 23.2°C within 5 minutes.",
            "strength": 0.91,
            "quality": {
                "status": "VALID",
                "freshness": "FRESH",
                "completeness": "COMPLETE"
            },
            "provenance": {
                "source_type": "DERIVED",
                "source_id": "temporal-detector-v1",
                "derived_from": ["obs-AWS03-000184"]
            },
            "independence_group": "station-temporal",
            "status": "AVAILABLE"
        }
        ev = Evidence.model_validate(payload)
        self.assertEqual(ev.evidence_id, "ev-000184")
        self.assertEqual(ev.relation, "SUPPORTS")
        self.assertEqual(ev.hypothesis, "SENSOR")
        self.assertEqual(ev.strength, 0.91)

    def test_canonical_decision(self):
        payload = {
            "decision_id": "dec-000184",
            "station_id": "AWS-03",
            "timestamp": "2026-09-16T18:30:02+05:30",
            "state": "SENSOR",
            "confidence": 0.91,
            "world_evidence": ["ev-001", "ev-002"],
            "sensor_evidence": ["ev-003"],
            "evidence_quality": {
                "overall": "HIGH"
            },
            "independence": {
                "status": "ESTABLISHED"
            },
            "reason": "Station behavior is inconsistent with available independent world evidence.",
            "action": "Inspect and validate AWS-03 sensor."
        }
        dec = Decision.model_validate(payload)
        self.assertEqual(dec.decision_id, "dec-000184")
        self.assertEqual(dec.state, "SENSOR")
        self.assertEqual(dec.evidence_quality.overall, "HIGH")
        self.assertEqual(dec.independence.status, "ESTABLISHED")


if __name__ == "__main__":
    unittest.main()
