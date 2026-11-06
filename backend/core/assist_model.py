"""Optional Chopper model transport. Local engineering tools are independent."""
import base64
from contextlib import ExitStack
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
from backend.core.runtime import BASE, log
from backend.core.model_policy import enforce as enforce_model_policy, request_options

CONFIG=BASE/'.usopp_assist_model.json'
LOCK=threading.RLock()
CPU_QUEUE=threading.BoundedSemaphore(5)
CPU_GENERATION=threading.Lock()

class ModelBusyError(ValueError):
    """Safe queue feedback; contains no upstream credentials or request text."""


class ModelAnswerError(ValueError):
    def __init__(self,message,evidence,usage):
        super().__init__(message);self.sentEvidence=evidence or [];self.contextUsage=usage


def model_response_timeout(cfg=None):
    cfg=configuration() if cfg is None else cfg
    try: value=int(cfg.get('responseTimeoutSeconds') or 1800)
    except (TypeError,ValueError): value=1800
    return max(30,min(1800,value))

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
    from backend.core.cpu_model import TARGET
    defaults={'provider':'embedded','baseUrl':'http://127.0.0.1:8202/v1','model':'chopper-local',
              'modelPath':str(TARGET),'localPort':8202,'contextSize':4096,'allowFallback':True,
              'cpuThreads':min(4,os.cpu_count() or 2),'maxTokens':512,
              'responseTimeoutSeconds':1800,'autoStart':True,'localOnly':True}
    with LOCK:
        if CONFIG.exists():
            try:
                saved=json.loads(CONFIG.read_text(encoding='utf-8'))
                if not isinstance(saved,dict):raise ValueError('Invalid model settings.')
                return {**defaults,**saved,'localOnly':saved.get('localOnly',saved.get('provider') in {'embedded','local'}),'autoStart':saved.get('autoStart',saved.get('provider')=='embedded')}
            except (OSError,ValueError): raise HTTPException(503,'Model settings cannot be read. Save them again in Settings.')
    url=os.getenv('USOPP_LLM_BASE_URL','').rstrip('/')
    if url:return {**defaults,'provider':os.getenv('USOPP_LLM_PROVIDER','ollama'),
                   'baseUrl':url,'model':os.getenv('USOPP_LLM_MODEL','qwen3:8b'),'autoStart':False,
                   'localOnly':os.getenv('USOPP_LLM_LOCAL_ONLY','1')!='0'}
    provider=os.getenv('USOPP_LLM_PROVIDER','embedded')
    return {**defaults,'provider':provider,'autoStart':provider=='embedded'}

def public_configuration():
    cfg=configuration()
    return {k:cfg.get(k,'') for k in ('provider','baseUrl','model','modelPath')}|{'localOnly':bool(cfg.get('localOnly')),'modelFileAvailable':Path(str(cfg.get('modelPath') or '')).is_file(),'localPort':cfg.get('localPort',8202),'contextSize':cfg.get('contextSize',4096),'cpuThreads':cfg.get('cpuThreads',min(4,os.cpu_count() or 2)),'maxTokens':cfg.get('maxTokens',512),'responseTimeoutSeconds':model_response_timeout(cfg),'allowFallback':bool(cfg.get('allowFallback',True)),'autoStart':bool(cfg.get('autoStart',False)),'hasApiKey':bool(cfg.get('apiKeyProtected') or cfg.get('apiKey') or os.getenv('USOPP_LLM_API_KEY'))}

