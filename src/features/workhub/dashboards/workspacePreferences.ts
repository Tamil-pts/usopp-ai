import {userStorage,flushUserStorage,storageStatus} from '../../../shared/userStorage';

export const NAV_KEY='usopp_workhub_overview_navigation_v1';
export const PROJECT_KEY='usopp_workhub_project_dashboard_v1';
export type Navigation={order:string[];hidden:string[];defaultId:string};
export type ProjectPresentation={id:string;visible:boolean};
const ids=(value:unknown):string[]=>Array.isArray(value)?[...new Set(value.filter((v):v is string=>typeof v==='string'&&v.length>0&&v.length<=64))].slice(0,500):[];
function read(key:string){try{const value=JSON.parse(userStorage.getItem(key)||'{}');return value&&typeof value==='object'&&!Array.isArray(value)?value:{};}catch{return {};}}
export function projectPresentation():ProjectPresentation{const v=read(PROJECT_KEY);return {id:typeof v.id==='string'?v.id:'',visible:v.visible!==false};}
export function navigation(available:string[]):Navigation{
 const v=read(NAV_KEY),valid=new Set(available),order=[...ids(v.order).filter(id=>valid.has(id)),...available.filter(id=>!ids(v.order).includes(id))];
 let hidden=ids(v.hidden).filter(id=>valid.has(id));if(order.every(id=>hidden.includes(id)))hidden=hidden.filter(id=>id!==order[0]);
 const shown=order.filter(id=>!hidden.includes(id));return {order,hidden,defaultId:shown.includes(v.defaultId)?v.defaultId:shown.includes('portfolio')?'portfolio':shown[0]||'portfolio'};
}
export async function savePreference(key:string,value:unknown){
 userStorage.setItem(key,JSON.stringify(value));await flushUserStorage();
 // Another settings save may already be draining the shared queue.
 if(storageStatus().saving)await new Promise<void>((resolve,reject)=>{
  const finish=()=>{if(storageStatus().saving)return;clearTimeout(timer);window.removeEventListener('usopp-storage-status',finish);resolve();};
  const timer=setTimeout(()=>{window.removeEventListener('usopp-storage-status',finish);reject(Error('Dashboard preferences are still saving. Check the connection before reloading.'));},15000);
  window.addEventListener('usopp-storage-status',finish);finish();
 });
 const status=storageStatus();if(status.error||status.pending)throw Error(status.error||'Dashboard preferences have not reached the server yet.');
 window.dispatchEvent(new Event('workhub-dashboard-layouts'));
}
