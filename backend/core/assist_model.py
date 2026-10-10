"""Optional Chopper model transport. Local engineering tools are independent."""
import base64
import ctypes
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests
from fastapi import HTTPException
from backend.core.runtime import BASE

CONFIG=BASE/'.usopp_assist_model.json'
LOCK=threading.RLock()
CPU_QUEUE=threading.BoundedSemaphore(5)
CPU_GENERATION=threading.Lock()

def _protect(value, decrypt=False):
    if os.name!='nt': return value
    class Blob(ctypes.Structure):
        _fields_=[('size',ctypes.c_ulong),('data',ctypes.POINTER(ctypes.c_ubyte))]
    raw=base64.b64decode(value) if decrypt else value.encode('utf-8')
    buffer=ctypes.create_string_buffer(raw)
    source=Blob(len(raw),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)))
    output=Blob()
    function=ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(output)):
        raise ValueError('Cannot access the model credential for this Windows account.')
    try:
        result=ctypes.string_at(output.data,output.size)
        return result.decode('utf-8') if decrypt else base64.b64encode(result).decode('ascii')
    finally:
        ctypes.windll.kernel32.LocalFree(output.data)

def configuration():
    with LOCK:
        if CONFIG.exists():
            try: return json.loads(CONFIG.read_text(encoding='utf-8'))
            except (OSError,ValueError): raise HTTPException(503,'Model settings cannot be read. Save them again in Settings.')
    url=os.getenv('USOPP_LLM_BASE_URL','').rstrip('/')
    return {'provider':os.getenv('USOPP_LLM_PROVIDER','ollama') if url else 'local',
            'baseUrl':url or 'http://127.0.0.1:11434','model':os.getenv('USOPP_LLM_MODEL','qwen3:8b')}

def public_configuration():
    cfg=configuration()
    return {k:cfg.get(k,'') for k in ('provider','baseUrl','model','modelPath')}|{'localPort':cfg.get('localPort',8202),'contextSize':cfg.get('contextSize',4096),'cpuThreads':cfg.get('cpuThreads',min(4,os.cpu_count() or 2)),'maxTokens':cfg.get('maxTokens',512),'autoStart':bool(cfg.get('autoStart',False)),'hasApiKey':bool(cfg.get('apiKeyProtected') or cfg.get('apiKey') or os.getenv('USOPP_LLM_API_KEY'))}

