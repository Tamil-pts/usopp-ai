import {targetMode,targetModeLabel} from '../utils/targetMode';
import React, {useEffect, useState} from 'react';
import {Activity, Server, Cpu, Settings, ArrowRight, ArrowLeft, RefreshCw, Play, Square, Clock, Sliders, X} from 'lucide-react';
import {PLCConfig, GroupResponseData, SpinningMachineType} from '../types';
import {readGroup150Clock} from '../utils/rtcReader';
import {formatDecodedValue} from '../utils/valueDisplay';

interface HeaderProps {
  selectedPLC: PLCConfig;
  allPLCs: PLCConfig[];
  onSelectPLC: (plc: PLCConfig) => void;
  onToggleMachineId?: (id: number) => void;
  onOpenPLCModal: () => void;
  onOpenManualFrameModal?: () => void;
  onOpenMetadataModal: () => void;
  onOpenDataModels?: () => void;
  onConfigureConnection: (values: Pick<PLCConfig, 'port'|'endianness'|'timeoutMs'>) => void;
  onChangePLCIP: (ip: string) => void;
  onOpenSimulatorModal: () => void;
  onOpenRTCModal: () => void;
  onReadClock: () => void;
  onTestConnection: () => void;
  isTestingConnection: boolean;
  onPollAllGroups: () => void;
  isPollingAll: boolean;
  isPollingSingle: boolean;
  pollingProgress?: {current: number; total: number; groupCode: number} | null;
  isLivePolling: boolean;
  onToggleLivePolling: () => void;
  totalGroupsCount: number;
  totalParamsCount: number;
  currentMachineType: SpinningMachineType;
  metadataSource: string;
  latestResponse?: GroupResponseData;
  versionResponse?: GroupResponseData;
  clockResponse?: GroupResponseData;
}

