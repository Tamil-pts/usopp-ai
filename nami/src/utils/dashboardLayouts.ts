import type {MetadataItem,PLCConfig} from '../types';
import {compileFormula,dashboardParameterKey,numericParameters,validateCard,type DashboardCard,type PersonalDashboard,type DashboardLibrary,type DashboardResult} from './calculationDashboard';
import {dataModelMachineKey} from './dataModelChecks';
import * as XLSX from 'xlsx';

export type LayoutParameter={id:string;name:string;dataType:string;groupCodes:number[];kind:string;formula:string;keys:string[];unit:string;source:{workbook:string;sheet:string;row:number};aliases?:string[];dataTypeRole?:string;numericValueType?:boolean;bindingRole?:string;mongoKey?:string;tdEngineKey?:string;ignoreNameSeparators?:boolean;definitionPriority?:number;definitionSource?:{workbook:string;sheet:string;row:number}};
export type StarterSummary={id:string;name:string;service:string;machine:string;view:string;mode:'live'|'report';source:{workbook:string;sheet:string};parameterCount:number;displayCount:number;widgetCount:number;excludedCount:number};
export type StarterLayout=StarterSummary&{format:string;columns:number;parameters:LayoutParameter[];excluded:{row:number;name:string;reason:string}[];widgets:{title:string;widget:DashboardCard['widget'];span:number;parameterIds:string[]}[]};
export type LayoutIndex={accountId:number;templates:StarterSummary[];saved:{id:string;name:string;savedAt:string;dashboardCount:number}[]};
export async function layoutRequest<T>(path='',options:RequestInit={}):Promise<T>{
 const response=await fetch('/api/nami/dashboard-layouts'+path,{credentials:'same-origin',cache:'no-store',...options});
 const data=await response.json();if(!response.ok)throw new Error(data.detail||'Dashboard knowledge is unavailable.');return data;
}
export function parseStarter(value:unknown):StarterLayout{
 const data=value as StarterLayout;
 const text=(v:unknown,max:number)=>typeof v==='string'&&v.length<=max;
 if(!data||data.format!=='usopp-dashboard-template'||(data as unknown as {schemaVersion:number}).schemaVersion!==1||!text(data.id,180)||!text(data.name,80)||!data.name||!text(data.machine,80)||!['PMS','QMS','CMS'].includes(data.service)||!['live','report'].includes(data.mode)||!Number.isInteger(data.columns)||data.columns<1||data.columns>4||!Array.isArray(data.parameters)||data.parameters.length>1000||!Array.isArray(data.widgets)||data.widgets.length>32||!Array.isArray(data.excluded)||!data.source||!text(data.source.workbook,300)||!text(data.source.sheet,100))throw new Error('Invalid workbook dashboard template.');
 const ids=new Set<string>();
 for(const p of data.parameters){
  if(!p||!text(p.id,100)||!p.id||ids.has(p.id)||!text(p.name,300)||!p.name||!text(p.formula,2000)||!text(p.unit,32)||!text(p.dataType,40)||!['plc','formula','server'].includes(p.kind)||!Array.isArray(p.groupCodes)||p.groupCodes.length>32||p.groupCodes.some(n=>!Number.isInteger(n)||n<0||n>65535)||!Array.isArray(p.keys)||p.keys.length>20||p.keys.some(k=>!text(k,300))||!p.source||!text(p.source.workbook,300)||!text(p.source.sheet,100)||!Number.isInteger(p.source.row)||p.source.row<1)throw new Error('Invalid workbook parameter definition.');ids.add(p.id);
  if(p.aliases!==undefined&&(!Array.isArray(p.aliases)||p.aliases.length>40||p.aliases.some(value=>!text(value,300))))throw new Error('Invalid configured parameter aliases.');
  if(p.dataTypeRole!==undefined&&!['value','wire'].includes(p.dataTypeRole)||p.numericValueType!==undefined&&typeof p.numericValueType!=='boolean'||p.ignoreNameSeparators!==undefined&&typeof p.ignoreNameSeparators!=='boolean')throw new Error('Invalid reference type policy.');
  for(const key of ['mongoKey','tdEngineKey'] as const)if(p[key]!==undefined&&!text(p[key],300))throw new Error('Invalid database input key.');
  if(p.definitionSource&&(!text(p.definitionSource.workbook,300)||!text(p.definitionSource.sheet,100)||!Number.isInteger(p.definitionSource.row)))throw new Error('Invalid equation source.');
 }
 for(const widget of data.widgets)if(!widget||!text(widget.title,80)||!widget.title||!['value','line','table'].includes(widget.widget||'')||!Number.isInteger(widget.span)||widget.span<1||widget.span>4||!Array.isArray(widget.parameterIds)||!widget.parameterIds.length||widget.parameterIds.length>12||widget.parameterIds.some(id=>!ids.has(id)))throw new Error('Invalid workbook widget definition.');
 for(const row of data.excluded)if(!row||!Number.isInteger(row.row)||!text(row.name,300)||!text(row.reason,300))throw new Error('Invalid excluded workbook row.');
 return data;
}
const typeKey=(value:string)=>({FLOAT:'REAL',USINT:'BYTE'}[value.toUpperCase()]||value.toUpperCase());
const nameKey=(value:string)=>value.trim().toLowerCase();
const base=(name:string,targetId:string):DashboardCard=>({id:crypto.randomUUID(),title:name.slice(0,80),targetId,kind:'direct',expression:'a',unit:'',precision:2,inputs:[],validation:'none',minimum:null,maximum:null,comparisonKey:'',tolerance:0,maxAgeSeconds:300,maxSkewSeconds:10});

