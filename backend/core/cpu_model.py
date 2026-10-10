"""Pinned, checksum-verified CPU model installation in the persistent data root."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import requests
from fastapi import HTTPException
from backend.core.runtime import BASE, log

MODEL = {
    'id': 'qwen2.5-coder-1.5b-instruct-q4_k_m',
    'name': 'Qwen2.5-Coder 1.5B Instruct · CPU',
    'repository': 'Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF',
    'revision': 'f86cb2c1fa58255f8052cc32aeede1b7482d4361',
    'filename': 'qwen2.5-coder-1.5b-instruct-q4_k_m.gguf',
    'size': 1117320768,
    'sha256': 'cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046',
    'license': 'Apache-2.0',
    'source': 'https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF',
}
DIRECTORY = BASE / 'local_ai' / 'models'
TARGET = DIRECTORY / MODEL['filename']
MANIFEST = DIRECTORY / 'installed-model.json'
LOCK = threading.Lock()
STATE = {'phase': 'idle', 'downloaded': 0, 'error': ''}
THREAD = None


def status():
    with LOCK:
        state = dict(STATE)
    installed = False
    try:
        saved = json.loads(MANIFEST.read_text(encoding='utf-8'))
        installed = saved.get('sha256') == MODEL['sha256'] and TARGET.stat().st_size == MODEL['size']
    except (OSError, ValueError):
        pass
    return {**state, 'installed': installed, 'model': MODEL, 'modelPath': str(TARGET),
            'total': MODEL['size'], 'percent': round(100 * state['downloaded'] / MODEL['size'], 1)}


def update(**values):
    with LOCK:
        STATE.update(values)


def verify(path):
    if path.stat().st_size != MODEL['size']:
        raise ValueError('Model size does not match the approved release.')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        if stream.read(4) != b'GGUF':
            raise ValueError('Downloaded model is not GGUF.')
        stream.seek(0)
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != MODEL['sha256']:
        raise ValueError('Model checksum does not match the approved release. Retry the download.')


def install(activate=True, start_runtime=True):
    """Download only official fixed bytes; also accepts an offline copy at TARGET."""
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    temporary = TARGET.with_suffix('.gguf.part')
    try:
        update(phase='verifying', downloaded=0, error='')
        if not TARGET.is_file():
            if shutil.disk_usage(DIRECTORY).free < MODEL['size'] + 256 * 1024 * 1024:
                raise ValueError('Allow at least 1.4 GB free disk space to install the CPU model.')
            update(phase='downloading')
            url = f"https://huggingface.co/{MODEL['repository']}/resolve/{MODEL['revision']}/{MODEL['filename']}"
            with requests.get(url, stream=True, timeout=(20, 60)) as response:
                response.raise_for_status()
                with temporary.open('wb') as stream:
                    count = 0
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        count += len(chunk)
                        if count > MODEL['size']:
                            raise ValueError('Model download exceeded its expected size.')
                        stream.write(chunk)
                        update(downloaded=count)
                    stream.flush(); os.fsync(stream.fileno())
            update(phase='verifying')
            verify(temporary)
            os.replace(temporary, TARGET)
        else:
            verify(TARGET)
        from backend.core.run_history import write_json
        write_json(MANIFEST, MODEL)
        if activate:
            from backend.core.assist_model import save_configuration
            cfg = save_configuration({'provider': 'embedded', 'modelPath': str(TARGET),
                'localPort': 8202, 'contextSize': 8192, 'cpuThreads': min(4, os.cpu_count() or 2),
                'autoStart': True, 'maxTokens': 512, 'clearApiKey': True})
            if start_runtime:
                from backend.core.local_model_runtime import start
                start(cfg)
        update(phase='installed', downloaded=MODEL['size'])
    except Exception as error:
        # Deliberately omit upstream URLs/headers from the user-facing error.
        message = str(error) if isinstance(error, ValueError) else 'Model setup failed. Check Internet access, disk space and the backend log; then retry.'
        update(phase='failed', error=message)
        log.exception('CPU_MODEL_INSTALL_ERROR')
        raise
    finally:
        temporary.unlink(missing_ok=True)
    return status()


def begin_install():
    global THREAD
    with LOCK:
        if THREAD and THREAD.is_alive():
            raise HTTPException(409, 'CPU model setup is already running.')
        def worker():
            try: install()
            except Exception: pass  # Details are retained in STATE and backend log.
        THREAD = threading.Thread(target=worker, name='chopper-model-install', daemon=True)
        STATE.update(phase='preparing', downloaded=0, error='')
        THREAD.start()
    return status()
