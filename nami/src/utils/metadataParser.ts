import * as XLSX from 'xlsx';
import { MetadataItem, DropdownReferenceItem } from '../types';
import { attachDropdownsToMetadata, STANDARD_DROPDOWN_REFERENCES } from '../data/machinePresets';
import {buildDataModelRowChecks, buildDataModelRowReferences, checkedDataModels, groupDataModelReferences, dataModelResultLabel, metadataRowKey, type DataModelCheck, type DataModelReferenceData} from './dataModelChecks';

const VALID_DATA_TYPES = new Set(['REAL', 'LREAL', 'DINT', 'UDINT', 'UINT', 'INT', 'USINT', 'SINT', 'BOOL', 'BYTE', 'STRING']);

export class MetadataValidationError extends Error {
  items?: MetadataItem[];
  issues: string[];
  constructor(message: string, items: MetadataItem[] = [], issues: string[] = []) {
    super(message);
    this.name = 'MetadataValidationError';
    this.items = items;
    this.issues = issues;
  }
}

export function validateMetadata(items: MetadataItem[]): MetadataItem[] {
  const seen = new Set<string>();
  const errors: string[] = [];

  items.forEach((item, index) => {
    const row = index + 2;
    const key = `${item.groupCode}:${item.tagCode}`;
    const normalizedType = item.dataType.replace(/\[\d+\]$/, '').toUpperCase();

    if (!Number.isInteger(item.groupCode) || item.groupCode < 0) errors.push(`row ${row}: invalid GROUP_CODE`);
    if (!Number.isInteger(item.tagCode) || item.tagCode < 0) errors.push(`row ${row}: invalid TAG_CODE`);
    if (!Number.isInteger(item.offset) || item.offset < 0) errors.push(`row ${row}: invalid OFFSET`);
    if (!item.parameter.trim()) errors.push(`row ${row}: missing parameter name`);
    if (!VALID_DATA_TYPES.has(normalizedType)) errors.push(`row ${row}: unsupported data type "${item.dataType}"`);
    if (item.arraySize !== undefined && item.arraySize !== null && (!Number.isInteger(item.arraySize) || item.arraySize <= 0)) {
      errors.push(`row ${row}: invalid array size`);
    }
    if (seen.has(key)) errors.push(`row ${row}: duplicate GROUP_CODE/TAG_CODE (${key})`);
    seen.add(key);
  });

  if (errors.length > 0) {
    throw new MetadataValidationError(`Invalid metadata: ${errors.slice(0, 8).join('; ')}`, items, errors);
  }

  return items;
}

/**
 * Parses CSV text into MetadataItem[]
 */
