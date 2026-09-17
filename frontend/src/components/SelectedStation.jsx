import React from 'react';

export default function SelectedStation({ station }) {
  if (!station) {
    return (
      <div className="glass-card p-6 text-center text-slate-400">
        Select a station to inspect live observations.
      </div>
    );
  }

  const reading = station.latest_reading || {};

  return (
    <div className="glass-card p-4">
      <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-3">
        <div>
          <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
            <span>📍</span> {station.name} ({station.station_id})
          </h2>
          <p className="text-xs text-slate-400 font-mono">
            Last observation: {reading.timestamp ? new Date(reading.timestamp).toLocaleTimeString() : 'N/A'}
          </p>
        </div>
        <div className="text-right font-mono text-xs text-slate-400">
          <div>Lat: {station.latitude}°</div>
          <div>Lon: {station.longitude}°</div>
        </div>
      </div>

      {/* Live Telemetry Display Grid */}
      <div className="grid grid-cols-3 gap-3">
        {/* Temperature */}
        <div className="bg-slate-900/70 p-3 rounded-lg border border-slate-800/80">
          <div className="text-[11px] font-medium text-slate-400 flex items-center justify-between">
            <span>Temperature</span>
            <span className="text-amber-400">🌡️</span>
          </div>
          <div className="text-xl font-mono font-bold text-slate-100 mt-1">
            {reading.temperature !== null && reading.temperature !== undefined ? (
              <span>{reading.temperature.toFixed(1)} <span className="text-xs text-slate-400">°C</span></span>
            ) : (
              <span className="text-slate-500 text-sm italic font-normal">N/A (Missing)</span>
            )}
          </div>
        </div>

        {/* Relative Humidity */}
        <div className="bg-slate-900/70 p-3 rounded-lg border border-slate-800/80">
          <div className="text-[11px] font-medium text-slate-400 flex items-center justify-between">
            <span>Relative Humidity</span>
            <span className="text-cyan-400">💧</span>
          </div>
          <div className="text-xl font-mono font-bold text-slate-100 mt-1">
            {reading.humidity !== null && reading.humidity !== undefined ? (
              <span>{reading.humidity.toFixed(1)} <span className="text-xs text-slate-400">%</span></span>
            ) : (
              <span className="text-slate-500 text-sm italic font-normal">N/A (Missing)</span>
            )}
          </div>
        </div>

        {/* Barometric Pressure */}
        <div className="bg-slate-900/70 p-3 rounded-lg border border-slate-800/80">
          <div className="text-[11px] font-medium text-slate-400 flex items-center justify-between">
            <span>Barometric Pressure</span>
            <span className="text-blue-400">📊</span>
          </div>
          <div className="text-xl font-mono font-bold text-slate-100 mt-1">
            {reading.pressure !== null && reading.pressure !== undefined ? (
              <span>{reading.pressure.toFixed(1)} <span className="text-xs text-slate-400">hPa</span></span>
            ) : (
              <span className="text-slate-500 text-sm italic font-normal">N/A (Missing)</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
