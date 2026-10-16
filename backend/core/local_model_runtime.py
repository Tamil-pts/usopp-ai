"""App-owned llama.cpp process; no Ollama service or model download required."""
import atexit
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import ctypes
import requests
from fastapi import HTTPException
from backend.core.runtime import BASE, RESOURCE_ROOT

LOCK=threading.RLock()
PROCESS=None
IDENTITY=None
LOG=None
LAST_EXIT_CODE=None
SHUTTING_DOWN=threading.Event()
FALLBACK_REASON=''
LAST_RESPONSE=None


def memory_mb(pid):
    """Resident memory of the owned process only, without a new dependency."""
    try:
        if os.name=='nt':
            from ctypes import wintypes
            class Counters(ctypes.Structure):
                _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.OpenProcess.restype=wintypes.HANDLE
            handle=kernel.OpenProcess(0x1000|0x10,False,pid)
            if not handle:return None
            try:
                counters=Counters();counters.cb=ctypes.sizeof(counters)
                if ctypes.WinDLL('psapi').GetProcessMemoryInfo(wintypes.HANDLE(handle),ctypes.byref(counters),counters.cb):return round(counters.WorkingSetSize/1048576,1)
            finally:kernel.CloseHandle(wintypes.HANDLE(handle))
        else:
            match=__import__('re').search(r'VmRSS:\s+(\d+)',Path(f'/proc/{pid}/status').read_text())
            if match:return round(int(match[1])/1024,1)
    except (OSError,ValueError):pass
    return None

def executable():
    name='llama-server.exe' if __import__('os').name=='nt' else 'llama-server'
    for root in (BASE,RESOURCE_ROOT):
        path=root/'local_ai'/'runtime'/name
        if path.is_file():return path
    raise HTTPException(409,'Local model runtime is missing. Use the complete Windows package or the updated CPU container image.')

def stop():
    global PROCESS,IDENTITY,LOG,LAST_EXIT_CODE
    with LOCK:
        if PROCESS and PROCESS.poll() is None:
            PROCESS.terminate()
            try:PROCESS.wait(timeout=10)
            except subprocess.TimeoutExpired:PROCESS.kill();PROCESS.wait(timeout=5)
        if PROCESS:
            LAST_EXIT_CODE=PROCESS.poll()
        PROCESS=None;IDENTITY=None
        if LOG:LOG.close();LOG=None
    return {'running':False,'message':'Chopper local model stopped.'}

def status():
    with LOCK:
        exit_code=PROCESS.poll() if PROCESS else LAST_EXIT_CODE
        running=bool(PROCESS and exit_code is None)
        try:path=str(executable());available=True
        except HTTPException:path='';available=False
        ready=False
        if running:
            try:ready=requests.get(f'http://127.0.0.1:{IDENTITY[1]}/health',timeout=2).status_code==200
            except requests.RequestException:pass
        return {'running':running,'ready':ready,'runtimeAvailable':available,'runtimePath':path,'logFile':str(BASE/'logs'/'chopper-local-model.log'),'port':IDENTITY[1] if IDENTITY else None,'processExitCode':exit_code,'failed':bool(PROCESS and exit_code is not None and exit_code != 0),
                'modelName':Path(IDENTITY[0]).stem if IDENTITY else None,'contextLimit':IDENTITY[2] if IDENTITY else None,
                'ramMB':memory_mb(PROCESS.pid) if running else None,'responseSeconds':LAST_RESPONSE,'fallbackReason':FALLBACK_REASON}

