import React, { useState, useEffect, useCallback } from 'react';

import Header from './components/Header';
import StationNetwork from './components/StationNetwork';
import SelectedStation from './components/SelectedStation';
import HistoryCharts from './components/HistoryCharts';
import DecisionCard from './components/DecisionCard';
import EvidenceInspector from './components/EvidenceInspector';
import ScenarioLab from './components/ScenarioLab';

import {
  getStations,
  getStation,
  getHistory,
  getDecision,
  getEvidence,
  getNetworkStatus,
  runScenario,
} from './services/api';

export default function App() {
  const [stations, setStations] = useState([]);
  const [selectedStationId, setSelectedStationId] = useState('AWS-03');
  const [selectedStationInfo, setSelectedStationInfo] = useState(null);
  const [history, setHistory] = useState([]);
  const [decisions, setDecisions] = useState({});
  const [currentDecision, setCurrentDecision] = useState(null);
  const [decisionError, setDecisionError] = useState(null);
  const [evidenceData, setEvidenceData] = useState(null);
  const [networkStatus, setNetworkStatus] = useState(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Load all stations and network status
  const loadInitialData = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const [stList, netStat] = await Promise.all([
        getStations().catch(() => []),
        getNetworkStatus().catch(() => null),
      ]);
      setStations(stList);
      setNetworkStatus(netStat);

      // Fetch decisions for all stations
      const decMap = {};
      await Promise.all(
        stList.map(async (st) => {
          try {
            const dec = await getDecision(st.station_id);
            decMap[st.station_id] = dec;
          } catch (e) {
            // Error logged without fabricating decision state
          }
        })
      );
      setDecisions(decMap);
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  // Load specific selected station details, history, decision, evidence
  const loadStationDetails = useCallback(async (sid) => {
    if (!sid) return;
    setDecisionError(null);

    try {
      const [info, hist, dec, ev] = await Promise.allSettled([
        getStation(sid),
        getHistory(sid),
        getDecision(sid),
        getEvidence(sid),
      ]);

      if (info.status === 'fulfilled') setSelectedStationInfo(info.value);
      if (hist.status === 'fulfilled') setHistory(hist.value);

      if (dec.status === 'fulfilled') {
        setCurrentDecision(dec.value);
        setDecisions((prev) => ({ ...prev, [sid]: dec.value }));
      } else {
        setDecisionError(dec.reason);
        setCurrentDecision(null);
      }

      if (ev.status === 'fulfilled') setEvidenceData(ev.value);
    } catch (err) {
      console.error('Error fetching station details:', err);
    }
  }, []);

  // Initial load
  useEffect(() => {
    loadInitialData();
  }, [loadInitialData]);

  // Load selected station
  useEffect(() => {
    loadStationDetails(selectedStationId);
  }, [selectedStationId, loadStationDetails]);

  // Safe polling interval (5 seconds)
  useEffect(() => {
    const timer = setInterval(() => {
      loadStationDetails(selectedStationId);
      getNetworkStatus().then(setNetworkStatus).catch(() => {});
    }, 5000);
    return () => clearInterval(timer);
  }, [selectedStationId, loadStationDetails]);

  // Scenario execution
  const handleTriggerScenario = async (scenario, stationId) => {
    try {
      const resultingDecision = await runScenario(scenario, stationId);
      // Immediately refresh dashboard views with actual backend response
      await loadInitialData();
      await loadStationDetails(stationId);
    } catch (err) {
      console.error('Scenario execution failed:', err);
      alert(`Scenario execution error: ${err.message}`);
    }
  };

  return (
    <div className="min-h-screen p-4 md:p-6 max-w-[1600px] mx-auto flex flex-col gap-5">
      {/* Header */}
      <Header
        networkStatus={networkStatus}
        isRefreshing={isRefreshing}
        onRefresh={loadInitialData}
      />

      {/* Main Command-Center Layout Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Left Column: Station Network List */}
        <div className="lg:col-span-4 xl:col-span-3">
          <StationNetwork
            stations={stations}
            selectedStationId={selectedStationId}
            onSelectStation={setSelectedStationId}
            decisions={decisions}
          />
        </div>

        {/* Right Column: Selected Station Details, Decision & Evidence */}
        <div className="lg:col-span-8 xl:col-span-9 flex flex-col gap-5">
          {/* Selected Station Telemetry */}
          <SelectedStation station={selectedStationInfo} />

          {/* SKYGUARD Backend Decision Display */}
          <DecisionCard
            decision={currentDecision}
            error={decisionError}
            stationId={selectedStationId}
          />

          {/* History Trend Charts */}
          <HistoryCharts history={history} stationId={selectedStationId} />

          {/* Evidence Inspector */}
          <EvidenceInspector evidenceData={evidenceData} />

          {/* Scenario Lab Controls */}
          <ScenarioLab
            onTriggerScenario={handleTriggerScenario}
            activeStationId={selectedStationId}
          />
        </div>
      </div>
    </div>
  );
}