/** Match only a unique name, GC and PLC datatype. Never guess offsets or limits. */
export function instantiateStarter(template:StarterLayout,plc:PLCConfig,metadata:MetadataItem[]){
 if(dataModelMachineKey(template.machine)!==dataModelMachineKey(plc.machineType||''))throw new Error('Choose a target in the prepared layout department.');
 const available=numericParameters(metadata);
 const issues:{id:string;name:string;detail:string}[]=[];const bound=new Map<string,DashboardCard>();
 const direct=(p:LayoutParameter)=>{
  const format=(name:string)=>p.ignoreNameSeparators?nameKey(name).replace(/[\s_]+/g,''):nameKey(name);
  const names=[p.name,...p.aliases||[]].map(format);
  const named=available.filter(item=>names.includes(format(item.parameter))&&p.groupCodes.includes(item.groupCode));
  const matches=named.filter(item=>typeKey(item.dataType)===typeKey(p.dataType)||p.dataTypeRole==='value'&&p.numericValueType&&item.dataType!=='BOOL');
  if(matches.length!==1||named.length!==1)throw new Error(named.length?`Reference ${p.name} (${p.dataType}, GC ${p.groupCodes.join(', ')}): ${named.map(item=>`${item.parameter} / ${item.dataType} / Tag ${item.tagCode}`).join('; ')}. Choose one source or correct its datatype mapping.`:`${p.name}: no numeric metadata match in GC ${p.groupCodes.join(', ')||'unspecified'}.`);
  return matches[0];
 };
 const resolve=(p:LayoutParameter,stack:string[]=[]):{expression:string;items:MetadataItem[]}=>{
  if(stack.includes(p.id)||stack.length>8)throw new Error('Circular or deeply nested workbook formula.');
  if(p.kind!=='formula'){const item=direct(p);return {expression:'$0',items:[item]}}
  const original=p.formula.trim().replace(/^=/,'').trim();
  const parsed=compileFormula(original),items:MetadataItem[]=[];
  const variables=new Map<string,string>();
  for(const variable of parsed.variables){
   // Database keys are evidence for formula inputs, not aliases for PLC names.
   const dependencies=template.parameters.filter(row=>row.bindingRole==='dependency');
   const mongo=dependencies.filter(row=>nameKey(row.mongoKey||'')===nameKey(variable));
   const keyed=mongo.length?mongo:dependencies.filter(row=>nameKey(row.tdEngineKey||'')===nameKey(variable));
   const allCandidates=keyed.length?keyed:template.parameters.filter(row=>row.keys.some(key=>nameKey(key)===nameKey(variable)));
   const priority=Math.max(0,...allCandidates.map(row=>row.definitionPriority||0));
   const candidates=allCandidates.filter(row=>(row.definitionPriority||0)===priority);
   const sources=[...new Map(candidates.map(row=>[JSON.stringify([row.kind,row.formula,row.groupCodes,nameKey(row.name)]),row])).values()];
   if(sources.length!==1)throw new Error(`Workbook formula input ${variable} has ${sources.length?'multiple definitions':'no definition'} in this sheet.`);
   let nested:{expression:string;items:MetadataItem[]};try{nested=resolve(sources[0],[...stack,p.id])}catch(error){throw new Error(`${variable}: ${error instanceof Error?error.message:'Input unavailable.'}`)}
   const expression=nested.expression.replace(/\$(\d+)/g,(_,index)=>{const item=nested.items[Number(index)];let i=items.findIndex(value=>dashboardParameterKey(value)===dashboardParameterKey(item));if(i<0){i=items.length;items.push(item)}return `$${i}`});
   variables.set(variable,`(${expression})`);
  }
  if(items.length>12)throw new Error('The formula needs more than 12 PLC inputs.');
  return {expression:original.replace(/[a-z_][a-z0-9_]*/gi,word=>variables.get(word)??word),items};
 };
 for(const p of template.parameters){
  const value=base(p.name,plc.id);value.reference={...p.source,formula:p.formula,templateId:template.id,valueType:p.dataType,...(p.definitionSource?{definitionSource:`${p.definitionSource.workbook} / ${p.definitionSource.sheet}:${p.definitionSource.row}`}:{})};
  try{
   const resolved=resolve(p);value.kind=p.kind==='formula'?'calculated':'direct';
   value.expression=resolved.expression.replace(/\$(\d+)/g,(_,index)=>`v${index}`);
   value.inputs=resolved.items.map((item,index)=>({alias:`v${index}`,parameterKey:dashboardParameterKey(item)}));
   value.reference.wireTypes=[...new Set(resolved.items.map(item=>item.dataType))];
   value.unit=p.unit||(value.kind==='direct'?resolved.items[0].units:'');
   if(['<null>','null','none'].includes(value.unit.toLowerCase()))value.unit='';
   validateCard(value);
  }catch(error){
   const detail=error instanceof Error?error.message:'Configure this workbook field.';
   value.kind='direct';value.expression='a';value.unit='';value.inputs=[{alias:'a',parameterKey:`unresolved:${template.id}:${p.id}`}];value.reference.issue=detail;
   issues.push({id:p.id,name:p.name,detail});
  }
  bound.set(p.id,value);
 }
 const cards=template.widgets.map(widget=>{
  const values=widget.parameterIds.map(id=>bound.get(id)).filter((value):value is DashboardCard=>!!value).map(value=>({...value,id:crypto.randomUUID()}));
  if(!values.length)return null;
  return {...values[0],title:widget.title,seriesLabel:values[0].title,widget:widget.widget,span:widget.span,height:widget.widget==='table'?340:widget.widget==='line'?300:200,series:values.slice(1)};
 }).filter((value):value is NonNullable<typeof value>=>!!value);
 const used=new Set(template.widgets.flatMap(widget=>widget.parameterIds));
 return {dashboard:{id:crypto.randomUUID(),name:template.name,mode:template.mode,columns:template.columns,cards} as PersonalDashboard,
  issues:issues.filter(issue=>used.has(issue.id)),
  matched:[...used].filter(id=>!bound.get(id)?.reference?.issue).length,total:used.size};
}

