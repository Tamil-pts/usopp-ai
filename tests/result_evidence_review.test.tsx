import React from 'react';
import test from 'node:test';
import assert from 'node:assert/strict';
import {renderToStaticMarkup as render} from 'react-dom/server';
import {normalizeResult} from '../src/features/validation/normalizeResult';
import {packetRecommendation,ValidationFindings} from '../src/features/validation/ValidationFindings';
import {RuleLogicEvidence} from '../src/features/rules/RuleLogicEvidence';
import {ReadableFindings} from '../src/features/rules/ReadableFindings';
import {ResultReview} from '../src/shared/ResultReview';
import {actions,evidenceText,fieldStatus,orderedFindings,packetAction,packetFindings,resultStatus,ruleFindings} from '../src/shared/resultEvidence';

test('missing and unrecognized statuses never become passes',()=>{
 for(const status of [undefined,null,'','DRAFT','unexpected','Not Matching','Mismatching','ERROR']){
  assert.notEqual(normalizeResult({groups:[{groupCode:20,parameters:[{status}]}]}).offsetRows[0].status,'pass');
 }
 assert.equal(resultStatus(undefined),'unknown');
 assert.equal(resultStatus('NOT_REQUIRED'),'skipped');
 assert.equal(resultStatus('Not Found'),'not_found');
 assert.equal(resultStatus('Matching'),'pass');
});

test('reported field failures and warnings take precedence over a pass label',()=>{
 assert.equal(fieldStatus('PASS',[{severity:'ERROR'}]),'fail');
 assert.equal(fieldStatus('PASS',[{severity:'WARNING'}]),'warn');
 assert.equal(fieldStatus('PASS',[{severity:'unrecognized'}]),'warn');
 const r=normalizeResult({groups:[{groupCode:30,parameters:[{parameter:'Temp[1]',status:'PASS',issues:[{severity:'FAIL'}]}]}]});
 assert.equal(r.offsetRows[0].status,'fail');
});

test('dropdown mismatch wording cannot be read as matching',()=>{
 const statuses=['Matching','Mismatch','Mismatching','Not Matching','unknown'];
 const r=normalizeResult({dropdownValidation:{controls:statuses.map(status=>({status}))}});
 assert.deepEqual(r.dropdownRows.map((r:any)=>r.status),['pass','fail','fail','fail','warn']);
});

test('group failures remain visible when all payload fields pass; empty groups do not default to pass',()=>{
 const groups=[{groupCode:10,parameters:[]},{groupCode:20,overallStatus:'FAIL',parameters:[{status:'PASS'}]},
  {groupCode:30,overallStatus:'PASS',parameters:[{status:'FAIL'}]},{groupCode:40,overallStatus:'PASS',parameters:[{status:'WARNING'}]}];
 assert.deepEqual(normalizeResult({groups}).groupSummary.map((g:any)=>g.status),['warn','fail','fail','warn']);
});

test('engine sequence is retained without fabricating a protocol TAG_CODE or source line',()=>{
 const rows=normalizeResult({groups:[{groupCode:20,parameters:[{logicSequence:17,sequence:8,status:'PASS'},{sequence:42,status:'PASS'},{status:'PASS'}]}]}).offsetRows;
 assert.deepEqual(rows.map((r:any)=>r.tag),[17,42,'']);
 assert.deepEqual(rows.map((r:any)=>r.lineNumber),[0,0,0]);
});

test('missing expected offsets or field sizes are not filled from actual values or a made-up zero',()=>{
 const rows=normalizeResult({groups:[{groupCode:20,parameters:[{runningOffset:7,status:'PASS'},
  {runningOffset:0,expectedOffset:0,memcpySize:0,status:'WARNING'}]}]}).offsetRows;
 assert.equal(rows[0].expected,'');assert.equal(rows[0].size,'');
 assert.equal(rows[1].expected,0);assert.equal(rows[1].size,0);
});

test('a finding for a different source never borrows the field source line',()=>{
 const html=render(<ValidationFindings sourceFile="Packet.st" lineNumber={42} onSource={()=>{}}
  issues={[{severity:'FAIL',sourceFile:'Types.var',validationType:'Declaration check'}]}/>);
 assert.ok(html.includes('Types.var'));assert.ok(!html.includes('line 42'));assert.ok(!html.includes('Open source at line'));
});

test('packet branches with identical tags retain independent findings and source evidence',()=>{
 const input={groups:[{groupCode:20,packetVariants:[
  {condition:'Machine = 1',parameters:[{parameter:'speed',status:'PASS',sourceFile:'A.st',lineNumber:15}]},
  {condition:'Machine = 2',parameters:[{parameter:'speed',status:'PASS',sourceFile:'A.st',lineNumber:35}]},
 ]}],issues:[{parameter:'speed',groupCode:20,condition:'Machine = 2',sourceFile:'A.st',lineNumber:35,severity:'FAIL'}]};
 const before=JSON.stringify(input);const rows=normalizeResult(input).offsetRows;
 assert.deepEqual(rows.map((r:any)=>r.status),['pass','fail']);
 assert.deepEqual(rows.map((r:any)=>r.condition),['Machine = 1','Machine = 2']);
 assert.equal(JSON.stringify(input),before);
});

