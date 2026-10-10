import type {GroupResponseData, MetadataItem, PLCConfig} from '../types';
import type {DataModelCheck, DataModelReferenceData} from './dataModelChecks';
import {parsePLCResponse, parseGroupValues} from './packetParser';
import {getExpectedGroupPayloadLength} from './metadataParser';

export interface SavedInspectRun {
  testId: string;
  historyId: string;
  plc: PLCConfig;
  metadata: MetadataItem[];
  metadataSource: string;
  groupResponses?: Record<number, GroupResponseData>;
  results?: Array<Partial<GroupResponseData>>;
  groupCode?: number;
  dataModelCheck?: DataModelCheck;
  dataModelReferenceSource?: DataModelReferenceData;
  error?: string;
}

export function responsesForHistory(run: SavedInspectRun): Record<number, GroupResponseData> {
  if (run.groupResponses) return run.groupResponses;
  const rows = run.results || (run.groupCode !== undefined ? [run as unknown as Partial<GroupResponseData>] : []);
  return Object.fromEntries(rows.filter(row => row.groupCode !== undefined).map(row => {
    const groupCode = row.groupCode!;
    const raw = row.rawBytes || [];
    const frame = parsePLCResponse(raw, run.plc.machineId);
    const metadata = (run.metadata || []).filter(item => item.groupCode === groupCode);
    const expected = getExpectedGroupPayloadLength(metadata);
    const success = Boolean(row.success && frame.success);
    const response: GroupResponseData = {...row, groupCode, success, rawBytes: raw,
      resultCode: frame.resultCode, dataLength: frame.dataLength, expectedLength: expected,
      lengthMatch: frame.dataLength >= expected, rawHex: raw.map(byte => byte.toString(16).padStart(2, '0')).join(' '),
      rttMs: row.rttMs || 0, timestamp: row.timestamp || 'Saved test',
      error: row.error || frame.error, testId: run.testId, historyId: run.historyId,
      parsedValues: success ? parseGroupValues(frame.dataBytes, metadata, run.plc.endianness !== 'big') : []};
    return [groupCode, response];
  }));
}

export async function saveDecodedRun(identity: {historyId?: string; testId?: string},
  groups: Record<number, GroupResponseData>, check: DataModelCheck | null, references: DataModelReferenceData) {
  if (!identity.historyId) throw new Error('The server did not return a history ID.');
  const response = await fetch(`/api/nami/history/${encodeURIComponent(identity.historyId)}/decoded`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({groupResponses: groups, dataModelCheck: check, dataModelReferenceSource: references}),
  });
  if (!response.ok) throw new Error('Raw PLC data was saved, but decoded results could not be added to history.');
}
