import {MetadataItem, GroupResponseData} from '../types';
import {parsePLCResponse, parseGroupValues} from './packetParser';
import {getExpectedGroupPayloadLength} from './metadataParser';

export function decodeManualReceive(text: string, groupCode: number, metadata: MetadataItem[], littleEndian: boolean, machineId: number): GroupResponseData {
  const tokens = text.trim().split(/[\s,;\[\]]+/).filter(Boolean);
  if (!tokens.length) throw new Error('Paste the received decimal bytes first.');
  const bytes = tokens.map((token, index) => {
    if (!/^\d+$/.test(token) || Number(token) > 255) throw new Error(`Byte ${index}: "${token}" is not a decimal byte (0..255).`);
    return Number(token);
  });
  const frame = parsePLCResponse(bytes, machineId);
  if (!frame.success) throw new Error(frame.error || 'Invalid response frame.');
  if (bytes.length !== frame.dataLength + 7) throw new Error(`Expected one complete frame of ${frame.dataLength + 7} bytes; received ${bytes.length}.`);
  const items = metadata.filter(item => item.groupCode === groupCode);
  if (!items.length) throw new Error('Select a group present in the loaded metadata.');
  const expectedLength = getExpectedGroupPayloadLength(items);
  return {
    groupCode, success: true, resultCode: frame.resultCode, dataLength: frame.dataLength,
    expectedLength, lengthMatch: frame.dataLength >= expectedLength,
    rawBytes: bytes, rawHex: bytes.map(b => b.toString(16).padStart(2, '0')).join(' '),
    rttMs: 0, timestamp: new Date().toLocaleTimeString(), completedAt: Date.now(),
    parsedValues: parseGroupValues(frame.dataBytes, items, littleEndian),
    source: 'manual', stage: 'manual', tcpConnected: false,
  };
}
