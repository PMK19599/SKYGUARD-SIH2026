import React, { useState } from 'react';

export default function ScenarioLab({ onTriggerScenario, activeStationId }) {
  const [selectedScenario, setSelectedScenario] = useState('NORMAL');
  const [isRunning, setIsRunning] = useState(false);

  const handleRun = async () => {
    setIsRunning(true);
    try {
      await onTriggerScenario(selectedScenario, activeStationId);
    } finally {
      setIsRunning(false);
    }
  };

  const scenarios = [
    {
      id: 'NORMAL',
      label: 'Nominal Weather',
      icon: '☀️',
      desc: 'Consistent diurnal cycle across AWS network.',
      color: 'hover:border-emerald-500/50'
    },
    {
      id: 'WORLD',
      label: 'Cold Front (Storm)',
      icon: '🌩️',
      desc: 'Regional temp drop + humidity surge across neighbors.',
      color: 'hover:border-cyan-500/50'
    },
    {
      id: 'SENSOR',
      label: 'Sensor Hardware Fault',
      icon: '⚠️',
      desc: 'Isolated unphysical temperature spike on target AWS.',
      color: 'hover:border-amber-500/50'
    },
    {
      id: 'BOTH',
      label: 'Storm + Sensor Failure',
      icon: '⚡',
      desc: 'Cold front + simultaneous physical bounds error on target.',
      color: 'hover:border-rose-500/50'
    },
    {
      id: 'UNKNOWN',
      label: 'Ambiguous / Missing Data',
      icon: '❓',
      desc: 'Missing telemetry readings and conflicting neighbors.',
      color: 'hover:border-purple-500/50'
    }
  ];

  return (
    <div className="glass-card p-4">
      <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-3">
        <div>
          <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-2">
            <span>🧪</span> Scenario Lab (Pipeline Fault Injector)
          </h3>
          <p className="text-[11px] text-slate-400 font-mono mt-0.5">
            Target AWS: <span className="text-cyan-400 font-bold">{activeStationId}</span> | Ingests telemetry into real backend pipeline
          </p>
        </div>

        <button
          onClick={handleRun}
          disabled={isRunning}
          className="px-4 py-2 rounded-lg bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold text-xs shadow-md shadow-cyan-950/50 transition-all active:scale-95 disabled:opacity-50 flex items-center gap-2"
        >
          {isRunning ? (
            <>
              <span className="animate-spin">🔄</span>
              <span>Running Pipeline...</span>
            </>
          ) : (
            <>
              <span>🚀</span>
              <span>Inject Scenario</span>
            </>
          )}
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-2.5">
        {scenarios.map((sc) => {
          const isSelected = selectedScenario === sc.id;
          return (
            <button
              key={sc.id}
              onClick={() => setSelectedScenario(sc.id)}
              className={`p-3 rounded-lg border text-left transition-all ${sc.color} ${
                isSelected
                  ? 'bg-slate-800/90 border-cyan-500/70 shadow-sm ring-1 ring-cyan-500/40'
                  : 'bg-slate-900/50 border-slate-800/80 hover:bg-slate-800/40'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-lg">{sc.icon}</span>
                <span className="text-[10px] font-mono font-bold text-slate-400">{sc.id}</span>
              </div>
              <div className="text-xs font-bold text-slate-200 mt-1">{sc.label}</div>
              <p className="text-[10px] text-slate-400 mt-1 line-clamp-2 leading-tight">{sc.desc}</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
