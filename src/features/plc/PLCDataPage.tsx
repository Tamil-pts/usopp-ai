import {useEffect, useState} from 'react';

export function PLCDataPage({theme, setTheme,historyId='',onLive}:{theme:'light'|'dark';setTheme:(theme:'light'|'dark')=>void;historyId?:string;onLive:()=>void}){
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
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
    <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:12,marginBottom:8}}>
      <span>DataInspect · PLC packet and metadata checks</span>
      <div style={{display:'flex',gap:8}}>
        {historyId&&<button className="btn primary" onClick={onLive}>New live test</button>}
        <button className="btn" onClick={()=>setTheme(theme==='light'?'dark':'light')}>{theme==='light'?'Dark mode':'Light mode'}</button>

      </div>
    </div>
    <iframe key={historyId} title="Nami PLC Data Verification V1.5" src={`/nami/index.html${historyId?'?historyId='+encodeURIComponent(historyId):''}`} style={{width:'100%',height:'100%',minHeight:0,flex:1,border:0,display:'block',background:theme==='light'?'#ffffff':'#020617'}}/>
  </div>;
}