export function parseCSVMetadata(csvText: string): MetadataItem[] {
  const lines = csvText.split(/\r?\n/).filter(line => line.trim().length > 0);
  if (lines.length < 2) throw new MetadataValidationError('Metadata file must contain a header and at least one data row.');

  // Parse header
  const items: MetadataItem[] = [];

  // Robust CSV line splitter that handles quotes
  function parseCSVLine(line: string): string[] {
    const result: string[] = [];
    let cur = '';
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const char = line[i];
      if (char === '"') {
        inQuotes = !inQuotes;
      } else if (char === ',' && !inQuotes) {
        result.push(cur.trim());
        cur = '';
      } else {
        cur += char;
      }
    }
    result.push(cur.trim());
    return result;
  }

  const header = parseCSVLine(lines[0]).map(h => h.toUpperCase().replace(/\s+/g, '_'));

  // Find column indices
  const colIndex = {
    sNo: header.findIndex(h => h.includes('S_NO') || h.includes('SNO')),
    screenName: header.findIndex(h => h.includes('SCREEN')),
    machineVariants: header.findIndex(h => h.includes('MACHINE_VARIENT') || h.includes('VARIENT') || h.includes('VARIANT')),
    parameter: header.findIndex(h => h.includes('PARAM')),
    units: header.findIndex(h => h.includes('UNIT')),
    min: header.findIndex(h => h === 'MIN'),
    max: header.findIndex(h => h === 'MAX'),
    tagCode: header.findIndex(h => h.includes('TAG_CODE')),
    groupCode: header.findIndex(h => h.includes('GROUP_CODE') || h.includes('GROUP')),
    offset: header.findIndex(h => h.includes('OFFSET_FROM') || h.includes('OFFSET')),
    fromVersion: header.findIndex(h => h.includes('FROM_VERSION')),
    toVersion: header.findIndex(h => h.includes('TO_VERSION')),
    dataType: header.findIndex(h => h.includes('TAG_DATA_TYPE') || h.includes('DATA_TYPE') || h.includes('TYPE')),
    arraySize: header.findIndex(h => h.includes('ARRAY_SIZE') || h.includes('ARRAY_LENGTH') || h === 'SIZE'),
    offsetFactor: header.findIndex(h => h.includes('OFFSET_FACTOR')),
    scaleFactor: header.findIndex(h => h.includes('SCALE_FACTOR')),
    isVisible: header.findIndex(h => h.includes('IS_VISIBLE') || h.includes('VISIBLE')),
    isWritable: header.findIndex(h => h.includes('IS_WRITABLE') || h.includes('WRITABLE')),
    bitNo: header.findIndex(h => h.includes('BIT_NO')),
    conditionTagName: header.findIndex(h => h.includes('CONDITION_TAG')),
  };

  const requiredColumns: Array<[string, number]> = [
    ['GROUP_CODE', colIndex.groupCode],
    ['TAG_CODE', colIndex.tagCode],
    ['PARAMETERS', colIndex.parameter],
    ['OFFSET', colIndex.offset],
    ['TAG_DATA_TYPE', colIndex.dataType],
  ];
  const missingColumns = requiredColumns.filter(([, index]) => index === -1).map(([name]) => name);
  if (missingColumns.length > 0) {
    throw new MetadataValidationError(`Metadata header is missing: ${missingColumns.join(', ')}`);
  }

  for (let i = 1; i < lines.length; i++) {
    const row = parseCSVLine(lines[i]);
    // Excel often retains formatting on empty rows/columns outside the table.
    if (row.every(value => !value.trim())) continue;
    if (row.length < header.length) {
      throw new MetadataValidationError(`Invalid metadata row ${i + 1}: expected ${header.length} columns, found ${row.length}.`);
    }

    const parseNumOrNull = (idx: number): number | null => {
      if (idx === -1 || idx >= row.length) return null;
      const v = row[idx].replace(/<null>/gi, '').trim();
      if (v === '' || isNaN(Number(v))) return null;
      return Number(v);
    };

    const parseStr = (idx: number, fallback: string = ''): string => {
      if (idx === -1 || idx >= row.length) return fallback;
      const v = row[idx].replace(/<null>/gi, '').trim();
      return v || fallback;
    };

    const groupCode = parseNumOrNull(colIndex.groupCode);
    const tagCode = parseNumOrNull(colIndex.tagCode);
    const offset = parseNumOrNull(colIndex.offset);

    if (groupCode === null || tagCode === null || offset === null) {
      throw new MetadataValidationError(`Invalid metadata row ${i + 1}: GROUP_CODE, TAG_CODE, and OFFSET are required numbers.`);
    }

    const sNo = parseNumOrNull(colIndex.sNo) ?? i;
    const screenName = parseStr(colIndex.screenName, `Group ${groupCode ?? 'N/A'}`);
    const machineVariants = parseStr(colIndex.machineVariants, 'BOTH');
    const parameter = parseStr(colIndex.parameter);
    const units = parseStr(colIndex.units, '');
    const min = parseNumOrNull(colIndex.min);
    const max = parseNumOrNull(colIndex.max);
    const fromVersion = parseStr(colIndex.fromVersion, '5.295');
    const toVersion = parseStr(colIndex.toVersion, '5.296');
    const rawDataType = parseStr(colIndex.dataType).toUpperCase();
    const arrayTypeMatch = rawDataType.match(/^(REAL|LREAL|DINT|UINT|INT|UDINT|USINT|SINT|BOOL|BYTE|STRING)\[(\d+)\]$/);
    const dataType = arrayTypeMatch ? arrayTypeMatch[1] : rawDataType;
    const arraySize = arrayTypeMatch ? Number(arrayTypeMatch[2]) : parseNumOrNull(colIndex.arraySize);
    const offsetFactor = parseNumOrNull(colIndex.offsetFactor) ?? 1;
    const scaleFactor = parseNumOrNull(colIndex.scaleFactor) ?? 1;
    const isVisible = parseStr(colIndex.isVisible, 'YES').toUpperCase() === 'YES';
    const isWritable = parseStr(colIndex.isWritable, 'NO').toUpperCase() === 'YES';
    const bitNo = parseNumOrNull(colIndex.bitNo);
    const conditionTagName = parseStr(colIndex.conditionTagName, '') || null;

    const finalOffset = offset;

    items.push({
      sNo,
      screenName,
      machineVariants,
      parameter,
      units,
      min,
      max,
      tagCode: tagCode ?? sNo,
      groupCode,
      offset: finalOffset,
      fromVersion,
      toVersion,
      dataType,
      arraySize,
      offsetFactor,
      scaleFactor,
      isVisible,
      isWritable,
      bitNo,
      conditionTagName,
    });
  }

  return validateMetadata(items);
}

