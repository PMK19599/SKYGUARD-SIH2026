import React from 'react';

export default function HistoryCharts({ history, stationId }) {
  if (!history || history.length === 0) {
    return (
      <div className="glass-card p-4 text-center text-slate-500 text-xs font-mono">
        No historical telemetry records available for station {stationId}.
      </div>
    );
  }

  // Filter valid readings
  const temps = history.map(h => h.temperature).filter(v => v !== null && v !== undefined);
  const hums = history.map(h => h.humidity).filter(v => v !== null && v !== undefined);
  const press = history.map(h => h.pressure).filter(v => v !== null && v !== undefined);

  // SVG dimensions
  const width = 460;
  const height = 90;
  const padding = 15;

  const renderLineChart = (data, color, minVal, maxVal) => {
    if (!data || data.length < 2) return null;
    const min = minVal !== undefined ? minVal : Math.min(...data) - 1;
    const max = maxVal !== undefined ? maxVal : Math.max(...data) + 1;
    const range = max - min || 1;

    const points = data.map((val, idx) => {
      const x = padding + (idx / (data.length - 1)) * (width - 2 * padding);
      const y = height - padding - ((val - min) / range) * (height - 2 * padding);
      return `${x},${y}`;
    }).join(' ');

    return (
      <svg className="w-full h-24 overflow-visible" viewBox={`0 0 ${width} ${height}`}>
        <polyline
          fill="none"
          stroke={color}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          points={points}
        />
        {data.map((val, idx) => {
          const x = padding + (idx / (data.length - 1)) * (width - 2 * padding);
          const y = height - padding - ((val - min) / range) * (height - 2 * padding);
          return (
            <circle
              key={idx}
              cx={x}
              cy={y}
              r="3"
              fill={color}
              className="hover:r-5 transition-all"
            />
          );
        })}
      </svg>
    );
  };

  return (
    <div className="glass-card p-4">
      <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-3">
        <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-2">
          <span>📈</span> Telemetry History Trends ({history.length} Observations)
        </h3>
        <span className="text-[11px] font-mono text-slate-400">AWS: {stationId}</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Temperature Trend */}
        <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-800/80">
          <div className="flex items-center justify-between text-xs font-mono mb-1">
            <span className="text-amber-400 font-semibold">Temperature (°C)</span>
            <span className="text-slate-400">
              {temps.length > 0 ? `${temps[temps.length - 1].toFixed(1)}°C` : 'N/A'}
            </span>
          </div>
          {temps.length >= 2 ? (
            renderLineChart(temps, '#f59e0b')
          ) : (
            <div className="h-20 flex items-center justify-center text-[11px] text-slate-500 italic">
              Insufficient history points
            </div>
          )}
        </div>

        {/* Humidity Trend */}
        <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-800/80">
          <div className="flex items-center justify-between text-xs font-mono mb-1">
            <span className="text-cyan-400 font-semibold">Humidity (%)</span>
            <span className="text-slate-400">
              {hums.length > 0 ? `${hums[hums.length - 1].toFixed(1)}%` : 'N/A'}
            </span>
          </div>
          {hums.length >= 2 ? (
            renderLineChart(hums, '#06b6d4')
          ) : (
            <div className="h-20 flex items-center justify-center text-[11px] text-slate-500 italic">
              Insufficient history points
            </div>
          )}
        </div>

        {/* Pressure Trend */}
        <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-800/80">
          <div className="flex items-center justify-between text-xs font-mono mb-1">
            <span className="text-blue-400 font-semibold">Pressure (hPa)</span>
            <span className="text-slate-400">
              {press.length > 0 ? `${press[press.length - 1].toFixed(1)} hPa` : 'N/A'}
            </span>
          </div>
          {press.length >= 2 ? (
            renderLineChart(press, '#3b82f6')
          ) : (
            <div className="h-20 flex items-center justify-center text-[11px] text-slate-500 italic">
              Insufficient history points
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
