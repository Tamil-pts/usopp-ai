import {useState} from 'react';
import {apiJson,DEPARTMENTS} from '../rules/library';

export const isModuleSerialRule=(rule:any)=>rule?.kind==='module_serial_mapping'||rule?.id==='BR_MODULE_SERIAL_420';
const EXPECTED='Every controller and electronic remote module has a unique SerialNumber datapoint binding; its four-byte integer variable or array element is transmitted exactly once on each applicable GC 420 path, with matching payload length and response setup.';
const lines=(text:string)=>text.split(/\r?\n/).map(v=>v.trim()).filter(Boolean);
const showScope=(patterns:string[]|undefined,fallback:string)=>patterns?.length?patterns.join(', '):fallback;
export function completeModuleSerialRule(rule:any) {
 const value={...rule,kind:'module_serial_mapping',featureId:'hardware_io',featureName:rule.featureName&&rule.featureName!=='Unassigned'?rule.featureName:'Hardware / I/O',groupCode:420,sourceFile:rule.sourceFile||rule.subroutine||rule.checks?.[0]?.file||'mms_nw_rCyclic.st',allowedDatatypes:rule.allowedDatatypes?.length?rule.allowedDatatypes:['UDINT','DINT','DWORD']};
 value.subroutine=value.sourceFile;
 for(const key of ['checks','needsLogicConfiguration','needsRuleConfiguration','configurationIssues','configurationFormat'])delete value[key];
 return value;
}

export function ModuleSerialRuleSummary({rule}:{rule:any}) {
 const scope=rule.serialMapping||{};
 return <div className="structuredRuleSummary">
  <article><h3>Requirement 1 - Module serial numbers in GC 420</h3>
   <p><b>PLC packet source:</b> {rule.sourceFile||rule.subroutine||'mms_nw_rCyclic.st'} (equivalent AS 2.7 mms_nw_r.src is supported)</p>
   <p><b>Group Code:</b> 420. Check every applicable conditional packet path separately.</p>
   <p><b>Configuration:</b> Use the active configuration recorded in LastUser.set. AS 2.7 uses its single configuration. Inactive configurations are excluded; an unresolved selection is reported.</p>
   <ul><li>Transmit every bound controller/module serial variable exactly once, using four bytes per serial number.</li><li>Accept scalar variables, individual array elements or a contiguous bulk array copy. Use the actual I/O-bound variable names; names are discovered from the project.</li><li>Allowed declared types: {(rule.allowedDatatypes||['UDINT','DINT','DWORD']).join(', ')}. Array indices and the entire copied range must fit the declaration.</li><li>Start the packet cursor correctly, match every copy size and cursor increment, and match the size header to the complete payload.</li><li>Set nw_snd_buffer_length and nw_snd_response after preparing the data.</li></ul>
  </article>
  <article><h3>Cross references - AND: every stage is required</h3><p>Hardware module → SerialNumber I/O binding → PLC declaration → GC 420 copy. Check the active configuration and keep its conditional packet paths separate.</p>
   <table className="table"><thead><tr><th>Related source</th><th>Scope</th><th>Required check</th></tr></thead><tbody>
    <tr><td>Hardware inventory</td><td>{showScope(scope.hardwareFiles,'Hardware.hw belonging to the active configuration')}</td><td>Identify the controller and electronic remote modules. Exclude inactive configurations and passive terminal/base modules. Missing or ambiguous inventory is reported.</td></tr>
    <tr><td>I/O mappings</td><td>{showScope(scope.ioMappingFiles,'Active configuration IoMap.iom / IOMap.iom')}</td><td>One SerialNumber binding per module; distinct scalar/array element ownership. Follow the exact variable into the packet.</td></tr>
    <tr><td>PLC declarations</td><td>{showScope(scope.declarationFiles,'Project .var / .typ and AS 2.7 CPU.txt declarations')}</td><td>Resolve the bound variable's four-byte datatype and array bounds. Report missing declarations and copies outside the declared range.</td></tr>
    <tr><td>PLC task selection</td><td>Cpu.sw and the matching packet task</td><td>Use the source belonging to the physical PLC target. Report ambiguous target ownership.</td></tr>
   </tbody></table><p>This is a dedicated semantic check. Source names and array lengths can differ between machines; an empty exact-logic block is not required.</p>
  </article>
 </div>;
}

