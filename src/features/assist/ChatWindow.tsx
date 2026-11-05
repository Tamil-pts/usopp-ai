import {useEffect,useRef,useState,type ReactNode} from 'react';
import {createPortal} from 'react-dom';
import {Bot,ExternalLink,Maximize2,Minimize2,PanelLeft,Plus,Upload,Minus} from 'lucide-react';

export function useChatWindow(){
 const [docked,setDocked]=useState(false),[host,setHost]=useState<HTMLElement|null>(null),[error,setError]=useState('');
 const popup=useRef<Window|null>(null),closing=useRef<(()=>void)|null>(null);
 function restore(){if(popup.current&&!popup.current.closed)popup.current.close();popup.current=null;setHost(null);setDocked(false);}
 function popOut(){
  if(popup.current&&!popup.current.closed){popup.current.focus();return;}
  const target=window.open('about:blank','usopp-chopper','popup,width=1380,height=920,resizable=yes,scrollbars=yes');
  if(!target){setError('The browser blocked the pop-out. Allow pop-ups for this local server, then try again.');return;}
  setError('');target.document.title='Chopper · Engineering & data workspace';target.document.documentElement.lang=document.documentElement.lang||'en';
  target.document.documentElement.dataset.theme=document.documentElement.dataset.theme;target.document.documentElement.style.cssText=document.documentElement.style.cssText;
  const base=target.document.createElement('base');base.href=window.location.origin+'/';target.document.head.append(base);
  document.querySelectorAll('link[rel=stylesheet],style').forEach(node=>target.document.head.append(node.cloneNode(true)));
  const viewport=target.document.createElement('meta');viewport.name='viewport';viewport.content='width=device-width,initial-scale=1';target.document.head.append(viewport);
  target.document.body.style.margin='0';target.document.body.className='chopperPopoutBody';
  const container=target.document.createElement('main');container.className='workspaceApp studioPopoutHost';target.document.body.append(container);
  popup.current=target;closing.current=()=>{popup.current=null;setHost(null);};target.addEventListener('beforeunload',closing.current);setDocked(false);setHost(container);
 }
 useEffect(()=>()=>{if(popup.current){if(closing.current)popup.current.removeEventListener('beforeunload',closing.current);popup.current.close();}},[]);
 useEffect(()=>{
  if(!host)return;const check=()=>{if(!popup.current||popup.current.closed){popup.current=null;setHost(null);}};
  const timer=window.setInterval(check,400);window.addEventListener('focus',check);
  return()=>{window.clearInterval(timer);window.removeEventListener('focus',check);};
 },[host]);
 function minimize(){restore();setDocked(true);}
 function render(content:ReactNode){return <>{docked&&<button type="button" className="chopperDock" onClick={()=>setDocked(false)} aria-label="Restore Chopper chat"><Bot size={21}/><span><b>Chopper</b><small>Your chat and workbooks are here</small></span><Maximize2 size={16}/></button>}{host&&<div className="studioPopoutPlaceholder"><Bot size={30}/><h2>Chopper is open in its own window</h2><p>Your conversation and worksheets stay connected to this workspace.</p><button type="button" className="btn" onClick={()=>popup.current?.focus()}>Focus window</button><button type="button" className="btn primary" onClick={restore}>Return to workspace</button></div>}{host?createPortal(content,host):content}</>;}
 return {docked,popped:!!host,error,popOut,restore,minimize,render};
}

export function ChatWindowControls({onUpload,onNew,onTools,tools,onMinimize,fullscreen,onFullscreen,popped,onPopOut,onRestore}:{onUpload:()=>void;onNew:()=>void;onTools:()=>void;tools:boolean;onMinimize:()=>void;fullscreen:boolean;onFullscreen:()=>void;popped:boolean;onPopOut:()=>void;onRestore:()=>void}){
 return <div className="studioWindowControls"><button type="button" className="btn studioUploadButton" onClick={onUpload}><Upload size={16}/><span>Upload file</span></button><button type="button" className="studioIconButton" title="New chat" aria-label="New chat" onClick={onNew}><Plus size={18}/></button><button type="button" className="studioIconButton" title="Engineering tools" aria-label="Show engineering tools" aria-pressed={tools} onClick={onTools}><PanelLeft size={17}/></button><span className="studioControlDivider"/><button type="button" className="studioIconButton" aria-label="Minimize chat" title="Minimize to dock" onClick={onMinimize}><Minus size={18}/></button><button type="button" className="studioIconButton" aria-label={fullscreen?'Restore chat size':'Expand chat to full screen'} title={fullscreen?'Restore':'Full screen'} onClick={onFullscreen}>{fullscreen?<Minimize2 size={17}/>:<Maximize2 size={17}/>}</button><button type="button" className="studioIconButton" aria-label={popped?'Return chat to workspace':'Pop out chat'} title={popped?'Return to workspace':'Pop out'} onClick={popped?onRestore:onPopOut}><ExternalLink size={17}/></button></div>;
}
