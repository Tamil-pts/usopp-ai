import React from 'react';
import { X, CheckCircle2, AlertTriangle, Download, FileText, Activity } from 'lucide-react';
import { MetadataItem, GroupResponseData, PLCConfig } from '../types';
import { exportVerificationExcel } from '../utils/metadataParser';
import {groupOutcome} from '../utils/groupResult';
import {buildDataModelRowChecks, buildDataModelRowReferences, checkedDataModels, unavailableDataModelParameters, metadataRowKey, type DataModelCheck, type DataModelReferenceData} from '../utils/dataModelChecks';

interface TestReportModalProps {
  isOpen: boolean;
  onClose: () => void;
  plc: PLCConfig;
  metadata: MetadataItem[];
  groupResponses: Record<number, GroupResponseData>;
  dataModelCheck: DataModelCheck | null;
  dataModelReferences: DataModelReferenceData;
}

export const TestReportModal: React.FC<TestReportModalProps> = ({
  isOpen,
  onClose,
  plc,
  metadata,
  groupResponses,
  dataModelCheck,
  dataModelReferences,
}) => {
  if (!isOpen) return null;

  const testIds = [...new Set(Object.values(groupResponses).map(row => row.testId).filter(Boolean))];
  const reportName = testIds.length === 1 ? testIds[0] : `${plc.name}_Collected_Tests`;

  const distinctGroupCodes: number[] = Array.from(new Set<number>(metadata.map((m) => m.groupCode))).sort((a, b) => a - b);

  let totalParamsTested = 0;
  let inRangeCount = 0;
  let outOfRangeCount = 0;
  let groupsTestedCount = 0;
  let groupsSuccessCount = 0;

  // Flatten all parsed parameter values
  const allLiveValues: Record<number, any> = {};

  for (const gc of distinctGroupCodes) {
    const resp = groupResponses[gc];
    if (resp) {
      if (groupOutcome(resp) !== 'skipped') groupsTestedCount++;
      if (groupOutcome(resp) === 'passed') groupsSuccessCount++;
      if (resp.success && resp.lengthMatch && resp.parsedValues) {
        for (const pv of resp.parsedValues) {
          if (pv.rawValue === null) continue;
          allLiveValues[pv.tagCode] = pv;
          totalParamsTested++;
          if (pv.isInRange) inRangeCount++;
          else outOfRangeCount++;
        }
      }
    }
  }

  const handleDownloadExcel = () => {
    const bytes = exportVerificationExcel(metadata, allLiveValues, undefined, dataModelCheck, dataModelReferences, groupResponses);
    const blob = new Blob([bytes], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${reportName}_Verification_Report.xlsx`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleDownloadJSON = () => {
    const modelRows = buildDataModelRowChecks(metadata, dataModelCheck, dataModelReferences.models);
    const references = buildDataModelRowReferences(metadata, dataModelReferences.models, dataModelCheck);
    const reportData = {
      testIds,
      targetPLC: plc,
      timestamp: new Date().toISOString(),
      dataModelCheck,
      dataModelRequirements: checkedDataModels(metadata, dataModelReferences.models, dataModelCheck).map(({model, result}) => ({
        service: model.service, department: model.machine,
        checkMode: 'Current metadata evaluation', referenceScope: dataModelReferences.snapshot ? 'Saved reference snapshot' : 'Current department references',
        source: model.sourceRelativePath || model.source, fixed: !!model.fixed, ...result,
      })),
      unavailableDataModelParameters: unavailableDataModelParameters(metadata, dataModelReferences.models, dataModelCheck),
      dataModelReferenceSource: {
        loading: dataModelReferences.loading,
        error: dataModelReferences.error,
        snapshot: !!dataModelReferences.snapshot,
        models: dataModelReferences.models.map(model => ({id: model.id, source: model.sourceRelativePath || model.source, service: model.service, machine: model.machine, fixed: !!model.fixed})),
      },
      summary: {
        totalGroups: distinctGroupCodes.length,
        groupsTested: groupsTestedCount,
        groupsSuccessful: groupsSuccessCount,
        totalParamsTested,
        passedDataChecks: inRangeCount,
        failedDataChecks: outOfRangeCount,
      },
      groups: distinctGroupCodes.map((gc) => ({
        groupCode: gc,
        response: groupResponses[gc] || null,
        parameters: metadata.filter((m) => m.groupCode === gc).map(item => ({
          ...item,
          dataModelReferences: references.get(metadataRowKey(item)) || [],
          dataModelCheck: modelRows.get(metadataRowKey(item)) || {
            status: dataModelReferences.loading ? 'Loading references' : dataModelReferences.error ? 'References unavailable' : 'No matching reference for this department', requirements: [],
          },
        })),
      })),
    };

    const blob = new Blob([JSON.stringify(reportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${reportName}_Report.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl max-w-3xl w-full flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-emerald-400" />
            <div>
              <h2 className="text-base font-bold text-white">PLC Verification Test Report</h2>
              <p className="text-xs text-slate-400">
                Summary of TCP frame decodes and metadata boundary checks for {plc.name}
              </p>
              <p className="text-xs text-slate-400 break-all">{testIds.length === 1 ? `Test ID: ${testIds[0]}` : `${testIds.length} tests collected; each group retains its own test ID in the report.`}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white p-1 rounded-md">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-5 overflow-y-auto">
          {/* Top Scorecard */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center text-xs">
            <div className="bg-slate-800/60 p-3 rounded-lg border border-slate-700">
              <div className="text-slate-400">Tested Groups</div>
              <div className="text-xl font-bold text-white mt-1 font-mono">
                {groupsSuccessCount} / {distinctGroupCodes.length}
              </div>
              <div className="text-[10px] text-emerald-400 mt-0.5">
                {Math.round((groupsSuccessCount / (distinctGroupCodes.length || 1)) * 100)}% Pass
              </div>
            </div>

            <div className="bg-slate-800/60 p-3 rounded-lg border border-slate-700">
              <div className="text-slate-400">Total Tag Values</div>
              <div className="text-xl font-bold text-teal-400 mt-1 font-mono">
                {totalParamsTested}
              </div>
              <div className="text-[10px] text-slate-400 mt-0.5">Decoded</div>
            </div>

            <div className="bg-slate-800/60 p-3 rounded-lg border border-slate-700">
              <div className="text-slate-400">Passed data checks</div>
              <div className="text-xl font-bold text-emerald-400 mt-1 font-mono">
                {inRangeCount}
              </div>
              <div className="text-[10px] text-emerald-400 mt-0.5">Validated Normal</div>
            </div>

            <div className="bg-slate-800/60 p-3 rounded-lg border border-slate-700">
              <div className="text-slate-400">Data quality failures</div>
              <div className={`text-xl font-bold mt-1 font-mono ${outOfRangeCount > 0 ? 'text-amber-400' : 'text-slate-400'}`}>
                {outOfRangeCount}
              </div>
              <div className="text-[10px] text-slate-400 mt-0.5">
                {outOfRangeCount > 0 ? 'Requires Check' : 'None'}
              </div>
            </div>
          </div>

          {/* Group Code Summary Table */}
          <div className="border border-slate-800 rounded-xl overflow-hidden text-xs">
            <table className="w-full text-left text-slate-300">
              <thead className="bg-slate-800 text-slate-400 font-semibold">
                <tr>
                  <th className="py-2.5 px-3">Group Code</th>
                  <th className="py-2.5 px-3">Screen Name</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3">Data Bytes</th>
                  <th className="py-2.5 px-3">Latency (RTT)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {distinctGroupCodes.map((gc) => {
                  const resp = groupResponses[gc];
                  const screen = metadata.find((m) => m.groupCode === gc)?.screenName || `Group ${gc}`;

                  return (
                    <tr key={gc} className="hover:bg-slate-800/30">
                      <td className="py-2 px-3 font-mono font-bold text-white">GC {gc}</td>
                      <td className="py-2 px-3 text-slate-300">{screen}</td>
                      <td className="py-2 px-3">
                        {resp ? (
                          groupOutcome(resp) === 'passed' ? (
                            <span className="text-emerald-400 flex items-center gap-1 font-semibold">
                              <CheckCircle2 className="w-3.5 h-3.5" /> OK (0)
                            </span>
                          ) : (
                            <span className="text-rose-400 flex items-center gap-1 font-semibold">
                              <AlertTriangle className="w-3.5 h-3.5" /> {groupOutcome(resp) === 'skipped' ? 'Not requested' : groupOutcome(resp) === 'mismatch' ? 'Metadata mismatch' : 'Read failed'}
                            </span>
                          )
                        ) : (
                          <span className="text-slate-500">Untested</span>
                        )}
                      </td>
                      <td className="py-2 px-3 font-mono">
                        {resp ? `${resp.dataLength}B` : '—'}
                      </td>
                      <td className="py-2 px-3 font-mono">
                        {resp ? `${resp.rttMs} ms` : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Footer actions */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-slate-800 bg-slate-900/50">
          <div className="flex items-center gap-2">
            <button
              onClick={handleDownloadExcel}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export Excel (.xlsx)</span>
            </button>
            <button
              onClick={handleDownloadJSON}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-lg border border-slate-700 transition-colors"
            >
              <FileText className="w-3.5 h-3.5" />
              <span>Export JSON</span>
            </button>
          </div>

          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
