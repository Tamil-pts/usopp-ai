"""Optional, owner-scoped hybrid retrieval. Similarity never creates a fact."""
from contextlib import closing
import hashlib
import json
import os
import sqlite3
import tempfile
import threading

import numpy as np
import requests
from backend.core import semantic_runtime as runtime

VERSION='semantic-v1-chunks1200-overlap250-bge384'
JOBS={};LOCK=threading.RLock()


def snapshot(index,db,verify=True):
    from backend.core.project_intelligence import metadata
    if not db.in_transaction:db.execute('BEGIN')
    files=[dict(row) for row in db.execute('SELECT * FROM files ORDER BY path')]
    sections=[dict(row) for row in db.execute('SELECT * FROM sections ORDER BY id')]
    state=metadata(db,'state') or {}
    if not state.get('ready'):raise ValueError('Finish project indexing before building semantic retrieval.')
    if verify:
        discovered={p.relative_to(index.root).as_posix() for p in index.discover(threading.Event(),{},lambda:None)}
        if discovered!={row['path'] for row in files}:raise ValueError('Project files were added or removed; refresh the source index and rebuild semantic retrieval.')
        for row in files:
            if row['status']!='indexed':continue
            path=(index.root/row['path']).resolve()
            if not path.is_relative_to(index.root) or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha']:
                raise ValueError('Project source changed; refresh its source index and rebuild semantic retrieval.')
    identity={'version':VERSION,'owner':index.owner,'project':index.key,'parser':metadata(db,'parser_revision'),
              'configuration':metadata(db,'identity'),'models':runtime.MODELS,'files':files,'sections':sections}
    digest=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return digest,sections


def index_path(index):return index.path.parent/'semantic.sqlite3'


def status(index,check=False):
    with LOCK:job=JOBS.get(index.key)
    if job and job.get('running'):return {key:value for key,value in job.items() if key!='thread'}
    result={'ready':False,'running':False,'phase':'not_built','chunks':0,'message':'Build semantic retrieval for this project after indexing.'}
    if index_path(index).is_file():
        try:
            with closing(sqlite3.connect(index_path(index).resolve().as_uri()+'?mode=ro',uri=True)) as db:result.update(json.loads(db.execute('SELECT value FROM meta').fetchone()[0]),ready=True,phase='ready')
            if check:
                from backend.core.project_intelligence import connection
                with connection(index.path) as db:fingerprint,_=snapshot(index,db)
                if result['fingerprint']!=fingerprint:raise ValueError('The semantic index is stale; rebuild it after refreshing source indexing.')
        except (OSError,ValueError,sqlite3.Error) as error:result.update(ready=False,phase='stale',message=str(error))
    if job and job.get('error'):result.update(error=job['error'])
    return result


def build(index):
    from backend.core.project_intelligence import connection
    with connection(index.path) as db:fingerprint,sections=snapshot(index,db)
    chunks=[]
    for row in sections:
        if not row['enabled']:continue
        for start in range(0,len(row['text']),950):
            excerpt=row['text'][start:start+1200]
            if excerpt.strip():chunks.append((row['id'],start,row['file']+'\n'+row['label']+'\n'+excerpt))
    if not chunks:raise ValueError('There are no enabled source sections to embed.')
    if len(chunks)>20000:raise ValueError('Semantic retrieval supports 20,000 source chunks per project. Split this project or retain existing lexical/graph retrieval.')
    fd,temporary=tempfile.mkstemp(prefix='semantic-build-',suffix='.sqlite3',dir=index.path.parent);os.close(fd)
    try:
        with runtime.QUERY_LOCK,closing(sqlite3.connect(temporary)) as target:
            target.executescript('CREATE TABLE meta(value TEXT);CREATE TABLE vectors(section INTEGER,start INTEGER,vector BLOB);')
            for offset in range(0,len(chunks),8):
                part=chunks[offset:offset+8];vectors=runtime.embeddings([item[2] for item in part])
                target.executemany('INSERT INTO vectors VALUES (?,?,?)',[(item[0],item[1],vector.tobytes()) for item,vector in zip(part,vectors)])
                with LOCK:
                    if index.key in JOBS:JOBS[index.key].update(chunks=offset+len(part),totalChunks=len(chunks))
            with connection(index.path) as db:current,_=snapshot(index,db)
            if current!=fingerprint:raise ValueError('Project/index changed during embedding; the previous semantic index was retained.')
            target.execute('INSERT INTO meta VALUES (?)',(json.dumps({'fingerprint':fingerprint,'owner':index.owner,'projectId':index.key,'chunks':len(chunks),'dimensions':384,'version':VERSION}),));target.commit()
        os.replace(temporary,index_path(index))
    finally:
        if os.path.isfile(temporary):os.remove(temporary)
    return status(index)


