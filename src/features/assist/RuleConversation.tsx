import {GroupedRuleWizard} from './GroupedRuleWizard';
import {isModuleSerialRule,ModuleSerialRuleSummary,completeModuleSerialRule} from './ModuleSerialRule';
import {StructuredRuleSummary} from '../rules/StructuredRuleSummary';
import {useEffect,useRef,useState} from 'react';
import {ArrowRight, Bot, GitBranch, Plus, Send, Trash2, Upload} from 'lucide-react';
import {apiJson,CATEGORIES,DEPARTMENTS,useRuleLibrary} from '../rules/library';
import {categoryGuides,guideFor} from './ruleCategoryGuide';
import './rule-conversation.css';
import {RuleLogicEvidence} from '../rules/RuleLogicEvidence';
import {validateEngineeringRules} from '../rules/api';

const LOT_LOGIC=`memcpy(ADR(nw_snd_buffer[nw_i]),ADR(PMS_Lotname_Shift[0]),20);
stringlength:= strlen(ADR(PMS_Lotname_Shift[0]));
memset(ADR(nw_snd_buffer[nw_i+stringlength]),0,50-stringlength);
nw_i := nw_i + 50;`;
const HMI_XML=`<TextLayer LanguageId="en"><Text ID="1" Value="LOT NAME"/></TextLayer>
<Control ClassId="0x0000100B" Name="String_1">
  <Property Name="Input" Value="True"/>
  <Property Name="InputTouchpad" Value="Source[local].TouchPad[AlphaPadQVGA]"/>
  <Property Name="ValueDatapoint" Value="Source[global].Variable[Local.SpinConnect.PMS_Lot_Name_Temp]"/>
</Control>`;
type Step={key:string;question:string;options?:string[];example?:string;optional?:boolean};
type Turn={key:string;question:string;answer:string};
type LogicExtensionAction={type:'cross';sourceFile:string;logic:string}|{type:'accepted';logic:string}|{type:'skip';stepKey:string};
const splitLegacyLogic=(value:string)=>value.split(/^\s*OR\s*$/mi).map(part=>part.trim()).filter(Boolean);
const parseArrayAnswer=(value:any):any[]=>{
 if(Array.isArray(value))return value;
 if(typeof value!=='string'||!value.trim())return [];
 try{const parsed=JSON.parse(value);return Array.isArray(parsed)?parsed:[]}catch{return []}
};
const logicBlocks=(rule:any):string[]=>{
 const configured=Array.isArray(rule?.logicAlternatives)?rule.logicAlternatives.filter((value:any)=>typeof value==='string'):[];
 return configured.length?configured:(splitLegacyLogic(String(rule?.exactLogic||'' )).length?splitLegacyLogic(String(rule?.exactLogic||'')):['']);
};
const crossLogicBlocks=(check:any):string[]=>{
 const configured=Array.isArray(check?.logicAlternatives)?check.logicAlternatives.filter((value:any)=>typeof value==='string'):[];
 return configured.length?configured:(splitLegacyLogic(String(check?.exactLogic||'')).length?splitLegacyLogic(String(check?.exactLogic||'')):['']);
};
const supportsAcceptedLogic=(rule:any)=>!!rule;
export function stepsFor(answers:Record<string,any>,departments:string[]):Step[]{
 const lot=answers.template==='Lot Name: PLC + HMI';
 const plcHmi=answers.category==='PLC logic + HMI';
 const guide=guideFor(answers.category);
 const hmi=String(answers.category||'').startsWith('HMI');
 const declaration=answers.category==='Declaration';
 const tagCheck=['Logic / declaration','PLC logic + HMI'].includes(answers.category);
 const packet=answers.category==='Group code wise parameter check'||lot;
 const groupWise=answers.category==='Group code wise parameter check';
 const actions:LogicExtensionAction[]=Array.isArray(answers.logicExtensionActions)?answers.logicExtensionActions:[];
 const pending=answers.pendingLogicExtension||'';
 const choice=(index:number):Step=>({key:`logicExtensionChoice_${index}`,question:'Would you like to add another accepted version or check a related file? You can add as many as you need.',options:['Cross-function analysis','Accept logic','Skip']});
 const extensionSteps:Step[]=[];
 const crossFileStep=(index:number):Step=>({key:`crossFunctionFile_${index}`,question:'Which related file should we check? This can be another PLC subroutine, an HMI file or a configuration file.',example:hmi?'MachineStates.txtgrp':'mms_Pms.st'});
 const crossLogicStep=(index:number):Step=>({key:`crossFunctionLogic_${index}`,question:'What must be present in that related file? Paste the complete logic or XML block. This check must pass as well as the main check.',example:hmi?'<Text ID="1" Value="Running"/>':'PMS_Lotname_Shift[0] := PMS_Lot_Name_Temp;'});
 const acceptedLogicStep=(index:number):Step=>({key:`acceptedLogic_${index}`,question:'What other version is acceptable in the main file? Paste one complete block. Either the original or this version can pass.',example:guide.example});
 const addActionSteps=(action:LogicExtensionAction,index:number)=>{
  if(action.type==='skip'){
   if(action.stepKey==='crossFunctionFile')extensionSteps.push(crossFileStep(index));
   else if(action.stepKey==='crossFunctionLogic'){extensionSteps.push(crossFileStep(index),crossLogicStep(index))}
   else if(action.stepKey==='acceptedLogic')extensionSteps.push(acceptedLogicStep(index));
   return;
  }
  if(action.type==='cross'){
   extensionSteps.push(crossFileStep(index),crossLogicStep(index));
  }else extensionSteps.push(acceptedLogicStep(index));
 };
 actions.forEach((action,index)=>{extensionSteps.push(choice(index));addActionSteps(action,index)});
 extensionSteps.push(choice(actions.length));
 if(pending==='cross'){
  extensionSteps.push(crossFileStep(actions.length),crossLogicStep(actions.length));
 }else if(pending==='accepted')extensionSteps.push(acceptedLogicStep(actions.length));
 const beforeLogic:Step[]=[
  {key:'category',question:'What would you like to check?',options:CATEGORIES},
  ...(plcHmi?[{key:'template',question:'Which PLC + HMI check should this rule validate?',options:['Lot Name: PLC + HMI','Custom PLC + HMI']}]:[]),
  {key:'featureName',question:'Which feature does this rule belong to?',example:'Spin Connect'},
  {key:'name',question:'What would you like to call this rule?',example:guide.name},
  {key:'description',question:'What should this rule verify? Describe it in one sentence.',example:guide.summary},
  {key:'machineDepartment',question:'Which machines should use this rule? Choose All if it applies to every department.',options:departments},
  {key:'machineModel',question:'Is this for a particular machine model? Choose All or enter the model name.',options:['All'],optional:true},
  {key:'subroutine',question:declaration?'Which declaration file should we check?':hmi?'Which HMI file should we check?':'Which file should we check first?',example:guide.file},
  {key:'exactLogic',question:guide.question,example:lot?LOT_LOGIC:guide.example},
 ];
 const afterLogic:Step[]=[
  ...(groupWise?[
   {key:'groupCodeMode',question:'Which Group Codes should be checked?',options:['All group codes','All group codes except','Selected group codes']},
   ...(['All group codes except','Selected group codes'].includes(answers.groupCodeMode)?[{key:'groupCodes',question:answers.groupCodeMode==='All group codes except'?'Which Group Codes should be excluded?':'Which Group Codes should be checked? Enter comma-separated codes, for example 10, 20, 30.',example:'10, 20, 30'}]:[]),
  ]:packet?[
   {key:'groupCode',question:'Which Group Codes should contain this logic? Enter one or more codes separated by commas.',options:lot?['140']:['All','20','140'],optional:!lot},
  ]:[]),
  ...(tagCheck?[{key:'variable',question:lot?'Which PLC variable should match between the packet logic and HMI datapoint?':'Which PLC tag or variable should the rule check? Skip if the rule does not use one.',optional:true},
  {key:'datatype',question:'What declared datatype is required for that PLC tag? Enter accepted alternatives separated by commas, or skip if no declaration check is needed.',options:['STRING','DINT','REAL','DINT, REAL','UINT','BOOL'],optional:true}]:[]),
  ...(lot?[
   {key:'pagePrefix',question:'What is the HMI page filename prefix? Process matches ProcessSetting.pages and Process1_0.pages.',options:['Process']},
   {key:'label',question:'Which label must appear on the HMI page?',options:['LOT NAME']},
   {key:'controlPrefix',question:'What is the input control name prefix? String allows String_1 and String_2; IDs and ClassId can vary.',options:['String']},
   {key:'touchpad',question:'Which input touchpad should the String control use?',options:['Source[local].TouchPad[AlphaPadQVGA]']},
   {key:'hmiXml',question:'Which HMI control properties should match? Enter Name = Value lines. Start another Name line to add another required control. Blank values are not checked; <None> requires an unassigned property.',example:'Name = String\nName matching = Prefix\nInputTouchpad = AlphaPadQVGA\nValueDatapoint = Local.SpinConnect.PMS_LotName',optional:true},
   {key:'sameVariable',question:'The matched PLC memcpy source and the HMI ValueDatapoint must resolve to the same variable. Confirm this requirement.',options:['Yes, require the same PLC variable']},
  ]:[]),
  ...(plcHmi&&!lot?[
   {key:'hmiPages',question:'Which HMI screen should use this PLC variable? Enter the page filename or path.',example:'Process.pages',optional:true},
  ]:[]),
  {key:'expected',question:'Add any additional validation detail or expected result for the report. You can skip if the description already explains it.',optional:true},
 ];
 return [...beforeLogic,...extensionSteps,...(answers.logicExtensionsSkipped?afterLogic:[])];
}

