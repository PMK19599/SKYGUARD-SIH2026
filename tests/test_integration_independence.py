"""
SKYGUARD Critical Integration Test — Zero Client/API-side Diagnosis Verification

Verifies that the API/Frontend layer strictly reflects backend decision engine outputs
and performs no independent diagnostic rule mapping.
"""

from fastapi.testclient import TestClient
from backend.main import app
from backend.store import store
from backend.models import DecisionObject, EvidenceItem

client = TestClient(app)


def test_decision_engine_output_change_propagates_directly():
    """
    1. Set backend engine decision to SENSOR.
    2. Call GET /decision/AWS-03. Verify state is 'SENSOR'.
    3. Modify engine decision to UNKNOWN without changing API/frontend layer.
    4. Call GET /decision/AWS-03. Verify state automatically updates to 'UNKNOWN'.
    """
    station_id = "AWS-03"

    # 1. Force backend decision state to SENSOR
    initial_decision = DecisionObject(
        station_id=station_id,
        timestamp="2026-09-17T12:00:00Z",
        state="SENSOR",
        confidence=0.92,
        world_evidence=[],
        sensor_evidence=[
            EvidenceItem(
                evidence_id="EV-TEST-01",
                source_type="PHYSICAL_BOUNDS",
                label="SUPPORTED",
                description="Test sensor fault",
                quality_score=0.95
            )
        ],
        evidence_quality={},
        provenance=[],
        independence={"independence_verified": True},
        reason="Test sensor fault injected.",
        action="Inspect/validate sensor."
    )
    store.decisions[station_id] = initial_decision

    # Query API endpoint
    res1 = client.get(f"/decision/{station_id}")
    assert res1.status_code == 200
    assert res1.json()["state"] == "SENSOR"

    # 2. Change backend decision state to UNKNOWN
    updated_decision = DecisionObject(
        station_id=station_id,
        timestamp="2026-09-17T12:01:00Z",
        state="UNKNOWN",
        confidence=0.45,
        world_evidence=[],
        sensor_evidence=[],
        evidence_quality={},
        provenance=[],
        independence={"independence_verified": False},
        reason="Evidence insufficient for decision.",
        action="Human review."
    )
    store.decisions[station_id] = updated_decision

    # Query API endpoint again (WITHOUT touching frontend/API presentation code)
    res2 = client.get(f"/decision/{station_id}")
    assert res2.status_code == 200
    assert res2.json()["state"] == "UNKNOWN"
    assert res2.json()["reason"] == "Evidence insufficient for decision."