/**
 * Parses Sheet 2 (Dropdown Reference) from an Excel worksheet
 */
export function parseDropdownReferenceSheet(worksheet: XLSX.WorkSheet): DropdownReferenceItem[] {
  const rows = XLSX.utils.sheet_to_json(worksheet, { header: 1, defval: '' }) as any[][];
  if (!rows || rows.length < 2) return [];

  // Find header row (search first 6 rows)
  let headerRowIndex = 0;
  for (let i = 0; i < Math.min(rows.length, 6); i++) {
    const r = rows[i].map((c) => String(c || '').trim().toUpperCase());
    if (
      r.some(
        (h) =>
          h.includes('TAG') ||
          h.includes('VAL') ||
          h.includes('PARAM') ||
          h.includes('TEXT') ||
          h.includes('DROP') ||
          h.includes('DISPLAY') ||
          h.includes('MEANING')
      )
    ) {
      headerRowIndex = i;
      break;
    }
  }

  const rawHeader = rows[headerRowIndex].map((h) =>
    String(h || '').trim().toUpperCase().replace(/\s+/g, '_')
  );

  const colIndex = {
    tagCode: rawHeader.findIndex(
      (h) =>
        h.includes('TAG_CODE') ||
        h.includes('TAGCODE') ||
        h.includes('TAG_NO') ||
        h.includes('TAGNO') ||
        h === 'TAG' ||
        h.includes('S_NO')
    ),
    parameter: rawHeader.findIndex(
      (h) =>
        h.includes('PARAM') ||
        h.includes('SCREEN') ||
        h.includes('NAME') ||
        h.includes('FIELD')
    ),
    value: (() => {
      const plcValue = rawHeader.findIndex((h) => /^PLC_?VAL(?:UE)?$/.test(h));
      if (plcValue !== -1) return plcValue;
      // Prefer an actual VALUE column. Do not accidentally select TAG_CODE
      // merely because its header contains the word CODE.
      const exact = rawHeader.findIndex((h) => h === 'VALUE' || h === 'VAL');
      if (exact !== -1) return exact;
      return rawHeader.findIndex(
        (h) =>
          (h.includes('VAL') || h.includes('KEY') || h === 'ID' || h === 'CODE') &&
          !h.includes('TAG_CODE') &&
          !h.includes('TAGCODE') &&
          !/SHOWN|DISPLAY|TEXT/.test(h)
      );
    })(),
    displayText: rawHeader.findIndex(
      (h) =>
        /^SHOWN_?VAL(?:UE)?$/.test(h) ||
        h.includes('TEXT') ||
        h.includes('DISPLAY') ||
        h.includes('DESC') ||
        h.includes('DROP') ||
        h.includes('MEANING') ||
        h.includes('LABEL') ||
        h.includes('OPTION')
    ),
    machineVariant: rawHeader.findIndex(
      (h) => h.includes('MACHINE_VARIANT') || h.includes('MACHINE_VARIENT') || h.includes('VARIANT') || h.includes('VARIENT')
    ),
    isAlarm: rawHeader.findIndex(
      (h) => h.includes('IS_ALARM') || h.includes('ALARM')
    ),
  };

  // Fallbacks if columns are positional (e.g. Tag, Parameter, Value, Display Text)
  if (colIndex.tagCode === -1 && rawHeader.length >= 1) colIndex.tagCode = 0;
  if (colIndex.value === -1 && rawHeader.length >= 3) colIndex.value = 2;
  if (colIndex.displayText === -1 && rawHeader.length >= 4) colIndex.displayText = 3;
  if (colIndex.displayText === -1 && rawHeader.length === 3) colIndex.displayText = 2;

  const result: DropdownReferenceItem[] = [];

  for (let i = headerRowIndex + 1; i < rows.length; i++) {
    const row = rows[i];
    if (!row || row.length === 0) continue;

    const rawTagCode = colIndex.tagCode !== -1 ? row[colIndex.tagCode] : null;
    const rawVal = colIndex.value !== -1 ? row[colIndex.value] : null;
    const rawText = colIndex.displayText !== -1 ? row[colIndex.displayText] : null;
    const rawParam = colIndex.parameter !== -1 ? row[colIndex.parameter] : '';
    const rawVariant = colIndex.machineVariant !== -1 ? row[colIndex.machineVariant] : '';
    const rawAlarm = colIndex.isAlarm !== -1 ? row[colIndex.isAlarm] : '';

    if (
      rawVal === undefined ||
      rawVal === null ||
      rawVal === '' ||
      rawText === undefined ||
      rawText === null ||
      rawText === ''
    ) {
      continue;
    }

    const tagCodeNum = Number(rawTagCode);
    const valNum = Number(rawVal);

    const machineVariant = String(rawVariant ?? '').trim();
    const alarmText = String(rawAlarm ?? '').trim().toUpperCase();
    result.push({
      tagCode: isNaN(tagCodeNum) ? 0 : tagCodeNum,
      parameter: String(rawParam || '').trim(),
      value: isNaN(valNum) ? (rawVal as any) : valNum,
      displayText: String(rawText ?? '').trim(),
      machineVariant: machineVariant || undefined,
      isAlarm: alarmText === 'YES' ? true : alarmText === 'NO' ? false : undefined,
    });
  }

  return result;
}