export function ModuleSerialRuleEditor({seed,onReady,departments=DEPARTMENTS}:{seed:any;onReady:(value:any)=>void;departments?:string[]}) {
 const [name,setName]=useState(seed.name||'Module serial no mapping'),[description,setDescription]=useState(seed.description||seed.expected||EXPECTED);
 const [source,setSource]=useState(seed.sourceFile||seed.subroutine||seed.checks?.[0]?.file||'mms_nw_rCyclic.st');
 const [department,setDepartment]=useState(seed.machineDepartment||seed.machineScope?.[0]||'All');
 const [scope,setScope]=useState<Record<string,string>>({ioMappingFiles:(seed.serialMapping?.ioMappingFiles||[]).join('\n'),hardwareFiles:(seed.serialMapping?.hardwareFiles||[]).join('\n'),declarationFiles:(seed.serialMapping?.declarationFiles||[]).join('\n')});
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const rule={...seed,name,description,kind:'module_serial_mapping',featureId:'hardware_io',featureName:'Hardware / I/O',sourceFile:source,subroutine:source,groupCode:420,allowedDatatypes:['UDINT','DINT','DWORD'],machineDepartment:department,machineScope:[department],serialMapping:Object.fromEntries(Object.entries(scope).map(([key,value])=>[key,lines(value)]))};
 const review=async()=>{setBusy(true);setError('');try {
  const data=await apiJson('/api/assist/rule-config',{guided:true,answers:{configurationFormat:'serial-mapping-v1',editingRuleId:seed.id,ruleId:seed.id,rule}});
  if(data.config?.rules?.[0]?.kind!=='module_serial_mapping')throw Error('Restart the updated application to load the dedicated serial-number rule editor.');
  onReady({...data.config,editingRuleId:seed.id});
 }catch(e:any){setError(e.message||'Could not configure this rule.');}finally{setBusy(false);}};
 return <div className="groupedRuleWizard"><h3>Configure Module serial no mapping</h3><p>Hardware / I/O · GC 420 · scalar and array serial numbers</p>
  <div className="groupedFields"><label>Rule name<input value={name} disabled={busy} onChange={e=>setName(e.target.value)}/></label><label>Feature<input readOnly value="Hardware / I/O"/></label><label>Packet source / subroutine<input disabled={busy} value={source} onChange={e=>setSource(e.target.value)} placeholder="mms_nw_rCyclic.st or mms_nw_r.src"/></label><label>Machine / department<select disabled={busy} value={department} onChange={e=>setDepartment(e.target.value)}>{[...new Set(['All',...departments,department])].map(d=><option key={d}>{d}</option>)}</select></label><label className="wide">Description<textarea disabled={busy} value={description} onChange={e=>setDescription(e.target.value)}/></label></div>
  <h4>Configure related file scopes</h4><p>Leave a scope blank to discover files in the active configuration. Optional project-relative patterns narrow that scope; they do not include inactive configurations. Declaration files may be shared project files.</p>
  <div className="groupedFields">{[['ioMappingFiles','I/O mapping files','Physical/Config1/PLC1/IoMap.iom'],['hardwareFiles','Hardware inventory files','Physical/Config1/Hardware.hw'],['declarationFiles','Declaration files','Global.var\nmms_nw_r.var\nCPU.txt']].map(([key,label,placeholder])=><label key={key}>{label}<textarea disabled={busy} value={scope[key]} onChange={e=>setScope({...scope,[key]:e.target.value})} placeholder={placeholder}/></label>)}</div>
  <ModuleSerialRuleSummary rule={rule}/><div className="actions"><button className="btn primary" disabled={busy||!name.trim()||!source.trim()} onClick={()=>void review()}>{busy?'Preparing configuration...':'Review configured rule'}</button></div>{error&&<p className="ruleMessage" role="alert">{error}</p>}
 </div>;
}
