import type {HubRow} from './projectApi';

export type ProjectDateRange={date_field:string;from_date:string;to_date:string};
export const EMPTY_PROJECT_DATES:ProjectDateRange={date_field:'due_date',from_date:'',to_date:''};
export const PROJECT_DATE_FIELDS=[
 {id:'due_date',label:'Due date'}, {id:'start_date',label:'Planned start date'},
 {id:'started_at',label:'Actual start date'}, {id:'completed_at',label:'Closure date'},
 {id:'created_at',label:'Created date'}, {id:'updated_at',label:'Last updated date'},
];
export function projectDateOptions(projects:HubRow[]){
 const custom=new Map<string,string>();
 for(const p of projects)for(const f of p.custom_fields||[])if(f.type==='date')custom.set(f.id,f.label);
 return [...PROJECT_DATE_FIELDS,...[...custom].sort((a,b)=>a[1].localeCompare(b[1])).map(([id,label])=>({id,label:'Custom: '+label}))];
}
export function projectDate(row:HubRow,field:string):string{
 if(field==='completed_at'&&row.stage!=='released')return '';
 const raw=field.startsWith('custom_')?(row.custom_fields||[]).find((f:HubRow)=>f.id===field&&f.type==='date')?.value:row[field];
 const value=typeof raw==='string'?raw.slice(0,10):'';
 return /^\d{4}-\d{2}-\d{2}$/.test(value)?value:'';
}
export function matchesProjectDates(row:HubRow,range:ProjectDateRange){
 if(!range.from_date&&!range.to_date)return true;
 if(range.from_date&&range.to_date&&range.from_date>range.to_date)return false;
 const value=projectDate(row,range.date_field);
 return !!value&&(!range.from_date||value>=range.from_date)&&(!range.to_date||value<=range.to_date);
}
