"""Pinned offline CPU models. Network access is confined to explicit setup."""
import hashlib
import json
import os
import shutil
import threading
import requests
from fastapi import HTTPException
from backend.core.runtime import BASE,log

FALLBACK_MODEL={
 'id':'qwen2.5-coder-1.5b-instruct-q4_k_m','name':'Qwen2.5-Coder 1.5B Instruct · CPU fallback',
 'repository':'Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF','revision':'f86cb2c1fa58255f8052cc32aeede1b7482d4361',
 'filename':'qwen2.5-coder-1.5b-instruct-q4_k_m.gguf','size':1117320768,
 'sha256':'cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046',
 'license':'Apache-2.0','source':'https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF',
}
MODEL={
 'id':'qwen2.5-coder-3b-instruct-q4_k_m','name':'Qwen2.5-Coder 3B Instruct · CPU',
 'repository':'Qwen/Qwen2.5-Coder-3B-Instruct-GGUF','revision':'f74adce6aa16316c625447af059dbebe4983757c',
 'filename':'qwen2.5-coder-3b-instruct-q4_k_m.gguf','size':2104932800,
 'sha256':'724fb256bec1ff062b2f65e4569e871ad2e95ab2a3989723d1769c54294730b7',
 'license':'Qwen Research License','source':'https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF',
}
MODELS={'primary':MODEL,'fallback':FALLBACK_MODEL}
DIRECTORY=BASE/'local_ai/models';TARGET=DIRECTORY/MODEL['filename'];MANIFEST=DIRECTORY/'installed-model.json'
LOCK=threading.Lock();STATE={'phase':'idle','downloaded':0,'error':'','choice':'primary'};THREAD=None


def specification(choice):
    if choice not in MODELS:raise HTTPException(400,'Choose primary or fallback CPU model.')
    return MODELS[choice]


def model_path(choice='primary'):return DIRECTORY/specification(choice)['filename']


def _installed(model):
    target=DIRECTORY/model['filename']
    try:
        if target.stat().st_size!=model['size']:return False
        for manifest in (DIRECTORY/('installed-'+model['id']+'.json'),MANIFEST):
            try:
                if json.loads(manifest.read_text(encoding='utf-8')).get('sha256')==model['sha256']:return True
            except (OSError,ValueError):pass
    except OSError:pass
    return False


def status():
    with LOCK:state=dict(STATE)
    model=specification(state['choice'])
    return {**state,'installed':_installed(model),'model':model,'modelPath':str(DIRECTORY/model['filename']),
            'total':model['size'],'percent':round(100*state['downloaded']/model['size'],1),
            'models':[{'choice':choice,'installed':_installed(item),'model':item,'modelPath':str(DIRECTORY/item['filename'])} for choice,item in MODELS.items()]}


def update(**values):
    with LOCK:STATE.update(values)


def verify(path,model=None):
    model=model or MODEL
    if path.stat().st_size!=model['size']:raise ValueError('Model size does not match the pinned release.')
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        if stream.read(4)!=b'GGUF':raise ValueError('Downloaded file is not GGUF.')
        stream.seek(0)
        for chunk in iter(lambda:stream.read(4*1024*1024),b''):digest.update(chunk)
    if digest.hexdigest()!=model['sha256']:raise ValueError('Model checksum does not match the pinned release. Retry setup.')


def install(activate=True,start_runtime=True,model_id='primary'):
    model=specification(model_id);target=DIRECTORY/model['filename'];temporary=target.with_suffix('.gguf.part')
    DIRECTORY.mkdir(parents=True,exist_ok=True)
    try:
        update(phase='verifying',downloaded=0,error='',choice=model_id)
        if not target.is_file():
            if shutil.disk_usage(DIRECTORY).free<model['size']+256*1024*1024:raise ValueError('Allow the model size plus 256 MB of free disk space for setup.')
            update(phase='downloading')
            url=f"https://huggingface.co/{model['repository']}/resolve/{model['revision']}/{model['filename']}"
            with requests.get(url,stream=True,timeout=(20,90)) as response:
                response.raise_for_status()
                with temporary.open('wb') as stream:
                    count=0
                    for chunk in response.iter_content(chunk_size=1024*1024):
                        if not chunk:continue
                        count+=len(chunk)
                        if count>model['size']:raise ValueError('Model download exceeded its expected size.')
                        stream.write(chunk);update(downloaded=count)
                    stream.flush();os.fsync(stream.fileno())
            update(phase='verifying');verify(temporary,model);os.replace(temporary,target)
        else:verify(target,model)
        from backend.core.run_history import write_json
        write_json(DIRECTORY/('installed-'+model['id']+'.json'),model)
        if activate:
            from backend.core.assist_model import save_configuration
            cfg=save_configuration({'provider':'embedded','modelPath':str(target),'localPort':8202,
                'contextSize':4096,'cpuThreads':min(4,os.cpu_count() or 2),'autoStart':True,
                'allowFallback':True,'maxTokens':768,'responseTimeoutSeconds':1800})
            if start_runtime:
                from backend.core.local_model_runtime import start
                start(cfg)
        update(phase='installed',downloaded=model['size'])
    except Exception as error:
        message=str(error) if isinstance(error,ValueError) else 'Model setup failed. Check disk space, download access and the server log; then retry.'
        update(phase='failed',error=message);log.exception('CPU_MODEL_INSTALL_ERROR');raise
    finally:temporary.unlink(missing_ok=True)
    return status()


def begin_install(model_id='primary'):
    global THREAD
    specification(model_id)
    with LOCK:
        if THREAD and THREAD.is_alive():raise HTTPException(409,'CPU model setup is already running.')
        def worker():
            try:install(model_id=model_id)
            except Exception:pass
        THREAD=threading.Thread(target=worker,name='chopper-model-install',daemon=True)
        STATE.update(phase='preparing',downloaded=0,error='',choice=model_id);THREAD.start()
    return status()
