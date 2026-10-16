import {targetModeLabel} from '../utils/targetMode';
import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  X,
  Clock,
  Send,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Copy,
  Check,
  Calendar,
  Layers,
  ArrowRight,
  ShieldCheck,
  History,
  Info,
} from 'lucide-react';
import { PLCConfig,GroupResponseData } from '../types';
import {readGroup150Clock,type PLCClock} from '../utils/rtcReader';
import {
  RTCFormatType,
  formatRTCDateTime,
  buildRTCPacket,
  buildSpinConnect30ByteRequest,
  formatHexDump,
  parsePLCResponse,
} from '../utils/packetParser';

interface RTCModalProps {
  isOpen: boolean;
  onClose: () => void;
  plc: PLCConfig;
  onReadGroup?: (groupCode: number) => Promise<GroupResponseData|undefined>;
}

export const RTCModal: React.FC<RTCModalProps> = ({
  isOpen,
  onClose,
  plc,
  onReadGroup,
}) => {
  const [selectedFormat, setSelectedFormat] = useState<RTCFormatType>('ISO');
  const [rtcLayout, setRtcLayout] = useState<'spinconnect'|'legacy'>('spinconnect');
  const [groupCode, setGroupCode] = useState(10);
  const [functionCode, setFunctionCode] = useState<number>(1);
  const [customString, setCustomString] = useState<string>('');
  const [isCustom, setIsCustom] = useState<boolean>(false);
  const [autoSync, setAutoSync] = useState<boolean>(true);
  const [currentTime, setCurrentTime] = useState<Date>(new Date());
  const [activeDate, setActiveDate] = useState<Date>(new Date());
  
  // Execution state
  const [sending, setSending] = useState<boolean>(false);
  const [readingGroup150, setReadingGroup150] = useState<boolean>(false);
  const [result, setResult] = useState<{
    success: boolean;
    message: string;
    testId?: string;
    rttMs: number;
    sentBytes: number[];
    rawBytes: number[];
    resultCode?: number;
    error?: string;
    closeResult?: {sentBytes?:number[];plcClosed?:boolean;warning?:string;error?:string};
  } | null>(null);

  const [group150Result, setGroup150Result] = useState<{
    success: boolean;
    dateStr: string;
    rawValues?: Record<string, any>;
    fields?: PLCClock['fields'];
    error?: string;
  } | null>(null);

  const [copiedSent, setCopiedSent] = useState(false);
  const [copiedResponse, setCopiedResponse] = useState(false);
  const requestVersion=useRef(0);

  // Results belong to this target, never carry another controller's clock.
  useEffect(()=>{requestVersion.current++;setResult(null);setGroup150Result(null);setSending(false);setReadingGroup150(false);return()=>{requestVersion.current++;};},[isOpen,plc.id,plc.ip,plc.port,plc.machineId,plc.endianness]);

  // Live timer for system clock
  useEffect(() => {
    const timer = setInterval(() => {
      const now = new Date();
      setCurrentTime(now);
      if (autoSync && !isCustom) {
        setActiveDate(now);
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [autoSync, isCustom]);

  // Compute ASCII payload string
  const asciiPayload = useMemo(() => {
    if (isCustom) return customString;
    return formatRTCDateTime(activeDate, rtcLayout === 'spinconnect' ? 'ISO' : selectedFormat);
  }, [isCustom, customString, activeDate, selectedFormat, rtcLayout]);

  // Build the binary frame
  const packetFrame = useMemo(() => {
    try {
      if (!Number.isInteger(functionCode) || functionCode < 1 || functionCode > 4) throw new Error('Invalid function');
      if (rtcLayout === 'spinconnect') {
        if (!Number.isInteger(groupCode) || groupCode < 0 || groupCode > 65535 || groupCode === 11) throw new Error('Invalid group');
        return buildSpinConnect30ByteRequest(plc.machineId, groupCode, functionCode, asciiPayload);
      }
      return buildRTCPacket(plc.machineId, functionCode, asciiPayload);
    } catch {
      return new Uint8Array(0);
    }
  }, [plc.machineId, functionCode, asciiPayload, rtcLayout, groupCode]);

  const timestampOffset = rtcLayout === 'spinconnect' ? 9 : 5;
  const bodyLength = asciiPayload.length + timestampOffset - 5;

  const packetBytes = useMemo<number[]>(() => {
    const list: number[] = [];
    for (let i = 0; i < packetFrame.length; i++) {
      list.push(packetFrame[i]);
    }
    return list;
  }, [packetFrame]);

  const payloadBytes = useMemo<number[]>(() => {
    const list: number[] = [];
    for (let i = 0; i < asciiPayload.length; i++) {
      list.push(asciiPayload.charCodeAt(i));
    }
    return list;
  }, [asciiPayload]);

  // Checksum calculation breakdown
  const checksumValue = useMemo(() => {
    if (packetFrame.length < 2) return 0;
    return packetFrame[packetFrame.length - 2];
  }, [packetFrame]);

  if (!isOpen) return null;

  const handleSendRTC = async () => {
    const version=requestVersion.current;
    setSending(true);
    setResult(null);
    try {
      const res = await fetch('/api/nami/plc/send-rtc', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          plc,
          ip: plc.ip,
          port: plc.port,
          machineId: plc.machineId,
          functionCode,
          rtcLayout,
          groupCode,
          asciiPayload,
          isSimulated: plc.isSimulated,
          timeoutMs: plc.timeoutMs || 5000,
        }),
      });
      const data = await res.json();
      if(version!==requestVersion.current)return;
      setResult({
        success: data.success,
        testId: data.testId,
        message: data.message || data.detail || (data.success ? 'RTC exchange completed; clock application not confirmed' : 'RTC transmission failed'),
        rttMs: data.rttMs || 0,
        sentBytes: data.sentBytes || Array.from(packetFrame),
        rawBytes: data.rawBytes || [],
        resultCode: data.resultCode,
        error: data.error,
        closeResult: data.closeResult,
      });
    } catch (err: any) {
      if(version!==requestVersion.current)return;
      setResult({
        success: false,
        message: `Network error: ${err.message}`,
        rttMs: 0,
        sentBytes: Array.from(packetFrame),
        rawBytes: [],
        error: err.message,
      });
    } finally {
      if(version===requestVersion.current)setSending(false);
    }
  };

  const handleReadGroup150 = async () => {
    if (!onReadGroup) return;
    const version=requestVersion.current;
    setReadingGroup150(true);
    setGroup150Result(null);
    try {
      const resp = await onReadGroup(150);
      if(version!==requestVersion.current)return;
      const clock=readGroup150Clock(resp);
      setGroup150Result({success:true,dateStr:clock.dateStr,rawValues:clock.values,fields:clock.fields});
    } catch (e: any) {
      if(version!==requestVersion.current)return;
      setGroup150Result({
        success: false,
        dateStr: '',
        error: e.message,
      });
    } finally {
      if(version===requestVersion.current)setReadingGroup150(false);
    }
  };

  const copyToClipboard = (text: string, isSent: boolean) => {
    navigator.clipboard.writeText(text);
    if (isSent) {
      setCopiedSent(true);
      setTimeout(() => setCopiedSent(false), 2000);
    } else {
      setCopiedResponse(true);
      setTimeout(() => setCopiedResponse(false), 2000);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/80 backdrop-blur-sm overflow-y-auto">
      <div className="bg-slate-900 border border-slate-700 w-full max-w-4xl rounded-xl shadow-2xl overflow-hidden flex flex-col my-auto max-h-[92vh]">
        {/* Header */}
        <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-800/40">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
              <Clock className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base sm:text-lg font-bold text-white">PLC Real Time Clock (RTC) Tester</h2>
                <span className="px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-indigo-950 text-indigo-300 border border-indigo-800">
                  ASCII Protocol Frame
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Send time synchronization data in ASCII format to target PLC ({plc.name} • {plc.ip}:{plc.port})
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-5 overflow-y-auto space-y-5 text-sm">
          {/* Target Status bar */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 bg-slate-800/60 p-3 rounded-lg border border-slate-700/60 text-xs">
            <div>
              <span className="text-slate-400 block mb-0.5">Target IP & Port:</span>
              <span className="font-mono text-slate-200 font-semibold">{plc.ip}:{plc.port}</span>
            </div>
            <div>
              <span className="text-slate-400 block mb-0.5">Machine ID:</span>
              <span className="font-mono text-emerald-400 font-bold">{plc.machineId}</span>
            </div>
            <div>
              <span className="text-slate-400 block mb-0.5">Mode:</span>
              <span className={`font-semibold ${plc.isSimulated ? 'text-amber-400' : 'text-cyan-400'}`}>
                {targetModeLabel(plc)}
              </span>
            </div>
            <div>
              <span className="text-slate-400 block mb-0.5">Timeout Setting:</span>
              <span className="font-mono text-slate-300">{plc.timeoutMs || 5000} ms</span>
            </div>
          </div>

          {/* Time & Format Configuration */}
          <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
            {/* Left config column */}
            <div className="md:col-span-7 space-y-4 bg-slate-850 p-4 rounded-xl border border-slate-700/60">
              <div className="flex items-center justify-between pb-2 border-b border-slate-700/40">
                <span className="font-semibold text-slate-200 flex items-center gap-1.5">
                  <Calendar className="w-4 h-4 text-indigo-400" />
                  Clock Configuration
                </span>
                <div className="flex items-center gap-2">
                  <label className="text-xs text-slate-400 flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={autoSync}
                      onChange={(e) => {
                        setAutoSync(e.target.checked);
                        if (e.target.checked) setIsCustom(false);
                      }}
                      className="rounded border-slate-600 text-indigo-600 focus:ring-0"
                    />
                    Use computer time
                  </label>
                </div>
              </div>

              <label className="block text-xs text-slate-300">PLC RTC layout
                <select value={rtcLayout} onChange={e=>{const layout=e.target.value as 'spinconnect'|'legacy';setRtcLayout(layout);setFunctionCode(layout==='spinconnect'?1:2);setIsCustom(false);setSelectedFormat(layout==='spinconnect'?'ISO':'YYYYMMDDHHMMSS');setResult(null);}}
                  className="block w-full mt-1 p-2 rounded bg-slate-800 border border-slate-600">
                  <option value="spinconnect">SpinConnect: YYYY-MM-DD HH:MM:SS at byte 9</option>
                  <option value="legacy">Legacy: ASCII timestamp at byte 5</option>
                </select>
              </label>
              {rtcLayout === 'spinconnect' && <div className="text-xs text-slate-400 space-y-2">
                <p>30-byte request: group at 5–6, reserved at 7–8, date/time at 9–27. Function 1 reads a group with the timestamp attached.</p>
                <label className="block">Request group code <input type="number" min="0" max="65535" value={groupCode} onChange={e=>setGroupCode(Number(e.target.value))} className="ml-2 w-24 p-1 bg-slate-800 rounded border border-slate-600" /></label>
              </div>}
              {/* Other formats belong to the legacy layout. */}
              {rtcLayout === 'legacy' && <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  ASCII Date-Time Format:
                </label>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <button
                    type="button"
                    onClick={() => { setSelectedFormat('YYYYMMDDHHMMSS'); setIsCustom(false); }}
                    className={`px-2.5 py-2 rounded-lg border text-left font-mono transition-colors ${
                      !isCustom && selectedFormat === 'YYYYMMDDHHMMSS'
                        ? 'bg-indigo-600/20 border-indigo-500 text-indigo-200 font-bold'
                        : 'bg-slate-800/80 border-slate-700 text-slate-300 hover:bg-slate-750'
                    }`}
                  >
                    <div className="text-[11px] text-slate-400">14 chars (YYYYMMDDHHMMSS)</div>
                    <div className="text-xs text-white truncate">{formatRTCDateTime(currentTime, 'YYYYMMDDHHMMSS')}</div>
                  </button>

                  <button
                    type="button"
                    onClick={() => { setSelectedFormat('DDMMYYYYHHMMSS'); setIsCustom(false); }}
                    className={`px-2.5 py-2 rounded-lg border text-left font-mono transition-colors ${
                      !isCustom && selectedFormat === 'DDMMYYYYHHMMSS'
                        ? 'bg-indigo-600/20 border-indigo-500 text-indigo-200 font-bold'
                        : 'bg-slate-800/80 border-slate-700 text-slate-300 hover:bg-slate-750'
                    }`}
                  >
                    <div className="text-[11px] text-slate-400">14 chars (DDMMYYYYHHMMSS)</div>
                    <div className="text-xs text-white truncate">{formatRTCDateTime(currentTime, 'DDMMYYYYHHMMSS')}</div>
                  </button>

                  <button
                    type="button"
                    onClick={() => { setSelectedFormat('YYMMDDHHMMSS'); setIsCustom(false); }}
                    className={`px-2.5 py-2 rounded-lg border text-left font-mono transition-colors ${
                      !isCustom && selectedFormat === 'YYMMDDHHMMSS'
                        ? 'bg-indigo-600/20 border-indigo-500 text-indigo-200 font-bold'
                        : 'bg-slate-800/80 border-slate-700 text-slate-300 hover:bg-slate-750'
                    }`}
                  >
                    <div className="text-[11px] text-slate-400">12 chars (YYMMDDHHMMSS)</div>
                    <div className="text-xs text-white truncate">{formatRTCDateTime(currentTime, 'YYMMDDHHMMSS')}</div>
                  </button>

                  <button
                    type="button"
                    onClick={() => { setSelectedFormat('DDMMYYHHMMSS'); setIsCustom(false); }}
                    className={`px-2.5 py-2 rounded-lg border text-left font-mono transition-colors ${
                      !isCustom && selectedFormat === 'DDMMYYHHMMSS'
                        ? 'bg-indigo-600/20 border-indigo-500 text-indigo-200 font-bold'
                        : 'bg-slate-800/80 border-slate-700 text-slate-300 hover:bg-slate-750'
                    }`}
                  >
                    <div className="text-[11px] text-slate-400">12 chars (DDMMYYHHMMSS)</div>
                    <div className="text-xs text-white truncate">{formatRTCDateTime(currentTime, 'DDMMYYHHMMSS')}</div>
                  </button>
                </div>
              </div>

              }
              {/* Function Code & Custom Payload */}
              <div className="grid grid-cols-2 gap-3 pt-1">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Function Code:
                  </label>
                  <div className="flex items-center gap-1.5">
                    <input
                      type="number"
                      value={functionCode}
                      min="1" max="4"
                      onChange={(e) => setFunctionCode(Number(e.target.value))}
                      className="w-full bg-slate-800 border border-slate-600 rounded-lg px-2.5 py-1.5 text-xs text-white font-mono focus:outline-none focus:border-indigo-500"
                    />
                    <button
                      type="button"
                      onClick={() => setFunctionCode(1)}
                      title="Function 1: read group with attached RTC"
                      className="px-2 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] font-mono rounded border border-slate-700"
                    >
                      Fn 1
                    </button>
                    <button
                      type="button"
                      onClick={() => setFunctionCode(2)}
                      title="Function 2: only if supported by this PLC program"
                      className="px-2 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] font-mono rounded border border-slate-700"
                    >
                      Fn 2
                    </button>
                  </div>
                  <span className="text-[10px] text-slate-400 mt-1 block">
                    Function 2 requires PLC write logic. The shared project handles Function 1.
                  </span>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Custom ASCII String:
                  </label>
                  <input
                    type="text"
                    placeholder={rtcLayout === 'spinconnect' ? '2026-10-08 14:05:06' : '20261008140506'}
                    value={customString}
                    onChange={(e) => {
                      setCustomString(e.target.value);
                      setIsCustom(true);
                      setAutoSync(false);
                    }}
                    className={`w-full bg-slate-800 border rounded-lg px-2.5 py-1.5 text-xs font-mono focus:outline-none ${
                      isCustom
                        ? 'border-indigo-500 text-indigo-300'
                        : 'border-slate-600 text-slate-300'
                    }`}
                  />
                  <span className="text-[10px] text-slate-400 mt-1 block">
                    {isCustom ? `Custom mode (${customString.length} bytes)` : 'Type here to override format'}
                  </span>
                </div>
              </div>

              {/* Active Payload Display */}
              <div className="p-3 bg-slate-900 rounded-lg border border-slate-700/80">
                <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                  <span>Current ASCII String Sent in Payload:</span>
                  <span className="font-mono text-emerald-400">{asciiPayload.length} bytes</span>
                </div>
                <div className="font-mono text-emerald-300 text-sm font-semibold tracking-wider bg-slate-950 px-3 py-1.5 rounded border border-slate-800">
                  "{asciiPayload}"
                </div>
                {packetFrame.length === 0 && <p className="text-xs text-rose-300 mt-2">Check the timestamp, function and group. SpinConnect needs a valid 19-character YYYY-MM-DD HH:MM:SS date/time; GC 11 is reserved for close.</p>}
              </div>
            </div>

            {/* Right: Quick actions & Read Group 150 */}
            <div className="md:col-span-5 space-y-4">
              <div className="bg-slate-850 p-4 rounded-xl border border-slate-700/60 h-full flex flex-col justify-between">
                <div className="space-y-3">
                  <span className="font-semibold text-slate-200 flex items-center gap-1.5 pb-2 border-b border-slate-700/40">
                    <Send className="w-4 h-4 text-emerald-400" />
                    Transmit RTC to PLC
                  </span>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    Sends the selected frame to <span className="font-mono text-slate-200">{plc.ip}:{plc.port}</span>, then requests closure with GC 11. A response confirms communication; the PLC's RTC logic decides when to apply the time.
                  </p>

                  <button
                    type="button"
                    onClick={handleSendRTC}
                    disabled={sending || packetFrame.length === 0}
                    className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold shadow-lg shadow-emerald-950/40 transition-all cursor-pointer"
                  >
                    {sending ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        <span>Sending RTC Packet...</span>
                      </>
                    ) : (
                      <>
                        <Send className="w-4 h-4" />
                        <span>Send RTC to PLC (Test RTC)</span>
                      </>
                    )}
                  </button>

                  {/* Read Machine History Group 150 */}
                  {onReadGroup && (
                    <div className="pt-2 border-t border-slate-700/40">
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-xs font-medium text-slate-300">Verify Current PLC Clock:</span>
                      </div>
                      <button
                        type="button"
                        onClick={handleReadGroup150}
                        disabled={readingGroup150}
                        className="w-full flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg bg-slate-800 hover:bg-slate-750 text-xs text-slate-200 border border-slate-700 transition-colors"
                      >
                        {readingGroup150 ? (
                          <>
                            <RefreshCw className="w-3.5 h-3.5 animate-spin text-cyan-400" />
                            <span>Reading Group 150...</span>
                          </>
                        ) : (
                          <>
                            <History className="w-3.5 h-3.5 text-cyan-400" />
                            <span>Read RTC via Group 150</span>
                          </>
                        )}
                      </button>

                      {group150Result && (
                        <div className={`mt-2 p-2 rounded text-xs border ${
                          group150Result.success
                            ? 'bg-emerald-950/40 border-emerald-800/80 text-emerald-300'
                            : 'bg-rose-950/40 border-rose-800/80 text-rose-300'
                        }`}>
                          {group150Result.success ? (
                            <div className="space-y-2"><div className="flex items-center justify-between">
                              <span>PLC Stored Clock:</span>
                              <span className="font-mono font-bold">{group150Result.dateStr}</span>
                            </div><div className="grid grid-cols-2 gap-2">{Object.entries(group150Result.fields||{}).map(([name,field])=><div key={name}><b>{name}: {String(field.rawValue)}</b><div className="text-[10px] opacity-80">GC150 · Tag {field.tagCode} · +{field.offset}B · {field.dataType}</div></div>)}</div></div>
                          ) : (
                            <div>{group150Result.error}</div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div className="pt-3 text-[11px] text-slate-500 flex items-start gap-1.5">
                  <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5 text-slate-400" />
                  <span>
                    In B&R Structured Text (<code className="text-slate-400 font-mono">Cyclic.st</code>), the packet will arrive into <code className="text-slate-400 font-mono">nw_rcv_buffer</code> with Function Code = {functionCode}.
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Visual Data Frame Breakdown ("refer the data frame") */}
          <div className="bg-slate-850 p-4 rounded-xl border border-slate-700/60 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-indigo-400" />
                <span className="font-semibold text-slate-200">Data Frame Structure (Total: {packetFrame.length} bytes)</span>
              </div>
              <button
                type="button"
                onClick={() => copyToClipboard(JSON.stringify(Array.from(packetFrame)), true)}
                className="flex items-center gap-1 text-xs text-slate-400 hover:text-white px-2 py-1 rounded bg-slate-800 border border-slate-700 transition-colors"
              >
                {copiedSent ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedSent ? 'Copied Bytes!' : 'Copy Byte Array'}</span>
              </button>
            </div>

            {/* Frame Fields Table */}
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left border border-slate-700/80 rounded-lg overflow-hidden font-mono">
                <thead className="bg-slate-800 text-slate-300 font-sans">
                  <tr>
                    <th className="py-2 px-3 border-b border-slate-700">Byte Index</th>
                    <th className="py-2 px-3 border-b border-slate-700">Field Name</th>
                    <th className="py-2 px-3 border-b border-slate-700">Hex Value</th>
                    <th className="py-2 px-3 border-b border-slate-700">Dec Value</th>
                    <th className="py-2 px-3 border-b border-slate-700">Description / Meaning</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 bg-slate-900/60">
                  <tr className="hover:bg-slate-800/40">
                    <td className="py-1.5 px-3 text-slate-400 font-bold">Byte [0]</td>
                    <td className="py-1.5 px-3 text-amber-300">STX</td>
                    <td className="py-1.5 px-3 text-amber-400">0x03</td>
                    <td className="py-1.5 px-3 text-slate-300">3</td>
                    <td className="py-1.5 px-3 text-slate-400 font-sans">Start of Text marker</td>
                  </tr>
                  <tr className="hover:bg-slate-800/40">
                    <td className="py-1.5 px-3 text-slate-400 font-bold">Byte [1]</td>
                    <td className="py-1.5 px-3 text-cyan-300">Machine ID</td>
                    <td className="py-1.5 px-3 text-cyan-400">0x{plc.machineId.toString(16).padStart(2, '0').toUpperCase()}</td>
                    <td className="py-1.5 px-3 text-slate-300">{plc.machineId}</td>
                    <td className="py-1.5 px-3 text-slate-400 font-sans">Target Machine Identification number</td>
                  </tr>
                  <tr className="hover:bg-slate-800/40">
                    <td className="py-1.5 px-3 text-slate-400 font-bold">Byte [2]</td>
                    <td className="py-1.5 px-3 text-indigo-300 font-bold">Function Code</td>
                    <td className="py-1.5 px-3 text-indigo-400">0x{functionCode.toString(16).padStart(2, '0').toUpperCase()}</td>
                    <td className="py-1.5 px-3 text-slate-300">{functionCode}</td>
                    <td className="py-1.5 px-3 text-slate-400 font-sans">Function Code {functionCode} (RTC / Real Time Clock Data)</td>
                  </tr>
                  <tr className="hover:bg-slate-800/40">
                    <td className="py-1.5 px-3 text-slate-400 font-bold">Bytes [3..4]</td>
                    <td className="py-1.5 px-3 text-blue-300">Payload Length</td>
                    <td className="py-1.5 px-3 text-blue-400">{[(bodyLength >> 8)&255,bodyLength&255].map(b=>'0x'+b.toString(16).padStart(2,'0')).join(' ')}</td>
                    <td className="py-1.5 px-3 text-slate-300">{bodyLength}</td>
                    <td className="py-1.5 px-3 text-slate-400 font-sans">16-bit Big-Endian payload length ({bodyLength} bytes)</td>
                  </tr>
                  {rtcLayout === 'spinconnect' && <>
                    <tr><td className="py-1.5 px-3">Bytes [5..6]</td><td>Group Code</td><td>{((groupCode>>8)&255).toString(16).padStart(2,'0')} {(groupCode&255).toString(16).padStart(2,'0')}</td><td>{groupCode}</td><td>Requested data group (not GC 11)</td></tr>
                    <tr><td className="py-1.5 px-3">Bytes [7..8]</td><td>Reserved</td><td>00 00</td><td>0 0</td><td>RTC starts at byte 9</td></tr>
                  </>}
                  <tr className="hover:bg-slate-800/40 bg-emerald-950/20">
                    <td className="py-1.5 px-3 text-slate-400 font-bold">Bytes [{timestampOffset}..{timestampOffset - 1 + asciiPayload.length}]</td>
                    <td className="py-1.5 px-3 text-emerald-300 font-bold">Payload (ASCII)</td>
                    <td className="py-1.5 px-3 text-emerald-400">
                      {payloadBytes
                        .slice(0, 8)
                        .map((b) => b.toString(16).padStart(2, '0').toUpperCase())
                        .join(' ')}
                      {payloadBytes.length > 8 ? '...' : ''}
                    </td>
                    <td className="py-1.5 px-3 text-emerald-200 truncate max-w-[120px]">
                      "{asciiPayload}"
                    </td>
                    <td className="py-1.5 px-3 text-slate-300 font-sans">
                      Date-time string encoded in ASCII ({asciiPayload.length} characters)
                    </td>
                  </tr>
                  <tr className="hover:bg-slate-800/40">
                    <td className="py-1.5 px-3 text-slate-400 font-bold">Byte [{timestampOffset + asciiPayload.length}]</td>
                    <td className="py-1.5 px-3 text-yellow-300">Checksum (XOR)</td>
                    <td className="py-1.5 px-3 text-yellow-400">0x{checksumValue.toString(16).padStart(2, '0').toUpperCase()}</td>
                    <td className="py-1.5 px-3 text-slate-300">{checksumValue}</td>
                    <td className="py-1.5 px-3 text-slate-400 font-sans">Bitwise XOR sum of Bytes [0] through [{timestampOffset - 1 + asciiPayload.length}]</td>
                  </tr>
                  <tr className="hover:bg-slate-800/40">
                    <td className="py-1.5 px-3 text-slate-400 font-bold">Byte [{timestampOffset + 1 + asciiPayload.length}]</td>
                    <td className="py-1.5 px-3 text-amber-300">ETX</td>
                    <td className="py-1.5 px-3 text-amber-400">0x02</td>
                    <td className="py-1.5 px-3 text-slate-300">2</td>
                    <td className="py-1.5 px-3 text-slate-400 font-sans">End of Text marker</td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Exact Payload Character Breakdown */}
            <div>
              <div className="text-[11px] font-medium text-slate-400 mb-1.5">
                Character-by-Character ASCII Encoding Breakdown:
              </div>
              <div className="flex flex-wrap gap-1.5">
                {asciiPayload.split('').map((char, idx) => {
                  const asciiCode = char.charCodeAt(0);
                  return (
                    <div
                      key={idx}
                      className="bg-slate-900 border border-slate-700/80 rounded px-2 py-1 text-center font-mono text-xs"
                    >
                      <div className="text-emerald-300 font-bold text-sm">{char}</div>
                      <div className="text-[9px] text-slate-400">[{timestampOffset + idx}]</div>
                      <div className="text-[10px] text-slate-400">{asciiCode}</div>
                      <div className="text-[9px] text-slate-500 font-mono">0x{asciiCode.toString(16).toUpperCase()}</div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Raw Hex and Decimal Preview */}
            <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 font-mono text-xs space-y-1">
              <div className="text-slate-400 text-[11px]">Exact Raw Hex Frame:</div>
              <div className="text-indigo-300 break-all">
                {packetBytes
                  .map((b) => b.toString(16).padStart(2, '0').toUpperCase())
                  .join(' ')}
              </div>
              <div className="text-slate-400 text-[11px] pt-1">Exact Decimal Byte Array (for B&R Watch):</div>
              <div className="text-slate-300 break-all">
                [{packetBytes.join(', ')}]
              </div>
            </div>
          </div>

          {/* Test Execution Result Card */}
          {result && (
            <div
              className={`p-4 rounded-xl border ${
                result.success
                  ? 'bg-emerald-950/30 border-emerald-700/80 text-emerald-200'
                  : 'bg-rose-950/30 border-rose-700/80 text-rose-200'
              } space-y-3`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {result.success ? (
                    <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                  ) : (
                    <AlertCircle className="w-5 h-5 text-rose-400" />
                  )}
                  <span className="font-bold text-sm">
                    {result.success ? 'RTC Time Transmitted & Acknowledged' : 'RTC Transmission Result'}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-xs font-mono">
                  <span className="bg-slate-900 px-2 py-0.5 rounded border border-slate-700">
                    RTT: {result.rttMs} ms
                  </span>
                  {result.resultCode !== undefined && (
                    <span className={`px-2 py-0.5 rounded border ${
                      result.resultCode === 0 ? 'bg-emerald-900 border-emerald-700' : 'bg-rose-900 border-rose-700'
                    }`}>
                      Code: {result.resultCode}
                    </span>
                  )}
                </div>
              </div>

              <p className="text-xs">{result.message}</p>
              {result.testId && <p className="text-xs font-mono break-all">Test ID: {result.testId} (saved in history)</p>}
              <div className="text-xs font-mono break-all">Actual RTC request sent ({result.sentBytes.length} bytes): [{result.sentBytes.join(', ')}]</div>
              {result.closeResult && <details className="text-xs">
                <summary>GC 11 closure: {result.closeResult.plcClosed ? 'PLC close confirmed' : 'close not confirmed'}</summary>
                <p className="font-mono break-all">[{(result.closeResult.sentBytes || []).join(', ')}]</p>
                <p>{result.closeResult.warning || result.closeResult.error}</p>
                <p>The PLC watch buffer may now show this 9-byte close request. Bytes after index 8 are outside that request and can be stale.</p>
              </details>}

              {/* Response Bytes Breakdown if available */}
              {result.rawBytes && result.rawBytes.length > 0 && (
                <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-1.5 text-xs font-mono">
                  <div className="flex items-center justify-between text-[11px] text-slate-400">
                    <span>PLC Response Frame ({result.rawBytes.length} bytes received):</span>
                    <button
                      onClick={() => copyToClipboard(JSON.stringify(result.rawBytes), false)}
                      className="flex items-center gap-1 text-slate-400 hover:text-white"
                    >
                      {copiedResponse ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                      <span>{copiedResponse ? 'Copied' : 'Copy'}</span>
                    </button>
                  </div>
                  <div className="text-cyan-300 break-all">
                    [{result.rawBytes.join(', ')}]
                  </div>
                  <div className="text-slate-400 text-[11px]">
                    Hex: {result.rawBytes.map((b) => b.toString(16).padStart(2, '0').toUpperCase()).join(' ')}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-slate-800 flex items-center justify-between bg-slate-850">
          <div className="text-xs text-slate-400">
            Current Target: <span className="text-slate-200 font-semibold">{plc.name}</span> ({plc.ip}:{plc.port})
          </div>
          <button
            onClick={onClose}
            className="px-4 py-1.5 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors border border-slate-700"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
