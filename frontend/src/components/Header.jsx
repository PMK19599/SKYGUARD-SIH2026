import React from 'react';

export default function Header({ networkStatus, isRefreshing, onRefresh }) {
  return (
    <header className="glass-card p-4 mb-6 border-b border-slate-800 flex flex-col md:flex-row items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center text-slate-950 font-bold text-xl shadow-lg shadow-cyan-500/20">
          🛡️
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-extrabold tracking-wider bg-gradient-to-r from-cyan-400 via-sky-300 to-blue-400 bg-clip-text text-transparent">
              SKYGUARD
            </h1>
            <span className="text-xs px-2 py-0.5 rounded bg-cyan-950/80 border border-cyan-500/30 text-cyan-300 font-mono">
              SIH26073
            </span>
          </div>
          <p className="text-xs text-slate-400 font-medium">
            "When weather data looks wrong, determine whether the world changed—or the sensor did."
          </p>
        </div>
      </div>

      {/* Network Status Header Bar */}
      <div className="flex items-center gap-4 text-xs font-mono">
        {networkStatus && (
          <div className="flex items-center gap-3 bg-slate-900/80 px-3.5 py-1.5 rounded-lg border border-slate-800">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
              <span className="text-slate-400">AWS Grid:</span>
              <span className="text-slate-100 font-semibold">{networkStatus.online_stations}/{networkStatus.total_stations} Online</span>
            </div>
            
            <div className="h-3 w-px bg-slate-800"></div>

            <div className="flex items-center gap-1.5 text-slate-300">
              <span className="text-slate-400">States:</span>
              <span className="text-emerald-400">N:{networkStatus.state_distribution?.NORMAL || 0}</span>
              <span className="text-cyan-400">W:{networkStatus.state_distribution?.WORLD || 0}</span>
              <span className="text-amber-400">S:{networkStatus.state_distribution?.SENSOR || 0}</span>
              <span className="text-rose-400">B:{networkStatus.state_distribution?.BOTH || 0}</span>
              <span className="text-purple-400">U:{networkStatus.state_distribution?.UNKNOWN || 0}</span>
            </div>
          </div>
        )}

        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-all flex items-center gap-1.5 active:scale-95 disabled:opacity-50"
        >
          <span className={`inline-block ${isRefreshing ? 'animate-spin' : ''}`}>🔄</span>
          <span>Refresh</span>
        </button>
      </div>
    </header>
  );
}
