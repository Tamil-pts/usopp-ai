import type {GroupResponseData,MetadataItem,PLCConfig} from '../types';

export type DashboardInput={alias:string;parameterKey:string};
export type DashboardCard={id:string;title:string;kind:'direct'|'calculated';expression:string;unit:string;precision:number;
  targetId?:string;widget?:'value'|'gauge'|'bar'|'line'|'area'|'column'|'pie'|'doughnut'|'scatter'|'heatmap'|'table';span?:number;displayMin?:number;displayMax?:number;
  height?:number;seriesLabel?:string;series?:DashboardCard[];
  reference?:{workbook:string;sheet:string;row:number;formula?:string;templateId?:string;issue?:string;definitionSource?:string;valueType?:string;wireTypes?:string[]};
  inputs:DashboardInput[];validation:'none'|'range'|'compare';minimum:number|null;maximum:number|null;comparisonKey:string;
  tolerance:number;maxAgeSeconds:number;maxSkewSeconds:number};
type Node={type:'number';value:number}|{type:'variable';name:string}|{type:'unary';operator:string;value:Node}|
  {type:'binary';operator:string;left:Node;right:Node}|{type:'call';name:string;args:Node[]};
const functions:Record<string,{min:number;max:number;run:(...args:number[])=>number}>={
  abs:{min:1,max:1,run:Math.abs},min:{min:2,max:12,run:Math.min},max:{min:2,max:12,run:Math.max},
  round:{min:1,max:1,run:Math.round},floor:{min:1,max:1,run:Math.floor},ceil:{min:1,max:1,run:Math.ceil},sqrt:{min:1,max:1,run:Math.sqrt},
  gt:{min:2,max:2,run:(a,b)=>Number(a>b)},gte:{min:2,max:2,run:(a,b)=>Number(a>=b)},lt:{min:2,max:2,run:(a,b)=>Number(a<b)},lte:{min:2,max:2,run:(a,b)=>Number(a<=b)},eq:{min:2,max:2,run:(a,b)=>Number(a===b)},neq:{min:2,max:2,run:(a,b)=>Number(a!==b)}};
const owns=(value:object,key:string)=>Object.prototype.hasOwnProperty.call(value,key);

