import {useEffect, useMemo, useRef, useState} from 'react';
import type {MetadataItem} from '../types';
import {dataModelDepartmentLabel, dataModelMachineKey, dataModelResultLabel, evaluateDataModel,
  type DataModel, type DataModelCheck, type DataModelResult, type DataModelSelection, type DataModelSummary} from '../utils/dataModelChecks';
import './data-model.css';

async function read(response: Response) {
  const value = await response.json();
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : 'Data model request failed.');
  return value;
}

export function DataModelModal({metadata, machine, selection, check, onSelectionChange, onChecked, onClose}: {
  metadata: MetadataItem[];
  machine: string;
  selection: DataModelSelection;
  check: DataModelCheck | null;
  onSelectionChange: (selection: DataModelSelection) => void;
  onChecked: (check: DataModelCheck | null) => void;
  onClose: () => void;
}) {
  const {service, modelId, allMachines} = selection;
  const [catalog, setCatalog] = useState<DataModelSummary[]>([]);
  const [model, setModel] = useState<DataModel | null>(null);
  const [readingModel, setReadingModel] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const operation = useRef<AbortController | null>(null);
  const busy = readingModel || processing;
  const savedCheck = check?.model.id === modelId ? check : null;
  const preview = useMemo(() => model && metadata.length ? evaluateDataModel(model, metadata) : null, [model, metadata]);
  const result = preview || savedCheck?.result;
  const available = catalog.filter(item => item.service === service &&
    (allMachines || dataModelMachineKey(item.machine) === dataModelMachineKey(machine)))
    .sort((a, b) => Number(!!b.fixed) - Number(!!a.fixed) || a.machine.localeCompare(b.machine));

  useEffect(() => {
    const request = new AbortController();
    void fetch('/api/nami/data-models', {signal: request.signal}).then(read)
      .then(value => {if (!request.signal.aborted) setCatalog(value);})
      .catch(reason => {if (!request.signal.aborted) setError(reason.message);});
    return () => request.abort();
  }, []);
  useEffect(() => {
    if (modelId) return;
    const fixed = catalog.find(item => item.fixed && item.service === service &&
      dataModelMachineKey(item.machine) === dataModelMachineKey(machine));
    if (fixed) onSelectionChange({...selection, modelId: fixed.id});
  }, [catalog, machine, modelId, service, selection, onSelectionChange]);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => {if (event.key === 'Escape') onClose();};
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [onClose]);
  useEffect(() => {
    setModel(null);
    setReadingModel(false);
    setError('');
    if (!modelId) return;
    const request = new AbortController();
    setReadingModel(true);
    void fetch('/api/nami/data-models/' + modelId, {signal: request.signal}).then(read)
      .then(value => {if (!request.signal.aborted) setModel(value);})
      .catch(reason => {if (!request.signal.aborted) setError(reason.message);})
      .finally(() => {if (!request.signal.aborted) setReadingModel(false);});
    return () => request.abort();
  }, [modelId]);
  // Closing the window or changing inputs cancels an unfinished check/import.
  useEffect(() => () => {operation.current?.abort();}, [modelId, metadata, machine]);

  const runCheck = async () => {
    if (!model || !metadata.length) return;
    operation.current?.abort();
    const request = new AbortController();
    operation.current = request;
    setProcessing(true);
    setError('');
    onChecked(null);
    try {
      const value: DataModelResult = await read(await fetch('/api/nami/data-models/' + model.id + '/validate', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({metadata}), signal: request.signal,
      }));
      if (!request.signal.aborted) onChecked({model, result: value, validatedAt: new Date().toISOString()});
    } catch (reason) {
      if (!request.signal.aborted) setError(reason instanceof Error ? reason.message : 'Validation failed.');
    } finally {
      if (operation.current === request) setProcessing(false);
    }
  };
  const upload = async (file: File) => {
    operation.current?.abort();
    const request = new AbortController();
    operation.current = request;
    setProcessing(true);
    setError('');
    const form = new FormData();
    form.append('file', file);
    form.append('service', service);
    form.append('machine', machine);
    try {
      const imported: DataModel = await read(await fetch('/api/nami/data-models/import', {method: 'POST', body: form, signal: request.signal}));
      if (request.signal.aborted) return;
      setCatalog(previous => [...previous.filter(item => item.id !== imported.id), {
        ...imported, parameterCount: imported.parameters.length, warningCount: imported.warnings.length,
      }]);
      onSelectionChange({...selection, modelId: imported.id});
    } catch (reason) {
      if (!request.signal.aborted) setError(reason instanceof Error ? reason.message : 'Could not import the model.');
    } finally {
      if (operation.current === request) setProcessing(false);
    }
  };
  const downloadResult = () => {
    if (!result) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify({
      metadataSource: machine, validatedAt: preview ? null : savedCheck?.validatedAt || null,
      lastSavedAt: savedCheck?.validatedAt || null, checkMode: preview ? 'automatic' : 'saved', ...result,
    }, null, 2)], {type: 'application/json'}));
    const link = document.createElement('a');
    link.href = url;
    link.download = machine.replace(/[^\w-]/g, '_') + '_' + service + '_data_model_check.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const rows = (result?.rows || model?.parameters || []).filter(row =>
    (status === 'all' || row.status === status || row.kind === status) &&
    JSON.stringify([row.name, row.sheet, row.formula, row.groupCodes]).toLowerCase().includes(search.toLowerCase()));

  return <div className="dataModelBackdrop"><section className="dataModelWindow" role="dialog" aria-modal="true" aria-labelledby="data-model-title">
    <header><div><h2 id="data-model-title">Data model requirements</h2><p>{dataModelDepartmentLabel(machine)} · Fixed development-team references and loaded PLC metadata.</p></div><button aria-label="Close data model requirements" onClick={onClose}>×</button></header>
    <div className="dataModelTools">
      <label>Service<select aria-label="Data model service" value={service} disabled={processing} onChange={event => onSelectionChange({...selection, service: event.target.value, modelId: ''})}><option>PMS</option><option>QMS</option><option>CMS</option></select></label>
      <label><input type="checkbox" checked={allMachines} disabled={processing} onChange={event => onSelectionChange({...selection, allMachines: event.target.checked, modelId: ''})}/>Show other departments</label>
      <label>Department data model<select aria-label="Reference data model" value={modelId} disabled={processing} onChange={event => onSelectionChange({...selection, modelId: event.target.value})}><option value="">Choose department model</option>{available.map(item => <option key={item.id} value={item.id}>{dataModelDepartmentLabel(item.machine)} · {item.fixed ? 'Fixed' : 'Additional reference'} · {item.source} · {item.parameterCount} entries</option>)}
        {model && !available.some(item => item.id === model.id) && <option value={model.id}>{dataModelDepartmentLabel(model.machine)} · Saved reference · {model.source}</option>}
      </select></label>
    </div>
    <p>Uppercase and lowercase names are equivalent. Words, punctuation, Group Code and datatype must match. FLOAT maps to REAL; NCHAR/VARCHAR map to STRING. Server-generated IDs, timestamps and host fields are skipped. Calculated fields are shown for reference. Conflicting source definitions and database types without a PLC wire type require reference review; they do not prove a PLC failure.</p>
    <p>The Data model column groups the parameter name, services and result. All fixed services for the current department remain visible. Missing required parameters are listed here and above the parameter table.</p>
    <details><summary>Import an additional reference</summary><label className="dataModelUpload">XLSX / database JSON<input type="file" accept=".xlsx,.json" disabled={busy} onChange={event => {const file = event.target.files?.[0]; if (file) void upload(file); event.target.value = '';}}/></label></details>
    <div className="dataModelTools">
      <button disabled={!model || !metadata.length || busy} onClick={() => void runCheck()}>{busy ? 'Processing...' : 'Save check to history'}</button>
      {model && <a href={'/api/nami/data-models/' + model.id + '/download'} download>Download database JSON</a>}
      {result && <button onClick={downloadResult}>Download check JSON</button>}
      <label>Find<input aria-label="Search model parameters" value={search} onChange={event => setSearch(event.target.value)}/></label>
      <label>Show<select aria-label="Data model result filter" value={status} onChange={event => setStatus(event.target.value)}><option value="all">All entries</option>{['FAIL', 'PASS', 'UNRESOLVED', 'DERIVED', 'SKIPPED', 'OPTIONAL'].map(value => <option key={value}>{value}</option>)}</select></label>
    </div>
    {!metadata.length && <p>Load the machine metadata to check requirements.</p>}
    {error && <p role="alert" className="dataModelError">{error}</p>}
    {result && <p role="status"><strong>{result.status}</strong> · {preview ? 'Current metadata check' : 'Saved check'} · {Object.entries(result.summary).map(([key, value]) => key + ': ' + value).join(' · ')}{savedCheck && <> · Last saved {new Date(savedCheck.validatedAt).toLocaleString()}</>}</p>}
    {model?.warnings.length ? <details><summary>{model.warnings.length} reference warnings</summary>{model.warnings.map((warning, index) => <p key={index}>{warning}</p>)}</details> : null}
    <div className="dataModelTableScroll"><table><thead><tr><th>Reference parameter name</th><th>Data type → PLC</th><th>Group Code</th><th>Source / collection / row</th><th>Result</th><th>Details / formula / actual metadata</th></tr></thead>
      <tbody>{rows.map((row, index) => <tr key={index} data-status={row.status || row.kind}><td>{row.name || 'Missing name'}</td><td>{row.dataType || 'Not specified'} → {row.reasonCodes?.some(code => code === 'REFERENCE_CONFLICT' || code === 'REFERENCE_TYPE_UNSUPPORTED') ? 'PLC type requires review' : row.plcType || 'Unresolved'}</td><td>{row.groupCodes.join(', ') || 'Not specified'}</td><td>{model?.sourceRelativePath || row.source}<br/>{row.sheet}:{row.row}
        {!!row.excelReferences?.length && <details><summary>Excel reference</summary>{row.excelReferences.map((source, number) => <div key={number}>{source.source} / {source.sheet}:{source.row}{source.dataType && ` · ${source.dataType}`}</div>)}</details>}
      </td><td>{row.status ? dataModelResultLabel(row) : row.kind}</td><td>{row.detail}{row.formula && <pre>{row.formula}</pre>}{row.actual?.map((item, i) => <div key={i}>{item.parameter} · GC {item.groupCode} · {item.dataType} · Tag {item.tagCode}</div>)}</td></tr>)}</tbody>
    </table>{!rows.length && <p>{busy ? 'Reading model...' : model ? 'No entries match this filter.' : 'No fixed model for this department and service. Select or import a reference.'}</p>}</div>
  </section></div>;
}
