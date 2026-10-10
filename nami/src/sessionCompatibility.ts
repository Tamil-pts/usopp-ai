const originalFetch=window.fetch.bind(window);
window.fetch=async(...args:Parameters<typeof fetch>)=>{
  const response=await originalFetch(...args);
  if(response.status===401){
    try{
      if(window.parent!==window)window.parent.dispatchEvent(new Event('usopp-session-expired'));
      else window.location.replace('/');
    }catch{window.location.replace('/');}
  }
  return response;
};
