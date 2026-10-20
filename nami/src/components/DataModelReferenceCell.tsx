import {groupDataModelReferences, type DataModelReference} from '../utils/dataModelChecks';

export function DataModelReferenceCell({references, loading, error, parameterName}: {
  references: DataModelReference[];
  loading: boolean;
  error: string;
  parameterName: string;
}) {
  if (!references.length) return loading || error
    ? <div className="text-[11px] text-slate-500">{loading ? 'Loading references...' : 'References unavailable'}</div>
    : null;

  const groups = groupDataModelReferences(references);
  return <div className="space-y-2 max-w-[320px] break-words">
    <div className="font-medium text-white">{parameterName}</div>
    {groups.map((group, index) => <div key={index}>
      <div className="text-[10px] text-slate-400">{group.services.join(', ')}</div>
      {group.name.trim().toLowerCase()!==parameterName.trim().toLowerCase()&&<div className="text-[10px] text-slate-400">Reference name: {group.name}</div>}
      <div className="text-[10px] text-slate-400">{group.status==='DERIVED'?'Reference formula · no PLC group required':<>{group.references[0]?.dataTypeRole==='value'?'Data model value type':group.status === 'UNRESOLVED' ? 'Reference type' : 'Expected PLC type'}: {group.references[0]?.plcType || 'unspecified'} · GC {group.references[0]?.groupCodes.join(', ') || 'not configured'}</>}</div>
      <div className={'text-[11px] ' + (group.status === 'PASS' ? 'text-emerald-400' :
        group.status === 'FAIL' ? 'text-rose-400' : group.status==='DERIVED'?'text-slate-400':'text-amber-400')}>{group.status==='DERIVED'?'Configure and validate in My dashboard':group.label}</div>
      {group.status === 'UNRESOLVED' && <div className="text-[10px] text-slate-400">{group.references[0]?.suggestedPlcType ?
        `Excel specifies ${group.references[0].suggestedPlcType}; confirm the reference before checking the PLC.` :
        'Confirm the reference definition before checking the PLC.'}</div>}
    </div>)}
    <details className="text-[10px] text-slate-400"><summary className="cursor-pointer">Source details</summary>
      <div className="space-y-2 mt-1">{[...new Map(references.map(row=>[JSON.stringify([row.service,row.source,row.sheet,row.row,row.formula]),row])).values()].map((row, index) => <div key={index}>
        <div>{row.service} reference: {row.sourceRelativePath || row.source}</div>
        <div>{row.sheet}:{row.row} · {row.plcType || 'Unspecified type'} · GC {row.groupCodes.join(', ') || 'Unspecified'}</div>
        <div>{row.detail}</div>
        {row.aliases?.length&&<div>Configured names: {row.aliases.join(' / ')} · {row.mappingSource}</div>}
        {row.referenceCorrections?.map((item,i)=><div key={'correction'+i}>Reference correction: {item.previous} → {item.value}. {item.source}</div>)}
        {row.formula && <div className="font-mono">{row.formula}</div>}
        {row.excelReferences?.map((source, number) => <div key={number}>Excel: {source.source} / {source.sheet}:{source.row}{source.dataType && ` · ${source.dataType}`}</div>)}
      </div>)}</div>
    </details>
  </div>;
}
