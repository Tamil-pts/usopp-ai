export type ChangeStatus='all'|'differences'|'modified'|'added'|'removed'|'unchanged';
export type SourceRow={base_line:number|null;new_line:number|null;base:string|null;new:string|null;status:string;gap?:boolean;contextOnly?:boolean};
export const matchesChange=(status:string,filter:ChangeStatus)=>filter==='all'||filter==='differences'?filter==='all'||['modified','added','removed'].includes(status):status===filter;
export function visibleSourceRows(rows:SourceRow[],mode:'source'|'difference',filter:ChangeStatus,context=5):SourceRow[]{
 if(mode==='source'&&filter==='all')return rows;
 const match=(row:SourceRow)=>matchesChange(row.status,filter==='all'?'differences':filter);
 const selected=new Set<number>();
 rows.forEach((row,index)=>{if(match(row))for(let i=Math.max(0,index-context);i<Math.min(rows.length,index+context+1);i++)selected.add(i);});
 const result:SourceRow[]=[];let previous=-1;
 for(const index of selected){if(previous>=0&&index>previous+1)result.push({base_line:null,new_line:null,base:null,new:null,status:'gap',gap:true});result.push({...rows[index],contextOnly:rows[index].status!=='unchanged'&&!match(rows[index])});previous=index;}
 return result;
}