test('metadata source identity, zero limits and HMI lookup survive normalization',()=>{
 const r=normalizeResult({metadataSourceRows:[{sequence:1,groupCode:20,tagCode:653,min:0,max:0,parameter:'Intended workbook name',sheetName:'Sheet1',rowNumber:2}],
  metadataComparison:{results:[{logicSequence:99,groupCode:20,metadataSequence:1,metadataSheet:'Sheet1',metadataRow:2,status:'PASS'}]},
  dropdownValidation:{controls:[{groupCode:20,tagCode:653,logicComment:'Valve',status:'Matching',hmiPairs:[[0,'OFF'],[1,'ON']]}]}});
 assert.equal(r.metadataRows[0].meta,'Intended workbook name');assert.equal(r.metadataRows[0].metadataTagCode,653);
 assert.equal(r.metadataRows[0].metadataMin,0);assert.equal(r.metadataRows[0].metadataMax,0);
 assert.deepEqual(r.dropdownRows[0].hmi,['0 = OFF','1 = ON']);
});

test('recommendations prioritize the engine supplied fix and do not mandate cursor edits',()=>{
 assert.equal(packetAction({validationType:'Offset',suggestedFix:'Keep the fixed buffer address.'}),'Keep the fixed buffer address.');
 const recommendation=packetRecommendation({validationType:'Offset'});
 assert.ok(recommendation.includes('Fixed-address writes may not use nw_i'));
 assert.ok(!recommendation.includes('advance nw_i'));
 assert.ok(packetAction({validationType:'Copy Size'}).includes('declared PLC type'));
 assert.ok(packetAction({validationType:'Alarm Copy Size'}).includes('alarm array bounds'));
 assert.ok(packetAction({validationType:'Packet Size'}).includes('payload length'));
 assert.ok(packetAction({validationType:'Sheet2 Reference Missing'}).includes('do not invent'));
});

test('expected zero, actual false, objects and absent values display faithfully',()=>{
 assert.equal(evidenceText(0),'0');assert.equal(evidenceText(false),'false');
 assert.equal(evidenceText(null),'Not reported');assert.equal(evidenceText(undefined),'Not reported');
 const html=render(<ValidationFindings issues={[{severity:'ERROR',validationType:'Evidence check',expected:0,actual:false}]}/>);
 assert.ok(html.includes('>0<'));assert.ok(html.includes('>false<'));assert.ok(html.includes('validationFinding fail'));
 const structured=render(<ValidationFindings issues={[{expected:{bytes:0},actual:{bytes:4}}]}/>);
 assert.ok(structured.includes('&quot;bytes&quot;'));assert.ok(!structured.includes('[object Object]'));
});

test('multiple rule source locations are not replaced by an arbitrary first location',()=>{
 const rows=ruleFindings({results:[{id:'R1',status:'FAIL',structuredRequirements:[{file:'A.st',line:4},{file:'B.st',line:15}]},
  {id:'R2',status:'FAIL',evidence:[{file:'A.st',line:4}]}]});
 assert.equal(rows[0].file,'');assert.equal(rows[0].line,0);
 assert.equal(rows[1].file,'A.st');assert.equal(rows[1].line,4);
});

test('source line navigation requires a positive integer from the evidence',()=>{
 const rows=packetFindings({issues:[{sourceFile:'A.st',lineNumber:-1},{sourceFile:'B.st',lineNumber:2.5},{sourceFile:'C.st',lineNumber:'22'}]});
 assert.deepEqual(rows.map(r=>r.line),[0,0,22]);
 assert.equal((render(<ResultReview title="ByteMap" sourceKind="issues" rows={rows} onSource={()=>{}}/>).match(/Open reported source/g)||[]).length,1);
});

test('structured rules retain their engine recommendation, including string-valued older results',()=>{
 for(const recommendation of ['Inspect the configured T30 source.', ['Inspect the configured T30 source.']]){
  const html=render(<RuleLogicEvidence item={{status:'FAIL',actual:'HMI mismatch',structuredRequirements:[],recommendations:recommendation}}/>);
  assert.ok(html.includes('Recommended action'));assert.ok(html.includes('Inspect the configured T30 source.'));
 }
 assert.deepEqual(actions(undefined),[]);
});

test('warning properties are labeled warnings, not failed checks',()=>{
 const html=render(<ReadableFindings rows={[{properties:[{property:'Alias',status:'WARNING',expected:'A',actual:'B'}]}]}/>);
 assert.ok(html.includes('>Warning<'));assert.ok(!html.includes('>Failed<'));
});

test('action view excludes passed and optional rules and keeps unclassified results explicit',()=>{
 const rows=ruleFindings({results:[{id:'Passed marker',status:'PASS'},{id:'Optional marker',status:'NOT_REQUIRED'},
  {id:'Unknown marker'},{id:'Failed marker',status:'FAIL'}]});
 const html=render(<ResultReview title="LogicScan" sourceKind="checks" rows={rows}/>);
 assert.ok(html.includes('Failed marker'));assert.ok(html.includes('Unknown marker'));
 assert.ok(!html.includes('Passed marker'));assert.ok(!html.includes('Optional marker'));assert.ok(html.includes('Unclassified'));
 assert.ok(html.indexOf('Failed marker')<html.indexOf('Unknown marker'));
 assert.equal(rows[0].status,'pass');
});

test('no issue records are not presented as proof of a clean run',()=>{
 const html=render(<ResultReview title="ByteMap" sourceKind="issues" rows={[]}/>);
 assert.ok(html.includes('this alone does not establish a pass'));
});

test('priority sorting does not mutate results or combine distinct targets',()=>{
 const rows=ruleFindings({results:[{id:'R1',status:'PASS',hmiScope:{screenFolder:'C70'}},{id:'R1',status:'FAIL',hmiScope:{screenFolder:'T30'}}]});
 const before=JSON.stringify(rows);const sorted=orderedFindings(rows);
 assert.equal(sorted[0].scope,'R1 · T30');assert.equal(sorted[1].scope,'R1 · C70');assert.equal(JSON.stringify(rows),before);
});
