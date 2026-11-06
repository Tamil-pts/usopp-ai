"""Small pinned local retrieval models using the existing llama.cpp binary.

Only explicit install performs downloads. Queries never fetch a model or use a
remote endpoint. Retrieval processes are separate from the chat inference slot.
"""
import atexit
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import threading
import time

import requests
from backend.core.runtime import BASE

MODELS={
 'embedding':{'repository':'ggml-org/bge-small-en-v1.5-Q8_0-GGUF','revision':'f2068edd9b54f2a369549ccc71f70ed273a2a801','filename':'bge-small-en-v1.5-q8_0.gguf','size':36685152,'sha256':'f046db1dc724cf4f6f0a0c5917e922823b73eb1d27b8f9a9c2797f7866974804','license':'MIT','port':8204},
 'reranker':{'repository':'gpustack/jina-reranker-v1-tiny-en-GGUF','revision':'34fdafe5a08b64246bcbfdbf0b8a23f818baf8e3','filename':'jina-reranker-v1-tiny-en-Q8_0.gguf','size':36676960,'sha256':'0defc1f8a1f4dd22183124a2a25a97765603e5a9e42258046c9b2c8a26d1f553','license':'Apache-2.0','port':8205},
}
DIRECTORY=BASE/'local_ai/models';CONFIG=BASE/'.usopp_semantic.json'
LOCK=threading.RLock();QUERY_LOCK=threading.Lock();PROCESSES={};VERIFIED={}
INSTALL={'phase':'idle','downloaded':0,'total':sum(m['size'] for m in MODELS.values()),'error':''}


def settings():
    try:value=json.loads(CONFIG.read_text(encoding='utf-8')) if CONFIG.exists() else {}
    except (OSError,ValueError):raise ValueError('Semantic retrieval settings cannot be read.') from None
    if not isinstance(value,dict):raise ValueError('Semantic retrieval settings cannot be read.')
    return {'enabled':value.get('enabled') is True,'rerank':value.get('rerank',True) is True}


def save_settings(value):
    if any(key not in {'enabled','rerank'} or not isinstance(item,bool) for key,item in value.items()):
        raise ValueError('Semantic settings accept enabled and rerank booleans only.')
    temporary=CONFIG.with_suffix('.tmp')
    with LOCK:
        result={**settings(),**value}
        temporary.write_text(json.dumps(result),encoding='utf-8');os.replace(temporary,CONFIG)
        if not result['enabled']:stop()
    return status()


def path(kind):return DIRECTORY/MODELS[kind]['filename']


def verify(kind):
    model=MODELS[kind];target=path(kind)
    if not target.is_file() or target.stat().st_size!=model['size']:raise ValueError('Install the local '+kind+' model in Chopper settings first.')
    stat=target.stat();identity=(stat.st_size,stat.st_mtime_ns)
    if VERIFIED.get(kind)==identity:return
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    if digest!=model['sha256']:raise ValueError('Local '+kind+' model checksum does not match its pinned revision.')
    VERIFIED[kind]=identity


def status():
    with LOCK:
        return {**settings(),'installation':dict(INSTALL),'models':[{'kind':kind,**model,'installed':path(kind).is_file() and path(kind).stat().st_size==model['size'],'running':kind in PROCESSES and PROCESSES[kind][0].poll() is None} for kind,model in MODELS.items()],
                'transport':'native llama.cpp / loopback only','vectorEngine':'NumPy exact cosine / SQLite vectors','downloadsDuringQueries':False}


def install():
    try:
        DIRECTORY.mkdir(parents=True,exist_ok=True)
        for kind,model in MODELS.items():
            if not path(kind).exists():
                temporary=path(kind).with_suffix('.part')
                try:
                    url=f"https://huggingface.co/{model['repository']}/resolve/{model['revision']}/{model['filename']}"
                    with requests.get(url,stream=True,timeout=(20,90)) as response:
                        response.raise_for_status();count=0;digest=hashlib.sha256()
                        with temporary.open('wb') as stream:
                            for chunk in response.iter_content(1024*1024):
                                count+=len(chunk)
                                if count>model['size']:raise ValueError('Retrieval model download exceeded the pinned size.')
                                digest.update(chunk);stream.write(chunk)
                                with LOCK:INSTALL['downloaded']+=len(chunk)
                    if count!=model['size'] or digest.hexdigest()!=model['sha256']:raise ValueError('Retrieval model download failed its checksum/size check.')
                    os.replace(temporary,path(kind))
                finally:temporary.unlink(missing_ok=True)
            verify(kind)
        (DIRECTORY/'retrieval-models.json').write_text(json.dumps(MODELS,indent=2),encoding='utf-8')
        with LOCK:INSTALL.update(phase='installed',downloaded=INSTALL['total'])
    except Exception as error:
        with LOCK:INSTALL.update(phase='failed',error=str(error)[:300])


def begin_install():
    with LOCK:
        if INSTALL['phase']=='downloading':return status()
        INSTALL.update(phase='downloading',downloaded=0,error='')
        threading.Thread(target=install,name='chopper-retrieval-setup',daemon=True).start()
    return status()