def start(cfg):
    global PROCESS,IDENTITY,LOG,LAST_EXIT_CODE,FALLBACK_REASON
    model=Path(str(cfg.get('modelPath') or '')).expanduser()
    if not model.is_file():raise HTTPException(400,'Choose a local GGUF model file on the uSOPp computer.')
    with model.open('rb') as stream:
        if stream.read(4)!=b'GGUF':raise HTTPException(400,'The selected file is not a GGUF model.')
    port=int(cfg.get('localPort',8202))
    if not 8200<=port<=8500:raise HTTPException(400,'Local model port must be between 8200 and 8500.')
    context=int(cfg.get('contextSize',4096))
    if not 512<=context<=32768:raise HTTPException(400,'Context size must be 512–32768 tokens.')
    threads=int(cfg.get('cpuThreads') or min(4,os.cpu_count() or 2))
    if not 1<=threads<=64:raise HTTPException(400,'CPU threads must be between 1 and 64.')
    identity=(str(model.resolve()),port,context,threads)
    with LOCK:
        if SHUTTING_DOWN.is_set():raise HTTPException(503,'The application is shutting down. Start the model after restarting uSOPp.')
        if PROCESS and PROCESS.poll() is None and IDENTITY==identity:return status()
        stop()
        with socket.socket() as probe:
            try:probe.bind(('127.0.0.1',port))
            except OSError:raise HTTPException(409,'The local model port is already in use. Select another port in 8200–8500.')
        runtime=executable();(BASE/'logs').mkdir(exist_ok=True)
        LOG=(BASE/'logs'/'chopper-local-model.log').open('ab')
        try:
            LAST_EXIT_CODE=None
            FALLBACK_REASON=''
            PROCESS=subprocess.Popen([str(runtime),'-m',str(model.resolve()),'--host','127.0.0.1','--port',str(port),'-c',str(context),'--alias','chopper-local','--parallel','1','--threads',str(threads),'--threads-batch',str(threads),'--batch-size','128','--ubatch-size','128','--gpu-layers','0','--timeout','1800'],cwd=str(runtime.parent),stdin=subprocess.DEVNULL,stdout=LOG,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            IDENTITY=identity
            owned=PROCESS
        except OSError as error:
            stop();raise HTTPException(503,'Cannot start the bundled local model runtime.') from error
    if cfg.get('allowFallback',True):
        def monitor():
            global FALLBACK_REASON
            from backend.core.cpu_model import model_path
            # This monitor never downloads. A failed primary can use the installed fallback.
            for _ in range(180):
                if SHUTTING_DOWN.wait(1):return
                with LOCK:
                    if PROCESS is not owned:return
                    failed=owned.poll() is not None
                if failed:break
            else:return
            fallback=model_path('fallback')
            if fallback.is_file() and fallback.resolve()!=model.resolve():
                with LOCK:
                    if PROCESS is not owned:return
                    start({**cfg,'modelPath':str(fallback),'contextSize':min(context,4096),'allowFallback':False})
                    FALLBACK_REASON='Primary model exited during startup; using the installed 1.5B fallback.'
        threading.Thread(target=monitor,name='chopper-model-fallback',daemon=True).start()
    return status()|{'message':'Chopper local model is loading. Check status until it is ready.'}

def restart(cfg):
    """Restart the configured local model and return its new startup status."""
    stop()
    result=start(cfg)
    return result|{'message':'Chopper local model restarted and is loading. Refresh status until it is ready.'}

def autostart():
    """Model loading is optional and must not delay API/validation availability."""
    SHUTTING_DOWN.clear()
    def worker():
        from backend.core.assist_model import configuration
        from backend.core.runtime import log
        try:
            cfg=configuration()
            if cfg.get('provider')=='embedded' and cfg.get('autoStart',True):
                if Path(str(cfg.get('modelPath') or '')).is_file():start(cfg)
                else:log.info('LOCAL_MODEL_SETUP_REQUIRED; install or select a GGUF in Settings')
        except Exception:log.exception('LOCAL_MODEL_AUTOSTART_ERROR; engineering tools remain available')
    threading.Thread(target=worker,name='chopper-model-autostart',daemon=True).start()

def shutdown():
    SHUTTING_DOWN.set()
    stop()

atexit.register(shutdown)
