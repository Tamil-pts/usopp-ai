import {actions} from '../../shared/resultEvidence';
import {ReadableFindings,FindingValue} from './ReadableFindings';
import {useState} from 'react';
import './rule-logic-evidence.css';

export function RuleLogicEvidence({item,onSource,onAcceptHmiActual}:{item:any;onSource?:(path:string,line:number,edit:boolean)=>void;onAcceptHmiActual?:(finding:any,attempt:any,property:any)=>void}){
 const [choice,setChoice]=useState(0);
 const comparisons=item.logicComparisons||[];
 const comparison=comparisons[choice]||comparisons[0];
 const crossChecks=item.crossFunctionLogicChecks||[];
 const structured=item.structuredRequirements;
 const recommendations=actions(item.recommendations);
 const nextActions=recommendations.length>0&&<aside className="findingRecommendation"><b>Recommended action</b><ul>{recommendations.map((action,index)=><li key={index}>{action}</li>)}</ul></aside>;
 if(structured)return <section className="structuredEvidence">{item.hmiScope&&<p><b>HMI scope:</b> {item.hmiScope.screenFolder?`Active screen folder Logical/${item.hmiScope.screenFolder}`:(item.hmiScope.screenFolders?.length?`Checked discovered HMI folder(s): ${item.hmiScope.screenFolders.join(', ')}`:'No HMI screen folder found')}{item.hmiScope.configurationMessage?` - ${item.hmiScope.configurationMessage}`:''}</p>}<p>{item.actual}</p>{nextActions}<ReadableFindings rows={structured} onSource={onSource} onAcceptHmiActual={onAcceptHmiActual}/></section>;
 return <section className="ruleLogicEvidence">
  <p><b>{item.status==='PASS'?'Validation evidence':'Why this did not pass'}</b>: {item.actual}</p>
  {nextActions}
  {comparisons.length>1&&<label>Expected alternative <select value={choice} onChange={e=>setChoice(Number(e.target.value))}>{comparisons.map((x:any,i:number)=><option value={i} key={i}>{i+1} {x.matched?'(matched)':''}</option>)}</select></label>}
  {comparison?<>
   <div className="logicCompareHeader"><span>{comparison.matched?'Configured logic found':comparison.approximate?'Nearest source section — review the differences':'Source section not found'}</span><span>{comparison.file}{comparison.file?` : ${comparison.line}–${comparison.endLine}`:''}</span>
    {comparison.file&&onSource&&<div className="actions"><button className="btn" onClick={()=>onSource(comparison.file,comparison.line,false)}>View source</button><button className="btn" onClick={()=>onSource(comparison.file,comparison.line,true)}>Edit source</button></div>}
   </div>
   <div className="logicCodePair"><section><b>Expected — configured source</b><pre>{comparison.expected}</pre></section><section><b>Actual — project source</b><pre>{comparison.actual||comparison.note||'No matching source available.'}</pre></section></div>
   {comparison.matched?<p className="logicMatchNote">This logic matches. Other configured checks, such as datatype or HMI binding, can still fail.</p>:<div className="logicDifferences"><b>Differences from expected logic</b><p>Red: expected code missing or changed. Green: actual code added or changed. The nearest section is a preview, not an approved replacement.</p>{(comparison.differences||[]).map((diff:any,i:number)=><div className="logicCodePair" key={i}><section className="logicRemoved"><small>Expected line {diff.expectedLine}</small><pre>{diff.expected||'(no corresponding expected line)'}</pre></section><section className="logicAdded"><small>Source line {diff.actualLine}</small><pre>{diff.actual||'(missing in source)'}</pre></section></div>)}</div>}
   <small>{item.logicConfiguration}</small>
  </>:<p>{item.logicConfiguration||'No expected source snapshot is available for this older result. Rerun the configured rule.'} Use Assist / Teach to configure missing expected logic.</p>}
  {crossChecks.length>0&&<section className="crossFunctionEvidence"><h4>Cross-function logic checks</h4>{crossChecks.map((check:any,index:number)=><details key={`${check.crossFunctionIndex??index}-${check.file||''}`} open={check.status!=='PASS'}><summary><b>{check.status||'CHECK'}</b> · {check.name||check.check||`Subroutine check ${index+1}`}{check.file?` — ${check.file}${check.line?` : ${check.line}`:''}`:''}</summary><p>{check.actual}</p>{check.expected&&<FindingValue value={check.expected}/>}{check.matchedLogic&&<><small>Matched source logic</small><pre>{check.matchedLogic}</pre></>}{check.searchedFiles?.length>0&&<p>Files searched: {check.searchedFiles.join(', ')}</p>}{check.file&&onSource&&<button className="btn" onClick={()=>onSource(check.file,check.line||1,false)}>View source</button>}</details>)}</section>}
  <details><summary>All findings and source files</summary><ReadableFindings rows={item.evidence||[]} onSource={onSource}/>{onSource&&(item.sourceFiles||[]).map((path:string)=><button className="btn" key={path} onClick={()=>onSource(path,1,false)}>{path}</button>)}</details>
 </section>;
}

