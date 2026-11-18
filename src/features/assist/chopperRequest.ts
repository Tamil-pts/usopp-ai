export async function requestChopper(payload:unknown,signal:AbortSignal,onProgress:(value:any)=>void) {
 const startedAt=performance.now();
 const options={method:'POST',signal,headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)};
 const response=await fetch('/api/assist/start',options);
 if(response.status===404||response.status===405) {
  // Older running servers still expose the synchronous chat route.
  const timer=setInterval(()=>onProgress({stage:'Processing project question',elapsedSeconds:Math.round((performance.now()-startedAt)/100)/10}),500);
  try {
   const legacy=await fetch('/api/assist',options);const data=await legacy.json().catch(()=>({}));
   if(legacy.status===404||legacy.status===405)throw new Error('The running server needs a chat update. Stop and restart the updated uSOPp application.');
   if(!legacy.ok)throw new Error(data.detail||'Chopper could not process this question.');
   return {result:data,elapsedSeconds:Math.round((performance.now()-startedAt)/100)/10};
  }finally{clearInterval(timer);}
 }
 const data=await response.json().catch(()=>({}));
 if(!response.ok)throw new Error(data.detail||'Chopper is unavailable.');
 if(!data.jobId)throw new Error('The running server returned an incomplete chat request. Restart the updated application.');
 const cancel=()=>{void fetch('/api/assist/cancel/'+encodeURIComponent(data.jobId),{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',keepalive:true}).catch(()=>{})};
 signal.addEventListener('abort',cancel,{once:true});
 try{
 while(!signal.aborted) {
  const poll=await fetch(`/api/assist/status/${encodeURIComponent(data.jobId)}`,{signal,cache:'no-store'});
  const status=await poll.json().catch(()=>({}));
  if(status.status==='stopped')throw new DOMException('Request cancelled','AbortError');
  if(!poll.ok||status.status==='error')throw new Error(status.error||status.detail||'Chopper processing failed.');
  onProgress(status);
  if(status.status==='complete')return status;
  await new Promise<void>(resolve=>setTimeout(resolve,700));
 }
 throw new DOMException('Request cancelled','AbortError');
 }finally{signal.removeEventListener('abort',cancel)}
}