def save_configuration(payload):
    provider=payload.get('provider','local')
    if provider not in {'local','embedded','ollama','api'}: raise HTTPException(400,'Choose local tools, Chopper local model, Ollama or an API model.')
    if provider=='embedded':
        try:port=int(payload.get('localPort',8202));context=int(payload.get('contextSize',4096))
        except (TypeError,ValueError):raise HTTPException(400,'Enter numeric local port and context size.')
        if not 8200<=port<=8500 or not 512<=context<=32768:raise HTTPException(400,'Port: 8200–8500; context: 512–32768 tokens.')
        payload={**payload,'baseUrl':f'http://127.0.0.1:{port}/v1','model':'chopper-local'}
    try:
        threads=int(payload.get('cpuThreads') or min(4,os.cpu_count() or 2))
        max_tokens=int(payload.get('maxTokens') or 512)
    except (TypeError,ValueError):raise HTTPException(400,'Enter numeric CPU threads and answer tokens.')
    if not 1<=threads<=64 or not 64<=max_tokens<=2048:raise HTTPException(400,'CPU threads: 1–64; answer tokens: 64–2048.')
    url=str(payload.get('baseUrl','')).strip().rstrip('/')
    parsed=urlsplit(url)
    if provider!='local' and (parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise HTTPException(400,'Enter an HTTP/HTTPS base URL without credentials, query or fragment.')
    model=str(payload.get('model','')).strip()
    if provider!='local' and (not model or len(model)>200): raise HTTPException(400,'Enter an installed model or provider model ID.')
    with LOCK:
        existing=configuration()
        if any(existing.get(k)!=payload.get(k) for k in ('provider','modelPath','localPort','contextSize','cpuThreads')):
            from backend.core.local_model_runtime import stop
            stop()
        cfg={'provider':provider,'baseUrl':url,'model':model}
        cfg.update({'modelPath':str(payload.get('modelPath') or ''),'localPort':int(payload.get('localPort') or 8202),'contextSize':int(payload.get('contextSize') or 4096)})
        cfg.update(cpuThreads=threads,maxTokens=max_tokens,autoStart=payload.get('autoStart') is True)
        if not payload.get('clearApiKey'):
            for key in ('apiKeyProtected','apiKey'):
                if existing.get(key): cfg[key]=existing[key]
        key=str(payload.get('apiKey','')).strip()
        if len(key)>4096: raise HTTPException(400,'API key is too long.')
        if key:
            cfg.pop('apiKey',None);cfg.pop('apiKeyProtected',None)
            cfg['apiKeyProtected' if os.name=='nt' else 'apiKey']=_protect(key)
        fd,name=tempfile.mkstemp(prefix='.usopp-model-',dir=BASE)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as stream: json.dump(cfg,stream)
            os.chmod(name,0o600);os.replace(name,CONFIG)
        finally:
            if Path(name).exists(): Path(name).unlink()
    return public_configuration()

def _key(cfg):
    return (_protect(cfg['apiKeyProtected'],True) if cfg.get('apiKeyProtected') else cfg.get('apiKey')) or os.getenv('USOPP_LLM_API_KEY','')

def chat_model(system,prompt,history=None,timeout=120):
    cfg=configuration()
    if cfg['provider']=='local': return None
    if cfg['provider']=='embedded':
        from backend.core.local_model_runtime import status
        if not status()['ready']:raise ValueError('Start the Chopper local model in Settings and wait until it is ready.')
    messages=[{'role':'system','content':system}]
    for item in (history if isinstance(history,list) else [])[-12:]:
        if isinstance(item,dict) and item.get('role') in {'user','assistant'} and isinstance(item.get('content'),str):
            messages.append({'role':item['role'],'content':item['content'][:8000]})
    messages.append({'role':'user','content':prompt})
    headers={}
    if cfg['provider']=='api' and _key(cfg): headers['Authorization']='Bearer '+_key(cfg)
    suffix='/api/chat' if cfg['provider']=='ollama' else '/chat/completions'
    body={'model':cfg['model'],'messages':messages,'stream':False}
    if cfg['provider']=='ollama':
        # Preserve the system/evidence instructions when project retrieval adds
        # more context than a service's default window. Bound the answer length.
        body['options']={'num_ctx':max(8192,int(cfg.get('contextSize') or 4096)),
                         'num_predict':900,'temperature':0.1}
    if cfg['provider']=='embedded':
        body.update(max_tokens=int(cfg.get('maxTokens') or 512),temperature=0.1,cache_prompt=False)
        # Five independent request bodies; one CPU generation at a time.
        # Waiting for the model never takes a validation worker lock.
        if not CPU_QUEUE.acquire(blocking=False):raise ValueError('Chopper CPU queue is full. Try again after another answer completes.')
        acquired=False;started=time.monotonic()
        try:
            acquired=CPU_GENERATION.acquire(timeout=min(30,timeout))
            if not acquired:raise ValueError('Chopper CPU model is busy. Try again shortly; validation remains available.')
            remaining=max(1,timeout-(time.monotonic()-started))
            response=requests.post(cfg['baseUrl']+suffix,json=body,headers=headers,timeout=remaining,allow_redirects=False)
        finally:
            if acquired:CPU_GENERATION.release()
            CPU_QUEUE.release()
    else:
        response=requests.post(cfg['baseUrl']+suffix,json=body,headers=headers,timeout=timeout,allow_redirects=False)
    if response.status_code!=200: raise ValueError(f'Model endpoint returned HTTP {response.status_code}. Check its base URL, model and credential.')
    data=response.json()
    answer=(data.get('message',{}).get('content') or data.get('response','')) if cfg['provider']=='ollama' else data.get('choices',[{}])[0].get('message',{}).get('content','')
    if not isinstance(answer,str) or not answer.strip(): raise ValueError('The model returned no text answer.')
    return {'answer':answer,'model':cfg['model'],'provider':cfg['provider']}

def check_model():
    cfg=configuration()
    if cfg['provider']=='local': return {'connected':True,'message':'Local engineering tools are enabled. No model is required.','models':[]}
    if cfg['provider']=='embedded':
        from backend.core.local_model_runtime import status
        state=status()
        return {**state,'connected':state['ready'],'message':'Chopper local model is ready.' if state['ready'] else 'Choose a GGUF file, save, then Start local model in Settings.','models':['chopper-local']}
    if cfg['provider']=='ollama':
        response=requests.get(cfg['baseUrl']+'/api/tags',timeout=5,allow_redirects=False)
        if response.status_code!=200: raise ValueError(f'Ollama returned HTTP {response.status_code}.')
        models=[m.get('name') for m in response.json().get('models',[]) if m.get('name')]
        installed=cfg['model'] in models
        return {'connected':installed,'message':'Ollama is running; selected model is installed.' if installed else 'Ollama is running. Select one of the installed models.','models':models}
    chat_model('Reply with OK only.','Connection check.',timeout=30)
    return {'connected':True,'message':'API model responded.','models':[]}
