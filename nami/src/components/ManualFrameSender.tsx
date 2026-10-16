import {targetModeLabel} from '../utils/targetMode';
import {userStorage} from '../../../src/shared/userStorage';
import React, { useState, useEffect, useMemo } from 'react';
import {
  Send,
  RefreshCw,
  Copy,
  Check,
  Plus,
  Trash2,
  Clock,
  Sparkles,
  Info,
  CheckCircle2,
  AlertTriangle,
  FileCode,
  Sliders,
  Bookmark,
  ArrowRight,
  Database,
  ArrowDownLeft,
  ArrowUpRight
} from 'lucide-react';
import { PLCConfig } from '../types';
import { calculateXorChecksum, buildSpinConnect30ByteRequest, buildReadGroupRequest, formatHexDump } from '../utils/packetParser';

interface ManualFrameSenderProps {
  activePLC: PLCConfig;
  onUpdatePLC?: (updates: Partial<PLCConfig>) => void;
}

export interface FrameByteRow {
  id: string;
  arrayNo: number;
  dec: number;
  description: string;
  remarks: string;
}

// Default 30-byte frame matching the exact user uploaded image table
function createSpinConnect30ByteRows(machineId: number = 0, groupCode: number = 10, functionCode: number = 0): FrameByteRow[] {
  const bytes = Array.from(buildSpinConnect30ByteRequest(machineId, groupCode, functionCode));
  const descs = [
    'STX',
    'Machine ID',
    'Function Code',
    'Length (MSB)',
    'Length (LSB)',
    'Group Code (MSB)',
    'Group Code (LSB)',
    'Reserved',
    'Reserved',
    'RTC Data (Y1)',
    'RTC Data (Y2)',
    'RTC Data (Y3)',
    'RTC Data (Y4)',
    'RTC Data (-)',
    'RTC Data (M1)',
    'RTC Data (M2)',
    'RTC Data (-)',
    'RTC Data (D1)',
    'RTC Data (D2)',
    'RTC Data (Space)',
    'RTC Data (h1)',
    'RTC Data (h2)',
    'RTC Data (:)',
    'RTC Data (m1)',
    'RTC Data (m2)',
    'RTC Data (:)',
    'RTC Data (s1)',
    'RTC Data (s2)',
    'Check sum',
    'ETX',
  ];

  const remarks = [
    '3',
    '0',
    '1 (or 0)',
    'The length of frame (excluding STX, Machine ID, Func, Len, Checksum, ETX)',
    '23',
    'Any data bytes',
    'GC LSB',
    'No data',
    'No data',
    'RTC Data from server spin connect server',
    'RTC Data',
    'RTC Data',
    'RTC Data',
    'RTC Data',
    'RTC Data',
    'RTC Data',
    'RTC Data',
    'RTC Data',
    'RTC Data',
    'RTC Data',
    'RTC Data',
    'RTC Data',
    'RTC Data',
    'RTC Data',
    'RTC Data',
    'RTC Data',
    'RTC Data',
    'RTC Data',
    'XOR of all bytes from STX to before ETX',
    '2',
  ];

  return bytes.map((b, idx) => ({
    id: `b-${idx}-${Date.now()}`,
    arrayNo: idx,
    dec: b,
    description: descs[idx] || `Byte ${idx}`,
    remarks: remarks[idx] || '',
  }));
}

// 9-byte Compact Read Group rows
function createCompact9ByteRows(machineId: number = 0, groupCode: number = 10): FrameByteRow[] {
  const bytes = Array.from(buildReadGroupRequest(machineId, groupCode));
  const descs = [
    'STX',
    'Machine ID',
    'Function Code',
    'Length (MSB)',
    'Length (LSB)',
    'Group Code (MSB)',
    'Group Code (LSB)',
    'Check sum',
    'ETX',
  ];
  const remarks = [
    '3',
    '0 (Station ID)',
    '1 (Read Group)',
    '0',
    '2 bytes payload',
    'GC High Byte',
    'GC Low Byte',
    'XOR of bytes 0..6',
    '2',
  ];

  return bytes.map((b, idx) => ({
    id: `b-${idx}-${Date.now()}`,
    arrayNo: idx,
    dec: b,
    description: descs[idx] || `Byte ${idx}`,
    remarks: remarks[idx] || '',
  }));
}

