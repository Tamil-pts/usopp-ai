import {useEffect,useState} from 'react';
import {hub,type HubRow} from '../projectApi';
import {studio} from './api';
export function TemplatePicker({project,document,kind,editable,flush,changed}:{project:string;document:string;kind:string;editable:boolean;flush:()=>Promise<void>;changed:()=>Promise<void>}){
 const [items,setItems]=useState<HubRow[]>([]),[selected,setSelected]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 useEffect(()=>{let active=true;void hub('/studio/templates').then(value=>{if(active)setItems(value.items.filter((t:HubRow)=>t.active&&t.kind===kind));}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[project,document,kind]);
 const apply=async()=>{setBusy(true);setError('');setMessage('');try{await flush();const metadata=await studio(project,document);await studio(project,document,'/templates/'+selected+'/apply',{revision_id:metadata.revision.id,version:metadata.revision.version});await changed();setMessage('Template applied to the current draft.');}catch(e){setError((e as Error).message);}finally{setBusy(false);}};
 if(!items.length&&!error)return null;
 return <div className="actions"><label>Document template<select aria-label="Document template" className="textInput" value={selected} disabled={!editable||busy} onChange={e=>setSelected(e.target.value)}><option value="">Choose a template</option>{items.map(t=><option key={t.id} value={t.id}>{t.name} · v{t.version}</option>)}</select></label><button className="btn" disabled={!editable||busy||!selected} onClick={()=>void apply()}>Apply template</button>{message&&<small role="status">{message}</small>}{error&&<small className="wh-error" role="alert">{error}</small>}</div>;
}
