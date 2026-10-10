export interface DropdownOption {
  value: number | string;
  label: string;
  machineVariant?: string;
  isAlarm?: boolean;
}

export interface DropdownReferenceItem {
  tagCode: number;
  parameter?: string;
  screenName?: string;
  value: number;
  displayText: string;
  machineVariant?: string;
  isAlarm?: boolean;
}

export type DropdownReferenceMap = Record<number, DropdownOption[]>;

export interface MetadataItem {
  sNo: number;
  screenName: string;
  machineVariants: string;
  parameter: string;
  units: string;
  min: number | null;
  max: number | null;
  tagCode: number;
  groupCode: number;
  offset: number;
  fromVersion: string;
  toVersion: string;
  dataType: 'REAL' | 'UINT' | 'INT' | 'UDINT' | 'USINT' | 'SINT' | 'BOOL' | 'BYTE' | 'STRING' | string;
  arraySize?: number | null;
  offsetFactor: number;
  scaleFactor: number;
  isVisible: boolean;
  isWritable: boolean;
  conditionTagName?: string | null;
  bitOrTag?: string | null;
  bitNo?: number | null;
  bitCondition?: string | null;
  tagValue?: string | null;
  tagCondition?: string | null;
  isShownValueDifferent?: boolean;
  dropdownOptions?: DropdownOption[];
  sheet2MappingVersion?: number;
  sheet2NeedsReload?: boolean;
}

export type SpinningMachineType =
  | 'Carding'
  | 'Ring Frame'
  | 'Speed Frame'
  | 'Finisher'
  | 'Breaker'
  | 'Lapformer'
  | 'Comber'
  | 'Blow Room'
  | 'Auto Winder'
  | 'RAP'
  | 'Custom';

export interface PLCConfig {
  id: string;
  name: string;
  machineType?: SpinningMachineType;
  ip: string;
  port: number;
  machineId: number;
  isSimulated: boolean;
  endianness: 'little' | 'big';
  timeoutMs: number;
  interRequestDelayMs?: number;
  closeMode?: 'graceful' | 'wait_for_plc';
  status?: 'idle' | 'connected' | 'error' | 'testing';
  tcpConnected?: boolean;
  lastPingMs?: number;
  lastTested?: string;
  error?: string;
  programVersion?: number;
  programVersionStr?: string;
}

export interface ParsedParamValue {
  tagCode: number;
  parameter: string;
  screenName: string;
  groupCode: number;
  offset: number;
  dataType: string;
  units: string;
  rawValue: any;
  formattedValue: string;
  rawHex: string;
  min: number | null;
  max: number | null;
  isInRange: boolean;
  qualityIssue?: string;
  scaleFactor: number;
  offsetFactor: number;
  bitNo?: number | null;
  dropdownText?: string;
}

export interface GroupResponseData {
  testId?: string;
  historyId?: string;
  groupCode: number;
  groupName?: string;
  success: boolean;
  resultCode: number;
  dataLength: number;
  expectedLength?: number;
  lengthMatch: boolean;
  rawBytes: number[];
  sentBytes?: number[];
  rawHex: string;
  rttMs: number;
  timestamp: string;
  completedAt?: number;
  sequenceIndex?: number;
  error?: string;
  parsedValues: ParsedParamValue[];
  tcpConnected?: boolean;
  stage?: string;
  source?: 'manual' | 'plc';
  traceId?: string;
  closeResult?: { success: boolean; sentBytes?: number[]; plcClosed?: boolean; warning?: string; error?: string };
}

export interface TestExecutionSummary {
  plcId: string;
  plcName: string;
  totalGroups: number;
  successfulGroups: number;
  failedGroups: number;
  totalParams: number;
  validRangeParams: number;
  outOfRangeParams: number;
  durationMs: number;
  timestamp: string;
}