/**
 * Parses a standalone CSV text containing Dropdown Reference (Sheet 2)
 */
export function parseDropdownReferenceCSV(csvText: string): DropdownReferenceItem[] {
  const workbook = XLSX.read(csvText, { type: 'string' });
  const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
  return parseDropdownReferenceSheet(firstSheet);
}

/**
 * Parses Excel (.xlsx, .xls) ArrayBuffer and extracts both Sheet 1 (Metadata) and Sheet 2 (Dropdown Reference)
 */
export function parseExcelWithDropdownReferences(arrayBuffer: ArrayBuffer): {
  items: MetadataItem[];
  dropdownReferences: DropdownReferenceItem[];
} {
  const workbook = XLSX.read(arrayBuffer, { type: 'array' });
  const sheetNames = workbook.SheetNames;
  if (sheetNames.length === 0) {
    return { items: [], dropdownReferences: [] };
  }

  // Parse Sheet 1
  const firstSheet = workbook.Sheets[sheetNames[0]];
  const csvText = XLSX.utils.sheet_to_csv(firstSheet);
  const rawItems = parseCSVMetadata(csvText);

  // Check if Sheet 2 exists (by index or by name matching dropdown/reference)
  let dropdownReferences: DropdownReferenceItem[] = [];
  let refSheetName: string | undefined;

  if (sheetNames.length > 1) {
    // Check for named sheet first
    refSheetName = sheetNames.find((s) =>
      /drop\s*down|reference|lookup|enum|sheet\s*2/i.test(s)
    );
    // Otherwise default to the 2nd sheet
    if (!refSheetName) {
      refSheetName = sheetNames[1];
    }
  }

  if (refSheetName && workbook.Sheets[refSheetName]) {
    dropdownReferences = parseDropdownReferenceSheet(workbook.Sheets[refSheetName]);
  }

  // Attach dropdown references to items
  const items = dropdownReferences.length > 0
    ? attachDropdownsToMetadata(rawItems, dropdownReferences)
    : rawItems;

  return { items: items.map(item => ({...item, sheet2MappingVersion: 2})), dropdownReferences };
}

/** Old parsed caches have lost SHOWNVAL. Flag them for re-upload rather than
 * presenting MACHINE VARIANT as an engineering value or guessing the label. */
export function restoreSavedSheet2(items: MetadataItem[]): MetadataItem[] {
  return items.map(item => {
    const options = item.dropdownOptions || [];
    const legacyVariantLabels = item.sheet2MappingVersion !== 2 && options.length > 0 && options.every(option =>
      option.machineVariant && option.label.trim() === option.machineVariant.trim());
    return legacyVariantLabels ? {...item, dropdownOptions: undefined, sheet2NeedsReload: true} : item;
  });
}

