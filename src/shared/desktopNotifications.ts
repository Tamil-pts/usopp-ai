type Event={id:string;title:string;body:string;thread?:string};
const known=new Map<string,Set<string>>();
export function desktopStatus(){return !('Notification' in window)?'unavailable':!window.isSecureContext?'secure-connection-required':Notification.permission;}
export async function enableDesktop(){const status=desktopStatus();if(status==='unavailable'||status==='secure-connection-required')throw Error('System alerts need a supported browser on HTTPS or localhost.');const result=await Notification.requestPermission();if(result!=='granted')throw Error('System notifications are blocked. Allow them in this site’s browser settings.');return result;}
export function testDesktop(){if(desktopStatus()!=='granted')throw Error('Enable system alerts first.');const alert=new Notification('uSOPp.ai test notification',{body:'System notifications are enabled for this browser.',tag:'usopp-notification-test'});setTimeout(()=>alert.close(),10000);}
export function notifyNew(user:number,stream:string,events:Event[],onOpen:(event:Event)=>void){
 const key=user+':'+stream,previous=known.get(key);known.set(key,new Set([...(previous||[]),...events.map(e=>e.id)].slice(-1000)));
 // Opening/reloading the app establishes a baseline, never replays old alerts.
 if(!previous||desktopStatus()!=='granted')return;
 for(const event of events){if(previous.has(event.id))continue;const claim='usopp-desktop-alert:'+user+':'+stream+':'+event.id;try{const ledger='usopp-desktop-alerts:'+key;const seen:string[]=JSON.parse(localStorage.getItem(ledger)||'[]');if(seen.includes(event.id))continue;localStorage.setItem(ledger,JSON.stringify([...seen,event.id].slice(-500)));}catch{}
  try{const notification=new Notification(event.title,{body:event.body,tag:claim});notification.onclick=()=>{window.focus();onOpen(event);notification.close();};setTimeout(()=>notification.close(),12000);}catch{/* In-app unread records remain available when OS delivery is unavailable. */}
 }
}
