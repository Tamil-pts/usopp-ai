import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import type {MetadataItem} from '../nami/src/types';
import {buildDataModelRowReferences, checkedDataModels, evaluateDataModel, metadataRowKey,
  unavailableDataModelParameters, type DataModel} from '../nami/src/utils/dataModelChecks';

const metadata = (parameter = 'Delivery Speed', dataType = 'REAL', groupCode = 40): MetadataItem => ({
  sNo: 1, screenName: 'Current Shift Report', machineVariants: '', parameter, units: '', min: null, max: null,
  tagCode: 56, groupCode, offset: 64, fromVersion: '', toVersion: '', dataType, offsetFactor: 0,
  scaleFactor: 1, isVisible: true, isWritable: false,
});
const model = (machine = 'DRAWFRAMEFINISHER'): DataModel => ({
  id: machine, machine, source: machine + '.json', service: 'PMS', warnings: [],
  parameters: [{name: 'Delivery Speed', dataType: 'FLOAT', plcType: 'REAL', groupCodes: [40],
    kind: 'plc', formula: '', source: machine + '.json', sheet: 'live', row: 1, required: true}],
});
const catalog: DataModel[] = JSON.parse(readFileSync(new URL('../knowledge/data_models/catalog.json', import.meta.url), 'utf8')).models;

test('letter case is accepted and real wire datatype mismatches still fail', () => {
  assert.equal(evaluateDataModel(model(), [metadata('delivery speed')]).rows[0].status, 'PASS');
  const result = evaluateDataModel(model(), [metadata('Delivery Speed', 'INT')]);
  assert.equal(result.rows[0].status, 'FAIL');
  assert.deepEqual(result.rows[0].reasonCodes, ['TYPE_DIFFERS']);
});

test('Finisher screenshot keeps conflicting JSON and Excel evidence without failing the PLC REAL row', () => {
  const cms = catalog.find(value => value.machine === 'DRAWFRAMEFINISHER' && value.service === 'CMS')!;
  const item = metadata('Production in kg');
  const references = buildDataModelRowReferences([item], [cms]).get(metadataRowKey(item))!;
  assert.equal(references.length, 1);
  assert.equal(references[0].status, 'UNRESOLVED');
  assert.equal(references[0].dataType, 'TIMESTAMP');
  assert.equal(references[0].suggestedPlcType, 'REAL');
  assert.deepEqual(references[0].excelReferences?.map(value => value.row), [54, 98, 121]);
  assert.ok(references[0].excelReferences?.every(value => value.dataType === 'FLOAT'));
  const missing = unavailableDataModelParameters([item], [cms]).filter(value => value.name === 'Production in kg');
  assert.equal(missing.length, 1);
  assert.deepEqual(missing[0].groupCodes, [50]);
});

test('current metadata does not reuse a saved passing result', () => {
  const reference = model();
  const saved = {model: reference, result: evaluateDataModel(reference, [metadata()]), validatedAt: '2026-10-14T12:00:00Z'};
  const result = checkedDataModels([metadata('Delivery Speed', 'INT')], [reference], saved);
  assert.equal(result[0].result.rows[0].status, 'FAIL');
  assert.equal(saved.result.rows[0].status, 'PASS');
});

test('a saved check for a different department cannot join current department references', () => {
  const other = model('CARDING');
  const saved = {model: other, result: evaluateDataModel(other, [metadata()]), validatedAt: '2026-10-14T12:00:00Z'};
  assert.equal(checkedDataModels([metadata()], [model()], saved).length, 1);
});

test('missing other groups remain separate from the passing current group', () => {
  const reference = model(); reference.parameters[0].groupCodes = [40, 50];
  const item = metadata();
  assert.equal(evaluateDataModel(reference, [item]).rows[0].status, 'FAIL');
  const rows = buildDataModelRowReferences([item], [reference]).get(metadataRowKey(item))!;
  assert.equal(rows[0].status, 'PASS');
  assert.deepEqual(rows[0].reasonCodes, []);
  assert.equal(unavailableDataModelParameters([item], [reference]).length, 1);
});

test('unsupported database types in archived models need a wire definition', () => {
  const reference = model(); reference.parameters[0].plcType = reference.parameters[0].dataType = 'TIMESTAMP';
  const row = evaluateDataModel(reference, [metadata()]).rows[0];
  assert.equal(row.status, 'UNRESOLVED');
  assert.deepEqual(row.reasonCodes, ['REFERENCE_TYPE_UNSUPPORTED']);
});

test('different wording is not silently treated as a case-only name match', () => {
  const finisher = catalog.filter(value => value.machine === 'DRAWFRAMEFINISHER');
  const items = ['Powerfail_Time_Minute', 'Delivery Hanks', 'Feed Roller Stoppage'].map(value => metadata(value));
  const references = buildDataModelRowReferences(items, finisher);
  assert.ok(items.every(item => !(references.get(metadataRowKey(item)) || []).some(value => value.status === 'PASS')));
});