export const ManualFrameSender: React.FC<ManualFrameSenderProps> = ({
  activePLC,
  onUpdatePLC,
}) => {
  const [rows, setRows] = useState<FrameByteRow[]>(() =>
    createSpinConnect30ByteRows(activePLC.machineId ?? 0, 10, 0)
  );

  const [autoChecksum, setAutoChecksum] = useState<boolean>(true);
  const [rawTextMode, setRawTextMode] = useState<'table' | 'hexText' | 'decText'>('table');
  const [rawDecText, setRawDecText] = useState<string>('');
  const [rawHexText, setRawHexText] = useState<string>('');

  const [sending, setSending] = useState(false);
  const [copied, setCopied] = useState(false);

  // Response state
  const [lastResponse, setLastResponse] = useState<{
    success: boolean;
    sentBytes: number[];
    rawBytes: number[];
    rttMs: number;
    error?: string;
    isSimulated?: boolean;
    timestamp: string;
    testId?: string;
  } | null>(null);

  // Saved frames in localStorage
  const [savedFrames, setSavedFrames] = useState<{ name: string; bytes: number[] }[]>(() => {
    try {
      const saved = userStorage.getItem('spinconnect_saved_frames');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [newPresetName, setNewPresetName] = useState('');

  // Synchronize arrayNo in rows
  const reindexedRows = useMemo(() => {
    return rows.map((r, idx) => ({ ...r, arrayNo: idx }));
  }, [rows]);

  // Byte array
  const currentBytes = useMemo(() => {
    return reindexedRows.map((r) => r.dec & 0xff);
  }, [reindexedRows]);

  // Checksum calculation: XOR of all bytes from byte 0 up to (length - 2)
  const calculatedChecksum = useMemo(() => {
    if (currentBytes.length < 2) return 0;
    return calculateXorChecksum(currentBytes, 0, currentBytes.length - 2);
  }, [currentBytes]);

  // Keep checksum updated if autoChecksum is enabled
  useEffect(() => {
    if (!autoChecksum || rows.length < 3) return;
    const checksumIndex = rows.length - 2;
    if (rows[checksumIndex].dec !== calculatedChecksum) {
      setRows((prev) => {
        const next = [...prev];
        next[checksumIndex] = {
          ...next[checksumIndex],
          dec: calculatedChecksum,
          description: next[checksumIndex].description || 'Check sum',
          remarks: 'XOR of all bytes from STX to before ETX',
        };
        return next;
      });
    }
  }, [calculatedChecksum, autoChecksum, rows.length]);

  // Sync text representations
  useEffect(() => {
    setRawDecText(currentBytes.join(', '));
    setRawHexText(currentBytes.map((b) => b.toString(16).padStart(2, '0').toUpperCase()).join(' '));
  }, [currentBytes]);

  // Handlers for modifying bytes
  const handleDecChange = (index: number, newDecVal: number) => {
    const val = Math.max(0, Math.min(255, isNaN(newDecVal) ? 0 : newDecVal));
    setRows((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], dec: val };
      return next;
    });
  };

  const handleHexChange = (index: number, hexStr: string) => {
    const cleaned = hexStr.replace(/[^0-9a-fA-F]/g, '');
    const val = parseInt(cleaned, 16);
    handleDecChange(index, isNaN(val) ? 0 : val);
  };

  const handleApplyDecText = () => {
    const numbers = rawDecText
      .split(/[,\s]+/)
      .map((s) => parseInt(s.trim(), 10))
      .filter((n) => !isNaN(n))
      .map((n) => Math.max(0, Math.min(255, n)));

    if (numbers.length === 0) return;

    setRows(
      numbers.map((b, idx) => ({
        id: `custom-${idx}-${Date.now()}`,
        arrayNo: idx,
        dec: b,
        description: idx === 0 ? 'STX' : idx === numbers.length - 1 ? 'ETX' : idx === numbers.length - 2 ? 'Checksum' : `Byte ${idx}`,
        remarks: '',
      }))
    );
  };

  const handleApplyHexText = () => {
    const tokens = rawHexText.trim().split(/[\s,]+/);
    const numbers = tokens
      .map((t) => parseInt(t, 16))
      .filter((n) => !isNaN(n))
      .map((n) => Math.max(0, Math.min(255, n)));

    if (numbers.length === 0) return;

    setRows(
      numbers.map((b, idx) => ({
        id: `custom-hex-${idx}-${Date.now()}`,
        arrayNo: idx,
        dec: b,
        description: idx === 0 ? 'STX' : idx === numbers.length - 1 ? 'ETX' : idx === numbers.length - 2 ? 'Checksum' : `Byte ${idx}`,
        remarks: '',
      }))
    );
  };

  const handleAddByte = () => {
    setRows((prev) => [
      ...prev,
      {
        id: `b-new-${Date.now()}`,
        arrayNo: prev.length,
        dec: 0,
        description: `Byte ${prev.length}`,
        remarks: '',
      },
    ]);
  };

  const handleDeleteByte = (index: number) => {
    if (rows.length <= 2) return;
    setRows((prev) => prev.filter((_, idx) => idx !== index));
  };

  const handleInsertByteBefore = (index: number) => {
    setRows((prev) => {
      const next = [...prev];
      next.splice(index, 0, {
        id: `b-ins-${Date.now()}`,
        arrayNo: index,
        dec: 0,
        description: `Byte`,
        remarks: '',
      });
      return next;
    });
  };

  // Recalculate checksum on demand
  const handleForceRecalcChecksum = () => {
    if (rows.length < 2) return;
    const chkIdx = rows.length - 2;
    const chk = calculateXorChecksum(currentBytes, 0, chkIdx);
    setRows((prev) => {
      const next = [...prev];
      next[chkIdx] = { ...next[chkIdx], dec: chk };
      return next;
    });
  };

  // Presets
  const handleLoadSpinConnectPreset = (gc: number = 10, funcCode: number = 0) => {
    setRows(createSpinConnect30ByteRows(activePLC.machineId ?? 0, gc, funcCode));
  };

  const handleLoadCompact9BytePreset = (gc: number = 10) => {
    setRows(createCompact9ByteRows(activePLC.machineId ?? 0, gc));
  };

  const handleRefreshRTCTimestamp = () => {
    // If it's a 30-byte frame, update bytes 9..27 with current timestamp ASCII
    if (rows.length === 30) {
      const now = new Date();
      const YYYY = now.getFullYear();
      const MM = String(now.getMonth() + 1).padStart(2, '0');
      const DD = String(now.getDate()).padStart(2, '0');
      const hh = String(now.getHours()).padStart(2, '0');
      const mm = String(now.getMinutes()).padStart(2, '0');
      const ss = String(now.getSeconds()).padStart(2, '0');
      const rtcStr = `${YYYY}-${MM}-${DD} ${hh}:${mm}:${ss}`;
      const padded = rtcStr.padEnd(19, ' ').slice(0, 19);

      setRows((prev) => {
        const next = [...prev];
        for (let i = 0; i < 19; i++) {
          if (next[9 + i]) {
            next[9 + i] = {
              ...next[9 + i],
              dec: padded.charCodeAt(i) & 0xff,
            };
          }
        }
        return next;
      });
    }
  };

  // Save to presets
  const handleSavePreset = () => {
    if (!newPresetName.trim()) return;
    const newPreset = { name: newPresetName.trim(), bytes: currentBytes };
    const updated = [...savedFrames, newPreset];
    setSavedFrames(updated);
    setNewPresetName('');
    try {
      userStorage.setItem('spinconnect_saved_frames', JSON.stringify(updated));
    } catch {}
  };

  const handleLoadSavedPreset = (bytes: number[]) => {
    setRows(
      bytes.map((b, idx) => ({
        id: `saved-${idx}-${Date.now()}`,
        arrayNo: idx,
        dec: b,
        description: idx === 0 ? 'STX' : idx === bytes.length - 1 ? 'ETX' : idx === bytes.length - 2 ? 'Checksum' : `Byte ${idx}`,
        remarks: '',
      }))
    );
  };

  const handleDeleteSavedPreset = (idx: number) => {
    const updated = savedFrames.filter((_, i) => i !== idx);
    setSavedFrames(updated);
    try {
      userStorage.setItem('spinconnect_saved_frames', JSON.stringify(updated));
    } catch {}
  };

  // Send raw frame
  const handleSendFrame = async () => {
    setSending(true);
    try {
      const res = await fetch('/api/nami/plc/send-raw', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({plc: activePLC,
          machineId: activePLC.machineId,
          ip: activePLC.ip,
          port: activePLC.port,
          rawBytes: currentBytes,
          isSimulated: activePLC.isSimulated,
          timeoutMs: activePLC.timeoutMs || 5000,
          description: `Manual Frame (${currentBytes.length} bytes)`,
        }),
      });
      const data = await res.json();
      setLastResponse({
        success: data.success,
        testId: data.testId,
        sentBytes: data.sentBytes || currentBytes,
        rawBytes: data.rawBytes || [],
        rttMs: data.rttMs || 0,
        error: data.error || data.detail || (!res.ok ? `Request failed (${res.status})` : undefined),
        isSimulated: data.isSimulated,
        timestamp: new Date().toLocaleTimeString(),
      });
    } catch (err: any) {
      setLastResponse({
        success: false,
        sentBytes: currentBytes,
        rawBytes: [],
        rttMs: 0,
        error: err.message,
        isSimulated: activePLC.isSimulated,
        timestamp: new Date().toLocaleTimeString(),
      });
    } finally {
      setSending(false);
    }
  };

  const handleCopyHex = () => {
    const text = currentBytes.map((b) => b.toString(16).padStart(2, '0').toUpperCase()).join(' ');
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="space-y-4">
      {/* Target summary bar */}
      <div className="bg-slate-900/90 border border-slate-700/80 rounded-xl p-3.5 flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
            <Sliders className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-white text-sm">Target PLC: {activePLC.name}</span>
              <span
                className={`text-[10px] font-mono px-2 py-0.5 rounded ${
                  activePLC.isSimulated
                    ? 'bg-amber-950/60 text-amber-300 border border-amber-800'
                    : 'bg-emerald-950/60 text-emerald-300 border border-emerald-800'
                }`}
              >
                {targetModeLabel(activePLC)}
              </span>
            </div>
            <div className="text-xs text-slate-400 font-mono mt-0.5 flex items-center gap-3">
              <span>
                IP: <strong className="text-slate-200">{activePLC.ip}:{activePLC.port}</strong>
              </span>
              <span>
                Station / Machine ID:{' '}
                <strong className="text-amber-400 font-bold">{activePLC.machineId ?? 0}</strong>
              </span>
            </div>
          </div>
        </div>

        {/* Machine ID 0 vs 1 Quick Switch */}
        <div className="flex items-center gap-2">
          <div className="flex items-center bg-slate-800 border border-slate-700 rounded-lg p-1 text-xs">
            <span className="text-slate-400 px-1.5 text-[11px]">Machine ID:</span>
            <button
              onClick={() => {
                onUpdatePLC?.({ machineId: 0 });
                // If row 1 is Machine ID, update it
                if (rows.length > 1) handleDecChange(1, 0);
              }}
              className={`px-2.5 py-1 rounded text-xs font-bold transition-all ${
                activePLC.machineId === 0 ? 'bg-amber-500 text-slate-950 shadow-sm' : 'text-slate-400 hover:text-white'
              }`}
            >
              0
            </button>
            <button
              onClick={() => {
                onUpdatePLC?.({ machineId: 1 });
                // If row 1 is Machine ID, update it
                if (rows.length > 1) handleDecChange(1, 1);
              }}
              className={`px-2.5 py-1 rounded text-xs font-bold transition-all ${
                activePLC.machineId === 1 ? 'bg-amber-500 text-slate-950 shadow-sm' : 'text-slate-400 hover:text-white'
              }`}
            >
              1
            </button>
          </div>

          <button
            onClick={handleSendFrame}
            disabled={sending}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-lg shadow-md shadow-emerald-950/50 transition-all cursor-pointer disabled:opacity-50"
          >
            <Send className={`w-3.5 h-3.5 ${sending ? 'animate-pulse' : ''}`} />
            <span>{sending ? 'Transmitting...' : 'Send Frame to PLC'}</span>
          </button>
        </div>
      </div>

      {/* Preset bar & template selection */}
      <div className="bg-slate-800/60 border border-slate-700/80 rounded-xl p-3">
        <div className="flex flex-wrap items-center justify-between gap-2.5 mb-2">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-amber-400" />
            <span className="text-xs font-bold text-slate-200">Pre-Configured Frame Templates:</span>
          </div>

          <div className="flex items-center gap-1.5 flex-wrap text-xs">
            <button
              onClick={() => handleLoadSpinConnectPreset(10, 0)}
              className="px-2.5 py-1 rounded bg-indigo-950/80 hover:bg-indigo-900 border border-indigo-700/60 text-indigo-200 font-medium transition-colors"
            >
              30-Byte Frame (GC 10 + RTC)
            </button>
            <button
              onClick={() => handleLoadSpinConnectPreset(80, 0)}
              className="px-2.5 py-1 rounded bg-indigo-950/80 hover:bg-indigo-900 border border-indigo-700/60 text-indigo-200 font-medium transition-colors"
            >
              30-Byte Frame (GC 80 + RTC)
            </button>
            <button
              onClick={() => handleLoadSpinConnectPreset(20, 0)}
              className="px-2.5 py-1 rounded bg-indigo-950/80 hover:bg-indigo-900 border border-indigo-700/60 text-indigo-200 font-medium transition-colors"
            >
              30-Byte Frame (GC 20 + RTC)
            </button>
            <button
              onClick={() => handleLoadCompact9BytePreset(10)}
              className="px-2.5 py-1 rounded bg-slate-700 hover:bg-slate-600 border border-slate-600 text-slate-200 font-medium transition-colors"
            >
              Compact 9-Byte (GC 10)
            </button>
            <button
              onClick={() => handleLoadCompact9BytePreset(80)}
              className="px-2.5 py-1 rounded bg-slate-700 hover:bg-slate-600 border border-slate-600 text-slate-200 font-medium transition-colors"
            >
              Compact 9-Byte (GC 80)
            </button>
          </div>
        </div>

        {/* If 30-byte frame is active, show RTC timestamp refresh button */}
        {rows.length === 30 && (
          <div className="mt-2 pt-2 border-t border-slate-700/60 flex items-center justify-between text-xs text-slate-400">
            <div className="flex items-center gap-2">
              <Clock className="w-3.5 h-3.5 text-sky-400" />
              <span>
                30-Byte Spin Connect Format active (19-byte RTC Timestamp embedded in <code className="text-amber-300">nw_rcv_buffer[9..27]</code>)
              </span>
            </div>
            <button
              onClick={handleRefreshRTCTimestamp}
              className="flex items-center gap-1.5 px-2.5 py-1 bg-sky-950/70 hover:bg-sky-900/80 border border-sky-800 text-sky-300 rounded font-medium text-[11px] transition-colors"
            >
              <RefreshCw className="w-3 h-3" />
              <span>Update RTC to Current Time</span>
            </button>
          </div>
        )}
      </div>

      {/* Editor Controls & Checksum Bar */}
      <div className="bg-slate-900/70 border border-slate-700/80 rounded-xl p-3.5 flex flex-col md:flex-row md:items-center justify-between gap-3">
        {/* Left: Checksum status */}
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 cursor-pointer text-xs text-slate-300 select-none">
            <input
              type="checkbox"
              checked={autoChecksum}
              onChange={(e) => setAutoChecksum(e.target.checked)}
              className="w-4 h-4 rounded border-slate-700 text-emerald-600 focus:ring-emerald-500 bg-slate-800"
            />
            <span>Auto-Calculate Checksum (XOR of bytes 0 to {rows.length - 3})</span>
          </label>

          <span className="text-xs px-2 py-0.5 rounded bg-slate-800 border border-slate-700 font-mono text-emerald-400">
            Calculated: 0x{calculatedChecksum.toString(16).padStart(2, '0').toUpperCase()} ({calculatedChecksum})
          </span>

          {!autoChecksum && (
            <button
              onClick={handleForceRecalcChecksum}
              className="text-[11px] px-2 py-0.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700"
            >
              Apply Checksum
            </button>
          )}
        </div>

        {/* Right: View Mode Toggle & Copy */}
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg bg-slate-800 p-0.5 border border-slate-700 text-xs">
            <button
              onClick={() => setRawTextMode('table')}
              className={`px-2.5 py-1 rounded font-medium transition-colors ${
                rawTextMode === 'table' ? 'bg-emerald-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              Table View
            </button>
            <button
              onClick={() => setRawTextMode('hexText')}
              className={`px-2.5 py-1 rounded font-medium transition-colors ${
                rawTextMode === 'hexText' ? 'bg-emerald-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              Hex Stream
            </button>
            <button
              onClick={() => setRawTextMode('decText')}
              className={`px-2.5 py-1 rounded font-medium transition-colors ${
                rawTextMode === 'decText' ? 'bg-emerald-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              Decimal Stream
            </button>
          </div>

          <button
            onClick={handleCopyHex}
            className="flex items-center gap-1.5 px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 text-xs transition-colors"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            <span>{copied ? 'Copied' : 'Copy Hex'}</span>
          </button>
        </div>
      </div>

      {/* VIEW MODE 1: Interactive Table View (matches user's uploaded spreadsheet exactly) */}
      {rawTextMode === 'table' && (
        <div className="bg-slate-900 border border-slate-700/80 rounded-xl overflow-hidden shadow-lg">
          <div className="overflow-x-auto max-h-[420px] scrollbar-thin scrollbar-thumb-slate-700">
            <table className="w-full text-left text-xs border-collapse">
              <thead className="bg-slate-800/90 text-slate-300 border-b border-slate-700 sticky top-0 z-10">
                <tr>
                  <th className="py-2 px-3 font-semibold w-16 text-center">Array no</th>
                  <th className="py-2 px-3 font-semibold w-24">Data (Dec)</th>
                  <th className="py-2 px-3 font-semibold w-20">Hex</th>
                  <th className="py-2 px-3 font-semibold w-14 text-center">ASCII</th>
                  <th className="py-2 px-3 font-semibold">Description</th>
                  <th className="py-2 px-3 font-semibold">Remarks / Spec</th>
                  <th className="py-2 px-2 font-semibold w-16 text-center">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800 font-mono">
                {reindexedRows.map((row, idx) => {
                  const isStx = idx === 0;
                  const isMachineId = idx === 1;
                  const isFuncCode = idx === 2;
                  const isChecksum = idx === reindexedRows.length - 2;
                  const isEtx = idx === reindexedRows.length - 1;
                  const charCode = row.dec;
                  const asciiChar =
                    charCode >= 32 && charCode <= 126 ? String.fromCharCode(charCode) : '·';

                  return (
                    <tr
                      key={row.id}
                      className={`hover:bg-slate-800/40 transition-colors ${
                        isStx
                          ? 'bg-emerald-950/20'
                          : isMachineId
                          ? 'bg-amber-950/20'
                          : isChecksum
                          ? 'bg-indigo-950/20'
                          : isEtx
                          ? 'bg-emerald-950/20'
                          : ''
                      }`}
                    >
                      {/* Array no */}
                      <td className="py-1.5 px-3 text-center text-slate-400 font-bold bg-slate-900/50">
                        {row.arrayNo}
                      </td>

                      {/* Dec input */}
                      <td className="py-1.5 px-3">
                        <input
                          type="number"
                          min="0"
                          max="255"
                          value={row.dec}
                          onChange={(e) => handleDecChange(idx, parseInt(e.target.value, 10))}
                          className={`w-20 bg-slate-800 border rounded px-2 py-1 text-xs font-bold text-center focus:outline-none ${
                            isMachineId
                              ? 'border-amber-600 text-amber-300'
                              : isChecksum
                              ? 'border-indigo-600 text-indigo-300'
                              : isStx || isEtx
                              ? 'border-emerald-600 text-emerald-300'
                              : 'border-slate-700 text-white focus:border-emerald-500'
                          }`}
                        />
                      </td>

                      {/* Hex input */}
                      <td className="py-1.5 px-3">
                        <input
                          type="text"
                          maxLength={2}
                          value={row.dec.toString(16).padStart(2, '0').toUpperCase()}
                          onChange={(e) => handleHexChange(idx, e.target.value)}
                          className="w-14 bg-slate-800 border border-slate-700 rounded px-1.5 py-1 text-xs font-bold text-center text-slate-300 focus:outline-none focus:border-emerald-500"
                        />
                      </td>

                      {/* ASCII */}
                      <td className="py-1.5 px-3 text-center font-bold text-cyan-400">
                        {asciiChar}
                      </td>

                      {/* Description */}
                      <td className="py-1.5 px-3 font-sans">
                        <input
                          type="text"
                          value={row.description}
                          onChange={(e) => {
                            const val = e.target.value;
                            setRows((prev) => {
                              const next = [...prev];
                              next[idx] = { ...next[idx], description: val };
                              return next;
                            });
                          }}
                          className="w-full bg-transparent border-0 text-slate-200 text-xs focus:ring-0 focus:outline-none hover:bg-slate-800/40 rounded px-1"
                        />
                      </td>

                      {/* Remarks */}
                      <td className="py-1.5 px-3 font-sans text-slate-400">
                        <input
                          type="text"
                          value={row.remarks}
                          onChange={(e) => {
                            const val = e.target.value;
                            setRows((prev) => {
                              const next = [...prev];
                              next[idx] = { ...next[idx], remarks: val };
                              return next;
                            });
                          }}
                          placeholder="Note..."
                          className="w-full bg-transparent border-0 text-slate-400 text-xs focus:ring-0 focus:outline-none hover:bg-slate-800/40 rounded px-1"
                        />
                      </td>

                      {/* Actions */}
                      <td className="py-1.5 px-2 text-center">
                        <div className="flex items-center justify-center gap-1">
                          <button
                            onClick={() => handleInsertByteBefore(idx)}
                            title="Insert byte before"
                            className="p-1 text-slate-400 hover:text-emerald-400 rounded hover:bg-slate-800"
                          >
                            <Plus className="w-3 h-3" />
                          </button>
                          {reindexedRows.length > 2 && (
                            <button
                              onClick={() => handleDeleteByte(idx)}
                              title="Delete byte"
                              className="p-1 text-slate-400 hover:text-rose-400 rounded hover:bg-slate-800"
                            >
                              <Trash2 className="w-3 h-3" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="p-2.5 bg-slate-800/60 border-t border-slate-700/80 flex items-center justify-between">
            <button
              onClick={handleAddByte}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-lg text-xs font-semibold transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add Byte Row</span>
            </button>

            <span className="text-xs text-slate-400 font-mono">
              Total Frame Length: <strong className="text-emerald-400">{reindexedRows.length}</strong> bytes
            </span>
          </div>
        </div>
      )}

      {/* VIEW MODE 2: Hex Stream Editor */}
      {rawTextMode === 'hexText' && (
        <div className="bg-slate-900 border border-slate-700/80 rounded-xl p-4 space-y-3">
          <div className="text-xs text-slate-400">
            Enter space- or comma-separated two-digit Hex values (e.g.{' '}
            <code className="text-amber-300 font-mono">03 00 00 00 17 00 0A ...</code>):
          </div>
          <textarea
            rows={4}
            value={rawHexText}
            onChange={(e) => setRawHexText(e.target.value)}
            className="w-full bg-slate-950 border border-slate-700 rounded-lg p-3 font-mono text-xs text-emerald-400 focus:outline-none focus:border-emerald-500"
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400">
              Click &apos;Apply Hex to Frame&apos; to rebuild the table rows.
            </span>
            <button
              onClick={handleApplyHexText}
              className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-lg transition-colors"
            >
              Apply Hex to Frame
            </button>
          </div>
        </div>
      )}

      {/* VIEW MODE 3: Decimal Stream Editor */}
      {rawTextMode === 'decText' && (
        <div className="bg-slate-900 border border-slate-700/80 rounded-xl p-4 space-y-3">
          <div className="text-xs text-slate-400">
            Enter comma-separated Decimal byte numbers (e.g.{' '}
            <code className="text-amber-300 font-mono">3, 0, 0, 0, 23, 0, 10, 0, 0, 50, ...</code>):
          </div>
          <textarea
            rows={4}
            value={rawDecText}
            onChange={(e) => setRawDecText(e.target.value)}
            className="w-full bg-slate-950 border border-slate-700 rounded-lg p-3 font-mono text-xs text-emerald-400 focus:outline-none focus:border-emerald-500"
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400">
              Click &apos;Apply Decimals to Frame&apos; to rebuild the table rows.
            </span>
            <button
              onClick={handleApplyDecText}
              className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-lg transition-colors"
            >
              Apply Decimals to Frame
            </button>
          </div>
        </div>
      )}

      {/* Saved Custom Presets */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-3.5 space-y-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Bookmark className="w-4 h-4 text-emerald-400" />
            <span className="text-xs font-bold text-slate-200">Custom Saved Frames</span>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="text"
              value={newPresetName}
              onChange={(e) => setNewPresetName(e.target.value)}
              placeholder="e.g. Carding GC 10 Test"
              className="bg-slate-800 border border-slate-700 rounded px-2.5 py-1 text-xs text-white focus:outline-none focus:border-emerald-500"
            />
            <button
              onClick={handleSavePreset}
              disabled={!newPresetName.trim()}
              className="px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded text-xs font-medium disabled:opacity-40"
            >
              Save Current
            </button>
          </div>
        </div>

        {savedFrames.length > 0 ? (
          <div className="flex flex-wrap gap-2 pt-1">
            {savedFrames.map((preset, idx) => (
              <div
                key={idx}
                className="flex items-center gap-1.5 bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1 text-xs"
              >
                <button
                  onClick={() => handleLoadSavedPreset(preset.bytes)}
                  className="text-slate-300 hover:text-white font-medium"
                >
                  {preset.name} ({preset.bytes.length}B)
                </button>
                <button
                  onClick={() => handleDeleteSavedPreset(idx)}
                  className="text-slate-500 hover:text-rose-400"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-[11px] text-slate-500">
            No custom frames saved yet. Save your crafted test frames above to reuse them anytime.
          </p>
        )}
      </div>

      {/* LIVE RESPONSE SECTION */}
      {lastResponse?.testId && <p className="text-xs text-slate-400 font-mono break-all">Test ID: {lastResponse.testId} (saved in history)</p>}
      {lastResponse && (
        <div className="bg-slate-900 border border-slate-700 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
            <div className="flex items-center gap-2">
              {lastResponse.success ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              ) : (
                <AlertTriangle className="w-4 h-4 text-amber-400" />
              )}
              <span className="font-bold text-sm text-white">
                PLC Response ({lastResponse.rawBytes.length} Bytes, {lastResponse.rttMs} ms)
              </span>
              <span className="text-xs text-slate-500 font-mono">at {lastResponse.timestamp}</span>
            </div>

            {lastResponse.rawBytes.length > 0 && (
              <span
                className={`text-xs px-2.5 py-0.5 rounded font-mono font-bold ${
                  lastResponse.rawBytes[2] === 0
                    ? 'bg-emerald-950/80 border border-emerald-700 text-emerald-300'
                    : 'bg-rose-950/80 border border-rose-700 text-rose-300'
                }`}
              >
                Result Code: {lastResponse.rawBytes[2]} {lastResponse.rawBytes[2] === 0 ? '(Success)' : '(Error)'}
              </span>
            )}
          </div>

          {lastResponse.error && (
            <div className="p-3 bg-amber-950/50 border border-amber-800/80 rounded-lg text-xs text-amber-300 flex items-start gap-2">
              <Info className="w-4 h-4 shrink-0 mt-0.5 text-amber-400" />
              <div>
                <strong className="block font-semibold">Transmission Note:</strong>
                <span>{lastResponse.error}</span>
              </div>
            </div>
          )}

          {lastResponse.rawBytes.length > 0 && (
            <div className="space-y-2 font-mono">
              <div className="text-xs text-slate-400 font-sans font-semibold">
                Hex & ASCII Response Dump:
              </div>
              <pre className="p-3 bg-slate-950 rounded-lg border border-slate-800 text-slate-300 overflow-x-auto text-[11px] leading-relaxed max-h-48 scrollbar-thin scrollbar-thumb-slate-700">
                {formatHexDump(lastResponse.rawBytes)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
