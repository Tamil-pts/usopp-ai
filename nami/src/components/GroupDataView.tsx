import React, { useState } from 'react';
import { RefreshCw, CheckCircle2, AlertTriangle, AlertCircle, Binary, Copy, Check, ListFilter, Pencil } from 'lucide-react';
import { MetadataItem, GroupResponseData, ParsedParamValue } from '../types';
import {formatDecodedValue} from '../utils/valueDisplay';
import {metadataRowKey, groupDataModelReferences, type DataModelCheck, type DataModelReference, type DataModelReferenceData} from '../utils/dataModelChecks';
import {DataModelReferenceCell} from './DataModelReferenceCell';

interface GroupDataViewProps {
  groupCode: number;
  metadataItems: MetadataItem[];
  responseData?: GroupResponseData;
  onPollGroup: (code: number) => void;
  isPolling: boolean;
  readOnly?: boolean;
  searchQuery: string;
  dataModelCheck: DataModelCheck | null;
  missingDataModelParameters: DataModelReference[];
  dataModelReferences: Map<string, DataModelReference[]>;
  referenceData: DataModelReferenceData;
  onOpenDataModels: () => void;
  onEditParameter?: (item: MetadataItem) => void;
}

export const GroupDataView: React.FC<GroupDataViewProps> = ({
  groupCode,
  metadataItems,
  responseData,
  onPollGroup,
  isPolling,
  readOnly = false,
  searchQuery,
  dataModelCheck,
  missingDataModelParameters,
  dataModelReferences,
  referenceData,
  onOpenDataModels,
  onEditParameter,
}) => {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [filterMode, setFilterMode] = useState<'all' | 'outOfRange' | 'warnings'>('all');

  const screenName = metadataItems[0]?.screenName || `Group Code ${groupCode}`;
  const unavailable = groupDataModelReferences(missingDataModelParameters.filter(row =>
    row.groupCodes.includes(groupCode) && row.name.toLowerCase().includes(searchQuery.toLowerCase().trim())));
  const services = [...new Set(referenceData.models.map(model => model.service))];

  // Filter items if searching
  const filteredItems = metadataItems.filter((m) => {
    if (searchQuery.trim() === '') return true;
    const q = searchQuery.toLowerCase();
    return (
      m.parameter.toLowerCase().includes(q) ||
      m.tagCode.toString().includes(q) ||
      m.dataType.toLowerCase().includes(q) ||
      m.units.toLowerCase().includes(q)
    );
  });

  // Calculate parsed values map
  const parsedMap = new Map<number, ParsedParamValue>();
  if (responseData?.parsedValues) {
    for (const val of responseData.parsedValues) {
      parsedMap.set(val.tagCode, val);
    }
  }

  // Range checks stats
  let totalParams = metadataItems.length;
  let outOfRangeCount = 0;
  let validCount = 0;

  for (const item of metadataItems) {
    const p = parsedMap.get(item.tagCode);
    if (p && p.rawValue !== null && responseData?.success && responseData.lengthMatch) {
      if (!p.isInRange) outOfRangeCount++;
      else validCount++;
    }
  }

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 1500);
  };

  // Special Alarm bit decoder for Group 30 (Fault History)
  const isYbs = metadataItems[0]?.protocol==='ybs';
  const isGroup30Alarms = groupCode === 30 && !isYbs;

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-slate-950 p-4 sm:p-6 overflow-y-auto">
      {/* Top Banner for Active Group */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 sm:p-5 mb-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="px-2.5 py-1 text-xs font-bold rounded-lg bg-emerald-950 border border-emerald-800 text-emerald-400 font-mono">
                GROUP CODE: {groupCode}
              </span>
              <h2 className="text-lg font-bold text-white tracking-tight">{screenName}</h2>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Mapped {totalParams} parameters • Offsets from 0 to {Math.max(0, ...metadataItems.map(m => m.offset))} bytes
            </p>
          </div>

          {responseData?.testId && <p className="text-xs text-slate-400 font-mono break-all">Test ID: {responseData.testId}</p>}
          <div className="flex flex-wrap items-center gap-3">
            {/* Poll this group button */}
            <button
              onClick={() => onPollGroup(groupCode)}
              disabled={isPolling || readOnly}
              className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-semibold rounded-lg shadow-sm transition-all"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isPolling ? 'animate-spin' : ''}`} />
              <span>{isPolling ? 'Reading Socket...' : 'Read Group Data'}</span>
            </button>
          </div>
        </div>

        {/* Diagnostic Status metrics */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4 pt-4 border-t border-slate-800/80 text-xs">
          <div className="bg-slate-800/50 p-3 rounded-lg border border-slate-800">
            <div className="text-slate-400">Response Status</div>
            <div className="text-sm font-semibold mt-0.5 flex items-center gap-1.5">
              {responseData ? (
                responseData.success ? (
                  <>
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                    <span className={responseData.lengthMatch ? 'text-emerald-400' : 'text-amber-400'}>{responseData.lengthMatch ? 'Response received' : 'Metadata mismatch'}</span>
                  </>
                ) : (
                  <>
                    <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
                    <span className="text-rose-400">{responseData.stage === 'not_sent' ? 'Not requested' : responseData.rawBytes.length ? `Error ${responseData.resultCode}` : 'No PLC data'}</span>
                  </>
                )
              ) : (
                <span className="text-slate-500">Not Read Yet</span>
              )}
            </div>
          </div>

          <div className="bg-slate-800/50 p-3 rounded-lg border border-slate-800">
            <div className="text-slate-400">Payload Length</div>
            <div className="text-sm font-semibold mt-0.5 text-white font-mono">
              {responseData ? (
                <span>
                  {responseData.dataLength} bytes{' '}
                  <span className="text-[11px] text-slate-400">
                    ({responseData.rawBytes.length} frame total)
                  </span>
                </span>
              ) : (
                <span className="text-slate-500">—</span>
              )}
            </div>
          </div>

          <div className="bg-slate-800/50 p-3 rounded-lg border border-slate-800">
            <div className="text-slate-400">Round Trip Time (RTT)</div>
            <div className="text-sm font-semibold mt-0.5 text-white font-mono">
              {responseData ? `${responseData.rttMs} ms` : '—'}
            </div>
          </div>

          <div className="bg-slate-800/50 p-3 rounded-lg border border-slate-800">
            <div className="text-slate-400">Data quality</div>
            <div className="text-sm font-semibold mt-0.5 flex items-center gap-2">
              <span className="text-emerald-400">{validCount} Passed</span>
              {outOfRangeCount > 0 && (
                <span className="text-amber-400 font-bold">{outOfRangeCount} Failed</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {responseData && <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 mb-5 text-xs space-y-2">
        {responseData.success && !responseData.lengthMatch && <p className="text-amber-300 font-semibold">GC {groupCode} returned {responseData.dataLength} payload bytes; the metadata requires {isYbs?'exactly':'at least'} {responseData.expectedLength}. Check that this workbook matches the device program and its offsets.</p>}
        {responseData.error && <p className="text-rose-300 font-semibold">{responseData.error}</p>}
        <p className="text-slate-300">{responseData.source === 'manual' ? 'Offline manual frame; no TCP request was sent.' : responseData.tcpConnected
          ? 'TCP connection opened for this test.' : responseData.stage === 'connect'
          ? 'TCP connection could not be opened.' : 'Request diagnostics'}</p>
        <details className="text-slate-400">
          <summary className="cursor-pointer text-emerald-400">{responseData.source === 'manual' ? 'View manual frame details' : isYbs?'View request and local TCP closure':'View request and GC 11 closure'}</summary>
          <div className="mt-2 space-y-1 font-mono break-all">
            <p>Stage: {responseData.stage || 'response'} · Log ID: {responseData.traceId || '—'}</p>
            <p>Sent ({responseData.sentBytes?.length || 0} bytes): {responseData.sentBytes?.map((byte) => byte.toString(16).padStart(2, '0')).join(' ') || 'No request confirmed sent'}</p>
            <p>Received: {responseData.rawBytes.length} bytes</p>
            {responseData.source !== 'manual' && !isYbs && <p>GC 11: {responseData.closeResult?.sentBytes?.length ? 'Sent' : 'Not confirmed sent'} · PLC closed: {responseData.closeResult?.plcClosed ? 'Confirmed' : 'Not confirmed'}</p>}
            {(responseData.closeResult?.warning || responseData.closeResult?.error) && <p className="text-amber-300">{responseData.closeResult.warning || responseData.closeResult.error}</p>}
          </div>
        </details>
      </div>}

      {/* Special Bit Inspector for Group 30 Alarms */}
      {isGroup30Alarms && responseData?.success && responseData.rawBytes.length > 0 && (
        <div className="bg-slate-900/90 border border-amber-500/30 rounded-xl p-4 mb-5 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <Binary className="w-4 h-4 text-amber-400" />
            <h3 className="text-sm font-bold text-amber-300">
              Group 30 Alarm Bit Inspector (CARD_WOCC_ALARM Bits 0..131)
            </h3>
            <span className="text-xs text-slate-400 ml-auto font-mono">16 Fault Bytes Packed</span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-8 gap-2">
            {Array.from({ length: Math.max(0, responseData.dataLength) }).map((_, byteIdx) => {
              const byteVal = responseData.rawBytes[5 + byteIdx] || 0;
              const hasActiveBit = byteVal > 0;
              return (
                <div
                  key={byteIdx}
                  className={`p-2 rounded-lg border text-xs font-mono ${
                    hasActiveBit
                      ? 'bg-amber-950/40 border-amber-600/70 text-amber-200'
                      : 'bg-slate-800/50 border-slate-700 text-slate-400'
                  }`}
                >
                  <div className="text-[10px] text-slate-400 flex justify-between">
                    <span>Byte {byteIdx + 1}</span>
                    <span>0x{byteVal.toString(16).padStart(2, '0')}</span>
                  </div>
                  <div className="text-xs font-bold tracking-wider mt-1">
                    {byteVal.toString(2).padStart(8, '0')}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1">
                    Bits {byteIdx * 8}..{byteIdx * 8 + 7}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Parameter Table */}
      {isYbs&&<p className="text-xs text-slate-400 mb-3">YBS: actual = raw / division factor × multiplication factor. Offsets follow worksheet order and require the matching device layout. Source rows and original wire types are retained; missing bytes are unavailable.</p>}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
        <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
          <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
            Parameter Data Mapping ({filteredItems.length} items)
          </h3>
          <span className="text-xs text-slate-400">
            Byte offsets and IEEE 754 / Integer / Boolean decodings
          </span>
        </div>

        <div className="px-4 py-2 border-b border-slate-800 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400">
          {dataModelCheck ? <span role="status">
            <strong className="text-white">Current metadata evaluation</strong>
            {' · '}Last saved check: {dataModelCheck.model.service} · {new Date(dataModelCheck.validatedAt).toLocaleString()}
          </span> : <span>Data model checks run automatically against the loaded metadata.</span>}
          <button type="button" onClick={onOpenDataModels} className="text-emerald-400 underline">
            Review requirements / missing parameters
          </button>
        </div>
        <div className="px-4 py-2 border-b border-slate-800 text-[11px] text-slate-400" role="status">
          {referenceData.loading ? 'Reading fixed data models...' :
            referenceData.error ? <span className="text-amber-400">{referenceData.error}</span> :
            services.length ? (referenceData.snapshot ? 'Saved reference snapshot: ' : 'Current department references: ') + services.join(', ') + '. Names ignore letter case. Each result applies to its stated Group Code; requirements for other groups are listed separately. Reference conflicts require review and do not indicate a PLC failure.' : 'No fixed data model is available for this department.'}
        </div>
        {!!unavailable.length && <details className="px-4 py-3 border-b border-slate-800 text-xs">
          <summary className="cursor-pointer text-amber-400">Unavailable data model parameters in GC {groupCode} ({unavailable.length})</summary>
          <div className="mt-3 space-y-3 max-h-64 overflow-y-auto">{unavailable.map((group, index) => <div key={index}>
            <div className="font-medium text-white">{group.name}</div>
            <div className="text-slate-400">{group.services.join(', ')}</div>
            <div className={group.status === 'FAIL' ? 'text-rose-400' : 'text-amber-400'}>{group.label}</div>
            <div className="text-slate-400">{[...new Set(group.references.map(row => row.detail))].join(' ')}</div>
          </div>)}</div>
        </details>}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="bg-slate-800/60 text-slate-400 font-semibold border-b border-slate-800">
              <tr>
                <th className="py-2.5 px-3 w-14">Tag</th>
                <th className="py-2.5 px-3">Parameter Name</th>
                <th className="py-2.5 px-3 min-w-[210px]">Data model</th>
                <th className="py-2.5 px-3 w-24">Data Type</th>
                <th className="py-2.5 px-3 w-20">Offset</th>
                <th className="py-2.5 px-3">Decoded Value</th>
                <th className="py-2.5 px-3 w-20">Units</th>
                <th className="py-2.5 px-3 w-24 font-mono">Raw Hex</th>
                <th className="py-2.5 px-3 w-24">Min / Max (reference)</th>
                <th className="py-2.5 px-3 w-28 text-center">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-sans">
              {filteredItems.map((item) => {
                const parsed = parsedMap.get(item.tagCode);
                const hasValue = parsed && parsed.rawValue !== null;

                return (
                  <tr key={metadataRowKey(item)} className="di-parameter-row transition-colors">
                    <td className="py-2 px-3 font-mono text-slate-400">{item.tagCode}</td>
                    <td className="py-2 px-3">
                      <div className="font-medium text-white flex items-center gap-2">{item.parameter}
                        {item.isWritable && !readOnly && onEditParameter && <button type="button" disabled={isPolling}
                          onClick={()=>onEditParameter(item)} title="Edit writable PLC parameter" aria-label={`Edit ${item.parameter}`}
                          className="p-1 text-emerald-400 hover:text-emerald-200 disabled:opacity-50"><Pencil className="w-3.5 h-3.5"/></button>}
                      </div>
                      <div className="text-[10px] text-slate-500">{item.screenName}</div>
                      {item.sheet2NeedsReload && <div className="text-[11px] text-amber-400">Re-upload the workbook to restore Sheet2 shown values.</div>}
                      {item.dropdownOptions && item.dropdownOptions.length > 0 && (
                        <div
                          className="inline-flex items-center gap-1 mt-1 px-1.5 py-0.5 rounded text-[10px] bg-sky-950/80 text-sky-300 border border-sky-800/60"
                          title={`Sheet 2 Reference: ${item.dropdownOptions.map((o) => `${o.value}=${o.label}${o.machineVariant ? ` [${o.machineVariant}]` : ''}${o.isAlarm ? ' [ALARM]' : ''}`).join(', ')}`}
                        >
                          <ListFilter className="w-2.5 h-2.5 text-sky-400" />
                          <span>Sheet 2 Reference ({item.dropdownOptions.length} opts)</span>
                          {Array.from(new Set(item.dropdownOptions.map(o => o.machineVariant).filter(Boolean))).map(v => (
                            <span key={v} className="ml-1 px-1 rounded bg-slate-800 text-slate-300">{v}</span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="py-2 px-3 align-top">
                      <DataModelReferenceCell references={dataModelReferences.get(metadataRowKey(item)) || []} parameterName={item.parameter} loading={referenceData.loading} error={referenceData.error}/>
                    </td>
                    <td className="py-2 px-3">
                      <span className="px-1.5 py-0.5 rounded text-[11px] font-mono bg-slate-800 border border-slate-700 text-teal-300">
                        {item.dataType}
                      </span>
                    </td>
                    <td className="py-2 px-3 font-mono text-slate-300">+{item.offset}B</td>
                    <td className="py-2 px-3">
                      {hasValue ? (
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span
                            className={`font-semibold font-mono text-sm ${
                              !parsed.isInRange
                                ? 'text-amber-400 font-bold'
                                : 'text-emerald-300'
                            }`}
                          >
                            {formatDecodedValue(parsed.protocol==='ybs'?parsed.actualValue:parsed.rawValue)}
                          </span>
                          {parsed.protocol==='ybs'&&<span className="text-[10px] text-slate-400" title={`${item.sourceSheet}:${item.sourceRow}; worksheet order determines the offset`}>Raw {formatDecodedValue(parsed.rawValue)} / {item.divideFactor} × {item.multiplyFactor} · {item.wireDataType}</span>}
                          {parsed.dropdownText && (
                            <span className="px-2 py-0.5 rounded-full text-[11px] font-sans font-semibold bg-emerald-950/90 text-emerald-300 border border-emerald-700/80 shadow-xs">
                              {parsed.dropdownText}
                            </span>
                          )}
                          <button
                            onClick={() => handleCopy(parsed.formattedValue, `val-${item.tagCode}`)}
                            title="Copy Value"
                            className="p-1 text-slate-500 hover:text-slate-300 rounded cursor-pointer"
                          >
                            {copiedKey === `val-${item.tagCode}` ? (
                              <Check className="w-3 h-3 text-emerald-400" />
                            ) : (
                              <Copy className="w-3 h-3" />
                            )}
                          </button>
                        </div>
                      ) : (
                        <span className="text-slate-500 font-mono text-xs">{responseData
                          ? responseData.stage === 'not_sent' ? 'Not requested' : responseData.success ? 'Value unavailable' : 'No PLC data received'
                          : 'Waiting for read...'}</span>
                      )}
                    </td>
                    <td className="py-2 px-3 font-mono text-slate-400">{item.units || '—'}</td>
                    <td className="py-2 px-3 font-mono text-[11px] text-slate-400">
                      {hasValue ? parsed.rawHex : '—'}
                    </td>
                    <td className="py-2 px-3 font-mono text-[11px] text-slate-400">
                      {item.min !== null || item.max !== null ? (
                        <span>
                          [{item.min ?? '-∞'} .. {item.max ?? '+∞'}]
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="py-2 px-3 text-center">
                      {responseData?.success && !responseData.lengthMatch ? (
                        <span className="text-amber-400 text-[10px]">CHECK METADATA</span>
                      ) : hasValue ? (
                        parsed.isInRange ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-950 text-emerald-400 border border-emerald-800">
                            <CheckCircle2 className="w-3 h-3" /> PASS
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-amber-950 text-amber-400 border border-amber-800" title={parsed.qualityIssue}>
                            <AlertTriangle className="w-3 h-3" /> FAIL
                          </span>
                        )
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-800 text-slate-500">
                          {responseData ? responseData.stage === 'not_sent' ? 'SKIPPED' : 'UNAVAILABLE' : 'PENDING'}
                        </span>
                      )}
                      {parsed?.qualityIssue && <p className="text-xs text-amber-400 mt-1">{parsed.qualityIssue}</p>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
