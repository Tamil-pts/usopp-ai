"""App-owned llama.cpp process; no Ollama service or model download required."""
import atexit
from pathlib import Path
import socket
import subprocess
import threading
import requests
from fastapi import HTTPException
from backend.core.runtime import BASE, RESOURCE_ROOT

LOCK=threading.RLock()
PROCESS=None
IDENTITY=None
LOG=None

def executable():
    name='llama-server.exe' if __import__('os').name=='nt' else 'llama-server'
    for root in (BASE,RESOURCE_ROOT):
        path=root/'local_ai'/'runtime'/name
        if path.is_file():return path
    raise HTTPException(409,'Local model runtime is missing. Use the complete Windows package or place llama-server in local_ai/runtime.')

def stop():
    global PROCESS,IDENTITY,LOG
    with LOCK:
        if PROCESS and PROCESS.poll() is None:
            PROCESS.terminate()
            try:PROCESS.wait(timeout=10)
            except subprocess.TimeoutExpired:PROCESS.kill();PROCESS.wait(timeout=5)
        PROCESS=None;IDENTITY=None
        if LOG:LOG.close();LOG=None
    return {'running':False,'message':'Chopper local model stopped.'}

def status():
    with LOCK:
        running=bool(PROCESS and PROCESS.poll() is None)
        try:path=str(executable());available=True
        except HTTPException:path='';available=False
        ready=False
        if running:
            try:ready=requests.get(f'http://127.0.0.1:{IDENTITY[1]}/health',timeout=2).status_code==200
            except requests.RequestException:pass
        return {'running':running,'ready':ready,'runtimeAvailable':available,'runtimePath':path,'logFile':str(BASE/'logs'/'chopper-local-model.log')}

def start(cfg):
    global PROCESS,IDENTITY,LOG
    model=Path(str(cfg.get('modelPath') or '')).expanduser()
    if not model.is_file():raise HTTPException(400,'Choose a local GGUF model file on the uSOPp computer.')
    with model.open('rb') as stream:
        if stream.read(4)!=b'GGUF':raise HTTPException(400,'The selected file is not a GGUF model.')
    port=int(cfg.get('localPort',8202))
    if not 8200<=port<=8500:raise HTTPException(400,'Local model port must be between 8200 and 8500.')
    context=int(cfg.get('contextSize',4096))
    if not 512<=context<=32768:raise HTTPException(400,'Context size must be 512–32768 tokens.')
    identity=(str(model.resolve()),port,context)
    with LOCK:
        if PROCESS and PROCESS.poll() is None and IDENTITY==identity:return status()
        stop()
        with socket.socket() as probe:
            try:probe.bind(('127.0.0.1',port))
            except OSError:raise HTTPException(409,'The local model port is already in use. Select another port in 8200–8500.')
        runtime=executable();(BASE/'logs').mkdir(exist_ok=True)
        LOG=(BASE/'logs'/'chopper-local-model.log').open('ab')
        try:
            PROCESS=subprocess.Popen([str(runtime),'-m',str(model.resolve()),'--host','127.0.0.1','--port',str(port),'-c',str(context),'--alias','chopper-local','--parallel','1'],cwd=str(runtime.parent),stdin=subprocess.DEVNULL,stdout=LOG,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            IDENTITY=identity
        except OSError as error:
            stop();raise HTTPException(503,'Cannot start the bundled local model runtime.') from error
    return status()|{'message':'Chopper local model is loading. Check status until it is ready.'}

atexit.register(stop)