/**
 * Parses Excel (.xlsx, .xls) ArrayBuffer or File (attaches Sheet 2 dropdowns if present)
 */
export function parseExcelMetadata(arrayBuffer: ArrayBuffer): MetadataItem[] {
  const result = parseExcelWithDropdownReferences(arrayBuffer);
  return result.items;
}

export interface MetadataGroupAnalysis {
  groupCode: number;
  parameterCount: number;
  expectedPayloadLength: number;
  screenNames: string[];
  dataTypes: string[];
  duplicateTagCodes: number[];
  duplicateOffsets: number[];
  overlappingRanges: Array<{ tagCode: number; otherTagCode: number; offset: number; otherOffset: number }>;
}

export interface MetadataAnalysis {
  totalParameters: number;
  totalGroups: number;
  totalScreens: number;
  sheet2Mappings: number;
  duplicateTagErrors: string[];
  duplicateOffsetErrors: string[];
  overlapErrors: string[];
  unsupportedTypeErrors: string[];
  invalidOffsetErrors: string[];
  groupSummaries: MetadataGroupAnalysis[];
}

export function analyzeMetadata(items: MetadataItem[], sheet2Mappings = 0): MetadataAnalysis {
  const typeSizes: Record<string, number> = {
    BOOL: 1, BYTE: 1, USINT: 1, SINT: 1,
    UINT: 2, INT: 2,
    DINT: 4, UDINT: 4, REAL: 4,
    LREAL: 8,
    STRING: 50,
  };
  const groups = new Map<number, MetadataItem[]>();
  const duplicateTagErrors: string[] = [];
  const duplicateOffsetErrors: string[] = [];
  const overlapErrors: string[] = [];
  const unsupportedTypeErrors: string[] = [];
  const invalidOffsetErrors: string[] = [];

  for (const item of items) {
    if (!groups.has(item.groupCode)) groups.set(item.groupCode, []);
    groups.get(item.groupCode)!.push(item);
    const base = String(item.dataType || '').replace(/\[\d+\]$/, '').toUpperCase();
    if (!typeSizes[base]) unsupportedTypeErrors.push(`Group ${item.groupCode}, Tag ${item.tagCode}: unsupported type ${item.dataType}`);
    if (!Number.isInteger(item.offset) || item.offset < 0) invalidOffsetErrors.push(`Group ${item.groupCode}, Tag ${item.tagCode}: invalid offset ${item.offset}`);
  }

  const groupSummaries: MetadataGroupAnalysis[] = [];
  for (const [groupCode, groupItems] of Array.from(groups.entries()).sort((a,b)=>a[0]-b[0])) {
    const tagMap = new Map<number, MetadataItem[]>();
    const offsetMap = new Map<number, MetadataItem[]>();
    const ranges: Array<{item: MetadataItem; start:number; end:number}> = [];
    for (const item of groupItems) {
      if (!tagMap.has(item.tagCode)) tagMap.set(item.tagCode, []);
      tagMap.get(item.tagCode)!.push(item);
      if (!offsetMap.has(item.offset)) offsetMap.set(item.offset, []);
      offsetMap.get(item.offset)!.push(item);
      const base = String(item.dataType || '').replace(/\[\d+\]$/, '').toUpperCase();
      const match = String(item.dataType || '').match(/\[(\d+)\]$/);
      const count = match ? Math.max(1, Number(match[1])) : (item.arraySize && item.arraySize > 0 ? item.arraySize : 1);
      const size = typeSizes[base] || 1;
      ranges.push({ item, start: item.offset, end: item.offset + size * count });
    }
    const duplicateTagCodes = Array.from(tagMap.entries()).filter(([,v])=>v.length>1).map(([k])=>k);
    const duplicateOffsets = Array.from(offsetMap.entries()).filter(([,v])=>v.length>1).map(([k])=>k);
    duplicateTagCodes.forEach(t => duplicateTagErrors.push(`Group ${groupCode}: duplicate TAG_CODE ${t}`));
    duplicateOffsets.forEach(o => duplicateOffsetErrors.push(`Group ${groupCode}: duplicate OFFSET ${o}`));
    const overlaps: MetadataGroupAnalysis['overlappingRanges'] = [];
    ranges.sort((a,b)=>a.start-b.start || a.end-b.end);
    for (let i=0;i<ranges.length;i++) for (let j=i+1;j<ranges.length;j++) {
      if (ranges[j].start >= ranges[i].end) break;
      if (ranges[i].item.tagCode !== ranges[j].item.tagCode) {
        overlaps.push({tagCode:ranges[i].item.tagCode, otherTagCode:ranges[j].item.tagCode, offset:ranges[i].start, otherOffset:ranges[j].start});
        overlapErrors.push(`Group ${groupCode}: overlapping offsets Tag ${ranges[i].item.tagCode} (+${ranges[i].start}) and Tag ${ranges[j].item.tagCode} (+${ranges[j].start})`);
      }
    }
    groupSummaries.push({
      groupCode,
      parameterCount: groupItems.length,
      expectedPayloadLength: Math.max(0, ...ranges.map(r=>r.end)),
      screenNames: Array.from(new Set(groupItems.map(i=>i.screenName).filter(Boolean))),
      dataTypes: Array.from(new Set(groupItems.map(i=>String(i.dataType).toUpperCase()))),
      duplicateTagCodes,
      duplicateOffsets,
      overlappingRanges: overlaps,
    });
  }
  return {
    totalParameters: items.length,
    totalGroups: groups.size,
    totalScreens: new Set(items.map(i=>i.screenName)).size,
    sheet2Mappings,
    duplicateTagErrors,
    duplicateOffsetErrors,
    overlapErrors,
    unsupportedTypeErrors,
    invalidOffsetErrors,
    groupSummaries,
  };
}

