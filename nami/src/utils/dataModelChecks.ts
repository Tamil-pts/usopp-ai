import type {MetadataItem} from '../types';

export type DataModelStatus = 'PASS' | 'FAIL' | 'OPTIONAL' | 'UNRESOLVED' | 'SKIPPED' | 'DERIVED';
export interface DataModelSummary {
  id: string; source: string; service: string; machine: string;
  parameterCount: number; warningCount: number; fixed?: boolean;
  sourceRelativePath?: string;
}
export interface DataModelParameter {
  name: string; dataType: string; plcType: string; groupCodes: number[];
  kind: string; formula: string; source: string; sheet: string; row: number;
  required?: boolean; status?: DataModelStatus; detail?: string;
  reasonCodes?: string[]; actual?: MetadataItem[];
  excelReferences?: {source: string; sheet: string; row: number; name?: string; dataType?: string; plcType?: string; kind?: string}[];
  referenceIssues?: {code: string; detail: string}[];
  suggestedPlcType?: string;
  dataTypeRole?: 'value'|'wire'; numericValueType?: boolean; aliases?: string[]; canonicalName?: string; mappingSource?: string;
  ignoreNameSeparators?: boolean;
  referenceCorrections?: {field:string;previous:string;value:string;source:string}[];
}
export interface DataModel extends Omit<DataModelSummary, 'parameterCount' | 'warningCount'> {
  parameters: DataModelParameter[]; warnings: string[];
  originalSource?: string; sourceType?: string;
  mappingRulesRevision?:string;
}
export interface DataModelResult {
  modelId: string; status: string; summary: Record<DataModelStatus, number>;
  rows: DataModelParameter[];
  mappingRulesRevision?:string;
}
export interface DataModelSelection {service: string; modelId: string; allMachines: boolean}
export interface DataModelCheck {model: DataModel; result: DataModelResult; validatedAt: string}
export interface DataModelRowCheck {status: DataModelStatus; requirements: DataModelParameter[]}
export interface DataModelReference extends DataModelParameter {
  modelId: string; service: string; machine: string; sourceRelativePath?: string;
  match: 'exact' | 'name-differs';
}
export interface DataModelReferenceData {models: DataModel[]; loading: boolean; error: string; snapshot?: boolean}

export const dataModelMachineKey = (value: string) => value.toLowerCase().replace(/[^a-z]/g, '')
  .replace(/^finisher$/, 'drawframefinisher').replace(/^breaker$/, 'drawframebreaker');
export const dataModelDepartmentLabel = (value: string) => ({drawframefinisher: 'Finisher', drawframebreaker: 'Breaker',
  ringframe: 'Ring Frame', ringframeybs: 'Ring Frame YBS', speedframe: 'Speed Frame', blowroom: 'Blow Room',
  carding: 'Carding', lapformer: 'Lapformer', comber: 'Comber'} as Record<string, string>)[dataModelMachineKey(value)] || value;
export const metadataRowKey = (item: MetadataItem) =>
  JSON.stringify([item.groupCode, item.tagCode, item.sNo, item.offset, item.parameter]);
const nameKey = (name: string) => name.trim().toLowerCase();
const similarName = (name: string) => name.toLowerCase().replace(/[^a-z0-9]/g, '');
const groupKey = (name: string, group: number) => JSON.stringify([name, group]);
const priority: Record<DataModelStatus, number> = {
  FAIL: 6, UNRESOLVED: 5, OPTIONAL: 4, DERIVED: 3, SKIPPED: 2, PASS: 1,
};
const serviceOrder = ['PMS', 'QMS', 'CMS'];
const plcTypes = new Set(['BOOL', 'SINT', 'USINT', 'BYTE', 'INT', 'UINT', 'WORD', 'DINT', 'UDINT', 'DWORD',
  'LINT', 'ULINT', 'LWORD', 'REAL', 'LREAL', 'STRING', 'WSTRING', 'TIME', 'LTIME', 'DATE', 'TIME_OF_DAY', 'TOD', 'DATE_AND_TIME', 'DT']);
