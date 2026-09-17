import React from 'react';

export default function StationNetwork({ stations, selectedStationId, onSelectStation, decisions }) {
  return (
    <div className="glass-card p-4 flex flex-col h-full">
      <div className="flex items-center justify-between mb-3 border-b border-slate-800/80 pb-2">
        <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-2">
          <span>📡</span> Station Network
        </h2>
        <span className="text-xs font-mono text-slate-400">{stations.length} Active AWS</span>
      </div>

      <div className="space-y-2.5 overflow-y-auto pr-1 max-h-[460px]">
        {stations.map((st) => {
          const isSelected = st.station_id === selectedStationId;
          const decision = decisions[st.station_id];
          const state = decision?.state || 'NORMAL';

          return (
            <button
              key={st.station_id}
              onClick={() => onSelectStation(st.station_id)}
              className={`w-full text-left p-3 rounded-lg border transition-all glass-card-hover flex items-center justify-between ${
                isSelected
                  ? 'bg-slate-800/90 border-cyan-500/60 shadow-md shadow-cyan-950/40 ring-1 ring-cyan-500/30'
                  : 'bg-slate-900/50 border-slate-800/80 hover:bg-slate-800/50'
              }`}
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono font-bold text-sm text-slate-100">{st.station_id}</span>
                  <span className="text-xs text-slate-400 font-medium truncate max-w-[120px]">
                    {st.name.replace(/Station \d+ — /, '')}
                  </span>
                </div>
                <div className="text-[11px] text-slate-500 font-mono mt-0.5">
                  {st.latitude.toFixed(2)}°N, {st.longitude.toFixed(2)}°E
                </div>
              </div>

              {/* State Badge strictly consumed from backend */}
              <div className="flex flex-col items-end gap-1">
                <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${`badge-${state}`}`}>
                  {state}
                </span>
                <span className="text-[10px] text-slate-400 font-mono">
                  {st.latest_reading?.temperature !== null && st.latest_reading?.temperature !== undefined
                    ? `${st.latest_reading.temperature.toFixed(1)}°C`
                    : 'N/A'}
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
