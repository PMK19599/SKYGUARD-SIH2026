"""
SKYGUARD Backend API Unit Test Suite
"""

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_get_stations():
    response = client.get("/stations")
    assert response.status_code == 200
    data = response.json()
    assert "stations" in data
    assert len(data["stations"]) >= 5
    station_ids = [s["station_id"] for s in data["stations"]]
    assert "AWS-03" in station_ids


def test_get_station_by_id():
    response = client.get("/stations/AWS-03")
    assert response.status_code == 200
    data = response.json()
    assert data["station_id"] == "AWS-03"
    assert "name" in data


def test_get_station_invalid_404():
    response = client.get("/stations/INVALID-AWS")
    assert response.status_code == 404


def test_get_station_history():
    response = client.get("/stations/AWS-03/history")
    assert response.status_code == 200
    data = response.json()
    assert data["station_id"] == "AWS-03"
    assert "history" in data
    assert isinstance(data["history"], list)


def test_ingest_observation_valid():
    payload = {
        "station_id": "AWS-03",
        "temperature": 29.5,
        "humidity": 72.0,
        "pressure": 1010.5,
        "timestamp": "2026-09-17T12:00:00+05:30"
    }
    response = client.post("/ingest", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["station_id"] == "AWS-03"
    assert "state" in data
    assert data["state"] in ["NORMAL", "WORLD", "SENSOR", "BOTH", "UNKNOWN"]


def test_ingest_observation_missing_values_retained_null():
    """Missing measurements must remain null and NEVER be converted to zero."""
    payload = {
        "station_id": "AWS-03",
        "temperature": None,  # Missing
        "humidity": 80.0,
        "pressure": None,     # Missing
        "timestamp": "2026-09-17T12:05:00+05:30"
    }
    response = client.post("/ingest", json=payload)
    assert response.status_code == 200
    
    # Inspect stored history
    hist_response = client.get("/stations/AWS-03/history")
    latest = hist_response.json()["history"][-1]
    assert latest["temperature"] is None
    assert latest["pressure"] is None
    assert latest["humidity"] == 80.0


def test_get_decision():
    response = client.get("/decision/AWS-03")
    assert response.status_code == 200
    data = response.json()
    assert data["station_id"] == "AWS-03"
    assert "state" in data
    assert "reason" in data
    assert "action" in data


def test_get_evidence():
    response = client.get("/evidence/AWS-03")
    assert response.status_code == 200
    data = response.json()
    assert data["station_id"] == "AWS-03"
    assert "world_evidence" in data
    assert "sensor_evidence" in data
    assert "independence" in data


def test_post_scenario():
    payload = {
        "scenario": "SENSOR",
        "station_id": "AWS-03"
    }
    response = client.post("/scenario", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["station_id"] == "AWS-03"
    assert "state" in data


def test_get_network_status():
    response = client.get("/network/status")
    assert response.status_code == 200
    data = response.json()
    assert "total_stations" in data
    assert "online_stations" in data
    assert "state_distribution" in data
