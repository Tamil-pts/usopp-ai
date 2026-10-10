import React from 'react';
import assert from 'node:assert/strict';
import {renderToStaticMarkup} from 'react-dom/server';
import {ReadableFindings} from '../src/features/rules/ReadableFindings';
import {RuleLogicEvidence} from '../src/features/rules/RuleLogicEvidence';

const findings=[
 {check:'Lot name copy',status:'PASS',file:'Logical/SpinConnect/Cyclic.st',line:437,groupCode:40,actual:'memcpy(ADR(nw_snd_buffer[nw_i]),ADR(PMS_LotName),50);\nnw_i := nw_i + 50;',expected:['memcpy(ADR(nw_snd_buffer[nw_i]),ADR(PMS_LotName),50);\nnw_i := nw_i + 50;']},
 {check:'HMI input',status:'FAIL',file:'Logical/HMI/Pages/Process.page',attempts:[{control:'String_1',alternative:2,status:'FAIL',properties:[{property:'ValueDatapoint',expected:'Local.SpinConnect.PMS_LotName',actual:'Local.GLOBAL.PMS_LotName',status:'FAIL'}]}],actual:'Long aggregated raw details that repeat the property table'},
 {check:'Older file',status:'NOT_REQUIRED',notRequiredReason:'Another complete OR cross reference passed; this alternative is not required.',actual:'File not found'},
];
const markup=renderToStaticMarkup(<ReadableFindings rows={findings}/>);
assert(markup.includes('Matched source / result'));
assert(markup.includes('line 437'));
assert(markup.includes('Group 40'));
assert(markup.includes('Property checked'));
assert(markup.includes('Recommended action'));
assert(markup.includes('Alternative not required'));
assert(!markup.includes('Long aggregated raw details'));
assert(!markup.includes('&quot;check&quot;:'));
assert(!markup.includes('\\n'));
const structured=renderToStaticMarkup(<RuleLogicEvidence item={{status:'FAIL',actual:'2 required checks: 1 passed, 1 failed.',structuredRequirements:findings}}/>);
assert(structured.includes('Lot name copy'));
assert(structured.includes('Expected'));
assert(structured.includes('Actual'));
console.log('Readable findings and RuleLogicEvidence render correctly without JSON or escaped source lines.');
