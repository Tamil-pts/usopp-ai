"""Versioned, paged engineering graph. Building is explicit; queries never rebuild."""
from collections import Counter, deque
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading

from .builder import Builder, VERSION, read_index, fingerprint, identity

_LOCKS = {}; _LOCK = threading.Lock()
SCHEMA = '''
CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE files(path TEXT PRIMARY KEY,status TEXT,sha TEXT,size INTEGER,mtime INTEGER,language TEXT,props TEXT);
CREATE TABLE blocks(id TEXT PRIMARY KEY,kind TEXT,name TEXT,file TEXT,first INTEGER,last INTEGER,scope TEXT,language TEXT,layer TEXT,status TEXT,props TEXT);
CREATE INDEX block_kind ON blocks(kind); CREATE INDEX block_name ON blocks(name); CREATE INDEX block_file ON blocks(file);
CREATE TABLE relations(id TEXT PRIMARY KEY,source TEXT REFERENCES blocks(id),target TEXT REFERENCES blocks(id),kind TEXT,file TEXT,first INTEGER,last INTEGER,status TEXT,props TEXT);
CREATE INDEX edge_source ON relations(source,kind); CREATE INDEX edge_target ON relations(target,kind);
CREATE TABLE issues(id TEXT PRIMARY KEY,code TEXT,severity TEXT,file TEXT,block TEXT,message TEXT);
CREATE TABLE tokens(file TEXT,ordinal INTEGER,line INTEGER,column INTEGER,kind TEXT,text TEXT,PRIMARY KEY(file,ordinal));
'''


def build(index):
    """Publish only after a complete transaction; retain the previous good graph on failure."""
    with _LOCK: lock = _LOCKS.setdefault(str(index.path), threading.Lock())
    with lock:
        data = read_index(index)
        if not (data['meta'].get('state') or {}).get('ready'): raise ValueError('Finish project indexing before building engineering blocks.')
        signature = fingerprint(data)
        path = index.path.parent/'engineering_model.sqlite3'
        descriptor, temporary = tempfile.mkstemp(prefix='engineering-build-',suffix='.sqlite3',dir=index.path.parent)
        os.close(descriptor)
        try:
            with closing(sqlite3.connect(temporary)) as db:
                db.execute('PRAGMA foreign_keys=ON');db.executescript(SCHEMA)
                builder = Builder(index,data,db)
                builder.inventory();builder.configurations();builder.routine_blocks();builder.logic();builder.cross_layers();builder.persist()
                report = validate_connection(db)
                if not report['structurallyValid']: raise ValueError('Engineering graph integrity failed: '+json.dumps(report))
                meta = {'schema':VERSION,'fingerprint':signature,'indexKey':index.key,'project':index.root.name,
                        'activeConfiguration':builder.active,'createdAt':datetime.now(timezone.utc).isoformat(),
                        'automaticChatEnabled':False,'runtimeSimulated':False,
                        'tokenMeaning':'Source lexical tokens, not model subword tokens; concept tags are separate block properties.',
                        'validation':report}
                db.executemany('INSERT INTO meta VALUES (?,?)',[(key,json.dumps(value)) for key,value in meta.items()]);db.commit()
            if fingerprint(read_index(index,False)) != signature: raise ValueError('Project index changed during build; retry against its completed revision.')
            os.replace(temporary,path)
        finally:
            if os.path.isfile(temporary): os.remove(temporary)
    return EngineeringModel(index).structure()


