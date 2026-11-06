import {frameProtocol,isYbsTarget,metadataMachine,frameProtocolUpdates} from '../utils/frameProfile';
import {targetMode} from '../utils/targetMode';
import React, { useState, useEffect, useRef } from 'react';
import { X, Plus, Trash2, CheckCircle2, AlertTriangle, RefreshCw, Cpu, Globe, Clock, FileSpreadsheet, Sliders, Upload, Radio } from 'lucide-react';
import { PLCConfig, SpinningMachineType } from '../types';
import { SPINNING_MACHINE_TYPES } from '../data/machinePresets';
import { ManualFrameSender } from './ManualFrameSender';
import {RequestFrameSelect} from './RequestFrameSelect';

interface PLCManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
  plcs: PLCConfig[];
  onSavePLCs: (plcs: PLCConfig[]) => Promise<void>;
  selectedPLCId: string;
  onSelectPLCId: (id: string) => void;
  onOpenRTCModal?: (plc: PLCConfig) => void;
  onOpenMetadataModal?: (machineType: SpinningMachineType) => void;
  initialTab?: 'targets' | 'manual-frame';
  liveStatus?:Record<string,{lastCapturedAt?:number;error?:string;collecting:boolean}>;
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
  liveStatus={},
}) => {
  const [items, setItems] = useState<PLCConfig[]>(plcs);
  const [activeTab, setActiveTab] = useState<'targets' | 'manual-frame'>(initialTab);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [pingingId, setPingingId] = useState<string | null>(null);
  const [draftSelectedId, setDraftSelectedId] = useState(selectedPLCId);
  const [formError, setFormError] = useState('');
  const [saving,setSaving]=useState(false);
  const [groupText,setGroupText]=useState<Record<string,string>>({});
  const requestRef = useRef<AbortController | null>(null);
  const [testResults, setTestResults] = useState<
    Record<string, { ok: boolean; msg: string; rtt?: number; version?: string | null }>
  >({});
  const [pingResults, setPingResults] = useState<Record<string, {ok:boolean;msg:string;rtt?:number}>>({});

  // Each opening starts from saved settings; Cancel must discard the draft.
  useEffect(() => {
    requestRef.current?.abort();
    setTestingId(null);
    setPingingId(null);
    if (isOpen) {
      setItems(plcs.map(p => ({...p})));
      setGroupText(Object.fromEntries(plcs.map(p=>[p.id,(p.liveGroupCodes||[]).join(', ')])));
      setDraftSelectedId(selectedPLCId);
      setTestResults({});
      setPingResults({});
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
    if(plc.liveEnabled&&plc.timeoutMs>30000)return `${plc.name}: live collection timeout must be at most 30000 ms.`;
    if(plc.liveEnabled&&!(plc.liveGroupCodes?.length))return `${plc.name}: enter the group codes to collect.`;
    if(plc.liveGroupCodes?.some(group=>!Number.isInteger(group)||group<0||group>65535||group===11)||((plc.liveGroupCodes?.length||0)>32))return `${plc.name}: select up to 32 valid group codes; GC 11 closes automatically.`;
    if(!Number.isInteger(plc.retentionDays??30)||(plc.retentionDays??30)<1||(plc.retentionDays??30)>30)return 'Retention must be 1–30 days.';
    if(!Number.isInteger(plc.liveIntervalSeconds??10)||(plc.liveIntervalSeconds??10)<5||(plc.liveIntervalSeconds??10)>3600)return 'Live sample interval must be 5–3600 seconds.';
    return '';
  };
  const applyDraft = async (id = draftSelectedId) => {
    const error = items.map(validate).find(Boolean);
    if (error) { setFormError(error); return false; }
    setSaving(true);
    try{await onSavePLCs(items.map(p => ({...p, name:p.name.trim(), ip:p.ip.trim()})));onSelectPLCId(id);return true}
    catch(reason){setFormError(reason instanceof Error?reason.message:'Could not save target settings.');return false}
    finally{setSaving(false)}
  };

  const handleUpdateItem = (id: string, updates: Partial<PLCConfig>) => {
    setItems((prev) => prev.map((p) => (p.id === id ? { ...p, ...updates } : p)));
    setFormError('');
    if (Object.keys(updates).some(key => ['ip','port','machineId','isSimulated','targetMode','endianness','timeoutMs','machineType','frameProtocol'].includes(key))) {
      setItems((prev) => prev.map((p) => p.id === id ? {...p, status: 'idle', tcpConnected: false,
        error: undefined, programVersion: undefined, programVersionStr: undefined} : p));
      requestRef.current?.abort();
      setTestingId(null);
      setPingingId(null);
      setTestResults(prev => { const next = {...prev}; delete next[id]; return next; });
      setPingResults(prev => { const next = {...prev}; delete next[id]; return next; });
    }
  };

  const handleAddPLC = () => {
    const newPLC: PLCConfig = {
      id: `plc-${crypto.randomUUID()}`,
      name: `Machine #${items.length + 1}`,
      machineType: 'Carding',
      frameProtocol: 'spinconnect',
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
          plc, machineType: plc.machineType,
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

  const handlePingIp = async (plc: PLCConfig) => {
    if (!plc.ip.trim()) { setFormError(`${plc.name}: enter an IP address to ping.`); return; }
    const controller = new AbortController();
    requestRef.current = controller;
    setPingingId(plc.id);
    setPingResults(previous => ({...previous,[plc.id]:{ok:false,msg:'Sending one ICMP ping…'}}));
    try {
      const response = await fetch('/api/nami/plc/ping', {
        signal: controller.signal,
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ip:plc.ip,timeoutMs:Math.min(Math.max(plc.timeoutMs || 2000,100),10000)}),
      });
      const data = await response.json();
      if (controller.signal.aborted) return;
      setPingResults(previous => ({...previous,[plc.id]:{
        ok: response.ok && data.success === true,
        msg: data.message || data.detail || 'Ping failed.',
        rtt: data.rttMs ?? undefined,
      }}));
    } catch (error: any) {
      if (controller.signal.aborted) return;
      setPingResults(previous => ({...previous,[plc.id]:{ok:false,msg:error?.message || 'Ping request failed.'}}));
    } finally {
      if (requestRef.current === controller) setPingingId(null);
    }
  };

  const handleSaveAndClose = async () => {
    if (await applyDraft()) onClose();
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
                const ping = pingResults[plc.id];
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
                          onClick={() => handlePingIp(plc)}
                          disabled={pingingId !== null || testingId !== null}
                          className="flex items-center gap-1.5 px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs font-medium rounded-lg border border-slate-600 transition-colors disabled:opacity-50"
                          title="Send one ICMP echo request only. This does not send PLC data."
                        >
                          <Radio className={`w-3.5 h-3.5 ${pingingId === plc.id ? 'animate-pulse' : ''}`} />
                          <span>{pingingId === plc.id ? 'Pinging IP…' : 'Ping IP'}</span>
                        </button>
                        <button
                          onClick={() => handleTestConnection(plc)}
                          disabled={testingId !== null || pingingId !== null}
                          className="flex items-center gap-1.5 px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs font-medium rounded-lg border border-slate-600 transition-colors"
                        >
                          <RefreshCw className={`w-3.5 h-3.5 ${testingId === plc.id ? 'animate-spin' : ''}`} />
                          <span>{testingId === plc.id ? 'Testing TCP / GC 10…' : 'TCP / GC 10 Test'}</span>
                        </button>

                        {onOpenMetadataModal && (
                          <button
                            onClick={async () => {
                              if (await applyDraft(plc.id)) onOpenMetadataModal(metadataMachine(plc));
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

                        {onOpenRTCModal && !isYbsTarget(plc) && (
                          <button
                            onClick={async () => {
                              if (await applyDraft(plc.id)) { onClose(); onOpenRTCModal(plc); }
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
                      <RequestFrameSelect className="block text-emerald-300 [&_select]:block [&_select]:w-full [&_select]:mt-1 [&_select]:bg-slate-800 [&_select]:border [&_select]:border-slate-600 [&_select]:rounded [&_select]:p-2" value={frameProtocol(plc)} onChange={protocol=>handleUpdateItem(plc.id,frameProtocolUpdates(plc,protocol))}/>
                      <div>
                        <label className="block text-slate-400 mb-1">Machine Type</label>
                        <select
                          value={plc.machineType || 'Carding'}
                          onChange={(e) => handleUpdateItem(plc.id, { machineType: e.target.value as SpinningMachineType, ...(e.target.value==='YBS'?frameProtocolUpdates(plc,'ybs'):{}) })}
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
                          value={targetMode(plc)}
                          onChange={(e) => handleUpdateItem(plc.id, {targetMode:e.target.value as PLCConfig['targetMode'],isSimulated:false,...(e.target.value==='data-simulator'?{ip:'127.0.0.1',port:21210+idx}:e.target.value==='automation-studio'?{ip:'127.0.0.1',port:21010}:{})})}
                          className="w-full bg-slate-700/50 border border-slate-600 rounded px-2 py-1.5 text-slate-200 focus:outline-none"
                        >
                          <option value="plc">Real PLC (Network TCP)</option>
                          <option disabled={isYbsTarget(plc)} value="automation-studio">Automation Studio simulation</option>
                          <option disabled={isYbsTarget(plc)} value="data-simulator">Data simulator (metadata-driven TCP)</option>
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
                          <label className="block text-slate-400 mb-1">SpinConnect TCP server port</label>
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
                          disabled={isYbsTarget(plc)} value={isYbsTarget(plc)?'big':plc.endianness}
                          onChange={(e) => handleUpdateItem(plc.id, { endianness: e.target.value as 'little' | 'big' })}
                          className="w-full bg-slate-700/50 border border-slate-600 rounded px-2 py-1.5 text-slate-200 focus:outline-none"
                        >
                          <option value="little">Little-Endian (B&R)</option>
                          <option value="big">Big-Endian</option>
                        </select>
                      </div>
                    </div>

                    {targetMode(plc)==='automation-studio'&&<div className="mt-3 rounded-lg border border-sky-700/60 bg-sky-950/30 p-3 text-xs text-slate-300 space-y-2">
                      <p className="font-semibold text-sky-200">Choose the port for the service Nami uses</p>
                      <p><code className="text-slate-100">REPO=11160</code> is the Automation Studio simulation’s INA port (UDP). <code className="text-slate-100">/PT</code> is the ANSL online port (TCP, commonly 11169). Nami’s GC 10 check uses neither B&amp;R protocol; it sends SpinConnect frames to your PLC program’s TCP server.</p>
                      <p>If you want Nami’s TCP server to use port <strong>11160</strong>, configure the PLC program’s <code className="text-slate-100">TcpServer</code> to listen for SpinConnect frames on TCP port 11160, then enter 11160 above. Changing <code className="text-slate-100">REPO</code> alone will not do this. The current configured value is <strong>{plc.port}</strong>.</p>
                      <p>Addresses in <code className="text-slate-100">127.0.0.0/8</code>, including 127.0.0.1 and 127.0.0.2, refer to this same computer. Use the simulation computer’s LAN IP only when it runs on another computer.</p>
                    </div>}
                    {targetMode(plc)==='data-simulator'&&<p className="mt-3 text-xs text-slate-300">Save this target, select it, then open Data simulator in PLC details to load metadata, configure the generated values and start the virtual PLC.</p>}
                    <fieldset className="mt-4 p-3 border border-slate-700 rounded-lg text-xs space-y-3" disabled={saving}>
                      <legend className="px-2 font-semibold text-emerald-400">Live collection &amp; report history</legend>
                      <label className="flex items-center gap-2 text-slate-200"><input type="checkbox" checked={plc.liveEnabled===true} onChange={event=>handleUpdateItem(plc.id,{liveEnabled:event.target.checked})}/>Enable live collection</label>
                      <p className="text-slate-400">Off by default. When enabled, the server reads this machine even after you close the browser. Other machines can be collected and tested at the same time.</p>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <label className="text-slate-400">Group codes to collect<input aria-label={`Live groups for ${plc.name}`} className="block w-full mt-1 bg-slate-800 border border-slate-600 rounded p-2 text-slate-100" placeholder="20, 40, 50" value={groupText[plc.id]??''} onChange={event=>{setGroupText(previous=>({...previous,[plc.id]:event.target.value}));handleUpdateItem(plc.id,{liveGroupCodes:event.target.value.split(',').map(value=>value.trim()).filter(Boolean).map(Number)})}}/></label>
                        <label className="text-slate-400">Sample interval (seconds)<input className="block w-full mt-1 bg-slate-800 border border-slate-600 rounded p-2 text-slate-100" type="number" min={5} max={3600} value={plc.liveIntervalSeconds??10} onChange={event=>handleUpdateItem(plc.id,{liveIntervalSeconds:Number(event.target.value)})}/></label>
                        <label className="text-slate-400">Keep stored readings (days)<input className="block w-full mt-1 bg-slate-800 border border-slate-600 rounded p-2 text-slate-100" type="number" min={1} max={30} value={plc.retentionDays??30} onChange={event=>handleUpdateItem(plc.id,{retentionDays:Number(event.target.value)})}/></label>
                      </div>
                      <label className="flex items-center gap-2 text-slate-200"><input type="checkbox" checked={plc.storeLiveData===true} onChange={event=>handleUpdateItem(plc.id,{storeLiveData:event.target.checked})}/>Store readings for trends and reports</label>
                      <p className="text-slate-400">Storage is optional. Without it, only the current server reading is kept in memory. Stored history expires after the selected retention, up to 30 days. Sampling resumes after a server restart.</p>
                      <p className={liveStatus[plc.id]?.error?'text-rose-400':'text-slate-300'} role="status">{liveStatus[plc.id]?.error|| (liveStatus[plc.id]?.collecting?'Reading configured groups…':liveStatus[plc.id]?.lastCapturedAt?`Last capture: ${new Date(liveStatus[plc.id].lastCapturedAt!).toLocaleString()}`:'No live capture yet.')}</p>
                    </fieldset>

                    {/* Status response badge if tested */}
                    {ping && (
                      <div role="status" className={`mt-2.5 px-3 py-2 rounded-lg text-xs flex items-center justify-between gap-2 ${ping.ok ? 'bg-emerald-950/60 border border-emerald-700 text-emerald-300' : 'bg-amber-950/50 border border-amber-800 text-amber-200'}`}>
                        <div className="flex items-center gap-2">
                          {ping.ok ? <CheckCircle2 className="w-4 h-4 shrink-0"/> : <AlertTriangle className="w-4 h-4 shrink-0"/>}
                          <div><div className="font-semibold">{ping.msg}</div><div className="text-[11px] opacity-80">ICMP only — no PLC protocol request was sent.</div></div>
                        </div>
                        {ping.rtt !== undefined && <span className="font-mono text-[11px] shrink-0">{ping.rtt} ms</span>}
                      </div>
                    )}
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
                              {targetMode(plc)==='automation-studio' && <li><strong className="text-slate-200">Automation Studio:</strong> RUN/ANSL and its online port do not confirm that the SpinConnect TCP listener is running. A connection refused at {plc.ip}:{plc.port} means there is no accepting TCP service at that address and port. Start the SpinConnect <code className="text-slate-300">TcpServer</code> program and verify its configured listening address and port.</li>}
                              <li>
                                <strong className="text-slate-200">PLC IP ({plc.ip}):</strong> Note that <code className="text-amber-300">192.168.1.1</code> is usually your Wi-Fi router. Verify your B&R PLC Ethernet IP in Automation Studio (commonly <code className="text-emerald-300">192.168.1.100</code> or similar).
                              </li>
                              <li>
                                <strong className="text-slate-200">Laptop Static IP:</strong> When connected directly via RJ45 cable, your Windows Ethernet adapter must be set to a static IP in the same subnet (e.g. <code className="text-emerald-300">192.168.1.50</code>, Mask <code className="text-emerald-300">255.255.255.0</code>).
                              </li>
                              <li>
                                <strong className="text-slate-200">SpinConnect TCP port {plc.port}:</strong> Ensure the PLC program’s <code className="text-slate-300">TcpServer</code> is listening for the SpinConnect protocol on TCP port {plc.port}. B&amp;R INA/UDP and ANSL/TCP online services are not interchangeable with this data service.
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
            disabled={saving}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors"
          >
            {saving?'Saving targets…':'Save & Apply'}
          </button>
        </div>
      </div>
    </div>
  );
};
