import React, { useEffect, useState } from 'react';
import { X, Sliders, Play, CheckCircle2, AlertTriangle, RefreshCw } from 'lucide-react';

interface SimulatorControlsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSimulatorUpdated: () => void;
}

export const SimulatorControlsModal: React.FC<SimulatorControlsModalProps> = ({
  isOpen,
  onClose,
  onSimulatorUpdated,
}) => {
  const [speed, setSpeed] = useState<number>(285.5);
  const [sliverHank, setSliverHank] = useState<number>(0.128);
  const [machineStatus, setMachineStatus] = useState<number>(8);
  const [alarm1, setAlarm1] = useState<boolean>(true);
  const [alarm2, setAlarm2] = useState<boolean>(false);
  const [lotName, setLotName] = useState<string>('CARD-COTTON-T40');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (isOpen) {
      setError('');
      fetch('/api/nami/simulator/state')
        .then((r) => r.json())
        .then((data) => {
          if (data.deliverySpeed !== undefined) setSpeed(data.deliverySpeed);
          if (data.sliverHank !== undefined) setSliverHank(data.sliverHank);
          if (data.machineStatus !== undefined) setMachineStatus(data.machineStatus);
          if (data.lotName !== undefined) setLotName(data.lotName);
          if (data.alarms) {
            setAlarm1((data.alarms[1] & 0x04) !== 0);
            setAlarm2((data.alarms[3] & 0x10) !== 0);
          }
        })
        .catch(() => {});
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleApply = async () => {
    setSaving(true);
    try {
      const alarms = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
      if (alarm1) alarms[1] |= 0x04;
      if (alarm2) alarms[3] |= 0x10;

      const response = await fetch('/api/nami/simulator/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          deliverySpeed: speed,
          sliverHank: sliverHank,
          machineStatus: machineStatus,
          lotName: lotName,
          alarms: alarms,
        }),
      });
      const result = await response.json();
      if (!response.ok || !result.success) throw new Error(result.detail || result.error || 'Simulator update failed.');

      onSimulatorUpdated();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Simulator update failed.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl max-w-lg w-full flex flex-col">
        {error && <p role="alert" className="p-3 text-rose-300">{error}</p>}
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Sliders className="w-5 h-5 text-purple-400" />
            <div>
              <h2 className="text-base font-bold text-white">PLC Logic Simulator Controls</h2>
              <p className="text-xs text-slate-400">
                Inject dynamic variables to test frontend metadata scaling and bitmask decoders.
              </p>
            </div>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white p-1 rounded-md">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4 text-xs">
          {/* Machine Status */}
          <div>
            <label className="block text-slate-300 font-semibold mb-1">
              Machine Status (Group 20 Offset 42 UINT)
            </label>
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => setMachineStatus(8)}
                className={`py-2 px-3 rounded-lg border font-medium transition-all ${
                  machineStatus === 8
                    ? 'bg-emerald-950 border-emerald-500 text-emerald-300'
                    : 'bg-slate-800 border-slate-700 text-slate-400'
                }`}
              >
                8: RUNNING
              </button>
              <button
                type="button"
                onClick={() => setMachineStatus(0)}
                className={`py-2 px-3 rounded-lg border font-medium transition-all ${
                  machineStatus === 0
                    ? 'bg-amber-950 border-amber-500 text-amber-300'
                    : 'bg-slate-800 border-slate-700 text-slate-400'
                }`}
              >
                0: IDLE
              </button>
              <button
                type="button"
                onClick={() => setMachineStatus(11)}
                className={`py-2 px-3 rounded-lg border font-medium transition-all ${
                  machineStatus === 11
                    ? 'bg-blue-950 border-blue-500 text-blue-300'
                    : 'bg-slate-800 border-slate-700 text-slate-400'
                }`}
              >
                11: DOFFING
              </button>
            </div>
          </div>

          {/* Delivery Speed */}
          <div>
            <label className="block text-slate-300 font-semibold mb-1">
              Delivery Speed (Group 20 Offset 0 REAL, m/min): <span className="text-emerald-400 font-mono">{speed}</span>
            </label>
            <input
              type="range"
              min="0"
              max="350"
              step="0.5"
              value={speed}
              onChange={(e) => setSpeed(Number(e.target.value))}
              className="w-full accent-emerald-500"
            />
          </div>

          {/* Sliver Hank */}
          <div>
            <label className="block text-slate-300 font-semibold mb-1">
              Sliver Hank (Group 20 Offset 4 REAL, Ne): <span className="text-emerald-400 font-mono">{sliverHank}</span>
            </label>
            <input
              type="number"
              step="0.001"
              value={sliverHank}
              onChange={(e) => setSliverHank(Number(e.target.value))}
              className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-white font-mono"
            />
          </div>

          {/* Lot Name */}
          <div>
            <label className="block text-slate-300 font-semibold mb-1">
              Lot Name (Group 40 STRING 50B)
            </label>
            <input
              type="text"
              value={lotName}
              onChange={(e) => setLotName(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-white font-mono"
            />
          </div>

          {/* Alarm Bit Toggles */}
          <div className="bg-slate-800/60 p-3.5 rounded-lg border border-slate-700">
            <div className="font-semibold text-slate-300 mb-2">Group 30 Alarm Bit Injections</div>
            <div className="space-y-2">
              <label className="flex items-center gap-2 cursor-pointer text-slate-300">
                <input
                  type="checkbox"
                  checked={alarm1}
                  onChange={(e) => setAlarm1(e.target.checked)}
                  className="rounded accent-emerald-500 w-4 h-4"
                />
                <span>CARD_WOCC_ALARM Bit 10 (Byte 1, Bit 2) Active</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer text-slate-300">
                <input
                  type="checkbox"
                  checked={alarm2}
                  onChange={(e) => setAlarm2(e.target.checked)}
                  className="rounded accent-emerald-500 w-4 h-4"
                />
                <span>CARD_WOCC_ALARM Bit 28 (Byte 3, Bit 4) Active</span>
              </label>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-800 bg-slate-900/50">
          <button
            onClick={onClose}
            className="px-4 py-2 text-slate-400 hover:text-white text-xs font-medium"
          >
            Cancel
          </button>
          <button
            onClick={handleApply}
            disabled={saving}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors"
          >
            {saving ? 'Updating Simulator...' : 'Apply to Simulator'}
          </button>
        </div>
      </div>
    </div>
  );
};