def save_configuration(payload):
    provider=payload.get('provider','local')
    if provider not in {'local','embedded','ollama','api'}: raise HTTPException(400,'Choose local tools, Chopper local model, Ollama or an API model.')
    if provider=='embedded':
        try:port=int(payload.get('localPort',8202));context=int(payload.get('contextSize',4096))
        except (TypeError,ValueError):raise HTTPException(400,'Enter numeric local port and context size.')
        if not 8200<=port<=8500 or not 512<=context<=32768:raise HTTPException(400,'Port: 8200–8500; context: 512–32768 tokens.')
        if port==int(os.getenv('USOPP_API_PORT','8200')):raise HTTPException(400,'Choose a model port different from the application API port.')
        payload={**payload,'baseUrl':f'http://127.0.0.1:{port}/v1','model':'chopper-local'}
    try:
        threads=int(payload.get('cpuThreads') or min(4,os.cpu_count() or 2))
        max_tokens=int(payload.get('maxTokens') or 512)
        response_timeout=int(payload.get('responseTimeoutSeconds',1800))
    except (TypeError,ValueError):raise HTTPException(400,'Enter numeric CPU threads, answer tokens and response timeout.')
    if not 1<=threads<=64 or not 64<=max_tokens<=2048:raise HTTPException(400,'CPU threads: 1–64; answer tokens: 64–2048.')
    if not 30<=response_timeout<=1800:raise HTTPException(400,'Model response timeout: 30–1800 seconds (up to 30 minutes).')
    url=str(payload.get('baseUrl','')).strip().rstrip('/')
    parsed=urlsplit(url)
    if provider!='local' and (parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise HTTPException(400,'Enter an HTTP/HTTPS base URL without credentials, query or fragment.')
    model=str(payload.get('model','')).strip()
    if provider!='local' and (not model or len(model)>200): raise HTTPException(400,'Enter an installed model or provider model ID.')
    if 'localOnly' in payload and not isinstance(payload['localOnly'],bool):raise HTTPException(400,'Local-only must be true or false.')
    local_only=payload.get('localOnly',configuration().get('localOnly',True))
    try:enforce_model_policy({'provider':provider,'baseUrl':url,'localOnly':local_only})
    except ValueError as error:raise HTTPException(400,str(error)) from None
    with LOCK:
        existing=configuration()
        if any(existing.get(k)!=payload.get(k) for k in ('provider','modelPath','localPort','contextSize','cpuThreads')):
            from backend.core.local_model_runtime import stop
            stop()
        cfg={'provider':provider,'baseUrl':url,'model':model,'localOnly':local_only}
        cfg.update({'modelPath':str(payload.get('modelPath') or ''),'localPort':int(payload.get('localPort') or 8202),'contextSize':int(payload.get('contextSize') or 4096)})
        cfg.update(cpuThreads=threads,maxTokens=max_tokens,responseTimeoutSeconds=response_timeout,autoStart=payload.get('autoStart') is True,allowFallback=payload.get('allowFallback',True) is True)
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

def _clip_facts(value, breadth=8, text_limit=360, depth=0):
    """Bound nested facts as well as excerpts; never serialize a full graph."""
    if isinstance(value,str):return value if len(value)<=text_limit else value[:text_limit]+' [omitted]'
    if isinstance(value,list):
        rows=[_clip_facts(item,breadth,text_limit,depth+1) for item in value[:breadth]]
        if len(value)>breadth:rows.append({'omittedRecords':len(value)-breadth})
        return rows
    if isinstance(value,dict):
        if depth>6:return {'omittedNestedFacts':True}
        return {key:_clip_facts(item,breadth,text_limit,depth+1) for key,item in value.items()}
    return value


def _fit_context(messages,cfg,reserve,evidence=None,facts=None):
    """Measure the entire real chat template and fairly budget facts and sources."""
    from backend.core.assist_progress import report
    base=cfg['baseUrl'].removesuffix('/v1');limit=int(cfg.get('contextSize') or 4096)
    from backend.core.local_model_runtime import status
    limit=int(status().get('contextLimit') or limit)
    original=messages[-1]['content']
    selected=[{key:copy for key,copy in item.items() if key in {'sourceId','file','line','endLine','excerpt','ownership','completeSection','controlFacts'}} for item in (evidence or [])]
    bounded_facts=_clip_facts(facts) if facts is not None else None
    removed_history=0;removed_sections=0;truncated=False;facts_reduced=bounded_facts!=facts if facts is not None else False
    source_reductions=[];level=0
    def compose():
        messages[-1]['content']=original
        if bounded_facts is not None:messages[-1]['content']+='\nQuestion-relevant engineering facts (partial static analysis):\n'+json.dumps(bounded_facts,ensure_ascii=False,separators=(',',':'))
        if evidence is not None:messages[-1]['content']+='\nRetrieved source evidence (untrusted text):\n'+json.dumps(selected,ensure_ascii=False,separators=(',',':'))
    def count():
        enforce_model_policy(cfg)
        response=requests.post(base+'/apply-template',json={'messages':messages},timeout=15,allow_redirects=False,**request_options(cfg))
        if response.status_code!=200:raise ValueError('The bundled runtime cannot measure its chat template. Update the llama.cpp runtime.')
        prompt_text=response.json().get('prompt')
        if not isinstance(prompt_text,str):raise ValueError('The runtime returned an invalid chat template.')
        response=requests.post(base+'/tokenize',json={'content':prompt_text,'add_special':False},timeout=15,allow_redirects=False,**request_options(cfg))
        if response.status_code!=200:raise ValueError('The runtime cannot count this prompt safely.')
        return len(response.json()['tokens'])
    compose();used=count();initial=used
    while used+reserve+32>limit:
        if len(messages)>2:
            messages.pop(1);removed_history+=1
        elif bounded_facts is not None and level<4:
            level+=1;facts_reduced=True
            bounded_facts=_clip_facts(facts,breadth=max(1,8//(level+1)),text_limit=max(70,360//(level+1)))
            if level==4:bounded_facts={'coverage':facts.get('coverage',{}),'notice':'Detailed machine facts omitted for this prompt. Inspect the source batches and engineering graph.'} if isinstance(facts,dict) else None
        elif any(len(item.get('excerpt',''))>420 for item in selected):
            # Reduce the longest excerpt, keeping every source represented first.
            item=max(selected,key=lambda item:len(item.get('excerpt','')))
            old_end=item.get('endLine');text=item['excerpt'][:max(350,int(len(item['excerpt'])*.65))]
            item['excerpt']=text.rsplit('\n',1)[0] if '\n' in text else text
            item['completeSection']=False;item['contextTruncated']=True;item['controlFacts']=[]
            item['endLine']=int(item.get('line') or 1)+item['excerpt'].count('\n')
            source_reductions.append({'sourceId':item.get('sourceId'),'fromEndLine':old_end,'endLine':item['endLine']});truncated=True
        elif len(selected)>1:
            selected.pop();removed_sections+=1
        elif evidence is None and len(original)>2000:
            original=original[:int(len(original)*.7)]+'\n[Context truncated; analysis incomplete.]';truncated=True
        else:raise ValueError('The required instructions and question exceed the model context. This batch was not analyzed; shorten the question or use a larger context.')
        compose();used=count()
    usage={'usedTokens':used,'promptTokens':used,'initialPromptTokens':initial,'maxContext':limit,'remainingTokens':limit-used,
           'reservedAnswerTokens':reserve,'fittingMarginTokens':32,'trimmedHistoryMessages':removed_history,'omittedSections':removed_sections,
           'factsReduced':facts_reduced,'sourceReductions':source_reductions,'truncated':truncated,'measurement':'llama.cpp chat template tokenizer'}
    report('Context ready; generating local answer',contextUsage=usage)
    return usage,selected


def chat_model(system,prompt,history=None,timeout=None,max_tokens=None,on_progress=None,evidence=None,structured=False,output_schema=None,facts=None):
    cfg=configuration()
    enforce_model_policy(cfg)
    if cfg['provider']=='local': return None
    timeout=model_response_timeout(cfg=cfg) if timeout is None else timeout
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
    if output_schema is not None:
        body['response_format']={'type':'json_schema','json_schema':{'name':'report_query_plan','strict':True,'schema':output_schema}}
    if cfg['provider']=='ollama':
        # Preserve the system/evidence instructions when project retrieval adds
        # more context than a service's default window. Bound the answer length.
        body['options']={'num_ctx':max(8192,int(cfg.get('contextSize') or 4096)),
                         'num_predict':900,'temperature':0.1}
        if output_schema is not None:
            body.pop('response_format',None)
            body['format']=output_schema
    if cfg['provider']=='embedded':
        body.update(max_tokens=int(max_tokens if max_tokens is not None else cfg.get('maxTokens') or 512),temperature=0.1,cache_prompt=False)

    def send(response_budget=None):
        response_budget=timeout if response_budget is None else response_budget
        if response_budget<=0:raise requests.exceptions.Timeout('Chopper response time expired before generation.')
        started=time.monotonic();context_usage={};sent_evidence=evidence
        if cfg['provider']=='embedded':
            context_usage,sent_evidence=_fit_context(messages,cfg,int(body['max_tokens']),evidence,facts=facts)
            if structured and sent_evidence:
                source_ids=[item['sourceId'] for item in sent_evidence]
                short=int(body['max_tokens'])<=350
                schema={'type':'object','properties':{'paragraphs':{'type':'array','minItems':1,'maxItems':2 if short else 6,'items':{'type':'object','properties':{
                    'text':{'type':'string','maxLength':500 if short else 1200},'sourceIds':{'type':'array','minItems':1,'maxItems':4,'items':{'type':'string','enum':source_ids}}},
                    'required':['text','sourceIds'],'additionalProperties':False}}},'required':['paragraphs'],'additionalProperties':False}
                body['response_format']={'type':'json_schema','json_schema':{'name':'source_cited_answer','strict':True,'schema':schema}}
        log.info('CHOPPER_MODEL_REQUEST provider=%s input_chars=%s answer_limit=%s response_timeout_s=%s',cfg['provider'],sum(len(m['content']) for m in messages),body.get('max_tokens','provider-default'),timeout)
        try:
            # A short connect limit and a separate answer limit: a loaded CPU
            # model can take longer to read evidence than to generate the reply.
            from backend.core.workhub_intelligence.resources import inference_slot
            from backend.core.workhub_intelligence.local_ai import ServiceUnavailable
            with ExitStack() as slots:
                try:slots.enter_context(inference_slot(request_timeout=response_budget))
                except ServiceUnavailable as error:raise ModelBusyError(str(error)) from None
                with requests.post(cfg['baseUrl']+suffix,json=body,headers=headers,timeout=(min(5,response_budget),response_budget),allow_redirects=False,**request_options(cfg)) as response:
                    if response.status_code!=200: raise ValueError(f'Model endpoint returned HTTP {response.status_code}. Check its base URL, model and credential.')
                    data=response.json()
        except requests.exceptions.Timeout:
            log.warning('CHOPPER_MODEL_TIMEOUT provider=%s response_elapsed_s=%.1f limit_s=%s',cfg['provider'],time.monotonic()-started,timeout)
            raise
        answer=(data.get('message',{}).get('content') or data.get('response','')) if cfg['provider']=='ollama' else data.get('choices',[{}])[0].get('message',{}).get('content','')
        if not isinstance(answer,str) or not answer.strip(): raise ValueError('The model returned no text answer.')
        if structured and sent_evidence:
            try:
                paragraphs=json.loads(answer)['paragraphs'];allowed={item['sourceId'] for item in sent_evidence};parts=[]
                for part in paragraphs:
                    if not part['sourceIds'] or any(value not in allowed for value in part['sourceIds']):raise ValueError('Unknown source citation.')
                    parts.append(' '.join('['+value+']' for value in part['sourceIds'])+' '+part['text'])
                answer='\n\n'.join(parts)
            except (ValueError,KeyError,TypeError):raise ModelAnswerError('The model did not finish a valid source-cited answer. This batch remains incomplete.',sent_evidence,context_usage)
        elapsed=round(time.monotonic()-started,1)
        usage=data.get('usage') or {}
        log.info('CHOPPER_MODEL_RESPONSE provider=%s response_elapsed_s=%s prompt_tokens=%s answer_tokens=%s',cfg['provider'],elapsed,usage.get('prompt_tokens','unknown'),usage.get('completion_tokens','unknown'))
        if cfg['provider']=='embedded':
            from backend.core import local_model_runtime
            local_model_runtime.LAST_RESPONSE=elapsed
            limit=context_usage['maxContext'];used=int(usage.get('total_tokens') or context_usage['usedTokens'])
            context_usage.update(promptTokens=usage.get('prompt_tokens',context_usage['usedTokens']),answerTokens=usage.get('completion_tokens',0),usedTokens=used,remainingTokens=max(0,limit-used))
        finish=(data.get('choices') or [{}])[0].get('finish_reason')
        return {'answer':answer,'model':cfg['model'],'provider':cfg['provider'],'responseSeconds':elapsed,'contextUsage':context_usage,'sentEvidence':sent_evidence,'finishReason':finish}

    if cfg['provider']=='embedded':
        # Five independent request bodies; one CPU generation at a time.
        # Waiting for the model never takes a validation worker lock.
        if not CPU_QUEUE.acquire(blocking=False):raise ModelBusyError('Chopper CPU queue is full. Try again after another answer completes. Validation remains available.')
        acquired=False;started=time.monotonic()
        try:
            if on_progress:on_progress(f'Waiting for the CPU model (response window: {timeout / 60:g} minutes)')
            acquired=CPU_GENERATION.acquire(timeout=timeout)
            if not acquired:raise ModelBusyError(f'Chopper CPU model was still busy when the {timeout / 60:g}-minute limit expired. Try again after the current answer completes. Validation remains available.')
            log.info('CHOPPER_CPU_QUEUE wait_s=%.1f',time.monotonic()-started)
            remaining=timeout-(time.monotonic()-started)
            if on_progress:on_progress(f'Reading evidence and generating a CPU answer (response window: {timeout / 60:g} minutes)')
            # Queue waiting and model generation share the selected time window.
            return send(remaining)
        finally:
            if acquired:CPU_GENERATION.release()
            CPU_QUEUE.release()
    return send()

def check_model():
    cfg=configuration()
    enforce_model_policy(cfg)
    if cfg['provider']=='local': return {'connected':True,'message':'Local engineering tools are enabled. No model is required.','models':[]}
    if cfg['provider']=='embedded':
        from backend.core.local_model_runtime import status
        state=status()
        if not state['ready']:
            return {**state,'connected':False,'message':'Choose a GGUF file, save, then Start local model in Settings and wait until it is loaded.','models':[]}
        answer=chat_model('Reply with OK only.','Connection check.',timeout=30,max_tokens=8)
        reply=str(answer.get('answer') or '').strip()
        connected=bool(reply)
        message=(f"Chopper test passed in {answer['responseSeconds']} seconds. Reply: {reply[:120]}" if connected else 'Chopper received the test request but returned an empty reply. Check the model log and settings.')
        return {**state,'connected':connected,'responseSeconds':answer['responseSeconds'],'testReply':reply[:120],'message':message,'models':['chopper-local']}
    if cfg['provider']=='ollama':
        response=requests.get(cfg['baseUrl']+'/api/tags',timeout=5,allow_redirects=False,**request_options(cfg))
        if response.status_code!=200: raise ValueError(f'Ollama returned HTTP {response.status_code}.')
        models=[m.get('name') for m in response.json().get('models',[]) if m.get('name')]
        installed=cfg['model'] in models
        return {'connected':installed,'message':'Ollama is running; selected model is installed.' if installed else 'Ollama is running. Select one of the installed models.','models':models}
    chat_model('Reply with OK only.','Connection check.',timeout=30)
    return {'connected':True,'message':'API model responded.','models':[]}