def validate_connection(db):
    dangling = db.execute('SELECT count(*) FROM relations e LEFT JOIN blocks a ON a.id=e.source LEFT JOIN blocks b ON b.id=e.target WHERE a.id IS NULL OR b.id IS NULL').fetchone()[0]
    spans = db.execute("SELECT count(*) FROM blocks b LEFT JOIN files f ON f.path=b.file WHERE b.file<>'' AND (f.path IS NULL OR b.first<1 OR b.last<b.first OR b.last>coalesce(json_extract(f.props,'$.lineCount'),b.last))").fetchone()[0]
    edge_spans = db.execute("SELECT count(*) FROM relations e LEFT JOIN files f ON f.path=e.file WHERE e.file<>'' AND (f.path IS NULL OR e.first<1 OR e.last<e.first OR e.last>coalesce(json_extract(f.props,'$.lineCount'),e.last))").fetchone()[0]
    unresolved = db.execute("SELECT count(*) FROM issues").fetchone()[0]
    samples=[tuple(row) for row in db.execute("SELECT b.kind,b.file,b.first,b.last,json_extract(f.props,'$.lineCount') FROM blocks b LEFT JOIN files f ON f.path=b.file WHERE b.file<>'' AND (f.path IS NULL OR b.first<1 OR b.last<b.first OR b.last>coalesce(json_extract(f.props,'$.lineCount'),b.last)) LIMIT 5")]
    partial = db.execute("SELECT count(*) FROM files WHERE status IN ('partial','not-indexed','index-failed','size-limit','unsupported-binary')").fetchone()[0]
    roots={row[0] for row in db.execute("SELECT id FROM blocks WHERE kind='task' AND json_extract(props,'$.active')=1 AND json_extract(props,'$.enabled')=1")}
    routine_ids={row[0] for row in db.execute("SELECT id FROM blocks WHERE kind IN ('routine','function','function_block')")}
    adjacency={}
    for source,target in db.execute("SELECT source,target FROM relations WHERE kind IN ('EXECUTES','CONTAINS','CALLS','INSTANCE_OF')"):
        adjacency.setdefault(source,[]).append(target)
    frontier=list(roots);reachable=set()
    while frontier:
        node=frontier.pop()
        if node in reachable:continue
        reachable.add(node);frontier.extend(adjacency.get(node,[]))
    errors = [message for count,message in [(dangling,'Dangling relation endpoints'),(spans,'Invalid block source spans'),(edge_spans,'Invalid relation source spans')] if count]
    return {'structurallyValid':not errors,'errors':errors,'danglingRelations':dangling,'invalidSourceSpans':spans+edge_spans,
            'unresolvedChecks':unresolved,'partialSourceFiles':partial,'semanticStatus':'partial' if unresolved or partial else 'source-model-only',
            'activeExecutionContexts':len(roots),'reachableRoutineBlocks':len(routine_ids&reachable),
            'unreachableOrUnassignedRoutineBlocks':len(routine_ids-reachable),
            'reachabilityMeaning':'Configured manifest/call reachability, not proof that conditional calls execute.',
            'invalidBlockSamples':samples,'completeMachineUnderstanding':False,'safeForAutomaticMachineClaims':False,
            'meaning':'Valid graph structure does not prove PLC behavior, task ordering, or machine safety.'}


def page_args(offset,limit): return max(0,min(10000000,int(offset))),max(1,min(500,int(limit)))


def unpack(row):
    item = dict(row)
    if 'props' in item: item['properties'] = json.loads(item.pop('props'))
    return item


