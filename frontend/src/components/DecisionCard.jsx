import React from 'react';

export default function DecisionCard({ decision, error, stationId }) {
  // Critical Error Boundary Handling
  if (error) {
    return (
      <div className="glass-card p-4 border-l-4 border-rose-500 bg-rose-950/20">
        <div className="flex items-center gap-2 text-rose-400 font-bold text-sm">
          <span>⚠️</span> Decision Unavailable
        </div>
        <p className="text-xs text-slate-300 mt-1">
          Unable to retrieve the current SKYGUARD decision for station <span className="font-mono">{stationId}</span>. ({error.message || 'API Error'})
        </p>
      </div>
    );
  }

  if (!decision) {
    return (
      <div className="glass-card p-4 text-center text-slate-400 text-xs animate-pulse">
        Fetching SKYGUARD decision state...
      </div>
    );
  }

  const state = decision.state || 'UNKNOWN';

  return (
    <div className="glass-card p-4 relative overflow-hidden">
      {/* Background glow accent matching state */}
      <div className={`absolute top-0 right-0 w-32 h-32 rounded-full opacity-10 blur-2xl pointer-events-none badge-${state}`} />

      <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-3">
        <div className="flex items-center gap-2">
          <span className="text-sm">🎯</span>
          <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
            SKYGUARD Decision Engine Output
          </h3>
        </div>

        {/* Operational State Badge directly from backend */}
        <div className="flex items-center gap-2">
          <span className={`text-xs font-mono font-extrabold px-3 py-1 rounded-md tracking-wide ${`badge-${state}`}`}>
            {state}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* State & Confidence Metric */}
        <div className="md:col-span-1 space-y-2">
          <div className="bg-slate-900/80 p-3 rounded-lg border border-slate-800">
            <div className="text-[11px] text-slate-400 font-medium">System State Attribution</div>
            <div className="text-lg font-extrabold font-mono text-slate-100 mt-0.5">{state}</div>
            
            {decision.confidence !== undefined && decision.confidence !== null && (
              <div className="mt-2 pt-2 border-t border-slate-800/80">
                <div className="flex justify-between items-center text-[11px] font-mono">
                  <span className="text-slate-400">Algorithmic Confidence:</span>
                  <span className="text-cyan-400 font-bold">{(decision.confidence * 100).toFixed(0)}%</span>
                </div>
                <div className="w-full bg-slate-950 rounded-full h-1.5 mt-1 overflow-hidden">
                  <div
                    className="bg-gradient-to-r from-cyan-500 to-blue-500 h-1.5 rounded-full"
                    style={{ width: `${Math.min(100, Math.max(0, decision.confidence * 100))}%` }}
                  />
                </div>
                <p className="text-[10px] text-slate-500 mt-1 italic">
                  Internal heuristic score; not a statistical probability.
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Backend Causal Explanation Reason */}
        <div className="md:col-span-1 bg-slate-900/80 p-3 rounded-lg border border-slate-800 flex flex-col justify-between">
          <div>
            <div className="text-[11px] font-medium text-slate-400 flex items-center gap-1.5 mb-1">
              <span>🧠</span> Causal Reason (Backend Engine)
            </div>
            <p className="text-xs text-slate-200 leading-relaxed font-sans">
              {decision.reason || 'No specific explanation provided by backend.'}
            </p>
          </div>
        </div>

        {/* Prescribed Operational Action */}
        <div className="md:col-span-1 bg-slate-900/80 p-3 rounded-lg border border-slate-800 flex flex-col justify-between">
          <div>
            <div className="text-[11px] font-medium text-slate-400 flex items-center gap-1.5 mb-1">
              <span>📋</span> Prescribed Operational Action
            </div>
            <p className="text-xs text-cyan-300 font-semibold leading-relaxed font-mono">
              {decision.action || 'Continue observation.'}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
