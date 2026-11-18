import React,{useState} from 'react';
import {createRoot} from 'react-dom/client';
import {ResultReview} from '../src/shared/ResultReview';
import {packetFindings,ruleFindings} from '../src/shared/resultEvidence';
import {PacketGroupTable} from '../src/features/validation/PacketGroupTable';
import {TablePage} from '../src/features/validation/ValidationViews';
import {normalizeResult} from '../src/features/validation/normalizeResult';
import {RuleLogicEvidence} from '../src/features/rules/RuleLogicEvidence';
import '../src/styles.css';
import '../src/features/validation/validation.css';

const ruleResult={results:[
 {id:'HMI-C70',name:'C70 target check',status:'PASS',hmiScope:{screenFolder:'C70'},expected:'Source mapped',actual:'Source mapped'},
 {id:'HMI-T30',name:'T30 target check',status:'FAIL',hmiScope:{screenFolder:'T30'},expected:'Local.Process.Setpoint',actual:'Local.GLOBAL.Setpoint',
  recommendations:['Inspect the T30 binding in its own active configuration.'],structuredRequirements:[{check:'Value binding',status:'FAIL',file:'T30/Process.page',line:22,expected:'Local.Process.Setpoint',actual:'Local.GLOBAL.Setpoint'}]},
 {id:'OPTIONAL',name:'Optional library',status:'NOT_REQUIRED',expected:'Optional library',actual:'Not required by this branch'},
 {id:'UNKNOWN',name:'Unclassified evidence',expected:0,actual:false},
]};

function Fixture({packet}:{packet:any}){
 const [tool,setTool]=useState('ByteMap'),[source,setSource]=useState(''),[offsets,setOffsets]=useState(false);
 const onSource=(file:string,line:number)=>setSource(`${file}:${line}`);
 return <main style={{padding:16,minWidth:0,maxWidth:1440,margin:'auto'}}>
  <nav className="actions"><button onClick={()=>setTool('ByteMap')}>ByteMap fixture</button><button onClick={()=>setTool('LogicScan')}>LogicScan fixture</button></nav>
  <output aria-label="Selected evidence source">{source}</output>
  <ResultReview key={tool} title={tool} sourceKind={tool==='ByteMap'?'issues':'checks'} rows={tool==='ByteMap'?packetFindings(packet):ruleFindings(ruleResult)} onSource={onSource}/>
  {tool==='ByteMap'?<><PacketGroupTable groups={packet.groups} issues={packet.issues} onOffsets={()=>setOffsets(true)} onSource={onSource}/>{offsets&&<TablePage title="ByteMap fields" desc="Engine result fixture" rows={normalizeResult(packet).offsetRows} type="offset" onSource={(r)=>onSource(r.sourceFile,r.lineNumber)}/>}</>:
   <RuleLogicEvidence item={ruleResult.results[1]} onSource={onSource}/>} 
 </main>;
}
fetch('./engine-result.json').then(r=>r.json()).then(packet=>createRoot(document.getElementById('root')!).render(<Fixture packet={packet}/>));