def stop():
    with LOCK:
        for process,log in PROCESSES.values():
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
            log.close()
        PROCESSES.clear()
        VERIFIED.clear()


def session():
    value=requests.Session();value.trust_env=False;return value


def ensure(kind):
    with LOCK:
        if not settings()['enabled']:raise ValueError('Local semantic retrieval is disabled. Enable it in Chopper settings before building/querying.')
        if kind not in PROCESSES or PROCESSES[kind][0].poll() is not None:VERIFIED.pop(kind,None)
        verify(kind);model=MODELS[kind];port=model['port']
        if kind in PROCESSES and PROCESSES[kind][0].poll() is None:return
        if kind in PROCESSES:PROCESSES.pop(kind)[1].close()
        from backend.core.local_model_runtime import executable
        with socket.socket() as probe:
            try:probe.bind(('127.0.0.1',port))
            except OSError:raise ValueError(f'Local retrieval port {port} is occupied. No evidence was sent to that service.') from None
        logdir=BASE/'logs';logdir.mkdir(exist_ok=True);log=(logdir/('chopper-'+kind+'.log')).open('ab')
        args=[str(executable()),'--model',str(path(kind)),'--host','127.0.0.1','--port',str(port),'--alias','chopper-'+kind,
              '--embedding','--pooling','cls' if kind=='embedding' else 'rank','--ctx-size','512' if kind=='embedding' else '1024',
              '--threads','2','--parallel','1','--batch-size','512','--ubatch-size','512','--no-webui']
        if kind=='reranker':args.append('--rerank')
        try:process=subprocess.Popen(args,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except Exception:log.close();raise
        PROCESSES[kind]=(process,log)
        with session() as client:
            for _ in range(100):
                if process.poll() is not None:raise ValueError('The local '+kind+' runtime exited; inspect its server log.')
                try:
                    if client.get(f'http://127.0.0.1:{port}/health',timeout=1,allow_redirects=False).status_code==200:return
                except requests.RequestException:pass
                time.sleep(.1)
        raise ValueError('The local '+kind+' model did not become ready.')


def post(kind,endpoint,payload):
    ensure(kind)
    with session() as client:
        with client.post(f"http://127.0.0.1:{MODELS[kind]['port']}"+endpoint,json=payload,timeout=(3,90),allow_redirects=False) as response:
            if response.status_code!=200:raise ValueError('The local '+kind+' service rejected this bounded request.')
            return response.json()


def fit(kind,text,budget):
    # Use the actual model tokenizer; representation shortening never changes
    # the stored source excerpt or its proof/coverage flags.
    text=str(text)[:6000]
    for _ in range(8):
        tokens=post(kind,'/tokenize',{'content':text,'add_special':True}).get('tokens',[])
        if tokens and len(tokens)<=budget:return text
        text=text[:max(1,int(len(text)*budget/max(1,len(tokens))*.85))]
    raise ValueError('A retrieval representation cannot fit its tokenizer budget.')


def embeddings(texts,query=False):
    import numpy as np
    prepared=[fit('embedding',('Represent this sentence for searching relevant passages: ' if query else '')+text,500) for text in texts]
    value=post('embedding','/v1/embeddings',{'input':prepared,'model':'chopper-embedding'})
    rows=value.get('data',[]) if isinstance(value,dict) else []
    if not isinstance(rows,list) or len(rows)!=len(texts) or any(not isinstance(row,dict) or type(row.get('index')) is not int for row in rows) or sorted(row['index'] for row in rows)!=list(range(len(texts))):raise ValueError('Embedding response did not identify every input exactly once.')
    if any(not isinstance(row.get('embedding'),list) for row in rows):raise ValueError('Embedding dimensions or values are invalid.')
    array=np.asarray([row['embedding'] for row in sorted(rows,key=lambda row:row['index'])],dtype=np.float32)
    if array.ndim!=2 or array.shape[1]!=384 or not np.isfinite(array).all():raise ValueError('Embedding dimensions or values are invalid.')
    norms=np.linalg.norm(array,axis=1,keepdims=True)
    if (norms==0).any():raise ValueError('A local embedding is empty.')
    return array/norms


def rerank(question,texts):
    query=fit('reranker',question,180);documents=[fit('reranker',text,740) for text in texts]
    value=post('reranker','/reranking',{'query':query,'documents':documents,'top_n':len(documents)})
    rows=value.get('results',value.get('data',[])) if isinstance(value,dict) else []
    if not isinstance(rows,list) or len(rows)!=len(texts) or any(not isinstance(row,dict) or type(row.get('index')) is not int for row in rows) or sorted(row['index'] for row in rows)!=list(range(len(texts))):raise ValueError('Reranker returned missing, repeated or unknown candidate indices.')
    if any(type(row.get('relevance_score')) not in (float,int) or not math.isfinite(row['relevance_score']) for row in rows):raise ValueError('Reranker returned invalid relevance scores.')
    return {row['index']:float(row['relevance_score']) for row in rows}


atexit.register(stop)
