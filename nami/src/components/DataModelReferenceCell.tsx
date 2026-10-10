import {groupDataModelReferences, type DataModelReference} from '../utils/dataModelChecks';

export function DataModelReferenceCell({references, loading, error, parameterName}: {
  references: DataModelReference[];
  loading: boolean;
  error: string;
  parameterName: string;
}) {
  if (!references.length) return <div className="text-[11px] text-slate-500">
    {loading ? 'Loading references...' : error ? 'References unavailable' : <>
      <div className="font-medium">{parameterName}</div><div>Not in data model</div>
    </>}
  </div>;

  const groups = groupDataModelReferences(references);
  return <div className="space-y-2 max-w-[320px] break-words">
    {groups.map((group, index) => <div key={index}>
      <div className="font-medium text-white">{group.name}</div>
      <div className="text-[10px] text-slate-400">{group.services.join(', ')}</div>
      <div className={'text-[11px] ' + (group.status === 'PASS' ? 'text-emerald-400' :
        group.status === 'FAIL' ? 'text-rose-400' : 'text-amber-400')}>{group.label}</div>
    </div>)}
    <details className="text-[10px] text-slate-400"><summary className="cursor-pointer">Source details</summary>
      <div className="space-y-2 mt-1">{references.map((row, index) => <div key={index}>
        <div>{row.service} / {row.sourceRelativePath || row.source}</div>
        <div>{row.sheet}:{row.row} · {row.plcType || 'Unspecified type'} · GC {row.groupCodes.join(', ') || 'Unspecified'}</div>
        <div>{row.detail}</div>
        {row.formula && <div className="font-mono">{row.formula}</div>}
        {row.excelReferences?.map((source, number) => <div key={number}>Excel: {source.source} / {source.sheet}:{source.row}</div>)}
      </div>)}</div>
    </details>
  </div>;
}
