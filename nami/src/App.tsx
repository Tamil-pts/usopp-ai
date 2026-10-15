import {responsesForHistory, saveDecodedRun, type SavedInspectRun} from './utils/runHistory';
import {userStorage} from '../../src/shared/userStorage';
import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Header } from './components/Header';
import {ManualDataModal} from './components/ManualDataModal';
import {DataModelModal} from './components/DataModelModal';
import {buildDataModelRowReferences, unavailableDataModelParameters, type DataModelCheck, type DataModelSelection} from './utils/dataModelChecks';
import {useDataModelReferences} from './hooks/useDataModelReferences';
import {groupOutcome, closeDescription} from './utils/groupResult';
import { PLCManagerModal } from './components/PLCManagerModal';
import { MetadataUploaderModal } from './components/MetadataUploaderModal';
import { GroupSelectorBar } from './components/GroupSelectorBar';
import { GroupDataView } from './components/GroupDataView';
import { RawPacketInspector } from './components/RawPacketInspector';
import { SimulatorControlsModal } from './components/SimulatorControlsModal';
import { TestReportModal } from './components/TestReportModal';
import { RTCModal } from './components/RTCModal';
import { MetadataItem, PLCConfig, GroupResponseData, SpinningMachineType } from './types';
import { parseCSVMetadata, validateMetadata, restoreSavedSheet2, getExpectedGroupPayloadLength } from './utils/metadataParser';
import { parsePLCResponse, parseGroupValues, buildReadGroupRequest } from './utils/packetParser';
import { getPredefinedMachineMetadata, attachDropdownsToMetadata } from './data/machinePresets';
import { FileText, Cpu, AlertCircle, RefreshCw, CheckCircle2, AlertTriangle, X, ShieldCheck, Clock, Sliders } from 'lucide-react';

const INITIAL_PLCS: PLCConfig[] = [
  {
    id: 'plc-carding-sim',
    name: 'Carding (xcarding) Simulator',
    machineType: 'Carding',
    ip: '127.0.0.1',
    port: 21010,
    machineId: 0,
    isSimulated: true,
    endianness: 'little',
    timeoutMs: 2500,
    status: 'idle',
  },
  {
    id: 'plc-factory-1',
    name: 'Carding Line #1 (B&R PLC)',
    machineType: 'Carding',
    ip: '192.168.1.100',
    port: 21010,
    machineId: 0,
    isSimulated: false,
    endianness: 'little',
    timeoutMs: 5000,
    status: 'idle',
  },
  {
    id: 'plc-ringframe-1',
    name: 'Ring Frame Line #1',
    machineType: 'Ring Frame',
    ip: '192.168.1.102',
    port: 21010,
    machineId: 0,
    isSimulated: false,
    endianness: 'little',
    timeoutMs: 5000,
    status: 'idle',
  },
  {
    id: 'plc-breaker-1',
    name: 'Breaker Drawframe #1',
    machineType: 'Breaker',
    ip: '192.168.1.103',
    port: 21010,
    machineId: 0,
    isSimulated: false,
    endianness: 'little',
    timeoutMs: 5000,
    status: 'idle',
  },
];