/**
 * Calculates the minimum PLC payload length required by metadata for one group.
 * Offsets are byte offsets from the start of the group payload.
 */
export function getExpectedGroupPayloadLength(items: MetadataItem[]): number {
  const typeSizes: Record<string, number> = {
    REAL: 4,
    LREAL: 8,
    DINT: 4,
    UINT: 2,
    INT: 2,
    UDINT: 4,
    USINT: 1,
    SINT: 1,
    BOOL: 1,
    BYTE: 1,
    STRING: 50,
  };

  return items.reduce((maxEnd, item) => {
    const type = String(item.dataType || '').replace(/\[\d+\]$/, '').toUpperCase();
    const elementSize = typeSizes[type] || 1;
    const declaredCount = Number(String(item.dataType || '').match(/\[(\d+)\]$/)?.[1] || 0);
    const count = item.arraySize && item.arraySize > 0 ? item.arraySize : declaredCount || 1;
    const width = type === 'STRING' ? (item.arraySize || declaredCount || 50) : elementSize * count;
    const end = item.offset + width;
    return Math.max(maxEnd, end);
  }, 0);
}

/**
 * Exports MetadataItem[] and their live tested values to .xlsx
 */
export function exportVerificationExcel(
  items: MetadataItem[],
  liveValues?: Record<number, any>,
  groupCodeFilter?: number,
  dataModelCheck: DataModelCheck | null = null,
  referenceData?: DataModelReferenceData,
  testRuns: Record<number, {testId?: string; historyId?: string}> = {}
): Uint8Array {
  const filtered = groupCodeFilter ? items.filter(i => i.groupCode === groupCodeFilter) : items;
  const modelRows = buildDataModelRowChecks(items, dataModelCheck, referenceData?.models || []);
  const references = buildDataModelRowReferences(items, referenceData?.models || [], dataModelCheck);
  const checkedModels = checkedDataModels(items, referenceData?.models || [], dataModelCheck);

  const data = filtered.map(item => {
    const live = liveValues ? liveValues[item.tagCode] : undefined;
    const modelRow = modelRows.get(metadataRowKey(item));
    const modelReferences = references.get(metadataRowKey(item)) || [];
    return {
      'S.No': item.sNo,
      'Group Code': item.groupCode,
      'Screen Name': item.screenName,
      'Parameter Name': item.parameter,
      'Data Model': modelReferences.length ? groupDataModelReferences(modelReferences).map(group => `${group.name}\n${group.services.join(', ')}\n${group.label}`).join('\n\n') :
        referenceData?.loading ? 'Loading references' : referenceData?.error ? 'References unavailable' : referenceData ? item.parameter + ' / Not in data model' : 'Not loaded',
      'Data Model Sources': modelReferences.map(reference => `${reference.sourceRelativePath || reference.source} / ${reference.sheet}:${reference.row} / ${reference.plcType} / GC ${reference.groupCodes.join(', ')}`).join('\n'),
      'Data Model Check': modelRow?.status || (referenceData?.loading ? 'Loading references' : referenceData?.error ? 'References unavailable' : referenceData || dataModelCheck ? 'Not in data model' : 'Not loaded'),
      'Data Model Details': modelRow?.requirements.map(row => `${row.name}: ${row.detail || ''}`).join('\n') || '',
      'Data Model Reference': [...new Set(modelReferences.map(row => row.service + ': ' + (row.sourceRelativePath || row.source)))].join('\n'),
      'Test ID': testRuns[item.groupCode]?.testId || '',
      'History ID': testRuns[item.groupCode]?.historyId || '',
      'Offset (Bytes)': item.offset,
      'Data Type': item.dataType,
      'Units': item.units,
      'Min': item.min ?? '-',
      'Max': item.max ?? '-',
      'Live Value': live !== undefined ? live.formattedValue : 'Not Read',
      'Raw Hex': live !== undefined ? live.rawHex : '-',
      'Data Quality Status': live !== undefined ? (live.isInRange ? 'PASS' : 'FAIL') : '-',
      'Data Quality Details': live?.qualityIssue || '',
      'Scale Factor': item.scaleFactor,
      'Offset Factor': item.offsetFactor,
      'Writable': item.isWritable ? 'YES' : 'NO',
      'Visible': item.isVisible ? 'YES' : 'NO',
    };
  });

  const worksheet = XLSX.utils.json_to_sheet(data);
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, 'PLC Verification');
  const runRows = Object.entries(testRuns).map(([group, run]) => ({'Group Code': Number(group), 'Test ID': run.testId || '', 'History ID': run.historyId || ''}));
  if (runRows.length) XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(runRows), 'Test IDs');
  if (checkedModels.length) {
    // Include missing requirements, which cannot appear as existing metadata rows.
    const requirements = checkedModels.flatMap(({model, result}) => result.rows
      .filter(row => !groupCodeFilter || row.groupCodes.includes(groupCodeFilter)).map(row => ({
      'Service': model.service,
      'Department': model.machine,
      'Reference Model': model.sourceRelativePath || model.source,
      'Check Mode': model.id === dataModelCheck?.model.id ? 'Saved' : 'Automatic',
      'Validated At': model.id === dataModelCheck?.model.id ? dataModelCheck.validatedAt : '',
      'Parameter Name': row.name,
      'Expected Data Type': row.plcType,
      'Expected Group Codes': row.groupCodes.join(', '),
      'Result': dataModelResultLabel(row),
      'Details': row.detail || '',
      'Actual Metadata': row.actual?.map(item => `${item.parameter} / GC ${item.groupCode} / ${item.dataType} / Tag ${item.tagCode}`).join('\n') || '',
      'Formula': row.formula,
      'Source': row.source,
      'Sheet': row.sheet,
      'Row': row.row,
      'Excel References': row.excelReferences?.map(source => `${source.source} / ${source.sheet}:${source.row}`).join('\n') || '',
    })));
    XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(requirements), 'Data Model Requirements');
  }

  const excelBuffer = XLSX.write(workbook, { bookType: 'xlsx', type: 'array' });
  return new Uint8Array(excelBuffer);
}