export const Header: React.FC<HeaderProps> = (props) => {
  const {selectedPLC: plc, latestResponse: response} = props;
  const [server, setServer] = useState<{serverTime: string; timezone: string; applicationPort: number} | null>(null);
  const [serverError, setServerError] = useState('');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [draft, setDraft] = useState({port: plc.port, endianness: plc.endianness, timeoutMs: plc.timeoutMs});
  const [formError, setFormError] = useState('');
  const [ipDraft, setIpDraft] = useState(plc.ip);
  const [ipError, setIpError] = useState('');
  useEffect(() => {setIpDraft(plc.ip); setIpError('');}, [plc.id, plc.ip]);
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    const update = async () => {
      try {
        const res = await fetch('/api/nami/server-status', {signal: controller.signal});
        if (!res.ok) throw new Error('Server clock unavailable');
        const data = await res.json();
        if (!cancelled) {setServer(data); setServerError('');}
      } catch {if (!cancelled) setServerError('Server clock unavailable');}
    };
    void update();
    const timer = setInterval(update, 5000);
    return () => {cancelled = true; controller.abort(); clearInterval(timer);};
  }, []);
  useEffect(() => {
    if (settingsOpen) {setDraft({port: plc.port, endianness: plc.endianness, timeoutMs: plc.timeoutMs}); setFormError('');}
  }, [settingsOpen, plc.id, plc.port, plc.endianness, plc.timeoutMs]);
  useEffect(() => {
    if (!settingsOpen) return;
    const onKey = (event: KeyboardEvent) => {if (event.key === 'Escape') setSettingsOpen(false);};
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [settingsOpen]);
  let clock = 'Not read';
  let clockIssue = '';
  if (props.clockResponse) {
    try {clock = readGroup150Clock(props.clockResponse).dateStr;} catch (err) {
      clock = 'Unavailable'; clockIssue = err instanceof Error ? err.message : 'Invalid GC 150 clock';
    }
  }
  const versionValue = props.versionResponse?.success
    ? props.versionResponse.parsedValues.find((item) => /program.*version|plc.*version/i.test(item.parameter)) : undefined;
  const version = versionValue ? versionValue.rawValue != null ? formatDecodedValue(versionValue.rawValue) : undefined : plc.programVersionStr;
  const busy = props.isPollingAll || props.isPollingSingle || props.isTestingConnection;
  const connection = plc.status === 'connected' ? 'Last test: PLC responded'
    : plc.status === 'error' ? plc.tcpConnected ? 'Last test: TCP opened, no valid PLC response' : 'PLC not connected' : 'Not tested';
  const sent = response?.sentBytes || [];
  const close = response?.closeResult;
  const openMetadata = () => {setSettingsOpen(false); props.onOpenMetadataModal();};
  const openFrame = () => {setSettingsOpen(false); props.onOpenManualFrameModal?.();};

  return <header className="di-mimic">
    <div className="di-mimic-title"><div><Activity size={20}/><strong>DataInspect</strong><span>Server ↔ PLC</span></div>
      <span>{props.totalGroupsCount} groups · {props.totalParamsCount} parameters</span>{props.onOpenDataModels&&<button onClick={props.onOpenDataModels}>Data model requirements</button>}</div>
    <div className="di-mimic-flow">
      <section className="di-mimic-card di-server">
        <div className="di-device-heading">
          <span className="di-device-icon"><Server size={26}/></span><span><strong>Server</strong><small>Metadata and requests</small></span>
        </div>
        <dl className="di-mimic-facts">
          <div><dt>Server RTC</dt><dd>{serverError || (server ? server.serverTime.slice(0, 19).replace('T', ' ') : 'Loading…')} {server && !serverError ? `(${server.timezone})` : ''}</dd></div>
          <div><dt>Metadata</dt><dd title={props.metadataSource}>{props.metadataSource} <button className="di-text-button" disabled={busy} onClick={openMetadata}>Change file</button></dd></div>
        </dl>
        <details className="di-more"><summary>Server details</summary>
          <dl className="di-mimic-facts">
            <div><dt>Application address</dt><dd>{window.location.origin}</dd></div>
            <div><dt>Application port</dt><dd>{server?.applicationPort || window.location.port || '—'}</dd></div>
            <div><dt>Last request sent</dt><dd>{sent.length ? `GC ${response?.groupCode} · ${sent.length} bytes · ${response?.timestamp}` : 'No request confirmed sent'}</dd></div>
          </dl>
          <div className="di-mimic-buttons"><button disabled={busy} onClick={() => setSettingsOpen(true)}><Settings size={15}/>Connection settings</button><button disabled={busy} onClick={openFrame}><Sliders size={15}/>Frame editor</button></div>
        </details>
      </section>

      <section className={`di-link ${busy ? 'di-link-active' : ''}`} aria-label="Request and response flow">
        <span className="di-link-label">{busy ? 'Communicating…' : 'TCP exchange'}</span>
        <div className="di-link-arrow"><span>Request {sent.length ? `GC ${response?.groupCode}` : ''}</span><ArrowRight size={30}/></div>
        <div className="di-link-arrow"><ArrowLeft size={30}/><span>{response?.success ? `Response GC ${response.groupCode}` : response ? 'No valid response' : 'Awaiting test'}</span></div>
        <span className="di-link-detail">{response ? `${response.rawBytes.length} bytes · ${response.rttMs} ms` : 'One connection per test'}</span>
        <span className="di-link-detail">{close ? close.sentBytes?.length ? 'GC 11 close request sent' : 'GC 11 could not be sent' : 'Finish with GC 11'}</span>
      </section>

      <section className="di-mimic-card di-plc">
        <div className="di-device-heading">
          <span className="di-device-icon"><Cpu size={26}/></span><span><strong>PLC</strong><small>{targetModeLabel(plc)}</small></span>
        </div>
        <div className={`di-connection ${plc.status === 'connected' ? 'di-good' : plc.tcpConnected ? 'di-warning' : ''}`} title={plc.error}><span/> {connection}</div>
        <form className="di-ip-form" onSubmit={(event) => {
          event.preventDefault();
          const ip = ipDraft.trim();
          if (!/^(\d{1,3}\.){3}\d{1,3}$/.test(ip) || ip.split('.').some((part) => Number(part) > 255)) {
            setIpError('Enter a valid PLC IPv4 address.'); return;
          }
          props.onChangePLCIP(ip); setIpError('');
        }}>
          <label htmlFor="di-plc-ip">PLC IP</label><input id="di-plc-ip" value={ipDraft} disabled={busy || targetMode(plc)==='data-simulator'} onChange={(event) => {setIpDraft(event.target.value); setIpError('');}}/>
          {ipDraft.trim() !== plc.ip && <button disabled={busy} type="submit">Save IP</button>}
        </form>
        {ipError && <p className="di-form-error" role="alert">{ipError}</p>}
        <details className="di-more"><summary>PLC details</summary>
        <select className="di-target-select" aria-label="PLC target" value={plc.id} disabled={busy} onChange={(event) => {
          const target = props.allPLCs.find((item) => item.id === event.target.value); if (target) props.onSelectPLC(target);
        }}>{props.allPLCs.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
        <dl className="di-mimic-facts">
          <div><dt>Machine ID</dt><dd>{plc.machineId} <span className="di-id-options">{[0, 1].map((id) => <button key={id} disabled={busy} aria-pressed={plc.machineId === id} onClick={() => props.onToggleMachineId?.(id)}>{id}</button>)}</span></dd></div>
          <div><dt>Request received / responded</dt><dd>{response?.success ? `GC ${response.groupCode} · response confirms receipt (${response.timestamp})` : 'Not confirmed by a valid response'}</dd></div>
          <div><dt>Program version · GC 10</dt><dd>{version || 'Not available'}{props.versionResponse ? ` · read ${props.versionResponse.timestamp}` : ''}</dd></div>
          <div><dt>PLC RTC · GC 150</dt><dd title={clockIssue}>{clock}{props.clockResponse?.success ? ` · read ${props.clockResponse.timestamp}` : ''}</dd></div>
        </dl>
        <div className="di-mimic-buttons"><button disabled={busy} onClick={props.onReadClock}><Clock size={15}/>Read PLC RTC</button><button disabled={busy} onClick={props.onOpenRTCModal}>RTC tester</button><button disabled={busy} onClick={props.onOpenPLCModal}>Manage targets</button>{targetMode(plc)==='data-simulator' && <button onClick={props.onOpenSimulatorModal}>Data simulator</button>}</div>
        </details>
      </section>
    </div>
    <div className="di-mimic-toolbar">
      <button disabled={busy || ipDraft.trim() !== plc.ip} onClick={props.onTestConnection}><RefreshCw size={15}/>Test GC 10</button>
      <button className="di-primary" disabled={busy || ipDraft.trim() !== plc.ip} onClick={props.onPollAllGroups}><Play size={15}/>{props.isPollingAll ? 'Reading metadata groups…' : 'Test all metadata groups'}</button>
      <button disabled={!props.isLivePolling && (busy || ipDraft.trim() !== plc.ip)} onClick={props.onToggleLivePolling}>{props.isLivePolling ? <Square size={15}/> : <Play size={15}/>} {props.isLivePolling ? 'Stop Live' : 'Live Poll'}</button>
      <details className="di-more"><summary>Test flow</summary><p>Single: open → selected GC → GC 11. Test All: open → GC 10 → metadata groups → GC 11. GC 11 requests closure; no reply frame is expected. A transport failure stops the sequence and sends GC 11.</p></details>
    </div>

    {settingsOpen && <div className="di-settings-backdrop"><section className="di-settings" role="dialog" aria-modal="true" aria-labelledby="di-settings-title">
      <div className="di-mimic-title"><h2 id="di-settings-title">Server request configuration</h2><button onClick={() => setSettingsOpen(false)} aria-label="Close server configuration"><X size={20}/></button></div>
      <p>Target: {plc.name} · {plc.ip}</p>
      <form onSubmit={(event) => {
        event.preventDefault();
        if (!Number.isInteger(draft.port) || draft.port < 1 || draft.port > 65535) {setFormError('Enter a PLC TCP port between 1 and 65535.'); return;}
        if (!Number.isInteger(draft.timeoutMs) || draft.timeoutMs < 100 || draft.timeoutMs > 120000) {setFormError('Enter a timeout between 100 and 120000 ms.'); return;}
        props.onConfigureConnection(draft); setSettingsOpen(false);
      }}>
        <label>PLC TCP request port<input autoFocus type="number" min={1} max={65535} required value={draft.port} onChange={(event) => setDraft({...draft, port: Number(event.target.value)})}/></label>
        <label>Response timeout (ms)<input type="number" min={100} max={120000} required value={draft.timeoutMs} onChange={(event) => setDraft({...draft, timeoutMs: Number(event.target.value)})}/></label>
        <label>Byte order<select value={draft.endianness} onChange={(event) => setDraft({...draft, endianness: event.target.value as PLCConfig['endianness']})}><option value="little">Little-endian</option><option value="big">Big-endian</option></select></label>
        {formError && <p role="alert">{formError}</p>}
        <div className="di-mimic-buttons"><button type="button" onClick={() => setSettingsOpen(false)}>Cancel</button><button className="di-primary" type="submit" disabled={busy}>Save configuration</button></div>
      </form>
    </section></div>}
  </header>;
};
