import React from 'react';

export default function EvidenceInspector({ evidenceData }) {
  if (!evidenceData) {
    return (
      <div className="glass-card p-4 text-center text-slate-500 text-xs font-mono">
        Evidence data loading...
      </div>
    );
  }

  const { world_evidence = [], sensor_evidence = [], evidence_quality = {}, provenance = [], independence = {} } = evidenceData;

  const renderLabelBadge = (label) => {
    switch (label) {
      case 'SUPPORTED':
        return <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-950/80 text-emerald-400 border border-emerald-500/30">SUPPORTED</span>;
      case 'QUALIFIED':
        return <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-sky-950/80 text-sky-400 border border-sky-500/30">QUALIFIED</span>;
      case 'REJECTED':
        return <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-rose-950/80 text-rose-400 border border-rose-500/30">REJECTED</span>;
      default:
        return <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-purple-950/80 text-purple-400 border border-purple-500/30">UNKNOWN</span>;
    }
  };

  return (
    <div className="glass-card p-4 space-y-4">
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-2">
          <span>🔍</span> Evidence & Provenance Inspector
        </h3>
        <div className="flex items-center gap-3 text-[11px] font-mono">
          <span className="text-slate-400">Independence:</span>
          <span className={independence.independence_verified ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
            {independence.independence_verified ? '✓ Verified' : '⚠️ Unverified/Overlap'}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* WORLD EVIDENCE SECTION */}
        <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-800">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-bold text-cyan-400 uppercase tracking-wide flex items-center gap-1.5">
              <span>🌍</span> World Evidence ({world_evidence.length})
            </h4>
            <span className="text-[10px] text-slate-500 font-mono">Spatial & Physical Context</span>
          </div>

          <div className="space-y-2">
            {world_evidence.length > 0 ? (
              world_evidence.map((item, idx) => (
                <div key={idx} className="p-2.5 rounded bg-slate-950/60 border border-slate-800 text-xs">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-[11px] font-semibold text-slate-200">{item.source_type}</span>
                    {renderLabelBadge(item.label)}
                  </div>
                  <p className="text-slate-300 text-[11px] leading-relaxed">{item.description}</p>
                  <div className="mt-1.5 pt-1 border-t border-slate-900 flex justify-between text-[10px] text-slate-500 font-mono">
                    <span>Quality: {(item.quality_score * 100).toFixed(0)}%</span>
                    <span>Sources: {item.provenance?.source_stations?.join(', ') || 'None'}</span>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-[11px] text-slate-500 italic p-2">No active world evidence items reported.</div>
            )}
          </div>
        </div>

        {/* SENSOR EVIDENCE SECTION */}
        <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-800">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-bold text-amber-400 uppercase tracking-wide flex items-center gap-1.5">
              <span>⚡</span> Sensor Evidence ({sensor_evidence.length})
            </h4>
            <span className="text-[10px] text-slate-500 font-mono">Hardware & Telemetry Diagnostics</span>
          </div>

          <div className="space-y-2">
            {sensor_evidence.length > 0 ? (
              sensor_evidence.map((item, idx) => (
                <div key={idx} className="p-2.5 rounded bg-slate-950/60 border border-slate-800 text-xs">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-[11px] font-semibold text-slate-200">{item.source_type}</span>
                    {renderLabelBadge(item.label)}
                  </div>
                  <p className="text-slate-300 text-[11px] leading-relaxed">{item.description}</p>
                  <div className="mt-1.5 pt-1 border-t border-slate-900 flex justify-between text-[10px] text-slate-500 font-mono">
                    <span>Quality: {(item.quality_score * 100).toFixed(0)}%</span>
                    <span>Method: {item.provenance?.method || 'N/A'}</span>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-[11px] text-slate-500 italic p-2">No sensor fault evidence reported.</div>
            )}
          </div>
        </div>
      </div>

      {/* PIPELINE PROVENANCE & QUALITY TRACE */}
      <div className="bg-slate-900/40 p-3 rounded-lg border border-slate-800/80 text-xs font-mono">
        <div className="text-[11px] text-slate-400 font-bold mb-1">Pipeline Provenance Trace</div>
        <div className="flex flex-wrap gap-2 text-[10px]">
          {provenance.map((p, idx) => (
            <span key={idx} className="bg-slate-950 px-2 py-1 rounded border border-slate-800 text-slate-300">
              Stage {idx+1}: <span className="text-cyan-400">{p.pipeline_stage}</span> ({p.ruleset || p.station_id || 'v1'})
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
