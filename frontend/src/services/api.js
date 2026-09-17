/**
 * SKYGUARD Centralized API Service Client
 * Encapsulates all backend REST communication cleanly with error handling.
 */

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function fetchJSON(url, options = {}) {
  try {
    const res = await fetch(`${BASE_URL}${url}`, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(errorData.detail || `HTTP Error ${res.status}`);
    }

    return await res.json();
  } catch (err) {
    console.error(`API Error on ${url}:`, err);
    throw err;
  }
}

export async function getStations() {
  const data = await fetchJSON('/stations');
  return data.stations || [];
}

export async function getStation(stationId) {
  return await fetchJSON(`/stations/${stationId}`);
}

export async function getHistory(stationId) {
  const data = await fetchJSON(`/stations/${stationId}/history`);
  return data.history || [];
}

export async function ingestObservation(payload) {
  return await fetchJSON('/ingest', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getDecision(stationId) {
  return await fetchJSON(`/decision/${stationId}`);
}

export async function getEvidence(stationId) {
  return await fetchJSON(`/evidence/${stationId}`);
}

export async function runScenario(scenario, stationId = 'AWS-03', mode = null) {
  return await fetchJSON('/scenario', {
    method: 'POST',
    body: JSON.stringify({ scenario, station_id: stationId, mode }),
  });
}

export async function getNetworkStatus() {
  return await fetchJSON('/network/status');
}
