"""Local, bounded speech recognition. Transcripts are drafts, never tool requests."""
from pathlib import Path
import importlib.util
import json
import os
import re
import threading
import time
import uuid
import numpy as np
from fastapi import HTTPException
from backend.core.runtime import BASE

ROOT=BASE/'.usopp_speech_jobs'
LANGUAGES={'auto':None,'ta':'ta','en':'en','hi':'hi','tanglish':None}
LOCK=threading.RLock();SLOT=threading.BoundedSemaphore(1);MODEL_LOCK=threading.Lock();MODEL=None;MODEL_ID=None
MAX_BYTES=20*1024*1024;MAX_SECONDS=300

def model_path():return Path(os.getenv('USOPP_CHOPPER_SPEECH_MODEL') or os.getenv('USOPP_PI_WHISPER_MODEL') or BASE/'local_ai/models/whisper-small').expanduser()
def status():
    path=model_path();installed=importlib.util.find_spec('faster_whisper') is not None
    configured=all((path/f).is_file() for f in ('model.bin','config.json','tokenizer.json'))
    return {'installed':installed,'modelAvailable':configured,'ready':installed and configured,'model':path.name,'localOnly':True,
            'languages':[{'id':k,'name':v} for k,v in [('auto','Auto detect'),('ta','Tamil'),('en','English'),('hi','Hindi'),('tanglish','Tanglish / Tamil + English')]],
            'maxBytes':MAX_BYTES,'maxSeconds':MAX_SECONDS,'requiresTranscriptReview':True,'downloadsDuringTranscription':False}

def write(folder,value):
    with LOCK:
        temp=folder/'job.tmp';temp.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8');temp.replace(folder/'job.json')
def load(folder):
    with LOCK:return json.loads((folder/'job.json').read_text(encoding='utf-8'))
def stamp(user):return str(user.get('createdAt',0))
def opened(key,user):
    if not re.fullmatch(r'[a-f0-9]{32}',key):raise HTTPException(404,'Transcription not found.')
    folder=ROOT/key
    if not (folder/'job.json').is_file():raise HTTPException(404,'Transcription not found.')
    value=load(folder)
    if value['owner']!=user['id'] or value['ownerIdentity']!=stamp(user):raise HTTPException(404,'Transcription not found.')
    if time.time()-value['created']>86400:raise HTTPException(410,'This temporary transcript expired. Upload the audio again.')
    if value['status'] in {'queued','loading','transcribing'} and value['process']!=os.getpid():
        for raw in folder.glob('audio.*'):raw.unlink(missing_ok=True)
        value.update(status='failed',error='Transcription was interrupted by a server restart. Upload the audio again.');write(folder,value)
    return folder,value
def public(value):return {k:v for k,v in value.items() if k not in {'owner','ownerIdentity','process'}}

def decode(path):
    import av
    with path.open('rb') as source:head=source.read(16)
    if not (head.startswith((b'RIFF',b'ID3',b'OggS',b'fLaC',b'\x1aE\xdf\xa3')) or len(head)>8 and head[4:8]==b'ftyp' or head[:1]==b'\xff'):
        raise ValueError('The file does not contain a supported audio recording.')
    chunks=[];samples=0
    with av.open(str(path),options={'protocol_whitelist':'file,pipe'}) as container:
        if not container.streams.audio:raise ValueError('No audio stream was found.')
        resampler=av.AudioResampler(format='fltp',layout='mono',rate=16000)
        for frame in container.decode(audio=0):
            for converted in resampler.resample(frame):
                array=converted.to_ndarray().flatten();samples+=len(array)
                if samples>MAX_SECONDS*16000:raise ValueError('Use recordings no longer than five minutes.')
                chunks.append(array)
        for converted in resampler.resample(None):
            array=converted.to_ndarray().flatten();samples+=len(array);chunks.append(array)
    if not samples or samples>MAX_SECONDS*16000:raise ValueError('The recording is empty or longer than five minutes.')
    return np.concatenate(chunks).astype(np.float32)

