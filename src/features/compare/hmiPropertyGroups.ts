/** Automation Studio property categories, shared by both HMI comparison views. */
export type HmiPropertyRow = {key:string; label:string; base:unknown; developed:unknown; changed:boolean};
export type HmiPropertyGroup = {id:string; label:string; rows:HmiPropertyRow[]; children:HmiPropertyGroup[]; count:number; changed:number};
type PropertyLocation = {group:string; child?:string; label?:string};
const ORDER=['Identity','Position','Bitmap','Appearance','Format','Value','Text Group','Input','Navigation / Virtual Key','Cursor','Runtime','Other'];
const normalize=(name:string)=>name.toLowerCase().replace(/[\s_.-]/g,'');

function location(name:string):PropertyLocation {
 const key=normalize(name);
 if(['name','id','controlname','controltype','class','classid','styleclass','description'].includes(key))return {group:'Identity'};
 if(['left','top','width','height','x','y','zorder','position'].includes(key))return {group:'Position'};
 if(key==='numlevel')return {group:'Bitmap'};
 if(key.includes('bitmap')){
  const labels:Record<string,string>={name:'Bitmap name',file:'Bitmap file',path:'Bitmap path',group:'BitmapGroup',index:'Preview index',status:'Preview status',note:'Preview note',indexnote:'Index note',sha256:'Image SHA256'};
  const resolved=key.replace(/^resolvedpressedbitmap|^resolvedbitmap/,'');
  const raw=name.replace(/^Pressed/,'');
  return {group:'Bitmap',child:key.includes('pressed')?'Pressed':'Released',label:key.startsWith('resolved')?labels[resolved]:raw==='BitmapOffset'?'BitmapIndexOffset':raw};
 }
 if(key.startsWith('alignment'))return {group:'Format',child:'Alignment',label:key==='alignmenthorizontal'?'Horizontal':key==='alignmentvertical'?'Vertical':undefined};
 if(key.includes('fraction')||key.includes('integerdigits')||key.includes('decimaldigits')||key.startsWith('format')||key==='unittext')return {group:'Format'};
 if(key.includes('color')||key.includes('font')||['border','fillstyle','linestyle','linewidth','appearance','shape','opacity'].includes(key))return {group:'Appearance'};
 if(key.startsWith('completion')||['oncomplete','complete'].includes(key))return {group:'Runtime',child:'Completion',label:key==='completiondatapoint'?'Datapoint':key==='completionvalue'?'Value':undefined};
 if(key.startsWith('lock')||key.includes('password'))return {group:'Runtime',child:'Locking',label:key==='lockingdatapoint'?'Datapoint':key==='lockingvalue'?'Value':undefined};
 if(key.startsWith('input')||['confirm','cancel','touchpad'].includes(key))return {group:'Input'};
 if(key.startsWith('virtualkey')||key.includes('target')||key.startsWith('navigation'))return {group:'Navigation / Virtual Key'};
 if(key.startsWith('cursor'))return {group:'Cursor'};
 if(key.startsWith('runtime')||key.includes('status')||['controlid','eventtrigger','onclick','updateinterval','updatetime','updatedatapoint','simulationindex'].includes(key))return {group:'Runtime'};
 if(key.startsWith('value')||['minvalue','maxvalue','mindatapoint','maxdatapoint','teachdatapoint','simulationvalue','minmaxviolation','indexdatapoint','indexmap'].includes(key))return {group:'Value',label:key==='valuedatapoint'?'Datapoint':undefined};
 if(key.includes('textgroup')||key.startsWith('text')||key.includes('language'))return {group:'Text Group'};
 return {group:'Other'};
}

const PROPERTY_ORDER=['Name','StyleClass','ClassId','Description','Left','Top','Width','Height',
 'BitmapSource','BitmapGroup','BitmapOffset','BitmapIndexOffset','BitmapIndex','Bitmap',
 'ResolvedBitmapName','ResolvedBitmapFile','ResolvedBitmapIndex','ResolvedBitmapStatus','ResolvedBitmapNote','ResolvedBitmapIndexNote',
 'PressedBitmapSource','PressedBitmapGroup','PressedBitmapOffset','PressedBitmapIndexOffset','PressedBitmapIndex','PressedBitmap',
 'ResolvedPressedBitmapName','ResolvedPressedBitmapFile','ResolvedPressedBitmapIndex','ResolvedPressedBitmapStatus','ResolvedPressedBitmapNote','ResolvedPressedBitmapIndexNote',
 'Border','ForeColor','BackColor','ColorMap','ColorDatapoint','Font','AlignmentHorizontal','AlignmentVertical','MinIntegerDigits','AddFractionDigits','AddFractionDigitsDatapoint','UnitText','Value','ValueDatapoint','MinValue','MinDatapoint','MaxValue','MaxDatapoint','TeachDatapoint','SimulationValue','MinMaxViolation','Input','InputTouchpad','InputNext','ControlID','StatusDatapoint','CompletionDatapoint','CompletionValue'];
const rank=new Map(PROPERTY_ORDER.map((key,index)=>[normalize(key),index]));

export function groupHmiProperties(base:Record<string,unknown>,developed:Record<string,unknown>,skip:(key:string)=>boolean=()=>false):HmiPropertyGroup[] {
 const groups=new Map<string,HmiPropertyGroup>();
 for(const key of new Set([...Object.keys(base),...Object.keys(developed)])) {
  if(skip(key))continue;
  const place=location(key);
  let group=groups.get(place.group);
  if(!group){group={id:place.group,label:place.group,rows:[],children:[],count:0,changed:0};groups.set(place.group,group)}
  let target=group;
  if(place.child){
   let child=group.children.find(item=>item.label===place.child);
   if(!child){child={id:place.group+'/'+place.child,label:place.child,rows:[],children:[],count:0,changed:0};group.children.push(child)}
   target=child;
  }
  const changed=base[key]!==developed[key];
  target.rows.push({key,label:place.label||key,base:base[key],developed:developed[key],changed});
  group.count++;if(changed)group.changed++;
  if(target!==group){target.count++;if(changed)target.changed++}
 }
 const sort=(rows:HmiPropertyRow[])=>rows.sort((a,b)=>(rank.get(normalize(a.key))??999)-(rank.get(normalize(b.key))??999)||a.key.localeCompare(b.key));
 for(const group of groups.values()){
  sort(group.rows);
  group.children.sort((a,b)=>group.id==='Bitmap'?['Released','Pressed'].indexOf(a.label)-['Released','Pressed'].indexOf(b.label):a.label.localeCompare(b.label));
  for(const child of group.children)sort(child.rows);
 }
 return [...groups.values()].sort((a,b)=>ORDER.indexOf(a.id)-ORDER.indexOf(b.id));
}