/**
 * Exports a clean Metadata Template in Excel (.xlsx) format for any machine type
 */
export function exportMetadataTemplateExcel(
  machineType: string,
  sampleItems: MetadataItem[]
): Uint8Array {
  const rows = sampleItems.map((item) => ({
    'S NO.': item.sNo,
    'Screen name': item.screenName,
    'Machine Varients': item.machineVariants || 'BOTH',
    'Parameters': item.parameter,
    'UNITS': item.units || '<null>',
    'MIN': item.min ?? '<null>',
    'MAX': item.max ?? '<null>',
    'TAG_CODE': item.tagCode,
    'GROUP_CODE': item.groupCode,
    'OFFSET_FROM_THE_START_OF_THE_GROUP_IN_BYTES': item.offset,
    'FROM_VERSION': item.fromVersion || '5.295',
    'TO_VERSION': item.toVersion || '5.296',
    'TAG_DATA_TYPE': item.dataType,
    'OFFSET_FACTOR': item.offsetFactor || 1,
    'SCALE_FACTOR': item.scaleFactor || 1,
    'IS_VISIBLE': item.isVisible ? 'YES' : 'NO',
    'IS_WRITABLE': item.isWritable ? 'YES' : 'NO',
    'CONDITION_TAG_NAME': '<null>',
    'BIT_OR_TAG': '<null>',
    'BIT_NO': '<null>',
    'BIT_CONDITION': '<null>',
    'TAG_VALUE': '<null>',
    'TAG_CONDITION': '<null>',
    'IS_SHOWN_VALUE_DIFFERENT': '<null>',
  }));

  const worksheet = XLSX.utils.json_to_sheet(rows);
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, `${machineType} Metadata`);

  // Sheet 2: Dropdown Reference
  const dropdownRows = STANDARD_DROPDOWN_REFERENCES.map((ref) => ({
    'TAG_CODE': ref.tagCode,
    'PARAMETER': ref.parameter,
    'VALUE': ref.value,
    'DISPLAY_TEXT': ref.displayText,
  }));
  const dropdownSheet = XLSX.utils.json_to_sheet(dropdownRows);
  XLSX.utils.book_append_sheet(workbook, dropdownSheet, 'Dropdown Reference');

  const excelBuffer = XLSX.write(workbook, { bookType: 'xlsx', type: 'array' });
  return new Uint8Array(excelBuffer);
}

