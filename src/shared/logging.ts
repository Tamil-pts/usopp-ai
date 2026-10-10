export function logEvent(event:string,details:any={}){
  try{ fetch('/api/log',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({event,details})}).catch(()=>{}); }catch{}
}
