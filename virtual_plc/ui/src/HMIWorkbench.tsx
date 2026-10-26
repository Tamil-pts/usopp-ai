import React,{useEffect,useState} from 'react';
import {Item,list,request,valueText} from './model';

export function HMIWorkbench({projectId,page,pages,layers,controls,selectedId,focusLayerId,onChoose,openSource}: {
  projectId:string;page:Item;pages:Item[];layers:Item;controls:Item;selectedId:string;focusLayerId:string;
  onChoose:(control:Item)=>void;openSource:(path:string,line?:number)=>void;
}){
  const [tab,setTab]=useState('layers'),[layerId,setLayerId]=useState(''),[query,setQuery]=useState(''),[details,setDetails]=useState<Item>({});
  const objects=list(page.objects),selected=objects.find(o=>o.id===selectedId),state=controls[selectedId]||{};
  useEffect(()=>{const controller=new AbortController();let busy=false;const load=async()=>{if(busy||document.hidden)return;busy=true;try{const result=await request(`/projects/${projectId}/hmi-inspect`,{method:'POST',signal:controller.signal,body:JSON.stringify({pageId:page.id,objectId:selectedId})});if(!controller.signal.aborted)setDetails(result);}catch{}finally{busy=false;}};setDetails({});void load();const timer=setInterval(()=>void load(),1500);return()=>{clearInterval(timer);controller.abort();};},[projectId,page.id,selectedId]);
  useEffect(()=>{setLayerId('');setQuery('');},[page.id]);
  useEffect(()=>{if(focusLayerId){setTab('layers');setLayerId(focusLayerId);}},[focusLayerId]);
  const binding=(name:string|undefined)=>name?<div className="hmi-binding"><code>{name}</code><b>{details.bindings?.[name]?.error||valueText(details.bindings?.[name]?.value??'—')}</b>{list(details.bindings?.[name]?.producers).slice(0,5).map((writer,i)=><button className="link" key={i} onClick={()=>openSource(writer.source,writer.line)}>{writer.source}:{writer.line}{writer.scheduled?'':' · not scheduled'}</button>)}</div>:null;
  return <aside className="hmi-workbench" aria-label="HMI runtime inspector">
    <header><strong>Layers & controls</strong><small>Live source configuration</small></header>
    <nav aria-label="HMI inspection panels">{['layers','keys'].map(t=><button key={t} className={tab===t?'active':''} onClick={()=>setTab(t)}>{t==='layers'?'Layers':'Virtual keys'}</button>)}</nav>
    <div className="hmi-workbench-content">
      {tab==='layers'&&list(page.layers).map(layer=>{const s=layers[layer.id]||{},word=s.statusWords?.layer;
        const switches:Item[]=pages.filter(p=>p.target===page.target).flatMap(p=>list(p.objects).filter(o=>list(o.actions).some(a=>layer.statusBinding&&a.variable===layer.statusBinding)).map(o=>({...o,pageName:p.name})));
        return <section className={`hmi-layer-card ${s.visible===false?'is-hidden':'is-visible'}`} key={layer.id}>
          <button className="hmi-layer-heading" aria-expanded={layerId===layer.id} onClick={()=>setLayerId(layerId===layer.id?'':layer.id)}><strong>{layer.name}</strong><span>{s.visible===undefined?'Waiting':s.visible===false?'Hidden':s.locked?'Visible · locked':'Visible'}</span></button>
          <small>Stack {layer.order??0}{word!==undefined?' · status '+word:''}</small>
          {layerId===layer.id&&<><p>{s.reason||s.visibilityReason}</p>{layer.statusBinding?binding(layer.statusBinding):<p>Always visible; no runtime status tag.</p>}
            <small>{switches.length?'Source controls that switch this layer:':'This layer follows its PLC program.'}</small>
            {switches.slice(0,8).map((o,i)=><button key={i} className="link" onClick={()=>openSource(o.keySource||o.source)}>{o.pageName} / {o.name}</button>)}
            <div className="hmi-layer-controls">{objects.filter(o=>o.layerState?.id===layer.id&&['button','hotspot','password','dropdown','numeric','string','alarm'].includes(o.kind)).map(o=><button key={o.id} className={selectedId===o.id?'active':''} onClick={()=>onChoose(o)}>{o.name}<small>{controls[o.id]?.visible===false?'Hidden':controls[o.id]?.locked?'Locked':o.kind}</small></button>)}</div>
          </>}
        </section>;
      })}
      {tab==='keys'&&<><input aria-label="Find HMI control or virtual key" placeholder="Find control or key…" value={query} onChange={e=>setQuery(e.target.value)}/>{objects.filter(o=>o.properties?.VirtualKey&&JSON.stringify([o.name,o.properties.VirtualKey,o.layer]).toLowerCase().includes(query.toLowerCase())).map(o=><button key={o.id} className={`hmi-key-choice ${selectedId===o.id?'active':''}`} onClick={()=>onChoose(o)}><strong>{o.name}</strong><small>{o.layer} · {o.properties.VirtualKey}</small><span>{controls[o.id]?.visible===false?'Hidden':controls[o.id]?.locked?'Locked':list(o.actions).some(a=>a.kind==='unsupported')?'Unsupported function':list(o.actions).length+' action(s)'}</span></button>)}</>}
      {selected&&<section className="hmi-control-detail" aria-label="Selected HMI control"><h3>{selected.name}</h3><small>{selected.layer} / {selected.kind}</small><p>{state.visible===false?state.visibilityReason:state.reason||'Visible; source input rules apply.'}</p>
        {list(selected.bindingNotices).map((note,i)=><p className="hmi-blocked" key={i}>{String(note)}</p>)}
        {state.coveredBy&&<p className="hmi-blocked">Covered by {state.coveredBy.layer} / <button className="link" onClick={()=>{const cover=objects.find(o=>o.id===state.coveredBy.id);if(cover)onChoose(cover);}}>{state.coveredBy.name}</button></p>}
        {selected.properties?.VirtualKey&&<><h4>Virtual key</h4><code>{selected.properties.VirtualKey}</code><ol>{list(selected.actions).map((a,i)=><li key={i}><strong>{a.kind==='unsupported'?'Unsupported: '+(a.function||a.classId):a.function||a.kind}</strong><code>{a.variable||a.page||a.control||a.classId}</code>{a.variable&&<span>Set {a.value}{a.resetValue!==undefined?' / reset '+a.resetValue:''}</span>}{a.command&&<span>{a.command}</span>}{a.reason&&<p>{a.reason}</p>}{a.properties?.Locking&&a.properties.Locking!=='Never'&&<p>Key permission: {a.properties.Locking} {a.properties.LockingLevel}</p>}</li>)}</ol>{!list(selected.actions).length&&<p>No source key action is configured for this control.</p>}<button onClick={()=>openSource(selected.keySource||selected.source)}>Open virtual key source</button></>}
        {[...new Set([selected.binding,selected.textIndexBinding,selected.statusBinding,selected.lockingBinding,selected.passwordLevelBinding,...list(selected.actions).map(a=>a.variable)].filter((v):v is string=>typeof v==='string'&&!!v))].map(name=><React.Fragment key={name}>{binding(name)}</React.Fragment>)}
      </section>}
    </div><footer>Visible layers follow PLC status bits. Select a control to inspect its key, permissions and PLC writers.</footer>
  </aside>;
}