export function RuleConversation({revision,onSaved,draft,onDraftConsumed,projectPath,projectFiles,projectName,departments=DEPARTMENTS}:{revision:number;onSaved:()=>void;draft:any;onDraftConsumed:()=>void;projectPath:string;projectFiles:File[];projectName:string;departments?:string[]}){
 const [answers,setAnswers]=useState<Record<string,any>>({});const [turns,setTurns]=useState<Turn[]>([]);const [input,setInput]=useState('');
 const [config,setConfig]=useState<any>(null);const [busy,setBusy]=useState(false);const [message,setMessage]=useState('');const [reviewed,setReviewed]=useState(false);const [jsonText,setJsonText]=useState('');const [testResults,setTestResults]=useState<any>(null);const [testReviewed,setTestReviewed]=useState(false);const [selectedSavedRule,setSelectedSavedRule]=useState('');
 const [wizardSeed,setWizardSeed]=useState<any>(undefined);const [wizardKey,setWizardKey]=useState(0);
 const testPanel=useRef<HTMLElement>(null);
 const [testedSignature,setTestedSignature]=useState('');
 const [savedSnapshot,setSavedSnapshot]=useState('');
 const persistedSignature=(value:any)=>JSON.stringify(value.rules||[]);
 let isSaved=false;try{isSaved=!!savedSnapshot&&savedSnapshot===persistedSignature(JSON.parse(jsonText))}catch{/* incomplete JSON is an unsaved edit */}
 const isEnabled=isSaved&&config?.rules?.every((rule:any)=>rule.enabled===true);
 const guide=guideFor(answers.category);
 const reviewSignature=(value:any)=>JSON.stringify((value.rules||[]).map(({enabled,reviewStatus,...rule}:any)=>rule));
 const projectIdentity=projectPath||projectFiles;
 const currentProject=useRef(projectIdentity);currentProject.current=projectIdentity;
 useEffect(()=>{setTestResults(null);setTestReviewed(false);setTestedSignature('')},[projectIdentity,projectName]);
 const {rules,reload}=useRuleLibrary(revision);const end=useRef<HTMLDivElement>(null);
 const steps=stepsFor(answers,departments);const step=steps[turns.length];
 const showConfig=(value:any,saved=false)=>{value={...value,rules:(value.rules||[]).map((rule:any)=>isModuleSerialRule(rule)?completeModuleSerialRule(rule):rule)};setSavedSnapshot(saved?persistedSignature(value):'');setTestedSignature('');setConfig(value);setJsonText(JSON.stringify(value,null,2));setReviewed(false);setTestResults(null);setTestReviewed(false)};
 const openSavedRule=(id:string)=>{
  setSelectedSavedRule(id);setAnswers({});setTurns([]);setInput('');setMessage('');
  const rule=rules.find(item=>item.id===id);
  if(rule)showConfig({version:'4.60.3',rules:[rule]},true);else setConfig(null);
 };
 const deleteSavedRule=async()=>{
  const rule=rules.find(item=>item.id===selectedSavedRule);if(!rule)return;
  if(!window.confirm(`Delete ${rule.id} — ${rule.name||rule.id} from the rule library and remove its feature/pipeline links?`))return;
  setBusy(true);setMessage('');
  try{await apiJson(`/api/rules/library/${encodeURIComponent(rule.id)}`,undefined,'DELETE');setSelectedSavedRule('');setConfig(null);setMessage(`Deleted ${rule.id}. Its saved feature and pipeline selections were removed.`);await reload();onSaved()}
  catch(error:any){setMessage(error.message||'Could not delete the rule.')}
  finally{setBusy(false)}
 };
 const configureRule=(rule:any)=>{setWizardSeed(rule);setWizardKey(key=>key+1);setConfig(null);setMessage('');setReviewed(false);setTestResults(null);setTestReviewed(false)};
 const updateRule=(index:number,patch:Record<string,any>)=>{
  try{const next=JSON.parse(jsonText);next.rules[index]={...next.rules[index],...patch};setConfig(next);setJsonText(JSON.stringify(next,null,2));setMessage('');setReviewed(false);setTestResults(null);setTestReviewed(false)}catch{setMessage('Correct the configuration JSON first.')}
 };
 const acceptHmiActual=(result:any,finding:any,attempt:any,property:any)=>{
  try{
   const next=JSON.parse(jsonText);const ruleIndex=(next.rules||[]).findIndex((rule:any)=>rule.id===result.id);if(ruleIndex<0)throw new Error('The tested rule is no longer in this draft.');
   const requirement=String(finding.check||'').match(/Requirement\s+(\d+)/i);if(!requirement)throw new Error('The HMI requirement could not be identified.');
   let check=next.rules[ruleIndex]?.checks?.[Number(requirement[1])-1];if(!check)throw new Error('The HMI requirement could not be found in the current configuration.');
   for(const match of String(finding.check||'').matchAll(/cross reference\s+(\d+)/gi)){check=check.crossChecks?.[Number(match[1])-1];if(!check)throw new Error('The HMI cross reference could not be found.');}
   if(check.type!=='hmi')throw new Error('This finding is not an HMI property check.');
   const configuration=Number(finding.acceptedConfiguration||attempt.alternative||1);const source=configuration===1?{file:check.file,variant:check.variants?.[0]}:check.acceptedHmiAlternatives?.[configuration-2];
   if(!source?.variant)throw new Error('The matched HMI configuration could not be found.');
   const variant=structuredClone(source.variant);variant.properties={...(variant.properties||{})};const raw=String(property.actual??'').trim();const wrapped=raw.match(/^Source\[[^\]]+\]\.\w+\[(.*)\]$/s);variant.properties[property.property]=wrapped?wrapped[1]:raw;
   if(attempt.control&&attempt.control!=='No matching object'){variant.name=attempt.control;variant.nameMatch='exact'}
   check.acceptedHmiAlternatives=[...(check.acceptedHmiAlternatives||[]),{file:source.file||finding.file||check.file,variant}];
   setConfig(next);setJsonText(JSON.stringify(next,null,2));setSavedSnapshot('');setTestedSignature('');setTestResults(null);setTestReviewed(false);setReviewed(false);setMessage(`Added an accepted HMI configuration for ${property.property} = ${variant.properties[property.property]}. Review it, then run the draft test again.`);
  }catch(error:any){setMessage(error.message||'Could not add the actual HMI value.')}
 };
 const updateLogicBlock=(rule:any,index:number,blockIndex:number,value:string)=>{const alternatives=logicBlocks(rule);alternatives[blockIndex]=value;updateRule(index,{logicAlternatives:alternatives,exactLogic:alternatives.find(item=>item.trim())||'',needsLogicConfiguration:!alternatives.some(item=>item.trim())||!rule.subroutine})};
 const addLogicBlock=(rule:any,index:number)=>{const alternatives=[...logicBlocks(rule),''];updateRule(index,{logicAlternatives:alternatives,exactLogic:alternatives.find(item=>item.trim())||'',needsLogicConfiguration:!alternatives.some(item=>item.trim())||!rule.subroutine})};
 const removeLogicBlock=(rule:any,index:number,blockIndex:number)=>{const alternatives=logicBlocks(rule);alternatives.splice(blockIndex,1);if(!alternatives.length)alternatives.push('');updateRule(index,{logicAlternatives:alternatives,exactLogic:alternatives.find(item=>item.trim())||'',needsLogicConfiguration:!alternatives.some(item=>item.trim())})};
 const updateCrossCheck=(rule:any,index:number,checkIndex:number,patch:Record<string,any>)=>{const checks=Array.isArray(rule.crossFunctionChecks)?[...rule.crossFunctionChecks]:[];checks[checkIndex]={...(checks[checkIndex]||{}),...patch};updateRule(index,{crossFunctionChecks:checks})};
 const updateCrossBlock=(rule:any,index:number,checkIndex:number,blockIndex:number,value:string)=>{const checks=Array.isArray(rule.crossFunctionChecks)?[...rule.crossFunctionChecks]:[];const check={...(checks[checkIndex]||{})};const alternatives=crossLogicBlocks(check);alternatives[blockIndex]=value;check.logicAlternatives=alternatives;check.exactLogic=alternatives.find(item=>item.trim())||'';checks[checkIndex]=check;updateRule(index,{crossFunctionChecks:checks})};
 const addCrossBlock=(rule:any,index:number,checkIndex:number)=>{const checks=Array.isArray(rule.crossFunctionChecks)?[...rule.crossFunctionChecks]:[];const check={...(checks[checkIndex]||{})};const alternatives=[...crossLogicBlocks(check),''];check.logicAlternatives=alternatives;checks[checkIndex]=check;updateRule(index,{crossFunctionChecks:checks})};
 const removeCrossCheck=(rule:any,index:number,checkIndex:number)=>{const checks=Array.isArray(rule.crossFunctionChecks)?[...rule.crossFunctionChecks]:[];checks.splice(checkIndex,1);updateRule(index,{crossFunctionChecks:checks})};
 const addCrossCheck=(rule:any,index:number)=>{const checks=Array.isArray(rule.crossFunctionChecks)?[...rule.crossFunctionChecks]:[];checks.push({name:`Cross-function check ${checks.length+1}`,searchAllSubroutines:true,sourceFiles:[],logicAlternatives:[''],exactLogic:''});updateRule(index,{crossFunctionChecks:checks})};

 useEffect(()=>{if(draft){showConfig(draft);onDraftConsumed()}},[draft,onDraftConsumed]);
 useEffect(()=>{end.current?.scrollIntoView({block:'nearest'})},[turns.length,config]);
 const answer=(value:string,skipQuestion=false)=>{
  if(!step||busy)return;const isExtensionChoice=step.key.startsWith('logicExtensionChoice_');let skipped=skipQuestion||(!isExtensionChoice&&value.trim().toLowerCase()==='skip');let text=skipped?'':value.trim();if(!text&&!step.optional&&!skipped)return;
  if(step.key==='category'&&!skipped){const category=CATEGORIES.find(value=>value.toLowerCase()===text.toLowerCase());if(!category){setMessage('Choose one of the categories above, or skip to save an incomplete draft.');return}text=category}
  if(step.key==='template'&&!skipped){if(/lot/i.test(text))text='Lot Name: PLC + HMI';else if(/custom/i.test(text))text='Custom PLC + HMI';else{setMessage('Choose a PLC + HMI rule type, or skip this question.');return}}
  if(step.key==='sameVariable'&&!skipped&&!/^(yes|confirm)/i.test(text)){setMessage('This rule requires the PLC and HMI variable to match. Confirm with Yes or skip this question.');return}
  if(step.key==='groupCode'&&!skipped&&text&&!/^\d+(?:\s*,\s*\d+)*$|^all$/i.test(text)){setMessage('Enter Group Codes such as 140, 40, 50, or All. You can also skip this question.');return}
  if(step.key==='groupCodes'&&!skipped&&text&&!/^\d+(?:\s*,\s*\d+)*$/.test(text)){setMessage('Enter numeric Group Codes separated by commas, such as 10, 20, 30, or skip this question.');return}
  const nextAnswers={...answers,[step.key]:text};
  if(skipped&&step.key==='category'){nextAnswers.category='Logic';nextAnswers.categorySkipped=true}
  if(step.key.startsWith('logicExtensionChoice_')){
   if(text==='Cross-function analysis')nextAnswers.pendingLogicExtension='cross';
   else if(text==='Accept logic')nextAnswers.pendingLogicExtension='accepted';
   else if(text==='Skip'){nextAnswers.pendingLogicExtension='';nextAnswers.logicExtensionsSkipped=true}
   else{setMessage('Choose Cross-function analysis, Accept logic or Skip.');return}
  }else if(step.key.startsWith('crossFunctionFile_')||step.key.startsWith('crossFunctionLogic_')||step.key.startsWith('acceptedLogic_')){
   const actions:LogicExtensionAction[]=Array.isArray(answers.logicExtensionActions)?[...answers.logicExtensionActions]:[];
   if(step.key.startsWith('crossFunctionFile_')){
    if(skipped){actions.push({type:'skip',stepKey:'crossFunctionFile'});nextAnswers.pendingLogicExtension='';}
    else nextAnswers.pendingLogicExtension='cross';
   }else{
    if(skipped)actions.push({type:'skip',stepKey:step.key.replace(/_\d+$/,'')});
    else if(step.key.startsWith('crossFunctionLogic_')){const index=Number(step.key.slice('crossFunctionLogic_'.length));actions.push({type:'cross',sourceFile:String(answers[`crossFunctionFile_${index}`]||'').trim(),logic:text});}
    else if(step.key.startsWith('acceptedLogic_'))actions.push({type:'accepted',logic:text});
    nextAnswers.pendingLogicExtension='';
   }
   nextAnswers.logicExtensionActions=actions;
  }
  if(step.key==='exactLogic'&&!skipped){
   const existing=parseArrayAnswer(answers.logicAlternatives).filter((item:any)=>typeof item==='string');
   if(existing.length)nextAnswers.logicAlternatives=JSON.stringify([text,...existing.slice(1)]);
  }
  if(skipped&&['groupCodes','groupCodeMode'].includes(step.key))nextAnswers.needsGroupCodeConfiguration=true;
  setAnswers(nextAnswers);setTurns(current=>[...current,{key:step.key,question:step.question,answer:skipped?'Skip':text||'Skip'}]);const nextStep=stepsFor(nextAnswers,departments)[turns.length+1];setInput(nextStep?String(nextAnswers[nextStep.key]||''):text);setMessage('');
 };
 const edit=(index:number)=>{
  const prior=turns[index];const rebuilt:Record<string,any>={ruleId:answers.ruleId||'',logicAlternatives:answers.logicAlternatives,crossFunctionChecks:answers.crossFunctionChecks};const actions:LogicExtensionAction[]=[];let pending='';
  for(const turn of turns.slice(0,index)){
   if(turn.key.startsWith('logicExtensionChoice_')){
    if(turn.answer==='Cross-function analysis')pending='cross';else if(turn.answer==='Accept logic')pending='accepted';else if(turn.answer==='Skip'){pending='';rebuilt.logicExtensionsSkipped=true}
   }else if(turn.key.startsWith('crossFunctionFile_')&&turn.answer==='Skip'){actions.push({type:'skip',stepKey:'crossFunctionFile'});pending=''}
   else if(turn.key.startsWith('crossFunctionLogic_')){if(turn.answer==='Skip')actions.push({type:'skip',stepKey:'crossFunctionLogic'});else{const actionIndex=Number(turn.key.slice('crossFunctionLogic_'.length));actions.push({type:'cross',sourceFile:String(rebuilt[`crossFunctionFile_${actionIndex}`]||''),logic:turn.answer})}pending=''}
   else if(turn.key.startsWith('acceptedLogic_')){actions.push(turn.answer==='Skip'?{type:'skip',stepKey:'acceptedLogic'}:{type:'accepted',logic:turn.answer});pending=''}
   else if(turn.key==='category'&&turn.answer==='Skip'){rebuilt.category='Logic';rebuilt.categorySkipped=true}
   else if(['groupCodes','groupCodeMode'].includes(turn.key)&&turn.answer==='Skip'){rebuilt[turn.key]='';rebuilt.needsGroupCodeConfiguration=true}
   else rebuilt[turn.key]=turn.answer==='Skip'?'':turn.answer;
  }
  if(rebuilt.exactLogic){const existing=parseArrayAnswer(rebuilt.logicAlternatives).filter((item:any)=>typeof item==='string');if(existing.length)rebuilt.logicAlternatives=JSON.stringify([rebuilt.exactLogic,...existing.slice(1)])}
  rebuilt.logicExtensionActions=actions;rebuilt.pendingLogicExtension=pending;
  setTurns(turns.slice(0,index));setAnswers(rebuilt);setInput(prior.answer==='Skip'?'':prior.answer);setConfig(null);setReviewed(false);setTestResults(null);setTestReviewed(false);
 };
 const generate=async()=>{
  setBusy(true);setMessage('');
  try{
   const preparedAnswers={...answers};
   const alternatives=parseArrayAnswer(answers.logicAlternatives).filter((item:any)=>typeof item==='string'&&item.trim());
   if(!answers.exactLogic)alternatives.splice(0);
   if(answers.exactLogic){if(alternatives.length)alternatives[0]=answers.exactLogic;else alternatives.push(answers.exactLogic)}
   const crossChecks=parseArrayAnswer(answers.crossFunctionChecks).filter((item:any)=>item&&typeof item==='object');
   for(const action of (Array.isArray(answers.logicExtensionActions)?answers.logicExtensionActions:[]) as LogicExtensionAction[]){
    if(action.type==='accepted')alternatives.push(action.logic);
    else if(action.type==='cross')crossChecks.push({name:`Cross-function check ${crossChecks.filter((check:any)=>check.name?.startsWith('Cross-function check')).length+1}`,sourceFiles:[action.sourceFile],searchAllSubroutines:false,logicAlternatives:[action.logic],exactLogic:action.logic});
   }
   preparedAnswers.logicAlternatives=JSON.stringify(alternatives);
   preparedAnswers.crossFunctionChecks=JSON.stringify(crossChecks);
   const data=await apiJson('/api/assist/rule-config',{guided:true,answers:preparedAnswers,description:answers.description||answers.name});
   showConfig({...data.config,rules:(data.config.rules||[]).map((rule:any)=>({...rule,featureName:answers.featureName||'Spin Connect'}))});
  }catch(e:any){setMessage(e.message)}finally{setBusy(false)}
 };
 const testDraft=async()=>{
  const testProject=currentProject.current;
  setBusy(true);setMessage('');setTestResults(null);setTestReviewed(false);
  try{if(!projectPath&&!projectFiles.length)throw new Error('Select a project in Validation before testing this draft.');const parsed=JSON.parse(jsonText);if(!Array.isArray(parsed.rules)||!parsed.rules.length)throw new Error('Configuration must contain rules.');if(parsed.rules.some((r:any)=>r.needsLogicConfiguration||r.needsRuleConfiguration||(['exact_logic_declaration','cross_domain_traceability','lot_name_packet_hmi'].includes(r.kind)&&!(r.logicAlternatives?.some((x:string)=>x.trim())||r.exactLogic?.trim()))))throw new Error('Complete the skipped source, logic or rule details before testing this draft.');const data=await validateEngineeringRules({localProjectPath:projectPath,projectFiles,projectName,rules:{...parsed,pipelineMode:'sequential'}} as any);if(currentProject.current!==testProject){setMessage('Project changed. Run the draft test against the selected project.');return}setTestedSignature(reviewSignature(parsed));setTestResults(data);setMessage('Draft rule test completed against the selected project. Review the evidence below before enabling the rule.');}
  catch(e:any){setMessage(e.message||'Draft test failed.')}finally{setBusy(false)}
 };
 const save=async(enable:boolean)=>{
  setBusy(true);setMessage('');try{
   const parsed=JSON.parse(jsonText);if(!Array.isArray(parsed.rules)||!parsed.rules.length)throw new Error('Configuration must contain rules.');
   if(enable&&parsed.rules.some((r:any)=>r.needsLogicConfiguration||r.needsRuleConfiguration))throw new Error('Complete the skipped source, logic or rule details before enabling this rule.');
   if(enable&&!reviewed)throw new Error('Tick the source scope and expected logic review checkbox below before enabling.');
   if(enable&&(!testResults||testedSignature!==reviewSignature(parsed))){testPanel.current?.scrollIntoView({behavior:'smooth',block:'center'});throw new Error('Run draft test for this configuration first. Then review its output and click Save and enable.')}
   if(enable&&!testReviewed){testPanel.current?.scrollIntoView({behavior:'smooth',block:'center'});throw new Error('Tick I reviewed the test output beneath the draft test results, then click Save and enable.')} 
   parsed.rules=parsed.rules.map((r:any)=>({...r,enabled:enable,reviewStatus:enable?'Engineer reviewed':'Needs engineer review'}));
   await apiJson('/api/rules/modules',{config:parsed,createOnly:parsed.configurationFormat==='grouped-v1'&&!parsed.editingRuleId&&!rules.some(rule=>rule.id===parsed.rules[0]?.id)});setConfig(parsed);setJsonText(JSON.stringify(parsed,null,2));setSavedSnapshot(persistedSignature(parsed));if(parsed.rules[0]?.id)setSelectedSavedRule(parsed.rules[0].id);onSaved();void reload();setMessage(enable?`Saved · Enabled: ${parsed.rules[0]?.id||'rule'}. Linked to its configured feature. Manage it in KnowHub ? Rule Library.`:`Saved · Draft: ${parsed.rules[0]?.id||'rule'}. Completed tests and review checkboxes are retained. Finish the enable steps below.`);
  }catch(e:any){setMessage(e.message)}finally{setBusy(false)}
 };
 const attach=async(file?:File)=>{
  if(!file)return;if(file.size>2*1024*1024){setMessage('Use a file smaller than 2 MB.');return}
  try{
   if(file.name.toLowerCase().endsWith('.csv')){const form=new FormData();form.append('file',file);form.append('machine',answers.machineDepartment||'All');const res=await fetch('/api/rules/checklists/normalize',{method:'POST',body:form});const data=await res.json();if(!res.ok)throw new Error(data.detail);showConfig(data.module);setMessage('Checklist imported as drafts. Review each requirement.');}
   else {setInput(await file.text());setMessage(`${file.name} loaded as your answer. Edit it if needed, then send.`)}
  }catch(e:any){setMessage(e.message||'Could not read attachment.')}
 };
 return <div className="ruleConversationWorkspace card">
  <div className="chopperChatHead"><span className="chopperAvatar"><Bot size={20}/></span><div><b>Chopper</b><span>Rule Configuration Assistant</span></div><button className="btn" disabled={busy} onClick={()=>{setWizardSeed(undefined);setWizardKey(key=>key+1);setSelectedSavedRule('');setAnswers({});setTurns([]);setInput('');setConfig(null);setMessage('')}}>New conversation</button></div>
   <div className="ruleDraftPicker"><label>Review a saved rule <select disabled={busy} value={selectedSavedRule} onChange={e=>openSavedRule(e.target.value)}><option value="">Select a saved rule...</option>{rules.map(r=><option key={r.id} value={r.id}>{r.enabled===false?'Saved · Draft':'Saved · Enabled'} — {r.id} - {r.name}</option>)}</select></label><button type="button" className="btn danger iconButton" title="Delete selected rule" aria-label="Delete selected rule" disabled={busy||!selectedSavedRule} onClick={()=>void deleteSavedRule()}><Trash2 size={15}/></button></div>
  {!config&&<GroupedRuleWizard key={wizardKey} seed={wizardSeed} departments={departments} onReady={value=>showConfig(value)}/>}
  {message&&!config&&<p className="ruleMessage" role="status">{message}</p>}
   {config&&<div className="conversationReview"><h3>{isEnabled?'Saved and enabled':isSaved?'Saved draft':'Review your rule'}</h3><p className="ruleSaveState" role="status">{isEnabled?'This configuration is saved and ready to select in the pipeline.':isSaved?'Your draft is saved. Complete the test and review to enable it.':savedSnapshot?'Unsaved changes. Test and review the updated rule before enabling.':'Review the requirements below, run a draft test, then save.'}</p>{(config.rules||[]).map((r:any,index:number)=>{const alternatives=logicBlocks(r);const crossChecks=Array.isArray(r.crossFunctionChecks)?r.crossFunctionChecks:[];return <article key={r.id}><b>{r.standardId||r.id} - {r.name}</b><p>{r.description||r.expected}</p>{(r.needsLogicConfiguration||r.needsRuleConfiguration)&&<p className="ruleMessage">Some required details were skipped. Save this as a draft, then complete the missing fields using Edit grouped requirements before testing or enabling.</p>}<dl className="draftRuleSummary"><div><dt>Category</dt><dd>{r.category||'?'}</dd></div><div><dt>Feature</dt><dd>{r.featureName||r.featureId||'?'}</dd></div><div><dt>Machine / department</dt><dd>{r.machineDepartment||r.machineScope?.join(', ')||'All'}{r.machineModels?.length?` / ${r.machineModels.join(', ')}`:''}</dd></div><div><dt>PLC source / subroutine</dt><dd>{r.subroutine||r.sourceFile||'?'}{r.groupCode!==undefined?` / Group ${r.groupCode}`:''}</dd></div><div><dt>PLC tag / variable</dt><dd>{isModuleSerialRule(r)?'Discovered from SerialNumber I/O bindings (scalar / array)':r.variable||'?'}</dd></div><div><dt>Declared datatype</dt><dd>{r.allowedDatatypes?.join(', ')||(isModuleSerialRule(r)?'UDINT, DINT, DWORD (4 bytes)':'?')}</dd></div></dl><p><b>Expected check:</b> {r.expected||r.description}</p>{r.sourceFiles?.length>0&&<p>PLC source scope: {r.sourceFiles.join(', ')}</p>}{r.crossDomainHmiPages?.length>0&&<p>HMI pages: {r.crossDomainHmiPages.join(', ')}</p>}
    {isModuleSerialRule(r)?<ModuleSerialRuleSummary rule={r}/>:r.kind==='structured_requirements'?<StructuredRuleSummary checks={r.checks||[]}/>:<>{supportsAcceptedLogic(r)?<section className="acceptedLogicEditor"><header><b>Primary logic and accepted alternatives</b><span>Each block is a valid PLC or HMI source alternative. Any one complete block can satisfy this check.</span></header>{alternatives.map((block:string,blockIndex:number)=><div className="acceptedLogicBlock" key={`${r.id}-logic-${blockIndex}`}><label>{blockIndex===0?'Primary exact logic':`Accepted alternative ${blockIndex}`}<textarea disabled={busy} aria-label={`${r.id} accepted logic alternative ${blockIndex+1}`} value={block} onChange={event=>updateLogicBlock(r,index,blockIndex,event.target.value)} placeholder="Paste one complete PLC or HMI source block"/></label><button className="btn danger" disabled={busy} onClick={()=>removeLogicBlock(r,index,blockIndex)}>Remove alternative</button></div>)}<button className="btn" disabled={busy} onClick={()=>addLogicBlock(r,index)}>+ Add accepted logic</button></section>:alternatives.some((block:string)=>block.trim())&&<details><summary>Configured source logic reference</summary><p>This rule uses its structured validator for execution. Edit its rule-specific fields or configuration JSON.</p>{alternatives.map((block:string,blockIndex:number)=><pre key={`${r.id}-reference-${blockIndex}`}>{block}</pre>)}</details>}
    <section className="crossFunctionEditor"><header><div><b>Cross-function checks</b><span>Check related PLC, HMI or configuration files. Choose AND to require every cross reference, or OR to accept any complete cross reference. Each reference can use its own file.</span></div><button className="btn" disabled={busy} onClick={()=>addCrossCheck(r,index)}>+ Add cross reference</button></header><label>Cross reference relationship<select aria-label="Cross reference relationship" disabled={busy} value={r.crossFunctionMode||'all'} onChange={event=>updateRule(index,{crossFunctionMode:event.target.value})}><option value="all">AND - every reference</option><option value="any">OR - any complete reference</option></select></label>{crossChecks.map((check:any,checkIndex:number)=>{const blocks=crossLogicBlocks(check);return <div className="crossFunctionCheck" key={`${r.id}-cross-${checkIndex}`}><div className="crossFunctionCheckHead"><b>{check.name||`Cross-function check ${checkIndex+1}`}</b><button className="btn danger" disabled={busy} onClick={()=>removeCrossCheck(r,index,checkIndex)}>Remove check</button></div><label>Check name<input disabled={busy} value={check.name||''} onChange={event=>updateCrossCheck(r,index,checkIndex,{name:event.target.value})} placeholder="For example, copy lot name into the shift buffer"/></label><label className="crossFunctionScope"><input type="checkbox" disabled={busy} checked={check.searchAllSubroutines!==false} onChange={event=>updateCrossCheck(r,index,checkIndex,{searchAllSubroutines:event.target.checked})}/> Search all other supported project files</label><label>Related file(s), one path per line<textarea disabled={busy||check.searchAllSubroutines!==false} value={(Array.isArray(check.sourceFiles)?check.sourceFiles:[]).join('\n')} onChange={event=>updateCrossCheck(r,index,checkIndex,{sourceFiles:event.target.value.split(/[\r\n,;]+/).map(value=>value.trim()).filter(Boolean)})} placeholder="Logical/MMS/mms_Pms.st"/></label><label>Group Code (optional)<input type="number" disabled={busy} value={check.groupCode??''} onChange={event=>updateCrossCheck(r,index,checkIndex,{groupCode:event.target.value===''?undefined:Number(event.target.value)})}/></label><b>Required logic or XML in the related file</b>{blocks.map((block:string,blockIndex:number)=><div className="acceptedLogicBlock" key={`${r.id}-cross-${checkIndex}-logic-${blockIndex}`}><label>Accepted block {blockIndex+1}<textarea disabled={busy} aria-label={`${r.id} cross-function ${checkIndex+1} logic ${blockIndex+1}`} value={block} onChange={event=>updateCrossBlock(r,index,checkIndex,blockIndex,event.target.value)} placeholder="Enter the complete required source logic"/></label><button className="btn danger" disabled={busy} onClick={()=>{const checks=[...crossChecks];const next={...checks[checkIndex]};const nextBlocks=crossLogicBlocks(next);nextBlocks.splice(blockIndex,1);if(!nextBlocks.length)nextBlocks.push('');next.logicAlternatives=nextBlocks;next.exactLogic=nextBlocks.find(value=>value.trim())||'';checks[checkIndex]=next;updateRule(index,{crossFunctionChecks:checks})}}>Remove alternative</button></div>)}<button className="btn" disabled={busy} onClick={()=>addCrossBlock(r,index,checkIndex)}>+ Add accepted block</button></div>})}</section>
    </>}<button className="btn" disabled={busy} onClick={()=>configureRule(r)}>{isModuleSerialRule(r)?'Configure serial requirements / cross references':'Edit grouped requirements'}</button>{r.kind==='lot_name_packet_hmi'&&<p>HMI: {r.pagePrefix||'Process'}*; label {r.label||'LOT NAME'}; String control with Input=True and a PLC variable linked to the packet source directly or through an approved cross-function assignment. Text ID and ClassId may vary.</p>}</article>})}
   <section className="draftRuleTest" ref={testPanel}><div><b>Test draft against selected project</b><span>{projectName||'No project selected'} · {projectPath||`${projectFiles.length} uploaded file(s)`}</span></div><button className="btn primary" disabled={busy||(!projectPath&&!projectFiles.length)} onClick={testDraft}>{busy?'Testing draft…':'Run draft test'}</button>{testResults&&<><div className="draftTestSummary">{(testResults.results||[]).map((item:any)=><details key={item.id}><summary><b>{item.status}</b> · {item.name||item.id} — {item.actual}</summary><RuleLogicEvidence item={item} onAcceptHmiActual={(finding,attempt,property)=>acceptHmiActual(item,finding,attempt,property)}/></details>)}</div><label><input type="checkbox" checked={testReviewed} onChange={event=>setTestReviewed(event.target.checked)}/> I reviewed the test output. A FAIL may mean the project violates a correctly configured requirement.</label></>}</section>
   <details><summary>Edit configuration JSON</summary><textarea disabled={busy} aria-label="Rule configuration JSON" className="configurationJson" value={jsonText} onChange={e=>{setJsonText(e.target.value);try{const parsed=JSON.parse(e.target.value);if(Array.isArray(parsed?.rules))setConfig(parsed)}catch{/* keep last valid preview */}setReviewed(false);setTestResults(null);setTestReviewed(false)}}/></details><label><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/> I reviewed the source scope, expected logic and variable requirements.</label>{!isEnabled&&<div className="ruleEnableChecklist" aria-live="polite"><b>To save and enable</b><ol><li>{reviewed?'Done: requirements reviewed.':'Review the source scope and expected logic above.'}</li><li>{testResults?'Done: draft test completed.':'Run draft test against the selected project.'}</li><li>{testReviewed?'Done: test output reviewed.':'Review the test output and tick its checkbox.'}</li></ol>{!testResults&&<button className="btn" disabled={busy||(!projectPath&&!projectFiles.length)} onClick={()=>{testPanel.current?.scrollIntoView({behavior:'smooth',block:'center'});void testDraft()}}>Run required draft test</button>}{!projectPath&&!projectFiles.length&&<p>Select a project in Validation to run the test.</p>}</div>}<div className="actions"><button className="btn" disabled={busy||(isSaved&&!isEnabled)} onClick={()=>save(false)}>{isSaved&&!isEnabled?'Saved draft':isEnabled?'Save as draft (disable)':'Save draft'}</button><button className="btn primary" disabled={busy||isEnabled} onClick={()=>save(true)}>{isEnabled?'Saved and enabled':'Save and enable'}</button><button className="btn" disabled={busy} onClick={()=>configureRule(config.rules[0])}>Back to configuration</button></div>{message&&<p className="ruleMessage" role="status">{message}</p>}</div>}
 </div>;
}
