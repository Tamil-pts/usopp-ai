import {useEffect,useRef} from 'react';
const blockers=new Set<()=>boolean>();
export function confirmNavigation(){return ![...blockers].some(check=>check())||window.confirm('You have unsaved changes. Leave this screen? Save your document first to retain a shared revision.');}
export function useUnsavedChanges(dirty:boolean|(()=>boolean)){const latest=useRef(dirty);latest.current=dirty;useEffect(()=>{const check=()=>typeof latest.current==='function'?latest.current():latest.current;blockers.add(check);return()=>{blockers.delete(check);};},[]);}
let installed=false,index=0,accepted='',restoring=false;
export const routeEvent='usopp-route-change';
export function installNavigation(){if(installed)return;installed=true;try{index=Number.isInteger(history.state?.usoppIndex)?history.state.usoppIndex:Number(sessionStorage.getItem('usopp-history-index')||'-1')+1;sessionStorage.setItem('usopp-history-index',String(index));}catch{index=Number(history.state?.usoppIndex)||0;}accepted=location.href;history.replaceState({...history.state,usoppIndex:index},'',location.href);
 window.addEventListener('popstate',()=>{if(restoring){restoring=false;return;}const next=Number(history.state?.usoppIndex);if(!confirmNavigation()){if(Number.isFinite(next)&&next!==index){restoring=true;history.go(index-next);}else history.replaceState({...history.state,usoppIndex:index},'',accepted);return;}index=Number.isFinite(next)?next:index;accepted=location.href;try{sessionStorage.setItem('usopp-history-index',String(index));}catch{}window.dispatchEvent(new Event(routeEvent));});
 window.addEventListener('beforeunload',event=>{if([...blockers].some(check=>check())){event.preventDefault();event.returnValue='';}});
 // Backspace edits fields; it must not activate legacy browser history shortcuts.
 window.addEventListener('keydown',event=>{const el=event.target as HTMLElement;if(event.key==='Backspace'&&!el.closest('input,textarea,[contenteditable=true]'))event.preventDefault();});
}
export function navigateRoute(patch:Record<string,string|null>,options:{replace?:boolean;guard?:boolean}={}){installNavigation();const url=new URL(location.href);for(const [key,value] of Object.entries(patch)){if(value)url.searchParams.set(key,value);else url.searchParams.delete(key);}if(url.href===location.href)return true;if(options.guard!==false&&!confirmNavigation())return false;
 if(!options.replace)index++;history[options.replace?'replaceState':'pushState']({...history.state,usoppIndex:index},'',url);accepted=url.href;try{sessionStorage.setItem('usopp-history-index',String(index));}catch{}window.dispatchEvent(new Event(routeEvent));return true;}
export function routeParams(){return new URLSearchParams(location.search);}
