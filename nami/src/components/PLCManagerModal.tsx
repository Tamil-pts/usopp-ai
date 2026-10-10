import React, { useState, useEffect, useRef } from 'react';
import { X, Plus, Trash2, CheckCircle2, AlertTriangle, RefreshCw, Cpu, Globe, Clock, FileSpreadsheet, Sliders, Upload } from 'lucide-react';
import { PLCConfig, SpinningMachineType } from '../types';
import { SPINNING_MACHINE_TYPES } from '../data/machinePresets';
import { ManualFrameSender } from './ManualFrameSender';

interface PLCManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
  plcs: PLCConfig[];
  onSavePLCs: (plcs: PLCConfig[]) => void;
  selectedPLCId: string;
  onSelectPLCId: (id: string) => void;
  onOpenRTCModal?: (plc: PLCConfig) => void;
  onOpenMetadataModal?: (machineType: SpinningMachineType) => void;
  initialTab?: 'targets' | 'manual-frame';
}

export const PLCManagerModal: React.FC<PLCManagerModalProps> = ({
  isOpen,
  onClose,
  plcs,
  onSavePLCs,
  selectedPLCId,
  onSelectPLCId,
  onOpenRTCModal,
  onOpenMetadataModal,
  initialTab = 'targets',
}) => {
  const [items, setItems] = useState<PLCConfig[]>(plcs);
  const [activeTab, setActiveTab] = useState<'targets' | 'manual-frame'>(initialTab);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [draftSelectedId, setDraftSelectedId] = useState(selectedPLCId);
  const [formError, setFormError] = useState('');
  const requestRef = useRef<AbortController | null>(null);
  const [testResults, setTestResults] = useState<
    Record<string, { ok: boolean; msg: string; rtt?: number; version?: string | null }>
  >({});

  // Each opening starts from saved settings; Cancel must discard the draft.
  useEffect(() => {
    requestRef.current?.abort();
    setTestingId(null);
    if (isOpen) {
      setItems(plcs.map(p => ({...p})));
      setDraftSelectedId(selectedPLCId);
      setTestResults({});
      setFormError('');
      setActiveTab(initialTab);
    }
    return () => { requestRef.current?.abort(); };
  }, [isOpen]);

  if (!isOpen) return null;

  const activePLC = items.find((p) => p.id === draftSelectedId) || items[0];

  const validate = (plc: PLCConfig) => {
    if (!plc.name.trim()) return 'Enter a PLC name.';
    if (!plc.isSimulated && !plc.ip.trim()) return `${plc.name}: enter the controller IP address or hostname.`;
    if (!Number.isInteger(plc.port) || plc.port < 1 || plc.port > 65535) return `${plc.name}: PLC TCP port must be 1–65535.`;
    if (!Number.isInteger(plc.machineId) || plc.machineId < 0 || plc.machineId > 255) return `${plc.name}: Machine ID must be 0–255.`;
    if (!Number.isInteger(plc.timeoutMs) || (plc.timeoutMs ?? 0) < 100 || (plc.timeoutMs ?? 0) > 120000) return `${plc.name}: timeout must be 100–120000 ms.`;
    return '';
  };
  const applyDraft = (id = draftSelectedId) => {
    const error = items.map(validate).find(Boolean);
    if (error) { setFormError(error); return false; }
    onSavePLCs(items.map(p => ({...p, name:p.name.trim(), ip:p.ip.trim()})));
    onSelectPLCId(id);
    return true;
  };

  const handleUpdateItem = (id: string, updates: Partial<PLCConfig>) => {
    setItems((prev) => prev.map((p) => (p.id === id ? { ...p, ...updates } : p)));
    setFormError('');
    if (Object.keys(updates).some(key => ['ip','port','machineId','isSimulated','endianness','timeoutMs','machineType'].includes(key))) {
      setItems((prev) => prev.map((p) => p.id === id ? {...p, status: 'idle', tcpConnected: false,
        error: undefined, programVersion: undefined, programVersionStr: undefined} : p));
      requestRef.current?.abort();
      setTestingId(null);
      setTestResults(prev => { const next = {...prev}; delete next[id]; return next; });
    }
  };

  const handleAddPLC = () => {
    const newPLC: PLCConfig = {
      id: `plc-${crypto.randomUUID()}`,
      name: `Machine #${items.length + 1}`,
      machineType: 'Carding',
      ip: '192.168.1.100',
      port: 21010,
      machineId: 0,
      isSimulated: false,
      endianness: 'little',
      timeoutMs: 3000,
      status: 'idle',
    };
    setItems([...items, newPLC]);
  };

  const handleDeletePLC = (id: string) => {
    if (items.length <= 1) return;
    const remaining = items.filter((p) => p.id !== id);
    setItems(remaining);
    if (draftSelectedId === id) {
      setDraftSelectedId(remaining[0].id);
    }
  };

  const handleTestConnection = async (plc: PLCConfig) => {
    const error = validate(plc);
    if (error) { setFormError(error); return; }
    const controller = new AbortController();
    requestRef.current = controller;
    setTestingId(plc.id);
    try {
      const res = await fetch('/api/nami/plc/test-connection', {
        signal:controller.signal,
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ip: plc.ip,
          port: plc.port,
          machineId: plc.machineId,
          isSimulated: plc.isSimulated,
          timeoutMs: plc.timeoutMs,
          endianness: plc.endianness,
        }),
      });
      const data = await res.json();
      if (controller.signal.aborted) return;
      setTestResults((prev) => ({
        ...prev,
        [plc.id]: {
          ok: res.ok && data.success,
          msg: data.message || data.error || data.detail || (data.success ? 'Handshake Successful' : 'Failed to connect'),
          rtt: data.rttMs,
          version: data.programVersionStr,
        },
      }));
      handleUpdateItem(plc.id, {
        status: data.success ? 'connected' : 'error',
        tcpConnected: data.tcpConnected,
        lastTested: new Date().toLocaleTimeString(),
        error: data.success ? undefined : data.message || data.error || data.detail,
        programVersion: data.programVersion ?? undefined,
        programVersionStr: data.programVersionStr ?? undefined,
      });
    } catch (err: any) {
      if (controller.signal.aborted) return;
      setTestResults((prev) => ({
        ...prev,
        [plc.id]: { ok: false, msg: err.message },
      }));
      handleUpdateItem(plc.id, { status: 'error', tcpConnected: false, error: err.message });
    } finally {
      if (requestRef.current === controller) setTestingId(null);
    }
  };

  const handleSaveAndClose = () => {
    if (applyDraft()) onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl max-w-6xl w-full flex flex-col max-h-[92vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-4 pb-2 border-b border-slate-800">
          <div>
            <h2 className="text-lg font-bold text-white">PLC Settings & Protocol Tools</h2>
            <p className="text-xs text-slate-400">
              Configure PLC connections and protocol frames. Changes take effect with Save &amp; Apply. Metadata and RTC actions also apply your draft first.
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white p-1 rounded-md">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-2 px-6 border-b border-slate-800 bg-slate-950/40">
          <button
            onClick={() => setActiveTab('targets')}
            className={`flex items-center gap-2 px-4 py-3 text-xs font-bold border-b-2 transition-all cursor-pointer ${
              activeTab === 'targets'
                ? 'border-emerald-500 text-emerald-400 bg-emerald-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Cpu className="w-4 h-4" />
            <span>PLC Connections & Targets</span>
            <span className="text-[10px] px-1.5 py-0.2 bg-slate-800 text-slate-400 rounded">
              {items.length}
            </span>
          </button>

          <button
            onClick={() => setActiveTab('manual-frame')}
            className={`flex items-center gap-2 px-4 py-3 text-xs font-bold border-b-2 transition-all cursor-pointer ${
              activeTab === 'manual-frame'
                ? 'border-emerald-500 text-emerald-400 bg-emerald-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Sliders className="w-4 h-4" />
            <span>Manual Data Frame Editor & Sender</span>
            <span className="text-[10px] px-1.5 py-0.2 bg-emerald-950 text-emerald-400 border border-emerald-700/60 rounded font-semibold">
              Live TCP
            </span>
          </button>
        </div>

        {/* Body content */}
        <div className="p-6 overflow-y-auto flex-1 space-y-4">
          {formError && <p role="alert" className="rounded-lg border border-rose-700 bg-rose-950/60 text-rose-300 p-3 text-sm">{formError}</p>}
          {activeTab === 'manual-frame' ? (
            <ManualFrameSender
              activePLC={activePLC}
              onUpdatePLC={(updates) => handleUpdateItem(activePLC.id, updates)}
            />
          ) : (
            <>
              {items.map((plc, idx) => {
                const test = testResults[plc.id];
                const isSelected = draftSelectedId === plc.id;

                return (
                  <div
                    key={plc.id}
                    className={`p-4 rounded-xl border transition-all ${
                      isSelected
                        ? 'bg-slate-800/80 border-emerald-500/60 shadow-md shadow-emerald-500/5'
                        : 'bg-slate-800/40 border-slate-700'
                    }`}
                  >
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-3">
                      <div className="flex items-center gap-2">
                        <span className="w-6 h-6 rounded-full bg-slate-700 text-slate-300 flex items-center justify-center text-xs font-bold">
                          {idx + 1}
                        </span>
                        <input
                          type="text"
                          value={plc.name}
                          onChange={(e) => handleUpdateItem(plc.id, { name: e.target.value })}
                          placeholder="PLC Machine Name"
                          className="font-semibold text-white bg-slate-700/50 border border-slate-600 rounded px-2.5 py-1 text-sm focus:outline-none focus:border-emerald-500"
                        />
                        <button
                          onClick={() => setDraftSelectedId(plc.id)}
                          className={`text-xs px-2 py-0.5 rounded font-medium ${
                            isSelected
                              ? 'bg-emerald-600 text-white'
                              : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                          }`}
                        >
                          {isSelected ? 'Active Target' : 'Set Active'}
                        </button>
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          onClick={() => handleTestConnection(plc)}
                          disabled={testingId !== null}
                          className="flex items-center gap-1.5 px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs font-medium rounded-lg border border-slate-600 transition-colors"
                        >
                          <RefreshCw className={`w-3.5 h-3.5 ${testingId === plc.id ? 'animate-spin' : ''}`} />
                          <span>{testingId === plc.id ? 'Testing GC 10...' : 'Ping / GC 10 Test'}</span>
                        </button>

                        {onOpenMetadataModal && (
                          <button
                            onClick={() => {
                              if (applyDraft(plc.id)) onOpenMetadataModal(plc.machineType || 'Carding');
                            }}
                            className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-lg border border-slate-600 transition-colors"
                            title="Upload/manage metadata for this PLC machine type"
                          >
                            <Upload className="w-3.5 h-3.5 text-indigo-400" />
                            <span>Metadata</span>
                          </button>
                        )}

                        <button
                          onClick={() => {
                            setDraftSelectedId(plc.id);
                            setActiveTab('manual-frame');
                          }}
                          className="flex items-center gap-1.5 px-2.5 py-1 bg-emerald-950/60 hover:bg-emerald-900/80 text-emerald-300 text-xs font-medium rounded-lg border border-emerald-700/60 transition-colors"
                          title="Open Manual Frame Editor for this PLC"
                        >
                          <Sliders className="w-3.5 h-3.5 text-emerald-400" />
                          <span>Edit Frame</span>
                        </button>

                        {onOpenRTCModal && (
                          <button
                            onClick={() => {
                              if (applyDraft(plc.id)) { onClose(); onOpenRTCModal(plc); }
                            }}
                            className="flex items-center gap-1.5 px-2.5 py-1 bg-indigo-950/60 hover:bg-indigo-900/80 text-indigo-300 text-xs font-medium rounded-lg border border-indigo-700/60 transition-colors"
                            title="Open RTC Tester for this PLC"
                          >
                            <Clock className="w-3.5 h-3.5 text-indigo-400" />
                            <span>Test RTC</span>
                          </button>
                        )}

                        {items.length > 1 && (
                          <button
                            onClick={() => handleDeletePLC(plc.id)}
                            className="p-1.5 text-rose-400 hover:text-rose-300 hover:bg-rose-950/40 rounded transition-colors"
                            title="Remove PLC"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Form fields */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
                      <div>
                        <label className="block text-slate-400 mb-1">Machine Type</label>
                        <select
                          value={plc.machineType || 'Carding'}
                          onChange={(e) => handleUpdateItem(plc.id, { machineType: e.target.value as SpinningMachineType })}
                          className="w-full bg-indigo-950/40 border border-indigo-700/60 rounded px-2 py-1.5 text-indigo-200 font-semibold focus:outline-none"
                        >
                          {SPINNING_MACHINE_TYPES.map((m) => (
                            <option key={m} value={m} className="bg-slate-800 text-white">
                              {m}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label className="block text-slate-400 mb-1">Target Mode</label>
                        <select
                          value={plc.isSimulated ? 'sim' : 'real'}
                          onChange={(e) => handleUpdateItem(plc.id, { isSimulated: e.target.value === 'sim' })}
                          className="w-full bg-slate-700/50 border border-slate-600 rounded px-2 py-1.5 text-slate-200 focus:outline-none"
                        >
                          <option value="sim">Simulated (Internal)</option>
                          <option value="real">Real PLC (Network TCP)</option>
                        </select>
                      </div>

                      <div>
                        <label className="block text-slate-400 mb-1">IP Address</label>
                        <input
                          type="text"
                          value={plc.ip}
                          onChange={(e) => handleUpdateItem(plc.id, { ip: e.target.value })}
                          placeholder="e.g. 192.168.1.100"
                          className="w-full bg-slate-700/50 border border-slate-600 rounded px-2 py-1.5 text-slate-200 font-mono focus:outline-none"
                        />
                      </div>

                      <div>
                        <label className="block text-slate-400 mb-1">PLC TCP Port</label>
                        <input
                          type="number"
                          value={plc.port}
                          min={1} max={65535} step={1}
                          onChange={(e) => handleUpdateItem(plc.id, { port: Number(e.target.value) })}
                          className="w-full bg-slate-700/50 border border-slate-600 rounded px-2 py-1.5 text-slate-200 font-mono focus:outline-none"
                        />
                      </div>

                      <div>
                        <label className="block text-amber-400 font-semibold mb-1">Machine ID (frame byte 1)</label>
                        <input
                          type="number"
                          value={plc.machineId}
                          min={0} max={255} step={1}
                          onChange={(e) =>
                            handleUpdateItem(plc.id, {
                              machineId: Number(e.target.value),
                            })
                          }
                          className="w-full bg-amber-950/30 border border-amber-600/70 rounded px-2 py-1.5 text-amber-300 font-mono font-bold focus:outline-none"
                        />
                      </div>

                      <div>
                        <label className="block text-slate-400 mb-1">Timeout (ms)</label>
                        <input
                          type="number"
                          value={plc.timeoutMs ?? 5000}
                          min={100} max={120000} step={100}
                          onChange={(e) => handleUpdateItem(plc.id, { timeoutMs: Number(e.target.value) })}
                          className="w-full bg-slate-700/50 border border-slate-600 rounded px-2 py-1.5 text-slate-200 font-mono focus:outline-none"
                        />
                      </div>

                      <div>
                        <label className="block text-slate-400 mb-1">Byte Endianness</label>
                        <select
                          value={plc.endianness}
                          onChange={(e) => handleUpdateItem(plc.id, { endianness: e.target.value as 'little' | 'big' })}
                          className="w-full bg-slate-700/50 border border-slate-600 rounded px-2 py-1.5 text-slate-200 focus:outline-none"
                        >
                          <option value="little">Little-Endian (B&R)</option>
                          <option value="big">Big-Endian</option>
                        </select>
                      </div>
                    </div>

                    {/* Status response badge if tested */}
                    {test && (
                      <div className="mt-2.5 space-y-2">
                        <div
                          className={`px-3 py-2 rounded-lg text-xs flex items-center justify-between gap-2 ${
                            test.ok
                              ? 'bg-emerald-950/60 border border-emerald-700 text-emerald-300'
                              : 'bg-rose-950/60 border border-rose-800 text-rose-300'
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            {test.ok ? (
                              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                            ) : (
                              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                            )}
                            <div>
                              <div className="font-semibold">{test.msg}</div>
                              {test.version && (
                                <div className="text-[11px] text-emerald-400 mt-0.5">
                                  Handshake Verified: Program Version <span className="font-mono font-bold bg-emerald-900/60 px-1.5 py-0.2 rounded border border-emerald-700">v{test.version}</span>
                                </div>
                              )}
                            </div>
                          </div>
                          {test.rtt !== undefined && (
                            <span className="font-mono text-[11px] opacity-90 shrink-0">{test.rtt} ms RTT</span>
                          )}
                        </div>

                        {!test.ok && !plc.isSimulated && (
                          <div className="p-3 bg-slate-900/80 border border-slate-700/80 rounded-lg text-[11px] text-slate-300 space-y-1.5">
                            <div className="font-semibold text-amber-400 flex items-center gap-1.5">
                              <AlertTriangle className="w-3.5 h-3.5" />
                              <span>Industrial Ethernet Connection Troubleshooting:</span>
                            </div>
                            <ul className="list-disc pl-4 space-y-1 text-slate-400">
                              <li>
                                <strong className="text-slate-200">PLC IP ({plc.ip}):</strong> Note that <code className="text-amber-300">192.168.1.1</code> is usually your Wi-Fi router. Verify your B&R PLC Ethernet IP in Automation Studio (commonly <code className="text-emerald-300">192.168.1.100</code> or similar).
                              </li>
                              <li>
                                <strong className="text-slate-200">Laptop Static IP:</strong> When connected directly via RJ45 cable, your Windows Ethernet adapter must be set to a static IP in the same subnet (e.g. <code className="text-emerald-300">192.168.1.50</code>, Mask <code className="text-emerald-300">255.255.255.0</code>).
                              </li>
                              <li>
                                <strong className="text-slate-200">TCP Port {plc.port}:</strong> Ensure the PLC's <code className="text-slate-300">TcpServer</code> function block is running and listening on port {plc.port}.
                              </li>
                              <li>
                                <strong className="text-slate-200">Machine ID ({plc.machineId}):</strong> Ensure the PLC's ST buffer check <code className="text-slate-300">IF (Rx_buffer[1] = {plc.machineId})</code> matches this ID (default is 0).
                              </li>
                            </ul>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}

              <button
                onClick={handleAddPLC}
                className="w-full py-2.5 border-2 border-dashed border-slate-700 hover:border-slate-500 rounded-xl text-slate-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors"
              >
                <Plus className="w-4 h-4" />
                <span>Add Another PLC Target</span>
              </button>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-800 bg-slate-900/50">
          <button
            onClick={onClose}
            className="px-4 py-2 text-slate-300 hover:text-white text-xs font-medium rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSaveAndClose}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors"
          >
            Save & Apply
          </button>
        </div>
      </div>
    </div>
  );
};