class EngineeringModel:
    def __init__(self,index):
        self.index=index;self.path=index.path.parent/'engineering_model.sqlite3'

    @contextmanager
    def connect(self):
        if not self.path.is_file():raise ValueError('Build engineering blocks for this project first.')
        db=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
        try:
            meta={row['key']:json.loads(row['value']) for row in db.execute('SELECT * FROM meta')}
            if meta.get('schema')!=VERSION or meta.get('fingerprint')!=fingerprint(read_index(self.index,False)):
                raise ValueError('Engineering graph is stale; explicitly rebuild against the current index/parser revision.')
            from python_engine.project_paths import project_files
            from backend.core.project_intelligence import EXCLUDED
            current_paths={p.relative_to(self.index.root).as_posix() for p in project_files(self.index.root,EXCLUDED)}
            saved_paths={row[0] for row in db.execute("SELECT path FROM files WHERE status NOT LIKE 'excluded%'")}
            if current_paths!=saved_paths:raise ValueError('Project inventory changed; explicitly rebuild the engineering graph.')
            # Detect source edits even before the source index is refreshed.
            for row in db.execute("SELECT path,size,mtime FROM files WHERE sha<>'' AND status NOT LIKE 'excluded%' AND status<>'unsupported'"):
                candidate=self.index.root/row['path']
                if not candidate.is_file() or candidate.is_symlink() or not candidate.resolve().is_relative_to(self.index.root):
                    raise ValueError('Indexed source is missing or outside the project: '+row['path'])
                stat=candidate.stat()
                if stat.st_size!=row['size'] or stat.st_mtime_ns!=row['mtime']:raise ValueError('Source changed; refresh index and engineering graph: '+row['path'])
            yield db,meta
        finally:db.close()

    def structure(self):
        with self.connect() as (db,meta):
            counts={key:dict(db.execute('SELECT '+field+',count(*) FROM '+table+' GROUP BY '+field).fetchall())
                    for key,table,field in [('blocks','blocks','kind'),('relations','relations','kind'),('files','files','status')]}
            roots=[unpack(row) for row in db.execute("SELECT * FROM blocks WHERE kind='task' ORDER BY file,first")]
            return {**meta,'counts':counts,'sourceTokens':db.execute('SELECT count(*) FROM tokens').fetchone()[0],
                    'executionContexts':roots,'entryPointBasis':'CPU task SOURCE plus program manifest membership, never a routine named main',
                    'layerOrder':['project','execution','logic','symbols','state','calls','hmi','hardware'],
                    'validation':validate_connection(db)}

    def blocks(self,kind='',file='',q='',offset=0,limit=100):
        offset,limit=page_args(offset,limit);where=[];values=[]
        for field,value in [('kind',kind),('file',file)]:
            if value:where.append(field+'=?');values.append(value)
        if q:where.append('(name LIKE ? OR scope LIKE ?)');values.extend(['%'+q[:200]+'%']*2)
        clause=' WHERE '+' AND '.join(where) if where else ''
        with self.connect() as (db,_):
            total=db.execute('SELECT count(*) FROM blocks'+clause,values).fetchone()[0]
            rows=[unpack(row) for row in db.execute('SELECT * FROM blocks'+clause+' ORDER BY file,first,kind,id LIMIT ? OFFSET ?',(*values,limit,offset))]
        for row in rows:
            for field in ('ir','diagram'):row['properties'].pop(field,None)
        return {'items':rows,'total':total,'offset':offset,'nextOffset':offset+limit if offset+limit<total else None}

    def block(self,block_id,include_ir=False):
        with self.connect() as (db,_):
            row=db.execute('SELECT * FROM blocks WHERE id=?',(block_id,)).fetchone()
            if not row:raise ValueError('Engineering block not found in this project.')
            result=unpack(row)
            if not include_ir:
                for field in ('ir','diagram'):result['properties'].pop(field,None)
            result['relationships']=[unpack(edge) for edge in db.execute('SELECT * FROM relations WHERE source=? OR target=? ORDER BY kind,first LIMIT 100',(block_id,block_id))]
            result['relationshipsArePaged']=True
            return result

    def relations(self,block_id='',kind='',offset=0,limit=100):
        offset,limit=page_args(offset,limit);where=[];values=[]
        if block_id:where.append('(source=? OR target=?)');values.extend([block_id]*2)
        if kind:where.append('kind=?');values.append(kind)
        clause=' WHERE '+' AND '.join(where) if where else ''
        with self.connect() as (db,_):
            total=db.execute('SELECT count(*) FROM relations'+clause,values).fetchone()[0]
            rows=[unpack(row) for row in db.execute('SELECT * FROM relations'+clause+' ORDER BY file,first,id LIMIT ? OFFSET ?',(*values,limit,offset))]
        return {'items':rows,'total':total,'offset':offset,'nextOffset':offset+limit if offset+limit<total else None}

    def tokens(self,file,offset=0,limit=100):
        offset,limit=page_args(offset,limit)
        with self.connect() as (db,_):
            total=db.execute('SELECT count(*) FROM tokens WHERE file=?',(file,)).fetchone()[0]
            rows=[dict(row) for row in db.execute('SELECT * FROM tokens WHERE file=? ORDER BY ordinal LIMIT ? OFFSET ?',(file,limit,offset))]
        return {'items':rows,'total':total,'offset':offset,'nextOffset':offset+limit if offset+limit<total else None,'meaning':'Source lexical tokens, not LLM tokens'}

    def validate(self,offset=0,limit=100):
        offset,limit=page_args(offset,limit)
        with self.connect() as (db,_):
            report=validate_connection(db)
            rows=[dict(row) for row in db.execute('SELECT * FROM issues ORDER BY code,file,id LIMIT ? OFFSET ?',(limit,offset))]
            total=db.execute('SELECT count(*) FROM issues').fetchone()[0]
        return {**report,'issues':rows,'total':total,'offset':offset,'nextOffset':offset+limit if offset+limit<total else None}

    def execution_flow(self,task_id='',limit=200):
        _,limit=page_args(0,limit)
        with self.connect() as (db,_):
            tasks=[unpack(row) for row in db.execute("SELECT * FROM blocks WHERE kind='task'"+(' AND id=?' if task_id else ''),(task_id,) if task_id else ())]
            if not task_id:tasks=[task for task in tasks if task['properties']['active'] and task['properties']['enabled']]
            contexts=[]
            for task in tasks:
                program_ids=[r[0] for r in db.execute("SELECT target FROM relations WHERE source=? AND kind='EXECUTES'",(task['id'],))]
                routines=[unpack(row) for p in program_ids for row in db.execute("SELECT b.* FROM relations e JOIN blocks b ON b.id=e.target WHERE e.source=? AND e.kind='CONTAINS'",(p,))]
                frontier=deque(r['id'] for r in routines);seen=set();calls=[]
                while frontier and len(calls)<limit:
                    node=frontier.popleft()
                    if node in seen:continue
                    seen.add(node)
                    for row in db.execute("SELECT * FROM relations WHERE source=? AND kind IN ('CALLS','INSTANCE_OF')",(node,)):
                        edge=unpack(row);calls.append(edge);frontier.append(edge['target'])
                        if len(calls)>=limit:break
                for routine in routines:routine['properties'].pop('ir',None)
                contexts.append({'task':task,'entryRoutines':routines,'reachableCalls':calls,'partial':bool(frontier),
                                 'unvisitedFrontier':list(frontier),'scanOrder':'Per-task lifecycle phases only; no cross-task total order asserted.'})
        return {'contexts':contexts,'runtimeSimulated':False,'completeMachineSequence':False,'limitPerTask':limit}

    def trace_signal(self,name,scope='',limit=100):
        _,limit=page_args(0,limit)
        with self.connect() as (db,_):
            rows=[unpack(r) for r in db.execute("SELECT * FROM blocks WHERE kind IN ('variable','member_access') AND (id=? OR name=?)",(name,name))]
            if scope:rows=[r for r in rows if r['scope']==scope]
            if len(rows)!=1:return {'resolved':False,'candidates':rows,'reason':'Select one scoped symbol; same names must not be merged.'}
            frontier=deque([rows[0]['id']]);seen=set();links={};nodes={rows[0]['id']:rows[0]}
            while frontier and len(links)<limit:
                node=frontier.popleft()
                if node in seen:continue
                seen.add(node)
                # Incoming writers/control conditions, then outgoing reads of
                # those writers. Mapping edges are supporting links, not causes.
                edges=list(db.execute("SELECT * FROM relations WHERE target=? AND kind IN ('WRITES','CONTROLS','BINDS_TO','MAPS_TO','MEMBER_OF') OR source=? AND kind IN ('READS','MEMBER_OF') ORDER BY kind,id",(node,node)))
                for raw in edges:
                    edge=unpack(raw);links[edge['id']]=edge
                    other=edge['source'] if edge['target']==node else edge['target']
                    row=db.execute('SELECT * FROM blocks WHERE id=?',(other,)).fetchone();item=unpack(row)
                    item['properties'].pop('ir',None);item['properties'].pop('diagram',None);nodes[other]=item
                    if edge['kind'] not in {'BINDS_TO','MAPS_TO'}:frontier.append(other)
                    if len(links)>=limit:break
            return {'resolved':True,'symbol':rows[0],'blocks':list(nodes.values()),'relationships':list(links.values()),
                    'partial':bool(frontier),'unvisitedFrontier':list(frontier),'runtimeValuesSupplied':False,
                    'meaning':'Typed source relationships; physical bindings and signal reads are not proof of live execution.'}

    def find_function(self,question,limit=20):
        _,limit=page_args(0,limit)
        stop=set('the a an explain full complete machine function how does work working is of for'.split())
        def terms(text):
            text=re.sub(r'([a-z])([A-Z])',r'\1 \2',text)
            return {re.sub(r'^(?:changing|changer)$','change',t) for t in re.findall(r'[a-z0-9]+',text.casefold())}-stop
        wanted=terms(question);scored=[]
        with self.connect() as (db,_):
            for raw in db.execute("SELECT * FROM blocks WHERE kind IN ('routine','function','function_block','variable','program')"):
                row=unpack(raw);overlap=terms(row['name']+' '+row['file'])&wanted
                if not overlap:continue
                row['properties'].pop('ir',None);row['matchTerms']=sorted(overlap);row['score']=len(overlap)
                row['classification']='source candidate, not a verified machine function';scored.append(row)
        return {'candidates':sorted(scored,key=lambda r:(-r['score'],r['file'],r['first']))[:limit],
                'candidateCount':len(scored),'query':question,'usesEmbeddings':False,'meaning':'Lexical concept discovery; inspect relationships before inferring purpose.'}

    def compare(self,other,limit=100):
        _,limit=page_args(0,limit)
        def semantic(value):
            if isinstance(value,dict):return {k:semantic(v) for k,v in value.items() if k not in {'line','endLine','first','last','id'}}
            if isinstance(value,list):return [semantic(v) for v in value]
            return value
        with self.connect() as (a,_),other.connect() as (b,_):
            left={r['id']:unpack(r) for r in a.execute('SELECT * FROM blocks')}
            right={r['id']:unpack(r) for r in b.execute('SELECT * FROM blocks')}
            def edges(db):
                result={}
                for raw in db.execute('SELECT * FROM relations'):
                    edge=unpack(raw);key=identity(edge['kind'],edge['source'],edge['target'],semantic(edge['properties']))
                    result[key]=edge
                return result
            left_edges,right_edges=edges(a),edges(b)
        added=sorted(right.keys()-left.keys());removed=sorted(left.keys()-right.keys())
        changed=sorted(key for key in left.keys()&right.keys() if semantic(left[key])!=semantic(right[key]))
        return {'added':[right[k] for k in added[:limit]],'removed':[left[k] for k in removed[:limit]],
                'modified':[{'before':left[k],'after':right[k]} for k in changed[:limit]],
                'counts':{'added':len(added),'removed':len(removed),'modified':len(changed)},
                'relationshipCounts':{'added':len(right_edges.keys()-left_edges.keys()),'removed':len(left_edges.keys()-right_edges.keys())},
                'partial':max(len(added),len(removed),len(changed))>limit,'meaning':'Engineering block changes; behavioral equivalence is not proved.'}