def begin_build(index):
    with LOCK:
        if JOBS.get(index.key,{}).get('running'):return status(index)
        if any(job.get('running') for job in JOBS.values()):raise ValueError('Wait for the current semantic index build to finish.')
        job={'running':True,'ready':False,'phase':'building','chunks':0,'error':''};JOBS[index.key]=job
        def worker():
            try:build(index);job.update(phase='ready',ready=True)
            except Exception as error:job.update(phase='failed',error=str(error)[:300])
            finally:job['running']=False
        thread=threading.Thread(target=worker,name='chopper-semantic-index',daemon=True);job['thread']=thread;thread.start()
        return status(index)


def candidates(index,db,question):
    info={'enabled':False,'used':False,'reranked':False,'engine':'NumPy exact cosine / SQLite vectors'}
    try:info['enabled']=runtime.settings()['enabled']
    except ValueError as error:return {},{**info,'notice':str(error)+' Existing lexical/graph retrieval is retained.'}
    if not info['enabled']:return {},info
    if not index_path(index).is_file():return {},{**info,'notice':'Semantic retrieval is enabled but this project has no semantic index. Existing lexical/graph retrieval is retained.'}
    if not runtime.QUERY_LOCK.acquire(timeout=.1):return {},{**info,'notice':'The local retrieval model is busy. Existing lexical/graph retrieval is retained.'}
    try:
        fingerprint,_=snapshot(index,db)
        with closing(sqlite3.connect(index_path(index).resolve().as_uri()+'?mode=ro',uri=True)) as cache:
            meta=json.loads(cache.execute('SELECT value FROM meta').fetchone()[0])
            if meta.get('fingerprint')!=fingerprint or meta.get('owner')!=index.owner or meta.get('projectId')!=index.key:
                raise ValueError('Semantic retrieval is stale or belongs to another scope; rebuild this project index.')
            rows=cache.execute('SELECT section,vector FROM vectors').fetchall()
        if len(rows)>20000:raise ValueError('Semantic vector count exceeds its inspection limit.')
        vectors=np.stack([np.frombuffer(row[1],dtype=np.float32) for row in rows])
        if vectors.shape!=(len(rows),384) or not np.isfinite(vectors).all():raise ValueError('Semantic index contains invalid vectors.')
        query=runtime.embeddings([question],query=True)[0];similarities=vectors@query
        matches={}
        for position in np.argsort(-similarities,kind='stable'):
            identifier=rows[int(position)][0]
            if identifier not in matches:matches[identifier]=float(similarities[position])
            if len(matches)>=48:break
        info.update(used=True,fingerprint=fingerprint,embeddingModel=runtime.MODELS['embedding']['sha256'],candidates=len(matches))
        return matches,info
    except (ValueError,OSError,sqlite3.Error,requests.RequestException) as error:
        return {},{**info,'notice':str(error)[:300]+' Existing lexical/graph retrieval is retained.'}
    finally:runtime.QUERY_LOCK.release()


def rank(candidates,dense,question,info):
    lexical=sorted(candidates.values(),key=lambda row:(-row['score'],row['file'],row['first']))
    if not info['used']:return lexical
    dense_order={identifier:position for position,identifier in enumerate(dense)}
    pinned=[];others=[]
    for position,row in enumerate(lexical):
        if row['matchReason'].startswith(('Explicit source','Named routine','Exact symbol','Declaration ')):pinned.append(row);continue
        score=1/(60+position+1)+(1/(60+dense_order[row['id']]+1) if row['id'] in dense_order else 0)
        others.append((score,row))
    others=[row for _,row in sorted(others,key=lambda item:(-item[0],item[1]['file'],item[1]['first']))]
    if runtime.settings()['rerank'] and others and runtime.QUERY_LOCK.acquire(timeout=.1):
        try:
            count=min(24,len(others));scores=runtime.rerank(question,[row['text'] for row in others[:count]])
            by_id={row['id']:scores[position] for position,row in enumerate(others[:count])}
            others=sorted(others[:count],key=lambda row:(-by_id[row['id']],row['file'],row['first']))+others[count:]
            info.update(reranked=True,rerankedCandidates=count,rerankerModel=runtime.MODELS['reranker']['sha256'])
        except (ValueError,requests.RequestException) as error:info['notice']='Reranking unavailable: '+str(error)[:160]+'. Fused retrieval is retained.'
        finally:runtime.QUERY_LOCK.release()
    return pinned+others
