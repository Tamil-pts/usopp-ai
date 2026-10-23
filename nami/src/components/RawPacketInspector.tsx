import React, { useState } from 'react';
import {
  Terminal,
  Copy,
  Check,
  CheckCircle2,
  AlertTriangle,
  ArrowUpRight,
  ArrowDownLeft,
  Info,
  HelpCircle,
  Sliders,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { GroupResponseData } from '../types';
import {YbsPacketInspector} from './YbsPacketInspector';
import { formatHexDump, buildReadGroupRequest } from '../utils/packetParser';

interface RawPacketInspectorProps {
  responseData?: GroupResponseData;
  groupCode: number;
  machineId?: number;
  isYbs?: boolean;
  onSwitchMachineId?: (newId: number) => void;
  onTestGroup?: (gc: number) => void;
  onOpenManualFrameEditor?: () => void;
}

export const RawPacketInspector: React.FC<RawPacketInspectorProps> = ({
  responseData,
  groupCode,
  machineId = 0,
  isYbs = false,
  onSwitchMachineId,
  onTestGroup,
  onOpenManualFrameEditor,
}) => {
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState<'both' | 'request' | 'response' | 'hexdump'>('both');
  const [isExpanded, setIsExpanded] = useState(false);

  // Compute standard 9-byte request frame that lands in PLC's nw_rcv_buffer
  const sentBytes = responseData?.sentBytes && responseData.sentBytes.length === 9
    ? responseData.sentBytes
    : Array.from(buildReadGroupRequest(machineId, groupCode));

  const reqStx = sentBytes[0];
  const reqMachineId = sentBytes[1];
  const reqFunc = sentBytes[2];
  const reqLenMsb = sentBytes[3];
  const reqLenLsb = sentBytes[4];
  const reqGcMsb = sentBytes[5];
  const reqGcLsb = sentBytes[6];
  const reqChecksum = sentBytes[7];
  const reqEtx = sentBytes[8];

  const hasResponse = responseData && responseData.rawBytes && responseData.rawBytes.length >= 7;
  const respBytes = responseData?.rawBytes || [];

  const respStx = respBytes[0];
  const respMachineId = respBytes[1];
  const respResultCode = respBytes[2];
  const respLengthMsb = respBytes[3];
  const respLengthLsb = respBytes[4];
  const respPayloadLen = (respLengthMsb << 8) | respLengthLsb;
  const respChecksum = respBytes[5 + respPayloadLen];
  const respEtx = respBytes[5 + respPayloadLen + 1];

  let calculatedXor = 0;
  if (hasResponse) {
    for (let i = 0; i < 5 + respPayloadLen; i++) {
      calculatedXor ^= respBytes[i];
    }
  }
  const checksumMatch = hasResponse && calculatedXor === respChecksum;
  const hexDumpText = hasResponse ? formatHexDump(respBytes) : '';
  const payloadBytes = hasResponse ? respBytes.slice(5, 5 + respPayloadLen) : [];
  const payloadHexText = payloadBytes.map((b, i) => `${i.toString().padStart(3, '0')}: ${b.toString(16).padStart(2, '0').toUpperCase()}`).join('\n');
  const payloadDecimalText = payloadBytes.map((b, i) => `${i.toString().padStart(3, '0')}: ${b}`).join('\n');

  const handleCopyHex = () => {
    const text = hasResponse
      ? `=== REQUEST (9 bytes to nw_rcv_buffer) ===\n${sentBytes.map(b => b.toString(16).padStart(2, '0').toUpperCase()).join(' ')}\n\n=== RESPONSE (${respBytes.length} bytes from nw_send_buffer) ===\n${hexDumpText}`
      : `=== REQUEST (9 bytes to nw_rcv_buffer) ===\n${sentBytes.map(b => b.toString(16).padStart(2, '0').toUpperCase()).join(' ')}`;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  if(isYbs||respBytes[0]===241)return <YbsPacketInspector response={responseData} group={groupCode} machine={machineId}/>;
  if (!isExpanded) {
    return (
      <div className="bg-slate-900 border-t border-slate-800 px-4 py-2 font-mono text-xs flex items-center justify-between gap-3 shadow-md hover:bg-slate-800/80 transition-colors">
        <button
          onClick={() => setIsExpanded(true)}
          className="flex items-center gap-2.5 text-left group cursor-pointer focus:outline-none"
          title="Click dropdown to expand TCP Socket Protocol Inspector"
        >
          <div className="p-1 rounded bg-slate-800 text-slate-400 group-hover:text-emerald-400 transition-colors">
            <ChevronDown className="w-4 h-4" />
          </div>
          <Terminal className="w-4 h-4 text-emerald-400" />
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-slate-200 group-hover:text-white uppercase tracking-wider text-xs">
              TCP Socket Protocol Inspector (Group {groupCode})
            </span>
            <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 border border-slate-700 text-slate-300">
              ID: <strong className="text-amber-400">{reqMachineId}</strong>
            </span>
            {hasResponse ? (
              <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-950/80 border border-emerald-800 text-emerald-300">
                {responseData.source === 'manual' ? 'Manual frame' : 'PLC Responded'} ({respBytes.length} bytes in {responseData.rttMs}ms)
              </span>
            ) : (
              <span className="px-2 py-0.5 rounded text-[10px] bg-amber-950/80 border border-amber-800 text-amber-300">
                Request Sent (Awaiting / No PLC Response)
              </span>
            )}
            <span className="text-[11px] text-slate-400 font-sans hidden md:inline">
              • Click to inspect raw byte array & frame diagnostics
            </span>
          </div>
        </button>

        <div className="flex items-center gap-2">
          {onOpenManualFrameEditor && (
            <button
              onClick={onOpenManualFrameEditor}
              className="flex items-center gap-1.5 px-2 py-1 bg-emerald-950/80 hover:bg-emerald-900 text-emerald-300 rounded border border-emerald-700/80 transition-colors font-sans text-xs cursor-pointer"
              title="Open Manual Frame Editor"
            >
              <Sliders className="w-3.5 h-3.5 text-emerald-400" />
              <span className="hidden sm:inline">Manual Frame Editor</span>
            </button>
          )}
          <button
            onClick={() => setIsExpanded(true)}
            className="flex items-center gap-1 px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded border border-slate-700 transition-colors font-sans text-xs cursor-pointer font-medium"
          >
            <span>Show Inspector</span>
            <ChevronDown className="w-3.5 h-3.5 text-emerald-400" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-slate-900/95 border-t border-slate-800 p-4 font-mono text-xs">
      {/* Inspector Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setIsExpanded(false)}
            className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-emerald-400 transition-colors cursor-pointer"
            title="Collapse Inspector"
          >
            <ChevronUp className="w-4 h-4" />
          </button>
          <Terminal className="w-4 h-4 text-emerald-400" />
          <h3 className="font-bold text-slate-200 uppercase tracking-wider text-xs">
            TCP Socket Protocol Inspector (Group {groupCode})
          </h3>
          <span className="px-2 py-0.5 rounded text-[11px] bg-slate-800 border border-slate-700 text-slate-300">
            Machine ID: <strong className="text-amber-400">{reqMachineId}</strong>
          </span>
          {hasResponse ? (
            <span className="px-2 py-0.5 rounded text-[11px] bg-emerald-950/80 border border-emerald-800 text-emerald-300">
              {responseData.source === 'manual' ? 'Manual frame' : 'PLC Responded'} ({respBytes.length} bytes in {responseData.rttMs}ms)
            </span>
          ) : (
            <span className="px-2 py-0.5 rounded text-[11px] bg-amber-950/80 border border-amber-800 text-amber-300">
              Request Sent (Awaiting / No PLC Response)
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <div className="flex rounded-lg bg-slate-800 p-0.5 border border-slate-700">
            <button
              onClick={() => setActiveTab('both')}
              className={`px-2.5 py-1 rounded text-[11px] font-sans font-medium transition-colors ${
                activeTab === 'both' ? 'bg-emerald-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              Request & Response
            </button>
            <button
              onClick={() => setActiveTab('request')}
              className={`px-2.5 py-1 rounded text-[11px] font-sans font-medium transition-colors ${
                activeTab === 'request' ? 'bg-emerald-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              Sent Frame (nw_rcv_buffer)
            </button>
            {hasResponse && (
              <>
                <button
                  onClick={() => setActiveTab('hexdump')}
                  className={`px-2.5 py-1 rounded text-[11px] font-sans font-medium transition-colors ${
                    activeTab === 'hexdump' ? 'bg-emerald-600 text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  Full Payload
                </button>
              </>
            )}
          </div>

          <button
            onClick={handleCopyHex}
            className="flex items-center gap-1 px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 transition-colors font-sans text-xs"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            <span>{copied ? 'Copied' : 'Copy Hex'}</span>
          </button>

          {onOpenManualFrameEditor && (
            <button
              onClick={onOpenManualFrameEditor}
              className="flex items-center gap-1.5 px-2.5 py-1 bg-emerald-950/80 hover:bg-emerald-900 text-emerald-300 rounded border border-emerald-700/80 transition-colors font-sans text-xs cursor-pointer"
              title="Open Manual Frame Editor to customize bytes and send over TCP"
            >
              <Sliders className="w-3.5 h-3.5 text-emerald-400" />
              <span>Manual Frame Editor</span>
            </button>
          )}

          <button
            onClick={() => setIsExpanded(false)}
            className="flex items-center gap-1 px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 transition-colors font-sans text-xs cursor-pointer"
            title="Hide / collapse Inspector"
          >
            <ChevronUp className="w-3.5 h-3.5 text-emerald-400" />
            <span>Hide</span>
          </button>
        </div>
      </div>

      {/* SECTION 1: REQUEST FRAME (Sent to PLC's nw_rcv_buffer) */}
      {responseData?.source !== 'manual' && (activeTab === 'both' || activeTab === 'request') && (
        <div className="mb-4 bg-slate-950/80 rounded-xl p-3 border border-slate-800">
          <div className="flex items-center justify-between gap-2 mb-2 pb-1.5 border-b border-slate-800/80">
            <div className="flex items-center gap-2">
              <ArrowUpRight className="w-4 h-4 text-sky-400" />
              <span className="font-semibold text-slate-200 text-xs">
                REQUEST FRAME SENT TO PLC (Stored in <code className="text-amber-300">nw_rcv_buffer[0..8]</code>)
              </span>
            </div>
            <div className="text-[11px] text-slate-400 font-mono">
              Raw bytes: [ {sentBytes.join(', ')} ]
            </div>
          </div>

          <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-9 gap-1.5 text-center">
            {/* STX */}
            <div className="bg-slate-900 border border-slate-800 rounded p-1.5">
              <div className="text-[9px] text-slate-500 font-sans">Byte 0 [STX]</div>
              <div className="text-emerald-400 font-bold text-xs mt-0.5">0x03</div>
              <div className="text-[10px] text-slate-400 font-mono">3</div>
            </div>

            {/* Machine ID */}
            <div className="bg-slate-900 border border-amber-900/60 rounded p-1.5">
              <div className="text-[9px] text-amber-400 font-sans font-semibold">Byte 1 [Machine ID]</div>
              <div className="text-amber-300 font-bold text-xs mt-0.5">
                0x{reqMachineId.toString(16).padStart(2, '0').toUpperCase()}
              </div>
              <div className="text-[10px] text-amber-200 font-mono">{reqMachineId}</div>
            </div>

            {/* Function Code */}
            <div className="bg-slate-900 border border-slate-800 rounded p-1.5">
              <div className="text-[9px] text-slate-500 font-sans">Byte 2 [Func Code]</div>
              <div className="text-sky-400 font-bold text-xs mt-0.5">0x01</div>
              <div className="text-[10px] text-slate-400 font-mono">1 (Read)</div>
            </div>

            {/* Len MSB */}
            <div className="bg-slate-900 border border-slate-800 rounded p-1.5">
              <div className="text-[9px] text-slate-500 font-sans">Byte 3 [Len MSB]</div>
              <div className="text-indigo-400 font-bold text-xs mt-0.5">0x00</div>
              <div className="text-[10px] text-slate-400 font-mono">0</div>
            </div>

            {/* Len LSB */}
            <div className="bg-slate-900 border border-slate-800 rounded p-1.5">
              <div className="text-[9px] text-slate-500 font-sans">Byte 4 [Len LSB]</div>
              <div className="text-indigo-400 font-bold text-xs mt-0.5">0x02</div>
              <div className="text-[10px] text-slate-400 font-mono">2</div>
            </div>

            {/* Group MSB */}
            <div className="bg-slate-900 border border-purple-900/60 rounded p-1.5">
              <div className="text-[9px] text-purple-400 font-sans">Byte 5 [GC MSB]</div>
              <div className="text-purple-300 font-bold text-xs mt-0.5">
                0x{reqGcMsb.toString(16).padStart(2, '0').toUpperCase()}
              </div>
              <div className="text-[10px] text-purple-200 font-mono">{reqGcMsb}</div>
            </div>

            {/* Group LSB */}
            <div className="bg-slate-900 border border-purple-900/60 rounded p-1.5">
              <div className="text-[9px] text-purple-400 font-sans font-semibold">Byte 6 [GC LSB]</div>
              <div className="text-purple-300 font-bold text-xs mt-0.5">
                0x{reqGcLsb.toString(16).padStart(2, '0').toUpperCase()}
              </div>
              <div className="text-[10px] text-purple-200 font-mono font-bold">{reqGcLsb}</div>
            </div>

            {/* Checksum */}
            <div className="bg-slate-900 border border-emerald-900/60 rounded p-1.5">
              <div className="text-[9px] text-emerald-400 font-sans font-semibold">Byte 7 [XOR Chk]</div>
              <div className="text-emerald-300 font-bold text-xs mt-0.5">
                0x{reqChecksum.toString(16).padStart(2, '0').toUpperCase()}
              </div>
              <div className="text-[10px] text-emerald-200 font-mono font-bold">{reqChecksum}</div>
            </div>

            {/* ETX */}
            <div className="bg-slate-900 border border-slate-800 rounded p-1.5">
              <div className="text-[9px] text-slate-500 font-sans">Byte 8 [ETX]</div>
              <div className="text-emerald-400 font-bold text-xs mt-0.5">0x02</div>
              <div className="text-[10px] text-slate-400 font-mono">2</div>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 2: RESPONSE FRAME (From PLC's nw_send_buffer) */}
      {(activeTab === 'both' || activeTab === 'response') && hasResponse && (
        <div className="mb-3 bg-slate-950/80 rounded-xl p-3 border border-slate-800">
          <div className="flex items-center justify-between gap-2 mb-2 pb-1.5 border-b border-slate-800/80">
            <div className="flex items-center gap-2">
              <ArrowDownLeft className="w-4 h-4 text-emerald-400" />
              <span className="font-semibold text-slate-200 text-xs">
                RESPONSE RECEIVED FROM PLC (<code className="text-emerald-300">nw_send_buffer</code>: {respBytes.length} Bytes)
              </span>
            </div>
            <div className="text-[11px] text-emerald-400 font-mono">
              Result Code: {respResultCode} (0 = OK)
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-2">
            {/* STX */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-2.5">
              <div className="text-[10px] text-slate-400 font-sans">Byte 0: STX</div>
              <div className="text-emerald-400 font-bold text-sm mt-0.5">
                0x{respStx.toString(16).padStart(2, '0')}
              </div>
              <div className="text-[10px] text-slate-500 font-sans">
                {respStx === 0x03 ? '✓ Standard STX' : '⚠ Invalid STX'}
              </div>
            </div>

            {/* Machine ID */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-2.5">
              <div className="text-[10px] text-slate-400 font-sans">Byte 1: Machine ID</div>
              <div className="text-teal-400 font-bold text-sm mt-0.5">{respMachineId}</div>
              <div className="text-[10px] text-slate-500 font-sans">
                Hex: 0x{respMachineId.toString(16).padStart(2, '0')}
              </div>
            </div>

            {/* Result Code */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-2.5">
              <div className="text-[10px] text-slate-400 font-sans">Byte 2: Result Code</div>
              <div
                className={`font-bold text-sm mt-0.5 ${
                  respResultCode === 0 ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                {respResultCode}
              </div>
              <div className="text-[10px] text-slate-500 font-sans">
                {respResultCode === 0 ? '✓ Success (0)' : `⚠ Error ${respResultCode}`}
              </div>
            </div>

            {/* Data Payload Length */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-2.5">
              <div className="text-[10px] text-slate-400 font-sans">Bytes 3-4: Data Length</div>
              <div className="text-indigo-400 font-bold text-sm mt-0.5">{respPayloadLen} Bytes</div>
              <div className="text-[10px] text-slate-500 font-sans">
                [MSB: {respLengthMsb}, LSB: {respLengthLsb}]
              </div>
            </div>

            {/* Payload Summary */}
            <button type="button" onClick={()=>setActiveTab('hexdump')} title="View all received payload bytes" className="bg-slate-900 border border-slate-800 rounded-lg p-2.5 text-left hover:border-emerald-500">
              <div className="text-[10px] text-slate-400 font-sans">Bytes 5..{5 + respPayloadLen - 1}</div>
              <div className="text-white font-bold text-sm mt-0.5">Payload</div>
              <div className="text-[10px] text-slate-500 font-sans truncate">
                {respBytes.slice(5, 9).map((b) => b.toString(16).padStart(2, '0')).join(' ')}...
              </div>
              <div className="text-[10px] text-emerald-400">View all {payloadBytes.length} bytes</div>
            </button>

            {/* Checksum */}
            <div
              className={`border rounded-lg p-2.5 ${
                checksumMatch
                  ? 'bg-emerald-950/40 border-emerald-800/70'
                  : 'bg-rose-950/40 border-rose-800/70'
              }`}
            >
              <div className="text-[10px] text-slate-400 font-sans">Byte {5 + respPayloadLen}: Checksum</div>
              <div
                className={`font-bold text-sm mt-0.5 ${
                  checksumMatch ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                0x{respChecksum.toString(16).padStart(2, '0')}
              </div>
              <div className="text-[10px] font-sans flex items-center gap-1 mt-0.5">
                {checksumMatch ? (
                  <span className="text-emerald-400 flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3" /> XOR OK
                  </span>
                ) : (
                  <span className="text-rose-400 flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" /> Exp: 0x{calculatedXor.toString(16).padStart(2, '0')}
                  </span>
                )}
              </div>
            </div>

            {/* ETX */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-2.5">
              <div className="text-[10px] text-slate-400 font-sans">Byte {5 + respPayloadLen + 1}: ETX</div>
              <div className="text-emerald-400 font-bold text-sm mt-0.5">
                0x{respEtx.toString(16).padStart(2, '0')}
              </div>
              <div className="text-[10px] text-slate-500 font-sans">
                {respEtx === 0x02 ? '✓ Standard ETX' : '⚠ Invalid ETX'}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 3: TROUBLESHOOTING & DIAGNOSTICS (If PLC did not respond) */}
      {!hasResponse && (
        <div className="bg-amber-950/40 border border-amber-800/70 rounded-xl p-3.5 text-xs text-slate-300">
          <div className="flex items-start gap-2.5">
            <Info className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
            <div className="space-y-2 flex-1">
              <div className="font-bold text-amber-200">
                PLC Buffer Status: Socket Connected & 9-Byte Request Delivered, but PLC has not called <code className="text-amber-300">TcpSend</code>
              </div>
              <p className="text-slate-300 text-[11px] leading-relaxed">
                As seen in your B&R Automation Studio watch window (<code className="text-slate-200">nw_rcv_buffer</code>), the PLC received the exact frame:{' '}
                <span className="font-mono text-amber-300">
                  [{sentBytes.map((b) => b).join(', ')}]
                </span>
                . If the PLC does not respond, consider these two key factors:
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-1">
                {/* Reason 1: Station ID mismatch */}
                <div className="bg-slate-900/90 rounded-lg p-2.5 border border-slate-800">
                  <div className="font-semibold text-slate-200 flex items-center justify-between">
                    <span>1. Station / Machine ID Check</span>
                    {onSwitchMachineId && (
                      <div className="flex items-center gap-1 text-[11px]">
                        <button
                          onClick={() => onSwitchMachineId(0)}
                          className={`px-2 py-0.5 rounded font-bold ${
                            reqMachineId === 0
                              ? 'bg-amber-500 text-slate-950'
                              : 'bg-slate-800 text-slate-400 hover:text-white'
                          }`}
                        >
                          Use ID 0
                        </button>
                        <button
                          onClick={() => onSwitchMachineId(1)}
                          className={`px-2 py-0.5 rounded font-bold ${
                            reqMachineId === 1
                              ? 'bg-amber-500 text-slate-950'
                              : 'bg-slate-800 text-slate-400 hover:text-white'
                          }`}
                        >
                          Use ID 1
                        </button>
                      </div>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                    Your B&R watch window shows <code className="text-amber-300 font-mono">nw_rcv_buffer[1] = {reqMachineId}</code>.
                    If the PLC&apos;s internal station ID is {reqMachineId === 0 ? '1' : '0'}, the PLC program will drop the request.
                  </p>
                </div>

                {/* Reason 2: Group Code 80 not in Carding */}
                <div className="bg-slate-900/90 rounded-lg p-2.5 border border-slate-800">
                  <div className="font-semibold text-slate-200 flex items-center justify-between">
                    <span>2. Group Code Supported in PLC?</span>
                    {onTestGroup && (
                      <div className="flex items-center gap-1 text-[11px]">
                        <button
                          onClick={() => onTestGroup(10)}
                          className="px-2 py-0.5 bg-indigo-900/80 hover:bg-indigo-800 text-indigo-200 rounded font-semibold transition-colors"
                        >
                          Try GC 10
                        </button>
                        <button
                          onClick={() => onTestGroup(20)}
                          className="px-2 py-0.5 bg-emerald-900/80 hover:bg-emerald-800 text-emerald-200 rounded font-semibold transition-colors"
                        >
                          Try GC 20
                        </button>
                        <button
                          onClick={() => onTestGroup(40)}
                          className="px-2 py-0.5 bg-sky-900/80 hover:bg-sky-800 text-sky-200 rounded font-semibold transition-colors"
                        >
                          Try GC 40
                        </button>
                      </div>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                    On a <strong>Carding (xcarding)</strong> machine, the factory metadata defines Group Codes{' '}
                    <strong className="text-emerald-400">10, 20, 30, 40, 130, 140, 150</strong>. Group Code 80 may only exist on other machines (e.g., Ring Frame or Inverter). If the PLC Structured Text program lacks a <code className="text-purple-300">CASE 80:</code> branch, it will not trigger <code className="text-purple-300">TcpSend</code>.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Hex Dump view tab */}
      {activeTab === 'hexdump' && hasResponse && (
        <div className="mt-3 grid grid-cols-1 lg:grid-cols-2 gap-3">
          <div>
            <div className="px-3 py-2 bg-slate-800 rounded-t-lg border border-slate-700 text-emerald-300 font-sans font-semibold">Payload HEX ({payloadBytes.length} bytes)</div>
            <pre className="p-3 bg-slate-950 rounded-b-lg border border-slate-800 text-slate-300 overflow-auto text-[11px] leading-relaxed max-h-72">{payloadHexText || '(empty payload)'}</pre>
          </div>
          <div>
            <div className="px-3 py-2 bg-slate-800 rounded-t-lg border border-slate-700 text-sky-300 font-sans font-semibold">Payload DECIMAL ({payloadBytes.length} bytes)</div>
            <pre className="p-3 bg-slate-950 rounded-b-lg border border-slate-800 text-slate-300 overflow-auto text-[11px] leading-relaxed max-h-72">{payloadDecimalText || '(empty payload)'}</pre>
          </div>
          <div className="lg:col-span-2">
            <div className="px-3 py-2 bg-slate-800 rounded-t-lg border border-slate-700 text-slate-300 font-sans font-semibold">Complete Frame HEX + ASCII</div>
            <pre className="p-3 bg-slate-950 rounded-b-lg border border-slate-800 text-slate-300 overflow-auto text-[11px] leading-relaxed max-h-72">{hexDumpText}</pre>
          </div>
        </div>
      )}
    </div>
  );
};
