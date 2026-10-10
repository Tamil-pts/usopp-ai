import React, { useEffect, useRef, useState } from 'react';
import { X, Upload, FileSpreadsheet, RefreshCw, CheckCircle2, AlertCircle, Layers, AlertTriangle } from 'lucide-react';
import { MetadataItem, SpinningMachineType } from '../types';
import { parseCSVMetadata, parseExcelWithDropdownReferences, analyzeMetadata, MetadataAnalysis, MetadataValidationError } from '../utils/metadataParser';

interface MetadataUploaderModalProps {
  isOpen: boolean;
  onClose: () => void;
  metadata: MetadataItem[];
  onMetadataLoaded: (items: MetadataItem[], sourceName: string, targetMachine?: SpinningMachineType) => void;
  onResetToDefault: () => void;
  currentSourceName: string;
  liveValues?: Record<number, any>;
  currentMachineType: SpinningMachineType;
  onSelectMachineType: (type: SpinningMachineType) => void;
}

export const MetadataUploaderModal: React.FC<MetadataUploaderModalProps> = ({
  isOpen,
  onClose,
  metadata,
  onMetadataLoaded,
  currentSourceName,
  currentMachineType,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [analysis, setAnalysis] = useState<MetadataAnalysis | null>(null);
  const [uploadedFileName, setUploadedFileName] = useState('');
  const [showAllGroups, setShowAllGroups] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setAnalysis(null);
    setUploadedFileName('');
    setMessage(null);
  }, [isOpen, currentMachineType]);

  if (!isOpen) return null;

  const handleFileProcess = async (file: File) => {
    setLoading(true);
    setMessage(null);
    setAnalysis(null);
    try {
      const lower = file.name.toLowerCase();
      let items: MetadataItem[];
      let sheet2Count = 0;

      if (lower.endsWith('.xlsx') || lower.endsWith('.xls')) {
        const result = parseExcelWithDropdownReferences(await file.arrayBuffer());
        items = result.items;
        sheet2Count = result.dropdownReferences.length;
      } else if (lower.endsWith('.csv') || lower.endsWith('.txt')) {
        items = parseCSVMetadata(await file.text());
      } else {
        throw new Error('Unsupported file. Upload .xlsx, .xls, or .csv.');
      }

      if (!items.length) throw new Error('No metadata rows were found in the uploaded file.');

      const report = analyzeMetadata(items, sheet2Count);
      setAnalysis(report);
      setUploadedFileName(file.name);

      const hardErrors = [
        ...report.unsupportedTypeErrors,
        ...report.invalidOffsetErrors,
        ...report.duplicateTagErrors,
        ...report.duplicateOffsetErrors,
      ];

      if (hardErrors.length > 0) {
        setMessage({
          type: 'error',
          text: `Metadata analysed but NOT activated. ${hardErrors.length} validation issue(s) found. Correct the file and upload again.`,
        });
        return;
      }

      onMetadataLoaded(items, file.name, currentMachineType);
      setMessage({
        type: 'success',
        text: `Metadata uploaded successfully: ${items.length} parameters, ${report.totalGroups} groups${sheet2Count ? `, ${sheet2Count} Sheet 2 mappings` : ''}.`,
      });
    } catch (err: any) {
      if (err instanceof MetadataValidationError && err.items?.length) {
        const report = analyzeMetadata(err.items, 0);
        setAnalysis(report);
        setUploadedFileName(file.name);
        const issues = err.issues?.length ? err.issues : [err.message];
        setMessage({ type: 'error', text: `Metadata analysed but NOT activated. ${issues.length} validation issue(s) found.` });
      } else {
        setMessage({ type: 'error', text: err?.message || 'Failed to read metadata file.' });
      }
    } finally {
      setLoading(false);
    }
  };

  const displayedGroups = analysis?.groupSummaries.slice(0, showAllGroups ? undefined : 12) || [];
  const errorCount = analysis
    ? analysis.duplicateTagErrors.length + analysis.duplicateOffsetErrors.length + analysis.overlapErrors.length + analysis.unsupportedTypeErrors.length + analysis.invalidOffsetErrors.length
    : 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl max-w-6xl w-full flex flex-col max-h-[94vh] overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-700 flex items-center justify-center text-white">
              <FileSpreadsheet className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white">NAmi Metadata Validator</h2>
              <p className="text-xs text-slate-400">Upload one metadata file and review its structure before using it.</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white"><X className="w-5 h-5" /></button>
        </div>

        <div className="overflow-y-auto p-6 space-y-5">
          <div className="flex items-center justify-between gap-3 p-3 rounded-xl bg-slate-800/50 border border-slate-700">
            <div>
              <div className="text-xs text-slate-400">Selected machine</div>
              <div className="text-sm font-bold text-white">{currentMachineType}</div>
            </div>
            <div className="text-right min-w-0">
              <div className="text-xs text-slate-400">Current metadata</div>
              <div className="text-xs font-mono text-slate-300 truncate max-w-[420px]">{currentSourceName}</div>
            </div>
          </div>

          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); if (e.dataTransfer.files[0]) handleFileProcess(e.dataTransfer.files[0]); }}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${dragging ? 'border-emerald-500 bg-emerald-950/20' : 'border-slate-700 bg-slate-800/40 hover:border-emerald-600 hover:bg-slate-800/70'}`}
          >
            <input ref={fileInputRef} type="file" accept=".xlsx,.xls,.csv,.txt" className="hidden" onChange={(e) => { const f=e.target.files?.[0]; e.target.value=''; if(f) handleFileProcess(f); }} />
            <div className="flex flex-col items-center gap-2">
              <div className="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center text-emerald-400">
                {loading ? <RefreshCw className="w-6 h-6 animate-spin" /> : <Upload className="w-6 h-6" />}
              </div>
              <div className="text-sm font-semibold text-white">Upload metadata file for {currentMachineType}</div>
              <div className="text-xs text-slate-400">.xlsx / .xls / .csv • Excel Sheet 1 = Parameters, Sheet 2 = Dropdown Reference (optional)</div>
            </div>
          </div>

          {uploadedFileName && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-950/40 border border-emerald-800 text-emerald-300 text-xs">
              <CheckCircle2 className="w-4 h-4" />
              <span>Uploaded file:</span>
              <strong className="font-mono text-white truncate">{uploadedFileName}</strong>
            </div>
          )}

          {message && (
            <div className={`p-3 rounded-xl text-xs flex items-start gap-2 ${message.type === 'success' ? 'bg-emerald-950/60 border border-emerald-800 text-emerald-300' : 'bg-rose-950/70 border border-rose-800 text-rose-300'}`}>
              {message.type === 'success' ? <CheckCircle2 className="w-4 h-4 shrink-0" /> : <AlertCircle className="w-4 h-4 shrink-0" />}
              <span>{message.text}</span>
            </div>
          )}

          {analysis && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                {[
                  ['Parameters', analysis.totalParameters, 'text-white'],
                  ['Group Codes', analysis.totalGroups, 'text-emerald-400'],
                  ['Screen Modules', analysis.totalScreens, 'text-cyan-400'],
                  ['Sheet 2 Mappings', analysis.sheet2Mappings, 'text-indigo-300'],
                  ['Issues', errorCount, errorCount ? 'text-rose-400' : 'text-emerald-400'],
                ].map(([label, value, cls]) => (
                  <div key={String(label)} className="bg-slate-950/70 border border-slate-800 rounded-xl p-3 text-center">
                    <div className={`text-xl font-bold ${cls}`}>{value}</div>
                    <div className="text-[11px] text-slate-400">{label}</div>
                  </div>
                ))}
              </div>

              <div className="bg-slate-950/70 border border-slate-800 rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
                  <div className="flex items-center gap-2"><Layers className="w-4 h-4 text-emerald-400" /><span className="text-sm font-semibold text-white">Group Code Packet Analysis</span></div>
                  <span className="text-xs text-slate-400">Expected minimum payload length • overlaps are warnings</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-slate-900 text-slate-400">
                      <tr><th className="text-left px-4 py-2">Group</th><th className="text-left px-4 py-2">Parameters</th><th className="text-left px-4 py-2">Packet Payload</th><th className="text-left px-4 py-2">Data Types</th><th className="text-left px-4 py-2">Duplicate</th></tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
                      {displayedGroups.map(g => {
                        const dup = g.duplicateTagCodes.length + g.duplicateOffsets.length + g.overlappingRanges.length;
                        return <tr key={g.groupCode}>
                          <td className="px-4 py-2 font-mono font-bold text-emerald-300">GC {g.groupCode}</td>
                          <td className="px-4 py-2 text-slate-300">{g.parameterCount}</td>
                          <td className="px-4 py-2 font-mono text-cyan-300">{g.expectedPayloadLength} bytes</td>
                          <td className="px-4 py-2 text-slate-400">{g.dataTypes.join(', ')}</td>
                          <td className={`px-4 py-2 ${dup ? 'text-rose-400' : 'text-emerald-400'}`}>{dup ? `${dup} issue(s)` : 'OK'}</td>
                        </tr>;
                      })}
                    </tbody>
                  </table>
                </div>
                {analysis.groupSummaries.length > 12 && <button onClick={() => setShowAllGroups(v=>!v)} className="m-3 px-3 py-1.5 text-xs rounded-lg bg-slate-800 text-slate-200 border border-slate-700">{showAllGroups ? 'Show first 12 groups' : `Show all ${analysis.groupSummaries.length} groups`}</button>}
              </div>

              {errorCount > 0 && (
                <div className="bg-rose-950/30 border border-rose-800 rounded-xl p-4">
                  <div className="flex items-center gap-2 text-rose-300 text-sm font-semibold mb-2"><AlertTriangle className="w-4 h-4" /> Validation issues</div>
                  <div className="space-y-1 max-h-48 overflow-y-auto text-xs text-rose-200">
                    {[...analysis.unsupportedTypeErrors, ...analysis.invalidOffsetErrors, ...analysis.duplicateTagErrors, ...analysis.duplicateOffsetErrors, ...analysis.overlapErrors].map((e,i)=><div key={i}>• {e}</div>)}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        <div className="flex items-center justify-end px-6 py-4 border-t border-slate-800">
          <button onClick={onClose} className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg">Done</button>
        </div>
      </div>
    </div>
  );
};