export function rebindLibrary(library:DashboardLibrary,plc:PLCConfig,metadata:MetadataItem[]):DashboardLibrary{
 const available=numericParameters(metadata);
 const bind=(value:DashboardCard):DashboardCard=>{
  const key=(previous:string)=>{
   let identity:unknown;try{identity=JSON.parse(previous)}catch{return previous}
   if(!Array.isArray(identity)||identity.length!==5)return previous;
   const matches=available.filter(item=>item.groupCode===identity[0]&&nameKey(item.parameter)===nameKey(String(identity[4]))&&typeKey(item.dataType)===typeKey(String(identity[3])));
   return matches.length===1?dashboardParameterKey(matches[0]):`unresolved:import:${previous}`;
  };
  return {...value,id:crypto.randomUUID(),targetId:plc.id,inputs:value.inputs.map(input=>({...input,parameterKey:key(input.parameterKey)})),comparisonKey:value.comparisonKey?key(value.comparisonKey):'',series:value.series?.map(bind)};
 };
 return {...library,migrated:[],dashboards:library.dashboards.map(board=>({...board,id:crypto.randomUUID(),cards:board.cards.map(bind)}))};
}

export type ExportValue={configuration:DashboardCard;machine:string;department:string;result:DashboardResult;points:{time:number;value:number|null}[]};
export async function exportDashboardExcel(board:PersonalDashboard,values:ExportValue[],context:Record<string,unknown>){
 const book=XLSX.utils.book_new();
 const rows:(string|number|null)[][]=[['Widget','Parameter','Target','Department','Value','Unit','Status','Detail','Formula','Capture source','Reference workbook','Reference sheet','Reference row','Reference value type','PLC input types','Equation definition']];
 const trends:(string|number|null)[][]=[['Widget','Parameter','Target','Capture time (UTC)','Value','Unit']];
 const inputs:(string|number|null)[][]=[['Widget','Parameter','Alias','GC','Tag','PLC parameter','Value','Capture time (UTC)','Source','PLC datatype']];
 for(const value of values){const c=value.configuration,r=value.result;
  rows.push([c.title,c.seriesLabel||c.title,value.machine,value.department,r.value,c.unit,r.status,r.detail,c.kind==='calculated'?c.expression:'Direct',r.source||'',c.reference?.workbook||'',c.reference?.sheet||'',c.reference?.row??null,c.reference?.valueType||'',c.reference?.wireTypes?.join(', ')||'',c.reference?.definitionSource||'']);
  for(const p of value.points)trends.push([c.title,c.seriesLabel||c.title,value.machine,new Date(p.time).toISOString(),p.value,c.unit]);
  for(const p of r.readings)inputs.push([c.title,c.seriesLabel||c.title,p.alias,p.groupCode,p.tagCode,p.name,p.value,p.time?new Date(p.time).toISOString():'',p.source,p.dataType||'']);
 }
 const sheets:[string,unknown[][]][]=[['Results',rows],['Trend samples',trends],['Input evidence',inputs],['Report context',[['Field','Value'],['Dashboard',board.name],['Mode',board.mode],...Object.entries(context).map(([key,value])=>[key,typeof value==='object'?JSON.stringify(value):value])]]];
 for(const [name,data] of sheets){const sheet=XLSX.utils.aoa_to_sheet(data);sheet['!cols']=data[0].map(()=>({wch:24}));XLSX.utils.book_append_sheet(book,sheet,name)}
 XLSX.writeFile(book,`usopp-${board.name.replace(/[^a-z0-9]+/gi,'-')}-results.xlsx`);
}
