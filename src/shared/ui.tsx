import type {Status} from './types';

export function Badge({status}:{status:Status}){const label=status==='pass'?'Pass':status==='warn'?'Warning':status==='fail'?'Fail':'Not Found';return <span className={'badge '+status}><i className="dot"/>{label}</span>}
export function Detail({k,v,mono=false}:{k:string,v:any,mono?:boolean}){return <div className="detailBlock"><div className="k">{k}</div><div className={'v '+(mono?'mono':'')}>{v}</div></div>}
