import React, {useState} from 'react';
import {MetadataItem, GroupResponseData, PLCConfig} from '../types';
import {decodeManualReceive} from '../utils/manualReceive';

export function ManualDataModal({metadata, plc, initialGroup, onClose, onDecoded}: {
  metadata: MetadataItem[]; plc: PLCConfig; initialGroup: number;
  onClose: () => void; onDecoded: (result: GroupResponseData) => void;
}) {
  const [group, setGroup] = useState(initialGroup);
  const [text, setText] = useState('');
  const [error, setError] = useState('');
  const [little, setLittle] = useState(plc.endianness === 'little');
  const [machineId, setMachineId] = useState(plc.machineId);
  const groups = Array.from(new Set(metadata.map(item => item.groupCode))).sort((a,b) => a-b);
  return <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
    <section role="dialog" aria-modal="true" aria-labelledby="manual-data-title" className="bg-slate-900 text-slate-100 rounded-xl border border-slate-700 p-6 w-full max-w-3xl max-h-[90vh] overflow-auto">
      <h2 id="manual-data-title" className="text-xl font-bold">Manual PLC received data</h2>
      <p className="text-sm my-3">Paste one complete response: 5 header bytes, payload, XOR checksum and ETX. Group code is selected here because the response does not contain it. Decoding is offline.</p>
      <div className="flex gap-4 flex-wrap mb-4">
        <label>Group code <select className="bg-slate-800 border rounded p-2" value={group} onChange={e=>setGroup(Number(e.target.value))}>{groups.map(code=><option key={code} value={code}>GC {code}</option>)}</select></label>
        <label>Machine ID <input className="bg-slate-800 border rounded p-2 w-20" type="number" min="0" max="255" value={machineId} onChange={e=>setMachineId(Number(e.target.value))}/></label>
        <label>Byte order <select className="bg-slate-800 border rounded p-2" value={little?'little':'big'} onChange={e=>setLittle(e.target.value==='little')}><option value="little">Little-endian</option><option value="big">Big-endian</option></select></label>
      </div>
      <label htmlFor="manual-decimal-bytes">Received bytes (decimal 0..255)</label>
      <textarea id="manual-decimal-bytes" className="w-full bg-slate-800 border border-slate-600 rounded p-3 font-mono text-sm mt-2" rows={9} value={text} onChange={e=>setText(e.target.value)} placeholder="3 0 0 0 199 ... 235 2"/>
      <p className="text-sm my-2">Mappings use the selected group's datatype, offset, scale factor and Sheet2 shown values. MIN/MAX are references. Empty lot names, invalid values and positive-exponent scientific values fail data checks.</p>
      {error&&<p role="alert" className="text-red-400 my-3">{error}</p>}
      <div className="flex gap-3 justify-end mt-4"><button className="border rounded px-4 py-2" onClick={onClose}>Cancel</button><button className="bg-emerald-600 rounded px-4 py-2" onClick={()=>{try {
        if (!Number.isInteger(machineId)||machineId<0||machineId>255) throw new Error('Machine ID must be 0..255.');
        onDecoded(decodeManualReceive(text,group,metadata,little,machineId));onClose();
      } catch(e) {setError(e instanceof Error?e.message:String(e));}}}>Decode and map</button></div>
    </section>
  </div>;
}
