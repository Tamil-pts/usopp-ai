import type {LayoutItem} from 'react-grid-layout';
export type Row=Record<string,any>;
export type Dimension={field:string;grain:string};
export type Metric={field:string;aggregation:string};
export type Filter={field:string;op:string;value:any};
export type GlobalFilters={project_id:string;engineer_id:string;from:string;to:string};
export type Query={source:string;dimensions:Dimension[];metrics:Metric[];filters:Filter[];global:GlobalFilters;limit:number;sort:string;mode:string;bin_count?:number};
export type Widget={id:string;type:string;title:string;query:Query;columns:string[];text:string;appearance:{colors:string[];legend:boolean;axes:boolean;horizontal:boolean;smooth:boolean;format:string;decimals:number;min:number;max:number;bins:number;x_label:string;y_label:string;series_types?:string[];secondary_axis?:boolean}};
export type Breakpoint='desktop'|'tablet'|'mobile';
export type Dashboard={schema_version:number;name:string;widgets:Widget[];layouts:Record<Breakpoint,LayoutItem[]>;filters:GlobalFilters;appearance:{theme:string;background:string;density:string;accent:string}};
export const COLS={desktop:12,tablet:8,mobile:4};
export const EMPTY_FILTERS:GlobalFilters={project_id:'',engineer_id:'',from:'',to:''};
export const clone=<T,>(v:T):T=>JSON.parse(JSON.stringify(v));
export const emptyDashboard=(name='My dashboard'):Dashboard=>({schema_version:1,name,widgets:[],layouts:{desktop:[],tablet:[],mobile:[]},filters:{...EMPTY_FILTERS},appearance:{theme:'inherit',background:'plain',density:'comfortable',accent:'#16a394'}});
export function makeWidget(type:string,registry:Row):Widget{
 const source=type==='documents'?'documents':type==='calendar'?'milestones':'projects',s=registry.sources[source];
 return {id:crypto.randomUUID().replaceAll('-',''),type,title:registry.widgets[type],text:'',columns:[],
 query:{source,dimensions:[{field:s.default_dimension,grain:s.default_dimension==='date'?'day':'value'}],metrics:[{field:s.default_metric,aggregation:s.default_aggregation}],filters:[],global:{...EMPTY_FILTERS},limit:100,sort:'dimension',mode:'aggregate'},
 appearance:{colors:['#16a394','#4269d0','#a383e3','#e8aa48','#d2657e'],legend:true,axes:true,horizontal:false,smooth:false,format:'number',decimals:0,min:0,max:100,bins:10,x_label:'',y_label:''}};
}
const collides=(a:LayoutItem,b:LayoutItem)=>a.x<b.x+b.w&&b.x<a.x+a.w&&a.y<b.y+b.h&&b.y<a.y+a.h;
export function settle(rows:LayoutItem[],cols:number):LayoutItem[]{
 const placed:LayoutItem[]=[];
 for(const r of rows){const row={i:r.i,x:Math.max(0,Math.min(cols-Math.min(cols,r.w),r.x)),y:Math.max(0,r.y),w:Math.max(1,Math.min(cols,r.w)),h:Math.max(2,Math.min(30,r.h))};
  while(placed.some(other=>collides(row,other)))row.y=Math.max(...placed.filter(other=>collides(row,other)).map(other=>other.y+other.h));placed.push(row);
 }return placed;
}
export function insertWidget(config:Dashboard,widget:Widget,bp?:Breakpoint,position?:LayoutItem){
 const next=clone(config);next.widgets.push(widget);
 for(const key of Object.keys(COLS) as Breakpoint[]){const rows=next.layouts[key];rows.push(bp===key&&position?{...position,i:widget.id}:{i:widget.id,x:0,y:Math.max(0,...rows.map(r=>r.y+r.h)),w:Math.min(key==='mobile'?4:6,COLS[key]),h:['kpi','progress','scorecard'].includes(widget.type)?3:6});next.layouts[key]=settle(rows,COLS[key]);}
 return next;
}
export function queryFor(widget:Widget,filters:GlobalFilters):Query{
 const raw=['table','gantt','roadmap','calendar','documents','scatter'].includes(widget.type);
 const combined={...widget.query.global};
 for(const k of Object.keys(filters) as (keyof GlobalFilters)[])if(filters[k])combined[k]=filters[k];
 combined.from=[widget.query.global.from,filters.from].filter(Boolean).sort().at(-1)||'';
 combined.to=[widget.query.global.to,filters.to].filter(Boolean).sort()[0]||'';
 return {...widget.query,global:combined,mode:widget.type==='histogram'?'histogram':raw?'records':'aggregate',bin_count:widget.appearance.bins};
}
export function formatValue(value:any,widget:Widget){
 if(value==null||!Number.isFinite(Number(value)))return 'Not enough information';
 const n=Number(value),a=widget.appearance;
 if(a.format==='bytes'){const unit=n>=1e9?'GB':n>=1e6?'MB':n>=1e3?'KB':'bytes',scale=unit==='GB'?1e9:unit==='MB'?1e6:unit==='KB'?1e3:1;return (n/scale).toLocaleString(undefined,{maximumFractionDigits:a.decimals})+' '+unit;}
 return n.toLocaleString(undefined,{minimumFractionDigits:a.decimals,maximumFractionDigits:a.decimals})+(a.format==='percent'?'%':a.format==='hours'?' h':'');
}
