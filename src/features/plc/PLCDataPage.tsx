import {useEffect, useLayoutEffect, useRef, useState} from 'react';

export function PLCDataPage({theme,historyId='',onLive,onContext}:{theme:'light'|'dark';historyId?:string;onLive:()=>void;onContext?:(value:Record<string,unknown>)=>void}){
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const frame=useRef<HTMLIFrameElement>(null);
  useLayoutEffect(()=>()=>{
    // Dispose React portals and document listeners before removing the frame.
    try{frame.current?.contentWindow?.dispatchEvent(new Event('usopp:datainspect-dispose'));}
    catch{/* A frame that has already navigated away has no selector to dispose. */}
  },[]);
  useEffect(()=>{
    onContext?.({});
    const receive=(event:MessageEvent)=>{
      if(event.origin!==window.location.origin||event.source!==frame.current?.contentWindow||event.data?.type!=='usopp:datainspect-context')return;
      const supplied=event.data.context;if(!supplied||typeof supplied!=='object')return;
      const safe:Record<string,unknown>={};
      for(const key of ['view','dialog','target','machine','groupCode','captureTime','captureSource','captureStatus','dataCheckStatus','findingSummary','parameterCount']){
        if(typeof supplied[key]==='string')safe[key]=supplied[key].slice(0,300);
        else if(typeof supplied[key]==='number'&&Number.isFinite(supplied[key]))safe[key]=supplied[key];
      }
      onContext?.(safe);
    };
    window.addEventListener('message',receive);return()=>window.removeEventListener('message',receive);
  },[onContext,historyId]);
  useEffect(() => {
    const controller = new AbortController();
    // Request the actual feature document. Older running backends otherwise
    // return the uSOPp SPA for /nami/, nesting the whole app indefinitely.
    fetch('/nami/index.html', {cache:'no-store', signal:controller.signal})
      .then(async response => {
        const html = await response.text();
        if (!response.ok || !html.includes('/nami/assets/')) {
          throw new Error('The PLC Data interface is unavailable. Rebuild the interface and restart uSOPp.ai.');
        }
        setReady(true);
      })
      .catch(reason => {
        if (!controller.signal.aborted) setError(reason.message || 'Could not load PLC Data.');
      });
    return () => controller.abort();
  }, []);
  if (error) return <div className="card" role="alert"><h2>DataInspect</h2><p>{error}</p></div>;
  if (!ready) return <p role="status">Loading PLC Data…</p>;
  return <div className="plcWorkspace">
    {historyId&&<div className="plcHistoryActions"><button className="btn primary" onClick={onLive}>New live test</button></div>}
    <iframe ref={frame} key={historyId} title="Nami PLC Data Verification V1.5" src={`/nami/index.html${historyId?'?historyId='+encodeURIComponent(historyId):''}`} style={{width:'100%',height:'100%',minHeight:0,flex:1,border:0,display:'block',background:theme==='light'?'#ffffff':'#020617'}}/>
  </div>;
}
