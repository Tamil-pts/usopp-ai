import type {DataModelRowCheck, DataModelStatus} from '../utils/dataModelChecks';

const badgeStyle: Record<DataModelStatus, string> = {
  PASS: 'bg-emerald-950 text-emerald-400 border-emerald-800',
  FAIL: 'bg-rose-950 text-rose-400 border-rose-800',
  UNRESOLVED: 'bg-amber-950 text-amber-400 border-amber-800',
  OPTIONAL: 'bg-amber-950 text-amber-400 border-amber-800',
  SKIPPED: 'bg-slate-800 text-slate-400 border-slate-700',
  DERIVED: 'bg-slate-800 text-slate-400 border-slate-700',
};

export function DataModelCheckCell({check, hasResult, onOpen}: {
  check?: DataModelRowCheck;
  hasResult: boolean;
  onOpen: () => void;
}) {
  if (!check) return <button
    type="button"
    onClick={onOpen}
    className="text-slate-400 text-[11px] underline decoration-dotted underline-offset-4"
    title={hasResult ? 'No requirement lists this metadata row in the selected model. Open the model to review missing requirements.' : 'Choose a reference model and run the parameter name / group check.'}
  >{hasResult ? 'Not listed' : 'Not checked'}</button>;

  return <details className="max-w-[320px] text-[11px]">
    <summary className="cursor-pointer whitespace-nowrap">
      <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-semibold border ${badgeStyle[check.status]}`}>{check.status}</span>
      <span className="ml-2 text-slate-400">Details</span>
    </summary>
    <div className="mt-2 space-y-2 whitespace-normal break-words">
      {check.requirements.map((row, index) => <div key={index}>
        <strong className="text-white">{row.name}</strong>
        <p>Expected: {row.plcType || 'Unspecified type'} · GC {row.groupCodes.join(', ') || 'Unspecified'}</p>
        <p>{row.status}: {row.detail}</p>
        {row.formula && <p className="font-mono">{row.formula}</p>}
        <p className="text-slate-500">{row.source} · {row.sheet}:{row.row}</p>
      </div>)}
      <button type="button" onClick={onOpen} className="text-emerald-400 underline">View model requirements</button>
    </div>
  </details>;
}