const plcType = (value: string) => {
  const root = String(value || '').trim().toUpperCase().replace(/\s*[\[(].*$/, '');
  return ({FLOAT: 'REAL', NCHAR: 'STRING', NVARCHAR: 'STRING', VARCHAR: 'STRING', CHAR: 'STRING', USINT: 'BYTE'} as Record<string, string>)[root] || root;
};
const numericWireTypes=new Set(['SINT','USINT','BYTE','INT','UINT','WORD','DINT','UDINT','DWORD','LINT','ULINT','LWORD','REAL','LREAL']);
const valueTypeMatches=(row:DataModelParameter,actual:string)=>row.dataTypeRole==='value'&&row.numericValueType?numericWireTypes.has(plcType(actual)):plcType(actual)===row.plcType;

export function dataModelReferenceLabel(reference: DataModelReference): string {
  let sheet = reference.sheet.replace(new RegExp('^' + reference.service + '[\\s_-]*', 'i'), '');
  const machine = dataModelMachineKey(reference.machine).split('').join('[\\s_-]*');
  if (machine) sheet = sheet.replace(new RegExp('^' + machine + '[\\s_-]*', 'i'), '');
  sheet = sheet.replace(/[_-]+/g, ' ').trim();
  return reference.service + (sheet ? ' ' + sheet.charAt(0).toUpperCase() + sheet.slice(1) : '');
}

/** Check loaded metadata immediately; no PLC request or invented name alias. */
export function evaluateDataModel(model: DataModel, items: MetadataItem[]): DataModelResult {
  const exact = new Map<string, MetadataItem[]>();
  const byName = new Map<string, MetadataItem[]>();
  const similar = new Map<string, MetadataItem[]>();
  const add = (index: Map<string, MetadataItem[]>, key: string, item: MetadataItem) =>
    index.set(key, [...(index.get(key) || []), item]);
  for (const item of items) {
    add(exact, groupKey(nameKey(item.parameter), item.groupCode), item);
    add(byName, nameKey(item.parameter), item);
    add(similar, groupKey(similarName(item.parameter), item.groupCode), item);
  }
  const rows = model.parameters.map(requirement => {
    const row: DataModelParameter = {...requirement, actual: [], reasonCodes: []};
    const names=[...new Set([row.name,...row.aliases||[]].map(nameKey))];
    if(row.ignoreNameSeparators){const compact=new Set(names.map(name=>name.replace(/[\s_]+/g,'')));for(const item of items){const name=nameKey(item.parameter);if(compact.has(name.replace(/[\s_]+/g,''))&&!names.includes(name))names.push(name)}}
    const named = names.flatMap(name=>byName.get(name)||[]);
    if (row.kind === 'server') return {...row, status: 'SKIPPED' as const, detail: 'Generated by server/host; no PLC parameter required.'};
    if (row.kind === 'formula') return {...row, actual: named, status: 'DERIVED' as const, detail: 'Calculated field; not required from the PLC.'};
    if (!row.name || !row.groupCodes.length || !row.plcType) return {...row, actual: named,
      status: 'UNRESOLVED' as const, detail: 'Reference is missing a name, datatype or group code.', reasonCodes: ['REFERENCE_INCOMPLETE']};
    if (row.referenceIssues?.length || !plcTypes.has(row.plcType)&&!(row.dataTypeRole==='value'&&row.numericValueType)) {
      const reasonCodes: string[] = []; const details: string[] = [];
      if (row.referenceIssues?.length) {
        reasonCodes.push('REFERENCE_CONFLICT'); details.push(...row.referenceIssues.map(issue => issue.detail));
      }
      if (!plcTypes.has(row.plcType)) {
        reasonCodes.push('REFERENCE_TYPE_UNSUPPORTED');
        details.push(`Database datatype ${row.dataType} does not define a supported PLC datatype. Specify the PLC wire datatype before checking it.`);
      }
      return {...row, actual: named.filter(item => row.groupCodes.includes(item.groupCode)),
        status: 'UNRESOLVED' as const, reasonCodes, detail: details.join(' ')};
    }
    const failures: string[] = []; const reasons: string[] = [];
    const actual = new Map<string, MetadataItem>();
    const capture = (values: MetadataItem[]) => values.forEach(value => actual.set(metadataRowKey(value), value));
    for (const group of row.groupCodes) {
      const matches = names.flatMap(name=>exact.get(groupKey(name,group))||[]);
      if (!matches.length) {
        if (named.length) {
          reasons.push('GROUP_DIFFERS'); capture(named);
          failures.push(row.name + ': required GC ' + group + '; found in GC ' + [...new Set(named.map(item => item.groupCode))].join(', ') + '.');
        } else {
          const near = similar.get(groupKey(similarName(row.name), group)) || [];
          reasons.push(near.length ? 'NAME_DIFFERS' : 'MISSING_PARAMETER'); capture(near);
          failures.push(row.name + ' is missing from GC ' + group + '.' + (near.length ? ' Name differs: ' + near.map(item => item.parameter).join(', ') + '.' : ''));
          for (const item of near) if (!valueTypeMatches(row,item.dataType)) {
            reasons.push('TYPE_DIFFERS');
            failures.push(`GC ${group}: reference ${row.name} expects ${row.plcType}; actual ${item.parameter} is ${item.dataType}.`);
          }
        }
        continue;
      }
      capture(matches);
      if (matches.length > 1) {
        reasons.push('DUPLICATE_PARAMETER'); failures.push('Duplicate parameter name in GC ' + group + ' (' + matches.length + ' rows, ignoring case).');
      }
      for (const match of matches) {
        if(nameKey(match.parameter)!==nameKey(row.name))reasons.push('NAME_MAPPED');
        if (!valueTypeMatches(row,match.dataType)) {
          reasons.push('TYPE_DIFFERS'); failures.push('GC ' + group + ': expected ' + row.plcType + ', actual ' + match.dataType + '.');
        }else if(plcType(match.dataType)!==row.plcType)reasons.push('NUMERIC_VALUE_MAPPED');
      }
    }
    return {...row, actual: [...actual.values()], reasonCodes: [...new Set(reasons)],
      status: (failures.length ? row.required === false ? 'OPTIONAL' : 'FAIL' : 'PASS') as DataModelStatus,
      detail: failures.join(' ') || (reasons.includes('NUMERIC_VALUE_MAPPED')?'Numeric database value is mapped to the PLC datatype declared in machine metadata. This checks value compatibility; it does not independently verify the wire datatype.':'Parameter name (ignoring case), group code and datatype match.')+(reasons.includes('NAME_MAPPED')?' Parameter name uses the configured department and Group Code alias.':'')};
  });
  const summary = {PASS: 0, FAIL: 0, OPTIONAL: 0, UNRESOLVED: 0, SKIPPED: 0, DERIVED: 0};
  rows.forEach(row => {if (row.status) summary[row.status]++;});
  return {modelId: model.id, status: summary.FAIL ? 'FAIL' : summary.UNRESOLVED ? 'REVIEW' : 'PASS', summary, rows,mappingRulesRevision:model.mappingRulesRevision};
}

export function checkedDataModels(items: MetadataItem[], models: DataModel[], check: DataModelCheck | null = null) {
  const selected = [...models].sort((a, b) => serviceOrder.indexOf(a.service) - serviceOrder.indexOf(b.service));
  const sameMachine = !models.length || models.some(model => dataModelMachineKey(model.machine) === dataModelMachineKey(check?.model.machine || ''));
  if (check && sameMachine && !selected.some(model => model.id === check.model.id)) selected.push(check.model);
  // Saved checks are historical evidence. The current table must always use
  // the current metadata and current reference definitions.
  return selected.map(model => ({model, result: evaluateDataModel(model, items)}));
}
function reference(row: DataModelParameter, model: DataModel): DataModelReference {
  return {...row, modelId: model.id, service: model.service, machine: model.machine,
    sourceRelativePath: model.sourceRelativePath, match: row.reasonCodes?.includes('NAME_DIFFERS') ? 'name-differs' : 'exact'};
}

export function buildDataModelRowReferences(items: MetadataItem[], models: DataModel[], check: DataModelCheck | null = null): Map<string, DataModelReference[]> {
  const result = new Map<string, DataModelReference[]>();
  const keys = new Set(items.map(metadataRowKey));
  for (const checked of checkedDataModels(items, models, check)) for (const row of checked.result.rows) {
    if (!row.name || row.kind === 'server') continue;
    for (const item of row.actual || []) {
      // A same-name parameter found in another GC is evidence for the
      // unavailable requirement, not a failure on this metadata row. Keep the
      // passing row attached to its own GC and list the missing GC separately.
      if (row.status === 'UNRESOLVED' && !row.reasonCodes?.some(code => code === 'REFERENCE_CONFLICT' || code === 'REFERENCE_TYPE_UNSUPPORTED')) continue;
      let displayRow = row;
      if (row.reasonCodes?.includes('GROUP_DIFFERS')) {
        if (!row.groupCodes.includes(item.groupCode)) continue;
        const sameGroup = (row.actual || []).filter(actual => actual.groupCode === item.groupCode);
        const duplicate = sameGroup.length > 1;
        const wrongType = sameGroup.some(actual => !valueTypeMatches(row,actual.dataType));
        const reasonCodes = [...(duplicate ? ['DUPLICATE_PARAMETER'] : []), ...(wrongType ? ['TYPE_DIFFERS'] : [])];
        const failed=reasonCodes.length>0;
        if(sameGroup.some(actual=>plcType(actual.dataType)!==row.plcType&&valueTypeMatches(row,actual.dataType)))reasonCodes.push('NUMERIC_VALUE_MAPPED');
        if(sameGroup.some(actual=>nameKey(actual.parameter)!==nameKey(row.name)))reasonCodes.push('NAME_MAPPED');
        displayRow = {...row, status: failed ? row.required === false ? 'OPTIONAL' : 'FAIL' : 'PASS', reasonCodes,
          detail: failed ? row.detail : `GC ${item.groupCode} has a compatible value mapping. Other required groups are checked separately. PLC decoding uses the machine metadata.`};
      }
      const key = metadataRowKey(item);
      if (!keys.has(key)) continue;
      const values = result.get(key) || [];
      if (!values.some(existing => existing.modelId === checked.model.id && existing.sheet === row.sheet && existing.row === row.row))
        result.set(key, [...values, reference(displayRow, checked.model)]);
    }
  }
  return result;
}

export function unavailableDataModelParameters(items: MetadataItem[], models: DataModel[], check: DataModelCheck | null = null): DataModelReference[] {
  return checkedDataModels(items, models, check).flatMap(({model, result}) => result.rows
    .filter(row => row.kind === 'plc' && (row.reasonCodes?.includes('MISSING_PARAMETER') || row.reasonCodes?.includes('GROUP_DIFFERS')))
    .map(row => reference(row, model)));
}

export function buildDataModelRowChecks(items: MetadataItem[], check: DataModelCheck | null, models: DataModel[] = []): Map<string, DataModelRowCheck> {
  const result = new Map<string, DataModelRowCheck>();
  for (const [key, rows] of buildDataModelRowReferences(items, models, check)) {
    const status = rows.reduce<DataModelStatus>((value, row) => row.status && priority[row.status] > priority[value] ? row.status : value, 'PASS');
    result.set(key, {status, requirements: rows});
  }
  return result;
}

export function dataModelResultLabel(row: DataModelParameter): string {
  if (row.status === 'PASS') return row.reasonCodes?.includes('NUMERIC_VALUE_MAPPED')?'Mapped numeric value':row.reasonCodes?.includes('NAME_MAPPED')?'Pass - configured name mapping':'Pass';
  if (row.status === 'DERIVED') return 'Calculated field';
  if (row.status === 'SKIPPED') return 'Server generated';
  if (row.status === 'UNRESOLVED') return row.reasonCodes?.includes('REFERENCE_CONFLICT') ? 'Reference conflict - review required' :
    row.reasonCodes?.includes('REFERENCE_TYPE_UNSUPPORTED') ? 'PLC datatype not defined' : 'Reference incomplete';
  const prefix = row.status === 'OPTIONAL' ? 'Optional' : 'Fail';
  if (row.reasonCodes?.includes('NAME_DIFFERS') && row.reasonCodes.includes('TYPE_DIFFERS')) return prefix + ' - name and datatype differ';
  if (row.reasonCodes?.includes('NAME_DIFFERS')) return prefix + ' - name differs';
  if (row.reasonCodes?.includes('GROUP_DIFFERS')) return prefix + ' - required group missing';
  if (row.reasonCodes?.includes('TYPE_DIFFERS')) return prefix + ' - datatype differs';
  if (row.reasonCodes?.includes('DUPLICATE_PARAMETER')) return prefix + ' - duplicate parameter';
  if (row.reasonCodes?.includes('MISSING_PARAMETER')) return prefix + ' - parameter missing';
  return row.status === 'OPTIONAL' ? 'Optional - unavailable' : row.status === 'FAIL' ? 'Fail' : 'Not checked';
}

/** Combine repeated worksheets and services without combining different outcomes. */
export function groupDataModelReferences(references: DataModelReference[]) {
  const groups = new Map<string, DataModelReference[]>();
  for (const row of references) {
    const key = JSON.stringify([nameKey(row.canonicalName||row.name), dataModelResultLabel(row), row.plcType, row.groupCodes]);
    groups.set(key, [...(groups.get(key) || []), row]);
  }
  return [...groups.values()].map(rows => ({name: rows[0].canonicalName||rows[0].name, label: dataModelResultLabel(rows[0]), status: rows[0].status,
    services: serviceOrder.filter(service => rows.some(row => row.service === service)), references: rows}));
}