def recognize(audio,language,check=lambda:None):
    global MODEL,MODEL_ID
    path=model_path();state=status()
    if not state['ready']:raise ValueError('Local speech recognition is not configured. Install the speech dependencies and multilingual model on this server.')
    identity=tuple((str(path.resolve()/f),(path/f).stat().st_mtime_ns) for f in ('model.bin','config.json','tokenizer.json'))
    with MODEL_LOCK:
        if MODEL is None or MODEL_ID!=identity:
            from faster_whisper import WhisperModel
            MODEL=WhisperModel(str(path),device='cpu',compute_type='int8',cpu_threads=2,local_files_only=True);MODEL_ID=identity
        if not MODEL.model.is_multilingual:raise ValueError('Choose a multilingual speech model for Tamil, Hindi and Tanglish.')
        check()
        segments,info=MODEL.transcribe(audio,language=LANGUAGES[language],multilingual=language=='tanglish',task='transcribe',beam_size=5,
            vad_filter=True,word_timestamps=True,condition_on_previous_text=False,
            initial_prompt='Engineering terms: PLC, HMI, B&R, SpinConnect, servo, VFD, Modbus, Group Code, tag code.')
        rows=[]
        for segment in segments:
            check()
            if len(rows)>=1500:raise ValueError('Too many transcript segments. Split the recording.')
            rows.append({'start':round(segment.start,2),'end':round(segment.end,2),'text':segment.text.strip(),
                         'uncertain':segment.avg_logprob<-1 or segment.no_speech_prob>.6 or any(w.probability<.5 for w in segment.words or [])})
        return {'text':' '.join(r['text'] for r in rows).strip(),'segments':rows,'detectedLanguage':info.language,
                'languageProbability':info.language_probability,'duration':round(len(audio)/16000,2),'requestedLanguage':language,
                'notice':'Review the transcript, numbers and PLC tags before use. Mixed Tamil/English may use Tamil script; Latin-script Tanglish is not guaranteed.'}

def worker(folder,path,language):
    def check():
        if load(folder)['status']=='cancelled':raise InterruptedError('Transcription cancelled.')
    def update(**patch):
        with LOCK:
            value=load(folder)
            if value['status']=='cancelled':raise InterruptedError('Transcription cancelled.')
            value.update(patch);write(folder,value)
    try:
        check();update(status='loading');audio=decode(path);check()
        if float(np.max(np.abs(audio)))<.0001:
            update(status='ready',result={'text':'','segments':[],'duration':round(len(audio)/16000,2),'notice':'No speech detected. Record a clear sample and try again.'});return
        update(status='transcribing');result=recognize(audio,language,check);check();update(status='ready',result=result)
    except InterruptedError:pass
    except Exception as error:
        with LOCK:
            value=load(folder)
            if value['status']!='cancelled':value.update(status='failed',error=str(error)[:350]);write(folder,value)
    finally:path.unlink(missing_ok=True);SLOT.release()

def start(upload,language,user):
    if language not in LANGUAGES:raise HTTPException(400,'Choose Tamil, English, Hindi, Tanglish or Auto detect.')
    suffix=Path(upload.filename or '').suffix.lower()
    if suffix not in {'.wav','.webm','.mp3','.m4a','.ogg','.flac','.mp4'}:raise HTTPException(400,'Upload WAV, WebM, MP3, M4A, OGG or FLAC audio.')
    if not status()['ready']:raise HTTPException(503,'Local speech model is unavailable. Configure it on the server; no audio was sent to an external service.')
    if not SLOT.acquire(blocking=False):raise HTTPException(429,'Local speech recognition is busy. Try again after the current recording finishes.')
    folder=ROOT/uuid.uuid4().hex;path=folder/('audio'+suffix)
    try:
        ROOT.mkdir(parents=True,exist_ok=True)
        # Delete only known temporary files in direct, non-symlink job folders.
        for candidate in list(ROOT.iterdir())[:500]:
            if not candidate.is_symlink() and candidate.is_dir() and re.fullmatch(r'[a-f0-9]{32}',candidate.name):
                try:
                    if time.time()-load(candidate)['created']>86400:
                        for item in candidate.iterdir():
                            if item.is_file() and (item.name in {'job.json','job.tmp'} or item.name.startswith('audio.')):item.unlink()
                        candidate.rmdir()
                except (OSError,ValueError,KeyError):pass
        folder.mkdir();size=0
        with path.open('xb') as output:
            while chunk:=upload.file.read(262144):
                size+=len(chunk)
                if size>MAX_BYTES:raise HTTPException(413,'Audio must be 20 MB or less.')
                output.write(chunk)
        if not size:raise HTTPException(400,'Audio file is empty.')
        value={'id':folder.name,'owner':user['id'],'ownerIdentity':stamp(user),'created':time.time(),'process':os.getpid(),'status':'queued','language':language}
        write(folder,value);threading.Thread(target=worker,args=(folder,path,language),daemon=True,name='chopper-speech').start();return public(value)
    except Exception:path.unlink(missing_ok=True);SLOT.release();raise
    finally:upload.file.close()