/**
 * Exports Dropdown Reference items to .xlsx format
 */
export function exportDropdownReferenceExcel(references: DropdownReferenceItem[]): Uint8Array {
  const rows = references.map((ref) => ({
    'TAG_CODE': ref.tagCode,
    'PARAMETER': ref.parameter || '',
    'VALUE': ref.value,
    'DISPLAY_TEXT': ref.displayText,
  }));

  const worksheet = XLSX.utils.json_to_sheet(rows);
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, 'Dropdown Reference');

  const excelBuffer = XLSX.write(workbook, { bookType: 'xlsx', type: 'array' });
  return new Uint8Array(excelBuffer);
}

/**
 * Exports Dropdown Reference items to CSV format
 */
export function exportDropdownReferenceCSV(references: DropdownReferenceItem[]): string {
  const headers = ['TAG_CODE', 'PARAMETER', 'VALUE', 'DISPLAY_TEXT'];
  const lines = [headers.join(',')];
  for (const ref of references) {
    lines.push(`${ref.tagCode},"${ref.parameter || ''}",${ref.value},"${ref.displayText}"`);
  }
  return lines.join('\n');
}

/**
 * Exports a clean Metadata Template in CSV format for any machine type
 */
export function exportMetadataTemplateCSV(
  machineType: string,
  sampleItems: MetadataItem[]
): string {
  const headers = [
    'S NO.',
    'Screen name',
    'Machine Varients',
    'Parameters',
    'UNITS',
    'MIN',
    'MAX',
    'TAG_CODE',
    'GROUP_CODE',
    'OFFSET_FROM_THE_START_OF_THE_GROUP_IN_BYTES',
    'FROM_VERSION',
    'TO_VERSION',
    'TAG_DATA_TYPE',
    'OFFSET_FACTOR',
    'SCALE_FACTOR',
    'IS_VISIBLE',
    'IS_WRITABLE',
    'CONDITION_TAG_NAME',
    'BIT_OR_TAG',
    'BIT_NO',
    'BIT_CONDITION',
    'TAG_VALUE',
    'TAG_CONDITION',
    'IS_SHOWN_VALUE_DIFFERENT',
  ];

  const lines = [headers.join(',')];
  for (const item of sampleItems) {
    const row = [
      item.sNo,
      `"${item.screenName}"`,
      `"${item.machineVariants || 'BOTH'}"`,
      `"${item.parameter}"`,
      item.units ? `"${item.units}"` : '<null>',
      item.min !== null ? item.min : '<null>',
      item.max !== null ? item.max : '<null>',
      item.tagCode,
      item.groupCode,
      item.offset,
      item.fromVersion || '5.295',
      item.toVersion || '5.296',
      item.dataType,
      item.offsetFactor || 1,
      item.scaleFactor || 1,
      item.isVisible ? 'YES' : 'NO',
      item.isWritable ? 'YES' : 'NO',
      '<null>',
      '<null>',
      '<null>',
      '<null>',
      '<null>',
      '<null>',
      '<null>',
    ];
    lines.push(row.join(','));
  }

  return lines.join('\n');
}