/** Parse a small arithmetic language. Never run JavaScript, properties or user code. */
export function compileFormula(expression:string){
  if(!expression.trim()||expression.length>400)throw new Error('Enter a formula of 1–400 characters.');
  const tokens:string[]=[];const matcher=/(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?|[a-z_][a-z0-9_]*|[()+\-*/%,^]/iy;
  for(let position=0;position<expression.length;){
    if(/\s/.test(expression[position])){position++;continue}
    matcher.lastIndex=position;const match=matcher.exec(expression);
    if(!match)throw new Error(`Unsupported formula character at position ${position+1}.`);
    tokens.push(match[0]);position=matcher.lastIndex;
    if(tokens.length>200)throw new Error('Formula is too complex.');
  }
  let index=0,depth=0;const variables=new Set<string>();
  const take=()=>tokens[index++];const peek=()=>tokens[index];
  const primary=():Node=>{
    if(++depth>40)throw new Error('Formula nesting is too deep.');
    const token=take();let result:Node;
    if(token==='('){result=addition();if(take()!==')')throw new Error('Missing closing parenthesis.')}
    else if(token&&/^(?:\d|\.)/.test(token)){const value=Number(token);if(!Number.isFinite(value))throw new Error('Number is not finite.');result={type:'number',value}}
    else if(token&&/^[a-z_]/i.test(token)){
      if(peek()==='('){
        if(!owns(functions,token))throw new Error(`Unknown function ${token}.`);
        take();const args:Node[]=[];if(peek()!==')'){args.push(addition());while(peek()===','){take();args.push(addition())}}
        if(take()!==')')throw new Error('Missing closing function parenthesis.');
        if(args.length<functions[token].min||args.length>functions[token].max)throw new Error(`Invalid number of arguments for ${token}.`);
        result={type:'call',name:token,args};
      }else{variables.add(token);result={type:'variable',name:token}}
    }else throw new Error('Expected a number, input alias or parenthesis.');
    depth--;return result;
  };
  const power=():Node=>{const left=primary();return peek()==='^'?(take(),{type:'binary',operator:'^',left,right:unary()}):left};
  const unary=():Node=>peek()==='+'||peek()==='-'?{type:'unary',operator:take(),value:unary()}:power();
  const product=():Node=>{let left=unary();while(['*','/','%'].includes(peek()))left={type:'binary',operator:take(),left,right:unary()};return left};
  const addition=():Node=>{let left=product();while(['+','-'].includes(peek()))left={type:'binary',operator:take(),left,right:product()};return left};
  const tree=addition();if(index!==tokens.length)throw new Error(`Unexpected token ${peek()}.`);
  const evaluate=(values:Record<string,number>):number=>{
    const visit=(node:Node):number=>{
      let value:number;
      if(node.type==='number')value=node.value;
      else if(node.type==='variable'){if(!owns(values,node.name))throw new Error(`Input ${node.name} is missing.`);value=values[node.name]}
      else if(node.type==='unary'){const right=visit(node.value);value=node.operator==='-'?-right:right}
      else if(node.type==='call')value=functions[node.name].run(...node.args.map(visit));
      else{const left=visit(node.left),right=visit(node.right);if((node.operator==='/'||node.operator==='%')&&right===0)throw new Error('Division by zero.');
        value=node.operator==='+'?left+right:node.operator==='-'?left-right:node.operator==='*'?left*right:node.operator==='/'?left/right:node.operator==='%'?left%right:left**right}
      if(!Number.isFinite(value))throw new Error('The calculation does not produce a finite number.');return value;
    };return visit(tree);
  };
  return {variables:[...variables],evaluate};
}

export const dashboardParameterKey=(item:MetadataItem)=>JSON.stringify([item.groupCode,item.tagCode,item.offset,item.dataType,item.parameter]);
export const numericParameters=(items:MetadataItem[])=>items.filter(item=>/^(BOOL|BYTE|SINT|USINT|INT|UINT|DINT|UDINT|REAL|LREAL)$/i.test(item.dataType)&&!(item.arraySize&&item.arraySize>1));
export function metadataFingerprint(items:MetadataItem[]){
  const text=JSON.stringify(items.map(item=>[dashboardParameterKey(item),item.units,item.scaleFactor,item.offsetFactor]).sort((a,b)=>String(a[0]).localeCompare(String(b[0]))));
  let hash=2166136261;for(let i=0;i<text.length;i++)hash=Math.imul(hash^text.charCodeAt(i),16777619);return (hash>>>0).toString(16);
}
export const dashboardStorageKey=(plc:PLCConfig,items:MetadataItem[])=>`nami_dashboard_v1_${encodeURIComponent(plc.machineType||'Custom')}_${metadataFingerprint(items)}_${encodeURIComponent(plc.id)}_${plc.machineId}`;

export function validateCard(card:DashboardCard){
  if(card.reference){const reference=card.reference,text=(value:unknown,max:number)=>typeof value==='string'&&value.length<=max;
    if(!text(reference.workbook,300)||!text(reference.sheet,100)||!Number.isInteger(reference.row)||reference.row<0)throw new Error('Invalid widget source reference.');
    for(const [key,limit] of [['formula',2000],['templateId',180],['issue',4000],['definitionSource',700],['valueType',40]] as const)if(reference[key]!==undefined&&!text(reference[key],limit))throw new Error('Invalid widget source detail.');
    if(reference.wireTypes!==undefined&&(!Array.isArray(reference.wireTypes)||reference.wireTypes.length>12||reference.wireTypes.some(type=>!text(type,40))))throw new Error('Invalid PLC input type list.');
  }
  if(card.widget&&!['value','gauge','bar','line','area','column','pie','doughnut','scatter','heatmap','table'].includes(card.widget))throw new Error('Unsupported widget type.');
  if(card.height!==undefined&&(!Number.isInteger(card.height)||card.height<180||card.height>1000))throw new Error('Widget height must be 180–1000 pixels.');
  if(card.seriesLabel!==undefined&&(typeof card.seriesLabel!=='string'||card.seriesLabel.length>80))throw new Error('Use a parameter display name of up to 80 characters.');
  if(card.series!==undefined){
    if(!Array.isArray(card.series)||card.series.length>11)throw new Error('A widget supports at most 12 parameters.');
    const ids=new Set([card.id]);
    for(const series of card.series){if(!series||series.series?.length||ids.has(series.id)||typeof series.targetId!=='string')throw new Error('Each parameter needs a unique ID and machine; nested series are not supported.');validateCard(series);ids.add(series.id)}
    if(['line','area','column','pie','doughnut','heatmap'].includes(card.widget||'')&&new Set([card,...card.series].map(series=>series.unit.trim().toLowerCase())).size>1)throw new Error('Parameters sharing a chart axis need the same display unit. Convert units in the formulas or use a separate widget.');
  }
  if(card.span!==undefined&&(!Number.isInteger(card.span)||card.span<1||card.span>4))throw new Error('Widget width must be 1–4 columns.');
  if(card.widget==='gauge'||card.widget==='bar'){
    if(!Number.isFinite(card.displayMin)||!Number.isFinite(card.displayMax)||card.displayMin!>=card.displayMax!)throw new Error('Set a display minimum smaller than the maximum.');
  }
  if(!card||typeof card.id!=='string'||!card.id||card.id.length>100||typeof card.title!=='string'||!card.title.trim()||card.title.length>80)throw new Error('Give the card a title of 1–80 characters.');
  if(!['direct','calculated'].includes(card.kind)||!['none','range','compare'].includes(card.validation)||typeof card.unit!=='string'||card.unit.length>32)throw new Error('Invalid card configuration.');
  if(!Number.isInteger(card.precision)||card.precision<0||card.precision>6)throw new Error('Decimals must be from 0 to 6.');
  if(!Array.isArray(card.inputs)||card.inputs.length>12||card.kind==='direct'&&card.inputs.length!==1)throw new Error('Choose up to 12 formula inputs (one for a direct value). A constant formula needs no inputs.');
  const aliases=new Set<string>();for(const input of card.inputs){
    if(!input||typeof input.alias!=='string'||!/^[a-z][a-z0-9_]{0,23}$/.test(input.alias)||['abs','min','max','round','floor','ceil','sqrt'].includes(input.alias)||aliases.has(input.alias))throw new Error('Use unique lowercase input aliases, such as hours or minutes.');
    if(typeof input.parameterKey!=='string'||!input.parameterKey||input.parameterKey.length>1200)throw new Error('Choose a metadata parameter for every input.');aliases.add(input.alias);
  }
  const formula=compileFormula(card.kind==='direct'?card.inputs[0].alias:card.expression);
  for(const variable of formula.variables)if(!aliases.has(variable))throw new Error(`Choose a parameter for ${variable}.`);
  for(const alias of aliases)if(!formula.variables.includes(alias))throw new Error(`Input ${alias} is not used in the formula.`);
  for(const value of [card.minimum,card.maximum])if(value!==null&&(typeof value!=='number'||!Number.isFinite(value)))throw new Error('Enter finite numeric limits.');
  if(card.validation==='range'&&(card.minimum===null&&card.maximum===null||card.minimum!==null&&card.maximum!==null&&card.minimum>card.maximum))throw new Error('Configure at least one limit, with minimum no greater than maximum.');
  if(card.validation==='compare'&&!card.comparisonKey)throw new Error('Choose the PLC parameter to compare with.');
  if(typeof card.tolerance!=='number'||!Number.isFinite(card.tolerance)||card.tolerance<0)throw new Error('Tolerance must be a nonnegative number.');
  if(!Number.isFinite(card.maxAgeSeconds)||card.maxAgeSeconds<1||card.maxAgeSeconds>86400||!Number.isFinite(card.maxSkewSeconds)||card.maxSkewSeconds<0||card.maxSkewSeconds>3600)throw new Error('Use a maximum age of 1–86400 seconds and input time gap of 0–3600 seconds.');
  return formula;
}

export type DashboardReading={alias:string;name:string;key:string;groupCode:number;tagCode:number;dataType?:string;value:number;time:number|null;source:string};
export type DashboardResult={status:'pending'|'invalid'|'ready'|'pass'|'fail';detail:string;value:number|null;expected?:number;difference?:number;readings:DashboardReading[];source?:string};
export function calculateCard(card:DashboardCard,metadata:MetadataItem[],responses:Record<number,GroupResponseData>,now=Date.now(),archived=false):DashboardResult{
  const readings:DashboardReading[]=[];
  const result=(status:DashboardResult['status'],detail:string,value:number|null=null):DashboardResult=>({status,detail,value,readings});
  try{
    const formula=validateCard(card);const parameters=new Map(metadata.map(item=>[dashboardParameterKey(item),item]));
    const read=(key:string,alias:string)=>{
      const item=parameters.get(key);if(!item)throw new Error(`${alias}: the configured metadata parameter is unavailable. Reconfigure this card.`);
      const response=responses[item.groupCode];if(!response)throw new Error(`${alias}: read GC ${item.groupCode} first.`);
      if(!response.success||!response.lengthMatch||response.stage==='not_sent')throw new Error(`${alias}: GC ${item.groupCode} has no valid decoded response.`);
      const matches=response.parsedValues.filter(value=>value.tagCode===item.tagCode&&value.offset===item.offset&&value.dataType===item.dataType&&value.parameter===item.parameter);
      if(matches.length!==1||matches[0].qualityIssue)throw new Error(`${alias}: no unambiguous, valid decoded value is available.`);
      const raw=matches[0].rawValue;const value=typeof raw==='boolean'?Number(raw):raw;
      if(typeof value!=='number'||!Number.isFinite(value))throw new Error(`${alias}: the input is not a finite numeric value.`);
      const time=Number.isFinite(response.completedAt)?response.completedAt!:null;
      if(!archived&&(time===null||now-time>card.maxAgeSeconds*1000||time-now>5000))throw new Error(`${alias}: input is stale or its capture time is unavailable. Read GC ${item.groupCode} again.`);
      readings.push({alias,key,name:item.parameter,groupCode:item.groupCode,tagCode:item.tagCode,dataType:item.dataType,value,time,source:response.source==='manual'?'manual':'plc'});return value;
    };
    const values:Record<string,number>=Object.create(null);for(const input of card.inputs)values[input.alias]=read(input.parameterKey,input.alias);
    const expected=card.validation==='compare'?read(card.comparisonKey,'comparison'):undefined;
    const sources=new Set(readings.map(input=>input.source));if(sources.size>1)return result('pending','Inputs mix manual and PLC captures. Use one capture source.');
    const groups=new Set(readings.map(input=>input.groupCode));const times=readings.map(input=>input.time).filter((time):time is number=>time!==null);
    if(groups.size>1&&(times.length!==readings.length||Math.max(...times)-Math.min(...times)>card.maxSkewSeconds*1000))return result('pending','Input capture times differ too much. Read the required groups together.');
    let value:number;try{value=formula.evaluate(values)}catch(error){return result('invalid',error instanceof Error?error.message:'Invalid calculation.')}
    const source=!card.inputs.length?'Configured constant':archived?'Saved capture':sources.has('manual')?'Manual capture':'PLC capture';
    if(card.validation==='compare'){
      const difference=value-expected!;return {...result(Math.abs(difference)<=card.tolerance?'pass':'fail',`Calculated ${value}; comparison ${expected}; absolute tolerance ${card.tolerance}.`,value),expected,difference,source};
    }
    if(card.validation==='range')return {...result((card.minimum===null||value>=card.minimum)&&(card.maximum===null||value<=card.maximum)?'pass':'fail',`Configured limits: ${card.minimum??'no minimum'} to ${card.maximum??'no maximum'}.`,value),source};
    return {...result('ready','Value available. No validation condition is configured.',value),source};
  }catch(error){return result('pending',error instanceof Error?error.message:'Input unavailable.')}
}

export function parseDashboard(value:string):DashboardCard[]{
  const data=JSON.parse(value);if(data.schemaVersion!==1||!Array.isArray(data.cards)||data.cards.length>32)throw new Error('Unsupported dashboard layout.');
  const ids=new Set<string>();for(const card of data.cards){validateCard(card);if(ids.has(card.id))throw new Error('Duplicate dashboard card ID.');ids.add(card.id)}return data.cards;
}

export type PersonalDashboard={id:string;name:string;mode:'live'|'report';columns:number;cards:DashboardCard[]};
export type DashboardLibrary={schemaVersion:2;dashboards:PersonalDashboard[];migrated:string[]};
export const DASHBOARDS_KEY='nami_dashboards_v2';
export function parseLibrary(value:string):DashboardLibrary{
  const data=JSON.parse(value);
  if(new TextEncoder().encode(JSON.stringify(data)).byteLength>8*1024*1024)throw new Error('Keep dashboard configuration below 8 MB. Export or remove unused layouts.');
  if(data.schemaVersion!==2||!Array.isArray(data.dashboards)||data.dashboards.length<1||data.dashboards.length>20||!Array.isArray(data.migrated))throw new Error('Invalid dashboard library.');
  const ids=new Set<string>();
  for(const dashboard of data.dashboards){
    if(typeof dashboard.id!=='string'||!dashboard.id||ids.has(dashboard.id)||typeof dashboard.name!=='string'||!dashboard.name.trim()||dashboard.name.length>80||!['live','report'].includes(dashboard.mode)||!Number.isInteger(dashboard.columns)||dashboard.columns<1||dashboard.columns>4||!Array.isArray(dashboard.cards)||dashboard.cards.length>32)throw new Error('Invalid named dashboard.');
    ids.add(dashboard.id);const cardIds=new Set<string>();
    for(const card of dashboard.cards){validateCard(card);if(typeof card.targetId!=='string'||card.targetId.length>100||cardIds.has(card.id))throw new Error('Each widget needs a machine and unique ID.');cardIds.add(card.id)}
  }
  return data;
}