export default function App({initialHistory}: {initialHistory?: SavedInspectRun}) {
  const archived = Boolean(initialHistory);
  const [latestTestId, setLatestTestId] = useState(initialHistory?.testId || '');
  const [historyWarning, setHistoryWarning] = useState('');
  const [metadata, setMetadata] = useState<MetadataItem[]>(initialHistory?.metadata || []);
  const [metadataSource, setMetadataSource] = useState<string>(initialHistory?.metadataSource || 'Factory Carding (xcarding) CSV');
  const [metadataLoading, setMetadataLoading] = useState<boolean>(!archived);

  const [plcs, setPLCs] = useState<PLCConfig[]>(() => {
    if (initialHistory) return [{...initialHistory.plc, status: 'idle', tcpConnected: false} as PLCConfig];
    const saved = userStorage.getItem('plc_configs');
    if (!saved) return INITIAL_PLCS;
    try {
      const parsed = JSON.parse(saved);
      if (!Array.isArray(parsed) || parsed.length === 0) return INITIAL_PLCS;
      // A browser reload must never imply that a PLC is still physically connected.
      // Connection status is re-established only after a successful communication test/read.
      return parsed.map((p: PLCConfig) => ({
        ...p,
        status: 'idle',
        tcpConnected: false,
        programVersion: undefined,
        programVersionStr: undefined,
        error: undefined,
      }));
    } catch {
      return INITIAL_PLCS;
    }
  });

  const [selectedPLCId, setSelectedPLCId] = useState<string>(plcs[0]?.id || 'plc-carding-sim');
  const selectedPLC = useMemo(() => plcs.find((p) => p.id === selectedPLCId) || plcs[0], [plcs, selectedPLCId]);

  const [currentMachineType, setCurrentMachineType] = useState<SpinningMachineType>(
    selectedPLC.machineType || 'Carding'
  );

  const [selectedGroupCode, setSelectedGroupCode] = useState<number>(initialHistory ? Number(Object.keys(responsesForHistory(initialHistory))[0] ?? initialHistory.metadata?.[0]?.groupCode ?? 20) : 20);
  const [groupResponses, setGroupResponses] = useState<Record<number, GroupResponseData>>(() => initialHistory ? responsesForHistory(initialHistory) : {});
  const responseContext = useMemo(() => ({}), [selectedPLC.id, selectedPLC.ip, selectedPLC.port,
    selectedPLC.machineId, selectedPLC.isSimulated, selectedPLC.endianness, metadata]);
  const responseContextRef = useRef(responseContext);
  responseContextRef.current = responseContext;

  const [isPollingSingle, setIsPollingSingle] = useState<boolean>(false);
  const [isPollingAll, setIsPollingAll] = useState<boolean>(false);
  const [pollingProgress, setPollingProgress] = useState<{ current: number; total: number; groupCode: number } | null>(null);
  const [isTestingConnection, setIsTestingConnection] = useState<boolean>(false);
  const [connectionNotice, setConnectionNotice] = useState<{
    type: 'success' | 'error';
    message: string;
    version?: string | null;
  } | null>(null);
  const [isLivePolling, setIsLivePolling] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Modals
  const [isPLCModalOpen, setIsPLCModalOpen] = useState(false);
  const [plcModalTab, setPLCModalTab] = useState<'targets' | 'manual-frame'>('targets');
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [isSimulatorModalOpen, setIsSimulatorModalOpen] = useState(false);
  const [isReportModalOpen, setIsReportModalOpen] = useState(false);
  const [isRTCModalOpen, setIsRTCModalOpen] = useState(false);
  const [isManualDataOpen, setIsManualDataOpen] = useState(false);
  const [isDataModelsOpen,setIsDataModelsOpen]=useState(false);
  const [dataModelSelection, setDataModelSelection] = useState<DataModelSelection>({service: initialHistory?.dataModelCheck?.model.service || 'PMS', modelId: initialHistory?.dataModelCheck?.model.id || '', allMachines: false});
  const [dataModelSnapshot, setDataModelSnapshot] = useState<{
    check: DataModelCheck; metadata: MetadataItem[]; machine: SpinningMachineType;
  } | null>(initialHistory?.dataModelCheck ? {check: initialHistory.dataModelCheck, metadata, machine: currentMachineType} : null);
  const dataModelCheck = dataModelSnapshot && dataModelSnapshot.metadata === metadata &&
    dataModelSnapshot.machine === currentMachineType &&
    dataModelSnapshot.check.model.id === dataModelSelection.modelId ? dataModelSnapshot.check : null;
  const liveReferenceData = useDataModelReferences(currentMachineType, dataModelSelection.modelId);
  const referenceData = initialHistory?.dataModelReferenceSource
    ? {...initialHistory.dataModelReferenceSource, snapshot: true} : liveReferenceData;
  const persistDecoded = async (identity: {historyId?: string; testId?: string}, groups: Record<number, GroupResponseData>) => {
    setLatestTestId(identity.testId || '');
    try {await saveDecodedRun(identity, groups, dataModelCheck, referenceData); setHistoryWarning('');}
    catch (error) {setHistoryWarning(error instanceof Error ? error.message : 'Decoded history could not be saved.');}
  };
  const dataModelReferences = useMemo(() => buildDataModelRowReferences(metadata, referenceData.models, dataModelCheck), [metadata, referenceData.models, dataModelCheck]);
  const missingDataModelParameters = useMemo(() => unavailableDataModelParameters(metadata, referenceData.models, dataModelCheck), [metadata, referenceData.models, dataModelCheck]);
  useEffect(() => {if (!archived) setDataModelSnapshot(null);}, [metadata, archived]);
  useEffect(() => {
    if (archived) return;
    setDataModelSelection({service: 'PMS', modelId: '', allMachines: false});
    setDataModelSnapshot(null);
  }, [currentMachineType]);

  // Load metadata for a machine (checks localStorage first, then default CSV or preset)
  const loadMetadataForMachine = useCallback(
    async (mType: SpinningMachineType) => {
      setMetadataLoading(true);
      try {
        const stored = userStorage.getItem(`spinning_metadata_${mType}`);
        if (stored) {
          try {
            const parsed = JSON.parse(stored);
            if (!Array.isArray(parsed) || parsed.length === 0) {
              throw new Error('Saved metadata is empty or invalid.');
            }
            const validated = restoreSavedSheet2(validateMetadata(parsed));
            setMetadata(validated);
            setMetadataSource(userStorage.getItem(`spinning_metadata_source_${mType}`) || `Saved Custom Metadata (${mType})`);
            setSelectedGroupCode(validated[0].groupCode);
            return;
          } catch (storedError) {
            const message = storedError instanceof Error ? storedError.message : 'Saved metadata is invalid.';
            console.error(`Saved metadata validation failed for ${mType}:`, storedError);
            setMetadata([]);
            setMetadataSource('Invalid saved metadata');
            setConnectionNotice({ type: 'error', message: `Saved metadata for ${mType} is invalid: ${message}. Reset to Factory Preset or upload a valid metadata file.` });
            return;
          }
        }

        if (mType === 'Carding') {
          const res = await fetch('/nami/default_metadata.csv');
          const text = await res.text();
          const parsed = parseCSVMetadata(text);
          const withDropdowns = attachDropdownsToMetadata(parsed);
          setMetadata(withDropdowns);
          setMetadataSource('Factory Carding (xcarding) CSV');
          if (parsed.length > 0) setSelectedGroupCode(parsed[0].groupCode);
        } else {
          const preset = getPredefinedMachineMetadata(mType);
          setMetadata(preset);
          setMetadataSource(`Factory Preset (${mType})`);
          if (preset.length > 0) setSelectedGroupCode(preset[0].groupCode);
        }
      } catch (e) {
        console.error('Failed to load metadata for machine:', mType, e);
        const errorMessage = e instanceof Error ? e.message : `Invalid metadata for ${mType}`;
        setMetadata([]);
        setMetadataSource('Invalid metadata');
        setConnectionNotice({ type: 'error', message: errorMessage });
      } finally {
        setMetadataLoading(false);
      }
    },
    []
  );

  // Initial load
  useEffect(() => {
    if (!archived) loadMetadataForMachine(currentMachineType);
  }, [loadMetadataForMachine, currentMachineType]);

  // When selected PLC changes, switch machine type if configured on PLC
  useEffect(() => {
    if (!archived && selectedPLC.machineType && selectedPLC.machineType !== currentMachineType) {
      setCurrentMachineType(selectedPLC.machineType);
      loadMetadataForMachine(selectedPLC.machineType);
    }
  }, [selectedPLC, currentMachineType, loadMetadataForMachine]);

  // Save PLCs to localStorage
  useEffect(() => {
    if (!archived) userStorage.setItem('plc_configs', JSON.stringify(plcs));
  }, [plcs]);

  // Compute distinct groups
  const distinctGroups = useMemo(() => {
    const map = new Map<number, { groupCode: number; screenName: string; paramCount: number }>();
    for (const item of metadata) {
      const existing = map.get(item.groupCode);
      if (!existing) {
        map.set(item.groupCode, {
          groupCode: item.groupCode,
          screenName: item.screenName,
          paramCount: 1,
        });
      } else {
        existing.paramCount++;
      }
    }
    if (groupResponses[10] && !map.has(10)) map.set(10, {groupCode: 10, screenName: 'PLC handshake / program version', paramCount: 0});
    return Array.from(map.values())
      .filter((group) => group.groupCode !== 11)
      .sort((a, b) => a.groupCode - b.groupCode);
  }, [metadata, groupResponses[10]]);

  // Query a single group from server
  useEffect(() => {
    if (archived) return;
    setGroupResponses({});
    setLatestTestId('');
    setConnectionNotice(null);
    setIsLivePolling(false);
  }, [responseContext]);

  const pollSingleGroup = useCallback(
    async (groupCode: number) => {
      if (archived) return;
      setIsPollingSingle(true);
      try {
        const res = await fetch('/api/nami/plc/read-group', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            plc: selectedPLC, metadata, metadataSource,
            ip: selectedPLC.ip,
            port: selectedPLC.port,
            machineId: selectedPLC.machineId,
            groupCode,
            isSimulated: selectedPLC.isSimulated,
            timeoutMs: selectedPLC.timeoutMs,
          }),
        });
        const json = await res.json();
        if (responseContextRef.current !== responseContext) return;
        if (!res.ok) {
          throw new Error(json.error || `PLC read failed for Group ${groupCode}`);
        }

        const metaForGroup = metadata.filter((m) => m.groupCode === groupCode);
        const parsedFrame = parsePLCResponse(json.rawBytes || [], selectedPLC.machineId);

        let parsedValues: any[] = [];
        if (json.success && parsedFrame.success && parsedFrame.dataBytes.length > 0) {
          parsedValues = parseGroupValues(
            parsedFrame.dataBytes,
            metaForGroup,
            selectedPLC.endianness === 'little'
          );
        }

        const groupData: GroupResponseData = {
          groupCode, testId: json.testId, historyId: json.historyId,
          success: json.success && parsedFrame.success,
          resultCode: parsedFrame.resultCode,
          dataLength: parsedFrame.dataLength,
          rawBytes: json.rawBytes || [],
          sentBytes: json.sentBytes || Array.from(buildReadGroupRequest(selectedPLC.machineId ?? 0, groupCode)),
          rawHex: Array.from((json.rawBytes || []) as number[])
            .map((b) => b.toString(16).padStart(2, '0'))
            .join(' '),
          rttMs: json.rttMs || 0,
          timestamp: new Date().toLocaleTimeString(),
          completedAt: Date.now(),
          error: json.error || parsedFrame.error,
          expectedLength: getExpectedGroupPayloadLength(metaForGroup),
          lengthMatch: parsedFrame.dataLength >= getExpectedGroupPayloadLength(metaForGroup),
          parsedValues,
          tcpConnected: json.tcpConnected,
          stage: json.stage,
          traceId: json.traceId,
          closeResult: json.closeResult,
        };

        // Only Group Code 10 is the PLC connection/handshake proof.
        // Reading another group successfully must not make the header show Connected.
        if (groupCode === 10 && groupData.success && groupData.resultCode === 0) {
          setPLCs((prev) =>
            prev.map((p) =>
              p.id === selectedPLC.id
                ? { ...p, status: 'connected', tcpConnected: json.tcpConnected, error: undefined, lastTested: new Date().toLocaleTimeString() }
                : p
            )
          );
        }

        if (!groupData.success) {
          if (groupCode === 10 || json.success === false) {
            setPLCs((prev) => prev.map((p) => p.id === selectedPLC.id
              ? { ...p, status: 'error', tcpConnected: json.tcpConnected, error: groupData.error,
                  programVersion: undefined, programVersionStr: undefined } : p));
          }
          setConnectionNotice({ type: 'error', message: groupData.error || `No valid response for Group ${groupCode}` });
        }

        setGroupResponses((prev) => ({
          ...prev,
          [groupCode]: groupData,
        }));
        await persistDecoded(json, {[groupCode]: groupData});
        return groupData;
      } catch (err: any) {
        if (responseContextRef.current !== responseContext) return;
        const errorMessage = err instanceof Error ? err.message : `Failed to read Group ${groupCode}`;
        console.error(`Error polling group ${groupCode}:`, err);
        // A failure on an arbitrary data group is not proof that the PLC is disconnected.
        // Only a failed Group Code 10 handshake changes the connection status.
        if (groupCode === 10 || !selectedPLC.isSimulated) {
          setPLCs((prev) =>
            prev.map((p) =>
              p.id === selectedPLC.id
                ? { ...p, status: 'error', tcpConnected: false, error: errorMessage, programVersion: undefined, programVersionStr: undefined }
                : p
            )
          );
        }
        setGroupResponses((prev) => ({ ...prev, [groupCode]: {
          groupCode, success: false, resultCode: -1, dataLength: 0, rawBytes: [], sentBytes: [],
          rawHex: '', rttMs: 0, timestamp: new Date().toLocaleTimeString(), completedAt: Date.now(), error: errorMessage,
          lengthMatch: false, parsedValues: [],
        } }));
        setConnectionNotice({ type: 'error', message: errorMessage });
      } finally {
        setIsPollingSingle(false);
      }
    },
    [selectedPLC.id, selectedPLC.ip, selectedPLC.port, selectedPLC.machineId,
      selectedPLC.isSimulated, selectedPLC.timeoutMs, selectedPLC.endianness, metadata, metadataSource, dataModelCheck, referenceData, responseContext, archived]
  );

  // Test connection explicitly by calling Group Code 10 and reading Program Version
  const handleTestConnection = useCallback(async () => {
    if (archived) return;
    setIsTestingConnection(true);
    setConnectionNotice(null);
    try {
      const res = await fetch('/api/nami/plc/test-connection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          plc: selectedPLC, metadata, metadataSource,
          ip: selectedPLC.ip,
          port: selectedPLC.port,
          machineId: selectedPLC.machineId,
          isSimulated: selectedPLC.isSimulated,
          timeoutMs: selectedPLC.timeoutMs || 3000,
          endianness: selectedPLC.endianness,
          programVersionOffset: metadata.find((item) => item.groupCode === 10
            && /program.*version|plc.*version/i.test(item.parameter) && item.dataType.toUpperCase() === 'REAL')?.offset ?? 0,
        }),
      });
      const data = await res.json();
      if (responseContextRef.current !== responseContext) return;

      if (!res.ok) {
        throw new Error(data.error || data.message || `Connection test failed (HTTP ${res.status})`);
      }

      const decoded = responsesForHistory({...data, plc: selectedPLC, metadata, groupCode: 10, metadataSource});
      await persistDecoded(data, decoded);

      if (data.success) {
        const verStr =
          data.programVersionStr ||
          (data.programVersion !== null && data.programVersion !== undefined
            ? Number(data.programVersion).toFixed(3)
            : undefined);

        // Update PLC status and version in state
        setPLCs((prev) =>
          prev.map((p) =>
            p.id === selectedPLC.id
              ? {
                  ...p,
                  status: 'connected',
                  tcpConnected: data.tcpConnected,
                  programVersion: data.programVersion,
                  programVersionStr: verStr,
                  lastTested: new Date().toLocaleTimeString(),
                  error: undefined,
                }
              : p
          )
        );

        setConnectionNotice({
          type: data.versionWarning ? 'error' : 'success',
          message: `${data.versionWarning || (verStr ? `Group Code 10 responded with Program Version v${verStr}.` : 'Group Code 10 responded.')} ${closeDescription(data.closeResult)}`,
          version: verStr,
        });

        // Automatically populate Group 10 in groupResponses
        if (Array.isArray(data.rawBytes) && data.rawBytes.length >= 5) {
          const parsedFrame = parsePLCResponse(data.rawBytes, selectedPLC.machineId);
          const metaFor10 = metadata.filter((m) => m.groupCode === 10);
          let parsedValues: any[] = [];
          if (parsedFrame.success && parsedFrame.dataBytes.length > 0) {
            parsedValues = parseGroupValues(
              parsedFrame.dataBytes,
              metaFor10,
              selectedPLC.endianness === 'little'
            );
          }
          setGroupResponses((prev) => ({
            ...prev,
            [10]: {
              groupCode: 10, testId: data.testId, historyId: data.historyId,
              success: true,
              resultCode: parsedFrame.resultCode,
              dataLength: parsedFrame.dataLength,
              rawBytes: data.rawBytes,
              sentBytes: data.sentBytes || [],
              tcpConnected: data.tcpConnected,
              stage: data.stage,
              traceId: data.traceId,
              closeResult: data.closeResult,
              rawHex: Array.from(data.rawBytes as number[])
                .map((b) => b.toString(16).padStart(2, '0'))
                .join(' '),
              rttMs: data.rttMs || 15,
              timestamp: new Date().toLocaleTimeString(),
              completedAt: Date.now(),
              expectedLength: getExpectedGroupPayloadLength(metaFor10),
              lengthMatch: parsedFrame.dataLength >= getExpectedGroupPayloadLength(metaFor10),
              parsedValues,
            },
          }));
        }
      } else {
        const errorMsg = data.message || data.error || 'Connection timed out or failed to reach PLC on Group 10.';
        setPLCs((prev) =>
          prev.map((p) =>
            p.id === selectedPLC.id
              ? {
                  ...p,
                  status: 'error',
                  tcpConnected: data.tcpConnected,
                  lastTested: new Date().toLocaleTimeString(),
                  error: errorMsg,
                  programVersion: undefined,
                  programVersionStr: undefined,
                }
              : p
          )
        );

        setConnectionNotice({
          type: 'error',
          message: errorMsg,
        });
        setGroupResponses((prev) => ({ ...prev, [10]: {
          groupCode: 10, testId: data.testId, historyId: data.historyId, success: false, resultCode: -1, dataLength: 0,
          rawBytes: data.rawBytes || [], sentBytes: data.sentBytes || [], rawHex: '',
          rttMs: data.rttMs || 0, timestamp: new Date().toLocaleTimeString(), completedAt: Date.now(), error: errorMsg,
          lengthMatch: false, parsedValues: [], tcpConnected: data.tcpConnected,
          stage: data.stage, traceId: data.traceId, closeResult: data.closeResult,
        } }));
      }
    } catch (err: any) {
      if (responseContextRef.current !== responseContext) return;
      const errorMsg = `Socket request failed: ${err.message}`;
      setPLCs((prev) =>
        prev.map((p) =>
          p.id === selectedPLC.id
            ? {
                ...p,
                status: 'error',
                tcpConnected: false,
                lastTested: new Date().toLocaleTimeString(),
                error: errorMsg,
                programVersion: undefined,
                programVersionStr: undefined,
              }
            : p
        )
      );
      setConnectionNotice({
        type: 'error',
        message: errorMsg,
      });
    } finally {
      setIsTestingConnection(false);
    }
  }, [selectedPLC, metadata, metadataSource, dataModelCheck, referenceData, responseContext, archived]);

  // Poll all groups sequentially one by one
  const pollAllGroups = useCallback(async () => {
    if (archived || distinctGroups.length === 0) return;
    setIsLivePolling(false);
    setIsPollingAll(true);
    setConnectionNotice(null);
    setGroupResponses({});

    try {
      // Always include Group Code 10 first so Run All also performs the real PLC
      // handshake even when the uploaded metadata does not contain Group 10.
      const groupCodes = Array.from(new Set([
        10,
        ...distinctGroups.map((group) => group.groupCode),
      ])).filter((groupCode) => groupCode !== 11);
      const res = await fetch('/api/nami/plc/read-multiple-groups', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          plc: selectedPLC, metadata, metadataSource,
          ip: selectedPLC.ip,
          port: selectedPLC.port,
          machineId: selectedPLC.machineId,
          groupCodes,
          isSimulated: selectedPLC.isSimulated,
          timeoutMs: selectedPLC.timeoutMs || 3000,
        }),
      });
      const json = await res.json();
      if (responseContextRef.current !== responseContext) return;

      if (!res.ok) {
        throw new Error(json.error || 'PLC group sequence failed');
      }

      const runResults: GroupResponseData[] = [];
      let group10Verified = false;
      let group10Error = '';
      for (let i = 0; i < groupCodes.length; i++) {
        const groupCode = groupCodes[i];
        const g = distinctGroups.find((group) => group.groupCode === groupCode) ||
          (groupCode === 10 ? { groupCode: 10, screenName: 'Program Version / PLC Handshake', paramCount: 0 } : undefined);
        if (!g) continue;
        setPollingProgress({ current: i + 1, total: groupCodes.length, groupCode: g.groupCode });

        try {
          const groupResult = json.results?.find((item: any) => item.groupCode === g.groupCode);
          const metaForGroup = metadata.filter((m) => m.groupCode === g.groupCode);
          const parsedFrame = parsePLCResponse(groupResult?.rawBytes || [], selectedPLC.machineId);

          let parsedValues: any[] = [];
          if (groupResult?.success && parsedFrame.success && parsedFrame.dataBytes.length > 0) {
            parsedValues = parseGroupValues(
              parsedFrame.dataBytes,
              metaForGroup,
              selectedPLC.endianness === 'little'
            );
          }

          const groupData: GroupResponseData = {
            groupCode: g.groupCode, testId: json.testId, historyId: json.historyId,
            success: Boolean(groupResult?.success && parsedFrame.success),
            resultCode: parsedFrame.resultCode,
            dataLength: parsedFrame.dataLength,
            rawBytes: groupResult?.rawBytes || [],
            sentBytes: groupResult?.sentBytes || [],
            rawHex: Array.from((groupResult?.rawBytes || []) as number[])
              .map((b) => b.toString(16).padStart(2, '0'))
              .join(' '),
            rttMs: groupResult?.rttMs || 0,
            timestamp: new Date().toLocaleTimeString(),
            completedAt: Date.now(),
            sequenceIndex: i,
            error: groupResult?.error || (!groupResult ? 'No result returned for this group.' : parsedFrame.error),
            expectedLength: getExpectedGroupPayloadLength(metaForGroup),
            lengthMatch: parsedFrame.dataLength >= getExpectedGroupPayloadLength(metaForGroup),
            parsedValues,
            tcpConnected: groupResult?.tcpConnected,
            stage: groupResult?.stage || (!groupResult ? 'not_sent' : undefined),
            traceId: groupResult?.traceId,
            closeResult: json.closeResult,
          };

          runResults.push(groupData);

          // PLC connection status is established specifically by a valid
          // Group Code 10 response, as required by the B&R handshake.
          if (g.groupCode === 10) {
            group10Verified = Boolean(groupData.success && groupData.resultCode === 0 && groupData.rawBytes.length >= 7);
            if (!group10Verified) group10Error = groupData.error || 'Group Code 10 did not return a valid PLC response.';
          }

          // Update response immediately for this group
          setGroupResponses((prev) => ({
            ...prev,
            [g.groupCode]: groupData,
          }));
        } catch (err: any) {
          console.error(`Error polling group ${g.groupCode}:`, err);
        }

      }
      await persistDecoded(json, Object.fromEntries(runResults.map(row => [row.groupCode, row])));
      const counts = {passed: 0, failed: 0, mismatch: 0, skipped: 0};
      for (const item of runResults) counts[groupOutcome(item)]++;
      const transportFailure = runResults.find((item) => !item.success && item.stage !== 'not_sent');
      const summary = `${counts.passed} passed, ${counts.mismatch} metadata mismatch, ${counts.failed} failed, ${counts.skipped} not requested.`;
      const stopReason = transportFailure ? ` Stopped at GC ${transportFailure.groupCode}: ${transportFailure.error || 'No valid response.'}` : '';
      if (!group10Verified) {
        const detail = group10Error || json.error || 'PLC connection not verified: Group Code 10 did not return valid data.';
        setPLCs((prev) =>
          prev.map((p) =>
            p.id === selectedPLC.id
              ? { ...p, status: 'error', tcpConnected: json.tcpConnected, error: detail, programVersion: undefined, programVersionStr: undefined }
              : p
          )
        );
        setConnectionNotice({ type: 'error', message: `${summary}${stopReason} ${closeDescription(json.closeResult)}` });
      } else {
        // A later transport failure must supersede an earlier GC 10 response.
        setPLCs((prev) =>
          prev.map((p) =>
            p.id === selectedPLC.id
              ? { ...p, status: transportFailure ? 'error' : 'connected', tcpConnected: json.tcpConnected,
                  error: transportFailure?.error, lastTested: new Date().toLocaleTimeString() }
              : p
          )
        );
        setConnectionNotice({
          type: counts.failed || counts.skipped || counts.mismatch ? 'error' : 'success',
          message: `${summary}${stopReason} ${closeDescription(json.closeResult)}`,
        });
      }
    } catch (err) {
      if (responseContextRef.current !== responseContext) return;
      console.error('Error in sequential group read:', err);
      setPLCs((prev) => prev.map((p) => p.id === selectedPLC.id ? {...p, status: 'error', tcpConnected: false} : p));
      setConnectionNotice({
        type: 'error',
        message: err instanceof Error ? err.message : 'PLC group sequence failed',
      });
    } finally {
      setIsPollingAll(false);
      setPollingProgress(null);
    }
  }, [distinctGroups, selectedPLC, metadata, metadataSource, dataModelCheck, referenceData, responseContext, archived]);

  // Live polling effect: never overlap TCP requests. Wait for each read to finish
  // before starting the next cycle.
  useEffect(() => {
    if (!isLivePolling) return;
    let cancelled = false;

    const runPollLoop = async () => {
      while (!cancelled) {
        await pollSingleGroup(selectedGroupCode);
        if (cancelled) break;
        await new Promise<void>((resolve) => setTimeout(resolve, 2000));
      }
    };

    void runPollLoop();
    return () => {
      cancelled = true;
    };
  }, [isLivePolling, selectedGroupCode, pollSingleGroup]);

  // Active group's metadata items
  const activeGroupMetadata = useMemo(() => {
    return metadata.filter((m) => m.groupCode === selectedGroupCode);
  }, [metadata, selectedGroupCode]);

  const activeResponse = groupResponses[selectedGroupCode];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-emerald-500 selection:text-black">
      {/* Top Header */}
      <fieldset disabled={archived} className="m-0 min-w-0 border-0 p-0">
      <Header
        selectedPLC={selectedPLC}
        allPLCs={plcs}
        onSelectPLC={(p) => setSelectedPLCId(p.id)}
        onToggleMachineId={(newId) => {
          setPLCs((prev) =>
            prev.map((p) => (p.id === selectedPLC.id ? { ...p, machineId: newId } : p))
          );
        }}
        onOpenPLCModal={() => {
          setPLCModalTab('targets');
          setIsPLCModalOpen(true);
        }}
        onOpenManualFrameModal={() => {
          setPLCModalTab('manual-frame');
          setIsPLCModalOpen(true);
        }}
        onOpenSimulatorModal={() => setIsSimulatorModalOpen(true)}
        onOpenMetadataModal={() => setIsUploadModalOpen(true)}
        onConfigureConnection={(values) => setPLCs((prev) => prev.map((p) => p.id === selectedPLC.id
          ? {...p, ...values, status: 'idle', tcpConnected: false, error: undefined,
            programVersion: undefined, programVersionStr: undefined} : p))}
        onChangePLCIP={(ip) => setPLCs((prev) => prev.map((p) => p.id === selectedPLC.id
          ? {...p, ip, status: 'idle', tcpConnected: false, error: undefined,
              programVersion: undefined, programVersionStr: undefined} : p))}
        onReadClock={() => {void pollSingleGroup(150);}}
        onOpenRTCModal={() => setIsRTCModalOpen(true)}
        onTestConnection={handleTestConnection}
        isTestingConnection={isTestingConnection}
        onPollAllGroups={pollAllGroups}
        isPollingAll={isPollingAll}
        isPollingSingle={isPollingSingle}
        pollingProgress={pollingProgress}
        isLivePolling={isLivePolling}
        onToggleLivePolling={() => setIsLivePolling((prev) => !prev)}
        totalGroupsCount={distinctGroups.length}
        totalParamsCount={metadata.length}
        currentMachineType={currentMachineType}
        metadataSource={metadataSource}
        onOpenDataModels={()=>setIsDataModelsOpen(true)}
        latestResponse={Object.values(groupResponses).filter((item) => item.stage !== 'not_sent' && item.source !== 'manual')
          .sort((a, b) => (b.completedAt || 0) - (a.completedAt || 0) || (b.sequenceIndex || 0) - (a.sequenceIndex || 0))[0]}
        versionResponse={groupResponses[10]?.source === 'manual' ? undefined : groupResponses[10]}
        clockResponse={groupResponses[150]?.source === 'manual' ? undefined : groupResponses[150]}
      />
      </fieldset>
      {(latestTestId || archived) && <div className="px-6 py-3 text-sm border-b border-slate-700"><b>{archived ? 'Saved test (read only)' : 'Latest test ID'}:</b> <span className="font-mono break-all">{latestTestId}</span>{archived && <p>Original PLC target, metadata and captured values. Open a new live test from uSOPp to send requests.</p>}</div>}
      {historyWarning && <p role="alert" className="px-6 py-3 text-amber-300">{historyWarning}</p>}

      {/* Connection Notice & Troubleshooting Banner */}
      <div className="px-6 py-2 flex gap-3 items-center text-sm"><button className="border border-slate-600 rounded px-3 py-2" disabled={archived || isPollingAll || isPollingSingle || isTestingConnection} onClick={()=>{setIsLivePolling(false);setIsManualDataOpen(true);}}>Manual received data</button>{activeResponse?.source === 'manual' && <span>Manual data · Offline decode · No live PLC connection verified</span>}</div>
      {connectionNotice && (
        <div
          className={`px-4 sm:px-6 py-2.5 text-xs border-b flex items-start justify-between gap-3 ${
            connectionNotice.type === 'success'
              ? 'bg-emerald-950/70 border-emerald-800 text-emerald-200'
              : 'bg-rose-950/80 border-rose-800 text-rose-200'
          }`}
        >
          <div className="flex items-start gap-2.5">
            {connectionNotice.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-rose-400 mt-0.5 shrink-0" />
            )}
            <div>
              <div className="font-semibold">{connectionNotice.message}</div>
              {connectionNotice.type === 'error' && !selectedPLC.isSimulated && (
                <details className="mt-1.5 text-[11px] text-slate-300 space-y-1">
                  <summary className="font-medium text-amber-300 cursor-pointer">Chopper · View guidance</summary>
                  <div className="text-slate-300">
                    <strong>Target {selectedPLC.ip}:{selectedPLC.port}:</strong> Ping checks IP reachability. A TCP connection confirms the configured port is reachable; a valid group response confirms PLC data communication.
                  </div>
                  <div className="text-slate-300">
                    <strong>No PLC response:</strong> Check that the SpinConnect function is enabled, the configured Machine ID ({selectedPLC.machineId}) matches nw_machineID, and the PLC receive/send logic is running.
                  </div>
                  <div className="text-slate-300">
                    <strong>Session closure:</strong> GC 11 is sent after the test. If an older session is stuck, stop Live Poll and allow the PLC's configured idle timeout (about 300 seconds) to release it before retrying.
                  </div>
                </details>
              )}
            </div>
          </div>
          <button
            onClick={() => setConnectionNotice(null)}
            className="text-slate-400 hover:text-white p-1 rounded transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col min-h-0">
        {/* Group Selector Horizontal Bar */}
        <GroupSelectorBar
          groups={distinctGroups}
          selectedGroupCode={selectedGroupCode}
          onSelectGroup={(code) => setSelectedGroupCode(code)}
          onTestGroup={(code) => {
            setSelectedGroupCode(code);
            pollSingleGroup(code);
          }}
          groupResponses={groupResponses}
          isPollingGroup={isPollingSingle || isPollingAll || isTestingConnection}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
        />

        {/* Diagnostic Bar / Quick Action Strip */}
        <div className="px-4 sm:px-6 py-2 bg-slate-900/60 border-b border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5 font-medium text-slate-300">
              <Cpu className="w-3.5 h-3.5 text-emerald-400" />
              <span>Target: {selectedPLC.name}</span>
            </span>
            {selectedPLC.isSimulated && (
              <span className="px-1.5 py-0.5 rounded text-[10px] bg-purple-950 text-purple-300 border border-purple-800">
                Built-in B&R Simulation
              </span>
            )}
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => setIsReportModalOpen(true)}
              className="flex items-center gap-1 text-slate-300 hover:text-white font-medium transition-colors"
            >
              <FileText className="w-3.5 h-3.5 text-emerald-400" />
              <span>Generate Full Report</span>
            </button>
          </div>
        </div>

        {/* Core Group View */}
        {metadataLoading ? (
          <div className="flex-1 flex items-center justify-center p-12 text-slate-400">
            <RefreshCw className="w-6 h-6 animate-spin text-emerald-400 mr-3" />
            <span>Loading factory parameter metadata...</span>
          </div>
        ) : (
          <div className="flex-1 flex flex-col min-h-0">
            {/* Table & Values */}
            <GroupDataView
              readOnly={archived}
              groupCode={selectedGroupCode}
              metadataItems={activeGroupMetadata}
              responseData={activeResponse}
              onPollGroup={pollSingleGroup}
              isPolling={isPollingSingle || isPollingAll || isTestingConnection}
              searchQuery={searchQuery}
              dataModelCheck={dataModelCheck}
              dataModelReferences={dataModelReferences}
              referenceData={referenceData}
              missingDataModelParameters={missingDataModelParameters}
              onOpenDataModels={() => setIsDataModelsOpen(true)}
            />

            {/* Bottom TCP Frame Inspector */}
            <RawPacketInspector
              responseData={activeResponse}
              groupCode={selectedGroupCode}
              machineId={selectedPLC.machineId}
              onSwitchMachineId={(newId) => {
                setPLCs((prev) =>
                  prev.map((p) => (p.id === selectedPLC.id ? { ...p, machineId: newId } : p))
                );
              }}
              onTestGroup={(gc) => {
                setSelectedGroupCode(gc);
                pollSingleGroup(gc);
              }}
              onOpenManualFrameEditor={() => {
                setPLCModalTab('manual-frame');
                setIsPLCModalOpen(true);
              }}
            />
          </div>
        )}
      </main>

      {/* Modals */}
      {isDataModelsOpen && <DataModelModal
        metadata={metadata} machine={currentMachineType}
        selection={dataModelSelection} check={dataModelCheck}
        onSelectionChange={selection => {
          setDataModelSelection(selection);
          setDataModelSnapshot(null);
        }}
        onChecked={check => setDataModelSnapshot(check ? {check, metadata, machine: currentMachineType} : null)}
        onClose={() => setIsDataModelsOpen(false)}
      />}
      {isManualDataOpen && <ManualDataModal metadata={metadata} plc={selectedPLC} initialGroup={selectedGroupCode} onClose={()=>setIsManualDataOpen(false)} onDecoded={result=>{
        setSelectedGroupCode(result.groupCode);
        setGroupResponses(prev=>({...prev,[result.groupCode]:result}));
        setConnectionNotice(null);
        void (async () => {
          try {
            const response = await fetch('/api/nami/history/manual', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({plc: selectedPLC, metadata, metadataSource, groupResponses: {[result.groupCode]: result}})});
            if (!response.ok) throw new Error('Manual decoded data could not be saved in history.');
            const identity = await response.json();
            const row = {...result, testId: identity.testId, historyId: identity.historyId};
            setGroupResponses(prev => ({...prev, [result.groupCode]: row}));
            await persistDecoded(identity, {[result.groupCode]: row});
          } catch (error) {setHistoryWarning(error instanceof Error ? error.message : 'Manual history could not be saved.');}
        })();
      }}/>}
      <PLCManagerModal
        isOpen={isPLCModalOpen}
        onClose={() => setIsPLCModalOpen(false)}
        plcs={plcs}
        onSavePLCs={setPLCs}
        selectedPLCId={selectedPLCId}
        onSelectPLCId={setSelectedPLCId}
        initialTab={plcModalTab}
        onOpenRTCModal={(plc) => {
          setSelectedPLCId(plc.id);
          setIsRTCModalOpen(true);
        }}
        onOpenMetadataModal={(machineType) => {
          setCurrentMachineType(machineType);
          setIsPLCModalOpen(false);
          setIsUploadModalOpen(true);
        }}
      />

      <MetadataUploaderModal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        metadata={metadata}
        currentMachineType={currentMachineType}
        onSelectMachineType={(mType) => {
          setCurrentMachineType(mType);
        }}
        onMetadataLoaded={(items, sourceName, targetMachine) => {
          const mType = targetMachine || currentMachineType;
          setMetadata(items);
          setMetadataSource(sourceName);
          setCurrentMachineType(mType);
          setConnectionNotice(null);
          // Keep the selected machine and metadata aligned. The PLC connection state is separate.
          setPLCs((prev) =>
            prev.map((p) => (p.id === selectedPLC.id ? { ...p, machineType: mType } : p))
          );
          userStorage.setItem(`spinning_metadata_${mType}`, JSON.stringify(items));
          userStorage.setItem(`spinning_metadata_source_${mType}`, sourceName);
          if (items.length > 0) {
            setSelectedGroupCode(items[0].groupCode);
          }
        }}
        onResetToDefault={() => {
          userStorage.removeItem(`spinning_metadata_${currentMachineType}`);
          userStorage.removeItem(`spinning_metadata_source_${currentMachineType}`);
          loadMetadataForMachine(currentMachineType);
        }}
        currentSourceName={metadataSource}
        liveValues={
          activeResponse?.parsedValues
            ? Object.fromEntries(activeResponse.parsedValues.map((v) => [v.tagCode, v]))
            : undefined
        }
      />

      <SimulatorControlsModal
        isOpen={isSimulatorModalOpen}
        onClose={() => setIsSimulatorModalOpen(false)}
        onSimulatorUpdated={() => {
          pollSingleGroup(selectedGroupCode);
        }}
      />

      <TestReportModal
        isOpen={isReportModalOpen}
        onClose={() => setIsReportModalOpen(false)}
        plc={selectedPLC}
        metadata={metadata}
        groupResponses={groupResponses}
        dataModelCheck={dataModelCheck}
        dataModelReferences={referenceData}
      />

      <RTCModal
        isOpen={isRTCModalOpen}
        onClose={() => setIsRTCModalOpen(false)}
        plc={selectedPLC}
        onReadGroup={pollSingleGroup}
      />
    </div>
  );
}
