import {StructuredRuleSummary} from './StructuredRuleSummary';
import {isModuleSerialRule,ModuleSerialRuleSummary} from '../assist/ModuleSerialRule';
import '../assist/grouped-rule-wizard.css';
import {useEffect,useRef} from 'react';
import {X,Code,GitBranch,Layers} from 'lucide-react';
import {categoryFor} from './library';
import './rule-details.css';

const blocks=(rule:any):string[]=>Array.isArray(rule.logicAlternatives)&&rule.logicAlternatives.length?rule.logicAlternatives.filter((x:any)=>typeof x==='string'&&x.trim()):String(rule.exactLogic||'').split(/^\s*OR\s*$/mi).filter(x=>x.trim());
const files=(rule:any)=>Array.isArray(rule.sourceFiles)&&rule.sourceFiles.length?rule.sourceFiles.join(', '):rule.subroutine||rule.sourceFile||'Not configured';
function SourceBlock({source,label,alternative=false}:{source:string;label:string;alternative?:boolean}){
 return <div className={'ruleSourceBlock'+(alternative?' alternative':'')}><b>{label}</b><pre>{source}</pre></div>;
}
export function RuleDetails({rule,onClose}:{rule:any;onClose:()=>void}){
 const dialog=useRef<HTMLDialogElement>(null);
 useEffect(()=>{if(dialog.current&&!dialog.current.open)dialog.current.showModal()},[]);
 const logic=blocks(rule),cross=Array.isArray(rule.crossFunctionChecks)?rule.crossFunctionChecks:[];
 const metadata=[['Category',categoryFor(rule)],['Feature',rule.featureName||rule.featureId||rule.featureIds?.join(', ')||'Not linked'],['Subroutine / file',rule.checks?.map((c:any)=>c.file).filter(Boolean).join(', ')||files(rule)],['PLC tag & datatype',rule.checks?.map((c:any)=>c.declarationText).filter(Boolean).join('; ')||[rule.variable,(rule.allowedDatatypes||[]).join(' / ')].filter(Boolean).join(' : ')||'Not configured']];
 return <dialog ref={dialog} className="ruleDetailsDialog" aria-labelledby="ruleDetailsTitle" onClose={onClose} onClick={event=>{
  if(event.target!==event.currentTarget)return;
  const box=event.currentTarget.getBoundingClientRect();
  if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)dialog.current?.close();
 }}>
  <header><div><span className="eyebrow">{rule.id} · {rule.machineScope?.join(', ')||rule.machineDepartment||'All'} · {rule.enabled===false?'Draft':'Enabled'}</span><h2 id="ruleDetailsTitle">{rule.name||rule.id}</h2><p>{rule.description||rule.expected}</p></div><button className="btn" aria-label="Close rule details" onClick={()=>dialog.current?.close()}><X size={20}/></button></header>
  <div className="ruleDetailsContent">
   <dl className="ruleMetadataCards">{metadata.map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>
   {rule.referenceProfile&&<section><h3>Lapformer reference profile</h3><p><b>{rule.referenceProfile.project}</b> · {rule.referenceProfile.crossReferenceCount} cross references</p><p>{rule.referenceProfile.basis}</p><p>Source: {rule.referenceProfile.sourceFile}</p>{rule.referenceProfile.groupCodes?.length>0&&<p>Packet groups: {rule.referenceProfile.groupCodes.join(', ')}</p>}<p>These requirements describe the supplied reference project. Review its conditions and differences before enabling the rule for another project.</p></section>}
   {rule.referenceFindings?.length>0&&<details><summary>Reference findings to review ({rule.referenceFindings.length})</summary><ul>{rule.referenceFindings.map((finding:any,index:number)=><li key={index}><b>{finding.severity==='source_concern'?'Source concern: ':''}{finding.variable||finding.file}</b>: {finding.reason||finding.message}{finding.file&&<p className="muted">{finding.file}{finding.line?` · Reference line ${finding.line}`:''}</p>}{finding.proposedDestination&&<p>Review destination: <code>{finding.proposedDestination}</code></p>}</li>)}</ul></details>}
   {rule.functionCalls?.length>0&&<details><summary>Function calls and definitions ({rule.functionCalls.length})</summary><ul>{rule.functionCalls.map((call:any,index:number)=><li key={index}><b>{call.instance||call.name}</b> / {call.functionType||call.name} · Reference line {call.line}<p>{call.resolution}: {call.definitionFiles?.join(', ')||'No readable definition in this reference project'}</p></li>)}</ul></details>}
   {rule.expected&&rule.expected!==rule.description&&<section><h3>Expected result</h3><p>{rule.expected}</p></section>}
   {(rule.groupCode!==undefined||rule.groupCodeMode)&&<section><h3>Group Code scope</h3><p>{rule.groupCodeMode==='all'?'All Group Codes':rule.groupCodeMode==='exclude'?`All Group Codes except ${(rule.groupCodes||rule.excludeGroupCodes||[]).join(', ')}`:rule.groupCodeMode==='selected'?`Selected Group Codes: ${(rule.groupCodes||[]).join(', ')}`:`Group Code ${rule.groupCode}`}</p></section>}
   {isModuleSerialRule(rule)?<ModuleSerialRuleSummary rule={rule}/>:rule.kind==='structured_requirements'?<StructuredRuleSummary checks={rule.checks||[]}/>:<><section><h3><Code size={20}/> Primary exact logic</h3><p className="muted">File: {files(rule)}</p>{logic[0]?<SourceBlock source={logic[0]} label="Primary requirement"/>:<p>No exact source block configured. See the structured requirements below.</p>}</section>
   <section><h3><Layers size={20}/> Accepted alternatives ({Math.max(0,logic.length-1)})</h3><p>The primary block or any one complete alternative can satisfy the source check.</p>{logic.slice(1).map((source,index)=><SourceBlock key={index} source={source} label={`Accepted alternative ${index+1}`} alternative/>)}{logic.length<2&&<p className="ruleEmptyState">No additional accepted versions configured.</p>}</section>
   <section><h3><GitBranch size={20}/> Cross references ({cross.length})</h3><p>{rule.crossFunctionMode==='any'?'OR: any one complete cross reference can match.':'AND: every cross reference is required.'} Within each check, any one accepted block can match.</p>{cross.map((check:any,index:number)=><article className="ruleCrossDetail" key={index}><h4>{check.name||`Cross reference ${index+1}`}</h4><p>Files: {check.searchAllSubroutines?'All other supported project files':files(check)}</p>{check.groupCode!==undefined&&<p>Group Code: {check.groupCode}</p>}{blocks(check).map((source,i)=><SourceBlock key={i} source={source} label={i===0?'Required source':`Accepted alternative ${i}`} alternative={i>0}/>)}</article>)}{!cross.length&&<p className="ruleEmptyState">No cross references configured.</p>}</section>
   {(rule.hmiReferenceXml||rule.pagePrefix||rule.crossDomainHmiPages?.length)&&<section><h3>HMI mapping</h3>{rule.crossDomainHmiPages?.length>0&&<p>Pages: {rule.crossDomainHmiPages.join(', ')}</p>}{rule.pagePrefix&&<p>Page prefix: {rule.pagePrefix} · Label: {rule.label} · Control: {rule.controlNamePrefix}</p>}{rule.inputTouchpad&&<p>Touchpad: {rule.inputTouchpad}</p>}{rule.requireSameVariable&&<p>The PLC source and HMI datapoint must use the same variable, directly or through an approved assignment.</p>}{rule.hmiReferenceXml&&<SourceBlock source={rule.hmiReferenceXml} label="HMI reference XML"/>}</section>}
   </>}<details className="ruleAdvancedDetails"><summary>All configuration details</summary><pre>{JSON.stringify(rule,null,2)}</pre></details>
  </div>
  <footer><span>{rule.enabled===false?'Draft — review and test before enabling':'Enabled for validation'}</span><button className="btn primary" onClick={()=>dialog.current?.close()}>Close</button></footer>
 </dialog>;
}
