"""Incremental, disk-backed PLC project knowledge. No validator state or writes."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import xml.etree.ElementTree as ET

from backend.core.runtime import WORK
from python_engine.project_paths import IGNORED_PROJECT_DIRS
from python_engine.project_knowledge import EXTENSIONS,category,STOP
from python_engine.project_analysis import _mask,collect_file
from python_engine.function_flow import _text_flow,_names
from python_engine.ladder_requirements import fragment
from python_engine.compare import decode_project_text
from python_engine.project_info import local_project_details

SCHEMA=1
EXCLUDED=IGNORED_PROJECT_DIRS|{'cache','generated','generatedcode','debug','release','.idea','.vs','.vscode','dbk'}
RELEVANT=EXTENSIONS|{'.prg','.pkg','.xml'}
MAX_FILE=8*1024*1024
INDEX_LOCK=threading.Lock()
JOBS={};JOBS_LOCK=threading.RLock()
KEYWORDS=set('if then else elsif end_if endif case of end_case for to by do end_for while end_while repeat until end_repeat program end_program function function_block end_function end_function_block true false and or xor not mod return exit var end_var var_global var_input var_output var_in_out var_temp var_external retain constant array struct end_struct sizeof adr'.split())
QUERY_STOP=STOP|{'in','to','of','a','an','as','is','it','be','by','at','on','do','we','me','my','your','our','their','these','those','exact','source','file','files','convert','conversion','between','into','using','use'}


def symbol(value):return re.split(r'[.\[]',str(value).strip(),1)[0].casefold()


def project_key(root,owner):return hashlib.sha256((str(owner)+'\0'+str(Path(root).resolve()).casefold()).encode()).hexdigest()


@contextmanager
def connection(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=20);db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA cache_size=-4096');db.execute('PRAGMA temp_store=FILE')
    try:yield db
    finally:db.close()


def initialize(path):
    with connection(path) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript("""
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY,size INTEGER,mtime INTEGER,sha TEXT,category TEXT,status TEXT,error TEXT);
        CREATE TABLE IF NOT EXISTS sections(id INTEGER PRIMARY KEY,file TEXT REFERENCES files(path) ON DELETE CASCADE,first INTEGER,last INTEGER,text TEXT,kind TEXT,label TEXT,complete INTEGER,enabled INTEGER,scope TEXT);
        CREATE INDEX IF NOT EXISTS section_file ON sections(file,first,last);
        CREATE VIRTUAL TABLE IF NOT EXISTS section_search USING fts5(text,tokenize='unicode61 tokenchars ''_''');
        CREATE TRIGGER IF NOT EXISTS remove_search AFTER DELETE ON sections BEGIN DELETE FROM section_search WHERE rowid=old.id; END;
        CREATE TABLE IF NOT EXISTS symbols(name TEXT,display TEXT,kind TEXT,datatype TEXT,file TEXT REFERENCES files(path) ON DELETE CASCADE,line INTEGER,scope TEXT);
        CREATE INDEX IF NOT EXISTS symbol_name ON symbols(name,scope);
        CREATE INDEX IF NOT EXISTS symbol_file ON symbols(file);
        CREATE TABLE IF NOT EXISTS refs(name TEXT,file TEXT REFERENCES files(path) ON DELETE CASCADE,line INTEGER,kind TEXT,scope TEXT);
        CREATE INDEX IF NOT EXISTS ref_name ON refs(name,kind);
        CREATE INDEX IF NOT EXISTS ref_file ON refs(file);
        CREATE TABLE IF NOT EXISTS edges(a TEXT,b TEXT,kind TEXT,file TEXT REFERENCES files(path) ON DELETE CASCADE,line INTEGER,scope TEXT,detail TEXT);
        CREATE INDEX IF NOT EXISTS edge_a ON edges(a,kind);CREATE INDEX IF NOT EXISTS edge_b ON edges(b,kind);
        CREATE INDEX IF NOT EXISTS edge_file ON edges(file);
        CREATE TABLE IF NOT EXISTS tasks(name TEXT,source TEXT,file TEXT REFERENCES files(path) ON DELETE CASCADE,line INTEGER,enabled INTEGER,configuration TEXT);
        CREATE INDEX IF NOT EXISTS task_file ON tasks(file);
        """)
        saved=db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
        if saved and json.loads(saved[0])!=SCHEMA:raise ValueError('Rebuild this project index for the updated schema.')
        db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',('schema',json.dumps(SCHEMA)));db.commit()


def metadata(db,key,value=None):
    if value is not None:db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',(key,json.dumps(value)));return value
    row=db.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
    return json.loads(row[0]) if row else None


def _line(text,position):return text.count('\n',0,position)+1


def _text(raw):
    try:return raw.decode('utf-8-sig')
    except UnicodeDecodeError:return raw.decode('cp1252',errors='replace')


def _blocks(text):
    """Complete outer IEC conditions where the parser resolves their extent."""
    lines=text.splitlines();sections=[]
    wrappers=list(re.finditer(r'(?im)^\s*(FUNCTION_BLOCK|FUNCTION|PROGRAM)\s+([A-Za-z_]\w*)[^\n]*\n',_mask(text)))
    for wrapper in wrappers:
        end=re.search(r'(?im)^\s*END_'+wrapper[1]+r'\b[^\n]*',text[wrapper.end():])
        if end:
            first=_line(text,wrapper.start());last=_line(text,wrapper.end()+end.end())
            if last-first<=220:sections.append((first,last,wrapper[2],True))
    try:
        parts,_,_,notices=_text_flow(text,'index.st',bool(re.search(r'\b(?:ENDIF|FUB|ENDLOOP)\b',_mask(text),re.I)))
        for part in parts:
            for node in part['nodes']:
                first=node['line'];last=node.get('endLine',first)
                sections.append((first,last,node.get('label') or part['name'],not notices and last>=first))
    except (ValueError,KeyError,IndexError):sections=[]
    if not sections:return [(start+1,min(len(lines),start+100),'Source window',False) for start in range(0,len(lines),90)]
    # Include program headers and otherwise unrepresented declarations as windows.
    covered=set()
    for first,last,_,_ in sections:covered.update(range(first,last+1))
    first=None
    for number in range(1,len(lines)+2):
        if number<=len(lines) and number not in covered:
            if first is None:first=number
            if number-first<89:continue
        if first is not None:
            last=number if number<=len(lines) and number not in covered else number-1
            sections.append((first,last,'Source context',False));first=None
    return sorted(set(sections))


class Index:
    def __init__(self,root,owner):
        self.root=Path(root).resolve();self.owner=str(owner);self.key=project_key(self.root,owner)
        self.path=WORK/'chopper_intelligence'/self.key/'project.sqlite3'
        initialize(self.path)

    def snapshot(self):
        with connection(self.path) as db:
            state=metadata(db,'state') or {'phase':'not_indexed','ready':False}
            counts={row['kind']:row['n'] for row in db.execute('SELECT kind,count(*) n FROM symbols GROUP BY kind')}
            state={**state,'projectId':self.key,'projectName':self.root.name,'programs':counts.get('program',0),
                   'variables':counts.get('variable',0),'functions':counts.get('function',0),'functionBlocks':counts.get('function_block',0),
                   'dependencies':db.execute('SELECT count(*) FROM edges').fetchone()[0],
                   'dataTypes':counts.get('data_type',0),'blockInstances':db.execute("SELECT count(*) FROM edges e WHERE kind='instance-of' AND EXISTS(SELECT 1 FROM symbols s WHERE s.name=e.b AND s.kind='function_block')").fetchone()[0],
                   'sections':db.execute('SELECT count(*) FROM sections').fetchone()[0],
                   'failedFiles':[dict(row) for row in db.execute("SELECT path,error FROM files WHERE status='failed' ORDER BY path LIMIT 30")]}
        return state

    def discover(self,cancel,state,publish):
        candidates=[];state.update(totalFiles=0,excludedFiles=0,excludedFolders=0,eligibleFiles=0,phase='discovering',percentage=None)
        def walk(folder,excluded=False):
            if cancel.is_set():raise InterruptedError('Indexing cancelled.')
            try:
                with os.scandir(folder) as entries:
                    for item in entries:
                        if cancel.is_set():raise InterruptedError('Indexing cancelled.')
                        if item.is_symlink():state['excludedFiles']+=1;state['totalFiles']+=1;continue
                        if item.is_dir(follow_symlinks=False):
                            skip=excluded or item.name.casefold() in EXCLUDED
                            if skip and not excluded:state['excludedFolders']+=1
                            walk(item.path,skip)
                        elif item.is_file(follow_symlinks=False):
                            state['totalFiles']+=1
                            if excluded or Path(item.name).suffix.casefold() not in RELEVANT:state['excludedFiles']+=1
                            else:candidates.append(Path(item.path));state['eligibleFiles']+=1
                            if state['totalFiles']%200==0:publish()
            except PermissionError:state['unreadableFolders']=state.get('unreadableFolders',0)+1
        walk(self.root);return sorted(candidates,key=lambda path:path.as_posix().casefold())

    def parse(self,path,text):
        relative=path.relative_to(self.root).as_posix();kind=category(path);suffix=path.suffix.casefold()
        lines=text.splitlines();scope=path.parent.relative_to(self.root).as_posix().casefold()
        sections=[];symbols=[];refs=[];edges=[];tasks=[];notices=[]
        def ref(name,line,role):
            name=symbol(name)
            if name and name not in KEYWORDS:refs.append((name,relative,line,role,scope))
        def edge(a,b,role,line,detail=''):
            if symbol(a) and symbol(b):edges.append((symbol(a),symbol(b),role,relative,line,scope,detail))
        def section(first,last,label,complete=True,enabled=True,body=None):
            body='\n'.join(lines[first-1:last]) if body is None else body
            # Preserve complete sections on disk; retrieval has its own token bound.
            sections.append((relative,first,last,body,kind,str(label)[:160],int(complete),int(enabled),scope))
        if suffix=='.ld' or '<networks' in text:
            networks=fragment(text);originals=list(re.finditer(r'<network\b[^>]*>.*?</network\s*>',text,re.I|re.S))
            for index,network in enumerate(networks):
                first=_line(text,originals[index].start()) if index<len(originals) else 1
                body=originals[index][0] if index<len(originals) else ET.tostring(network,encoding='unicode')
                enabled=network.get('commented','0').casefold() not in {'1','true'}
                section(first,first+body.count('\n'),f'Network {index+1}',True,enabled,body)
                if not enabled:continue
                reads=[];writes=[]
                for node in network.iter():
                    tag=node.tag.rsplit('}',1)[-1].casefold();name=node.get('name','')
                    if tag in {'contact','coil','analog'} and re.match(r'^[A-Za-z_]',name):
                        role='write' if tag=='coil' or tag=='analog' and node.get('type')=='output' else 'read'
                        ref(name,first,role);(writes if role=='write' else reads).append(name)
                    if tag in {'function','functionblock'} and node.get('type'):
                        block=node.get('type');ref(block,first,'call');edge(path.parent.name,block,'calls',first,'Ladder function type')
                    if tag=='functionblock' and node.get('position')=='header':ref(name,first,'call-instance')
                for output in writes:
                    for value in reads:edge(output,value,'depends-on',first,'Follow the complete ladder topology; this is not an inferred AND condition.')
        else:
            blocks=_blocks(text) if suffix in {'.st','.ab','.src','.fun'} else [(i+1,min(len(lines),i+100),'Source context',False) for i in range(0,len(lines),90)]
            for first,last,label,complete in blocks:section(first,last,label,complete)
        clean=_mask(text);code=_mask(text,strings=True)
        if suffix=='.prg':symbols.append((path.stem.casefold(),path.stem,'program','',relative,1,scope))
        for match in re.finditer(r'(?im)^\s*(PROGRAM|FUNCTION_BLOCK|FUNCTION)\s+([A-Za-z_]\w*)\s*(?::\s*([^\n;]+))?',clean):
            role=match[1].casefold();name=match[2];datatype=(match[3] or '').strip()
            symbols.append((name.casefold(),name,role,datatype,relative,_line(clean,match.start(2)),scope))
        if suffix in {'.var','.typ','.fun','.pgp','.h','.prg'} or re.search(r'\bVAR(?:_GLOBAL|_INPUT|_OUTPUT|_IN_OUT)?\b',clean,re.I):
            for match in re.finditer(r'(?im)^\s*([A-Za-z_]\w*)\s*(?:AT\s+[^:;]+)?\s*:(?!=)\s*([^;\n]+);',clean):
                name=match[1];dtype=match[2].split(':=',1)[0].strip()
                if name.casefold() in KEYWORDS:continue
                local=(suffix in {'.st','.ab'} or any(path.parent.glob('*.prg'))) and not re.search(r'\bVAR_GLOBAL\b',clean,re.I)
                declared_scope=scope if local else '@global/'+scope
                role='data_type' if suffix=='.typ' and re.match(r'STRUCT|ARRAY|\(',dtype,re.I) else 'variable'
                symbols.append((name.casefold(),name,role,dtype,relative,_line(clean,match.start(1)),declared_scope))
                target=re.findall(r'[A-Za-z_]\w*',dtype)
                if target:edge(name,target[-1],'instance-of',_line(clean,match.start(1)),declared_scope)
        if suffix in {'.st','.ab','.src','.c'}:
            records=collect_file(relative,text,'Logic','indexed; task scope checked separately')
            if len(records)>=3000:notices.append('Operation extraction is bounded; inspect the complete source for additional operations.')
            for record in records:
                line=record['eventLine']
                if record['kind']=='call':ref(record['name'],line,'call');edge(path.parent.name,record['name'],'calls',line)
                elif record['kind']=='assignment':
                    destination=record['name'];ref(destination,line,'write')
                    for name in _names(record.get('value','')):ref(name,line,'read');edge(destination,name,'depends-on',line)
                elif record['kind']=='branch':
                    for name in _names(record.get('expression','')):ref(name,line,'condition');edge(path.parent.name,name,'interlock-candidate',line,'Condition reference, not proof of a safety interlock.')
            # Record reads in call arguments and conditions as well as assignments.
            for number,line in enumerate(code.splitlines(),1):
                for name in set(re.findall(r'\b[A-Za-z_]\w*(?:\.\w+)*\b',line)):
                    if name.casefold() not in KEYWORDS:ref(name,number,'use')
        if suffix in {'.page','.pages','.layer','.dso','.algrp','.txtgrp','.sw','.pkg','.apj','.hw','.hwl','.xml','.prg'} and text.lstrip().startswith('<'):
            document=ET.fromstring(text);locations=text.splitlines()
            for node in document.iter():
                tag=node.tag.rsplit('}',1)[-1]
                if tag.casefold()=='task':
                    name=node.get('Name','');source=node.get('Source','');enabled=node.get('Disabled','false').casefold()!='true'
                    number=next((i for i,line in enumerate(locations,1) if '<Task ' in line and f'Name="{name}"' in line),1)
                    tasks.append((name,source,relative,number,int(enabled),relative.split('/')[1] if relative.startswith('Physical/') else ''))
                    edge(name,source,'task-source',number)
                if tag=='Property' and node.get('Name') in {'ValueDatapoint','IndexDatapoint','StatusDatapoint'}:
                    value=node.get('Value','');binding=re.search(r'\.Variable\[([^]]+)\]',value)
                    if binding:
                        name=binding[1].split('.',1)[-1];number=next((i for i,line in enumerate(locations,1) if value in line),1)
                        ref(name,number,'hmi');edge(path.stem,name,'hmi-binding',number,value)
        if suffix=='.iom':
            for number,line in enumerate(lines,1):
                match=re.search(r'([A-Za-z_]\w*)\s+AT\s+(%[^;]+)',line)
                if match:ref(match[1],number,'io');edge(match[1],match[2],'io-binding',number,line.strip())
        if len(refs)>100000 or len(edges)>100000:notices.append('Dependency extraction reached its per-file bound; inspect this source for additional references.')
        return sections,symbols,list(set(refs[:100000])),list(set(edges[:100000])),tasks,notices

    def build(self,cancel=None,publish=None,mode='refresh'):
        cancel=cancel or threading.Event();started=time.monotonic()
        state={'phase':'waiting','stage':'Waiting for the project index worker','ready':False,'indexedFiles':0,'failedFilesCount':0,'processedFiles':0,'unchangedFiles':0,'changedFiles':0,'removedFiles':0}
        def emit():
            state['elapsedSeconds']=round(time.monotonic()-started,1)
            if publish:publish(dict(state))
        while not INDEX_LOCK.acquire(timeout=.2):
            emit()
            if cancel.is_set():state.update(phase='cancelled',stage='Cancelled before indexing');emit();return state
        try:
            state['stage']='Discovering source files and exclusions';emit()
            files=self.discover(cancel,state,emit);names={path.relative_to(self.root).as_posix() for path in files}
            with connection(self.path) as db:
                metadata(db,'root',str(self.root))
                metadata(db,'identity',local_project_details(self.root))
                existing={row['path']:dict(row) for row in db.execute('SELECT path,size,mtime,status FROM files')}
                for name in set(existing)-names:db.execute('DELETE FROM files WHERE path=?',(name,));state['removedFiles']+=1
                db.commit()
                for number,path in enumerate(files,1):
                    if cancel.is_set():raise InterruptedError('Indexing cancelled; existing knowledge is retained.')
                    relative=path.relative_to(self.root).as_posix();previous=existing.get(relative)
                    try:stat=path.stat()
                    except OSError:
                        db.execute('DELETE FROM files WHERE path=?',(relative,));db.commit();state['removedFiles']+=1;continue
                    state.update(phase='indexing',stage='Indexing '+relative,currentFile=relative,processedFiles=number-1,percentage=round(100*(number-1)/max(1,len(files)),1))
                    if mode!='rebuild' and previous and previous['mtime']==stat.st_mtime_ns and previous['size']==stat.st_size and previous['status']=='indexed':
                        state['unchangedFiles']+=1;state['indexedFiles']+=1
                    else:
                        try:
                            if stat.st_size>MAX_FILE:raise ValueError('File exceeds the 8 MB per-file indexing limit.')
                            raw=path.read_bytes()
                            if b'\0' in raw[:2000] and path.suffix.casefold() not in {'.src','.ld'}:raise ValueError('Binary source cannot be interpreted as readable PLC text.')
                            text=decode_project_text(path,raw) if path.suffix.casefold() in {'.src','.ld'} else _text(raw)
                            parsed=self.parse(path,text)
                            db.execute('DELETE FROM files WHERE path=?',(relative,))
                            db.execute('INSERT INTO files VALUES (?,?,?,?,?,?,?)',(relative,stat.st_size,stat.st_mtime_ns,hashlib.sha256(raw).hexdigest(),category(path),'indexed',''))
                            sections,symbols,refs,edges,tasks,notices=parsed
                            for section in sections:
                                cursor=db.execute('INSERT INTO sections(file,first,last,text,kind,label,complete,enabled,scope) VALUES (?,?,?,?,?,?,?,?,?)',section)
                                expanded=re.sub(r'(?<=[a-z])(?=[A-Z])',' ',section[3]).replace('_',' ')
                                db.execute('INSERT INTO section_search(rowid,text) VALUES (?,?)',(cursor.lastrowid,section[3]+' '+expanded+' '+relative.replace('/',' ').replace('_',' ')))
                            db.executemany('INSERT INTO symbols VALUES (?,?,?,?,?,?,?)',symbols)
                            db.executemany('INSERT INTO refs VALUES (?,?,?,?,?)',refs)
                            db.executemany('INSERT INTO edges VALUES (?,?,?,?,?,?,?)',edges)
                            db.executemany('INSERT INTO tasks VALUES (?,?,?,?,?,?)',tasks)
                            if notices:state['analysisNotices']=state.get('analysisNotices',0)+len(notices)
                            db.commit();state['indexedFiles']+=1;state['changedFiles']+=1
                        except (OSError,ValueError,ET.ParseError,IndexError,KeyError) as error:
                            db.rollback();db.execute('DELETE FROM files WHERE path=?',(relative,))
                            db.execute('INSERT INTO files VALUES (?,?,?,?,?,?,?)',(relative,stat.st_size,stat.st_mtime_ns,'',category(path),'failed',str(error)[:300]));db.commit();state['failedFilesCount']+=1
                    state['processedFiles']=number;state['percentage']=round(100*number/max(1,len(files)),1)
                    if number%10==0 or number==len(files):emit();metadata(db,'state',state);db.commit()
                state.update(phase='ready',stage='Project ready' if not state['failedFilesCount'] else 'Project ready with failed files to review',ready=True,percentage=100)
                emit();metadata(db,'state',state);metadata(db,'root',str(self.root));db.commit()
        except InterruptedError:
            state.update(phase='cancelled',stage='Indexing cancelled; analysis is incomplete',ready=False);emit()
            with connection(self.path) as db:metadata(db,'state',state);metadata(db,'root',str(self.root));db.commit()
        finally:INDEX_LOCK.release()
        return self.snapshot()

    def retrieve(self,question,characters=18000,passes=3):
        candidates={};pass_log=[];query_symbols=[]
        tokens=list(dict.fromkeys(re.findall(r'[A-Za-z_][A-Za-z0-9_]{1,70}',question.casefold())))
        terms=[word for word in tokens if word not in QUERY_STOP and word not in KEYWORDS][:16]
        include_disabled=bool(re.search(r'disabled|commented|inactive',question,re.I))
        with connection(self.path) as db:
            def add(row,score,reason,number):
                if not row or not include_disabled and not row['enabled']:return
                item=dict(row);item.update(score=score,matchReason=reason,retrievalPass=number)
                previous=candidates.get(row['id'])
                if previous is None or score>previous['score']:candidates[row['id']]=item
            named_files=re.findall(r'\b[\w-]+\.(?:st|ab|src|ld|var|fun|typ|c|h)\b',question,re.I)
            for name in named_files[:4]:
                for row in db.execute('SELECT * FROM sections WHERE lower(file)=? OR lower(file) LIKE ? LIMIT 40',(name.casefold(),'%/'+name.casefold())):
                    add(row,220+sum(term in row['text'].casefold() for term in terms),'Explicit source file '+name,1)
            for token in terms:
                declared=db.execute('SELECT DISTINCT name FROM symbols WHERE name=? UNION SELECT name FROM refs WHERE name=? LIMIT 8',(symbol(token),symbol(token))).fetchall()
                if declared:query_symbols.append(symbol(token))
                if declared or '_' in token:
                    for row in db.execute('SELECT file,line,kind FROM refs WHERE name=? ORDER BY CASE kind WHEN \'write\' THEN 0 WHEN \'call\' THEN 1 ELSE 2 END LIMIT 40',(symbol(token),)):
                        section=db.execute('SELECT * FROM sections WHERE file=? AND first<=? AND last>=? ORDER BY complete DESC,(last-first) ASC LIMIT 1',(row['file'],row['line'],row['line'])).fetchone()
                        add(section,100,'Exact symbol '+token,1)
                    for row in db.execute('SELECT file,line FROM symbols WHERE name=? LIMIT 12',(symbol(token),)):
                        add(db.execute('SELECT * FROM sections WHERE file=? AND first<=? AND last>=? ORDER BY (last-first) ASC LIMIT 1',(row['file'],row['line'],row['line'])).fetchone(),105,'Declaration '+token,1)
            if terms:
                expression=' OR '.join('"'+term.replace('"','""')+'"' for term in terms)
                for row in db.execute('SELECT s.*,bm25(section_search) rank FROM section_search JOIN sections s ON s.id=section_search.rowid WHERE section_search MATCH ? ORDER BY rank LIMIT 60',(expression,)):
                    add(row,40+min(15,-float(row['rank'])),'Full-text search',1)
            if not candidates:
                for row in db.execute("SELECT * FROM sections WHERE enabled=1 AND kind IN ('Logic','Ladder') ORDER BY complete DESC,length(text) DESC LIMIT 20"):add(row,10,'Project overview candidate',1)
            pass_log.append({'pass':1,'strategy':'Exact symbols and SQLite FTS5','candidates':len(candidates)})
            frontier=set(query_symbols)
            for row in sorted(candidates.values(),key=lambda value:-value['score'])[:8]:
                frontier.update(value['name'] for value in db.execute("SELECT DISTINCT name FROM refs WHERE file=? AND line BETWEEN ? AND ? AND kind IN ('call','write','condition','call-instance') LIMIT 12",(row['file'],row['first'],row['last'])))
            traced=set()
            for number in range(2,min(4,passes)+1):
                before=len(candidates);next_frontier=set()
                for name in sorted(frontier-traced)[:32]:
                    traced.add(name)
                    for edge in db.execute('SELECT * FROM edges WHERE a=? OR b=? LIMIT 25',(name,name)):
                        next_frontier.update([edge['a'],edge['b']])
                        line=edge['line'];section=db.execute('SELECT * FROM sections WHERE file=? AND first<=? AND last>=? ORDER BY complete DESC,(last-first) ASC LIMIT 1',(edge['file'],line,line)).fetchone()
                        add(section,65-number,'Dependency: '+edge['kind']+' '+name,number)
                    for decl in db.execute('SELECT * FROM symbols WHERE name=? LIMIT 8',(name,)):
                        add(db.execute('SELECT * FROM sections WHERE file=? AND first<=? AND last>=? ORDER BY (last-first) ASC LIMIT 1',(decl['file'],decl['line'],decl['line'])).fetchone(),70-number,'Related declaration '+name,number)
                pass_log.append({'pass':number,'strategy':'Calls, variable producers/consumers, types and conditions','candidatesAdded':len(candidates)-before,'symbolsTraced':len(traced)})
                frontier=next_frontier
                if not frontier:break
            identity=metadata(db,'identity') or {};active=identity.get('activeConfiguration')
            tasks=[dict(row) for row in db.execute('SELECT * FROM tasks LIMIT 200')]
            def ownership(row):
                if row['file'].startswith('Physical/'):
                    return 'active configuration' if active and row['file'].split('/')[1].casefold()==str(active).casefold() else 'other configuration / active configuration unresolved'
                for task in tasks:
                    source=task['source'].removesuffix('.prg').replace('.','/').casefold()
                    if source and '/'+source+'/' in '/'+row['file'].casefold():
                        selected=active and task['configuration'].casefold()==str(active).casefold()
                        if selected:return 'active task' if task['enabled'] else 'disabled task'
                return 'shared / task assignment unresolved'
            chosen=[];used=0;seen=[]
            for row in sorted(candidates.values(),key=lambda value:(-value['score'],value['file'],value['first'])):
                if used>=characters or len(chosen)>=14:break
                if not include_disabled and ownership(row)=='disabled task':continue
                if any(file==row['file'] and first<=row['first'] and last>=row['last'] for file,first,last in seen):continue
                remaining=characters-used
                if remaining<400:break
                text=row['text'];truncated=len(text)>remaining
                if truncated:text=text[:remaining].rsplit('\n',1)[0]
                evidence={'file':row['file'],'line':row['first'],'endLine':row['first']+text.count('\n'),'excerpt':text,
                    'sourceId':'S'+str(len(chosen)+1),'category':row['kind'],'enabled':bool(row['enabled']),
                    'ownership':ownership(row),'scope':row['scope'],
                    'completeSection':bool(row['complete']) and not truncated,'retrievalPass':row['retrievalPass'],'matchReason':row['matchReason']}
                chosen.append(evidence);used+=len(text);seen.append((row['file'],row['first'],row['last']))
            state=metadata(db,'state') or {}
            ambiguous=[row['name'] for row in db.execute('SELECT name FROM symbols GROUP BY name HAVING count(DISTINCT scope)>1 LIMIT 100') if row['name'] in traced or row['name'] in query_symbols]
        notices=[]
        if not state.get('ready'):notices.append('Indexing is incomplete. Findings cover only the indexed sources currently available.')
        if state.get('failedFilesCount'):notices.append(f"{state['failedFilesCount']} source files failed indexing; their behavior is unresolved.")
        if ambiguous:notices.append('Same-named symbols occur in multiple scopes; do not merge their behavior: '+', '.join(ambiguous[:12]))
        if any(not item['completeSection'] for item in chosen):notices.append('Some retrieved sections are bounded source windows. Full sequence or branch completeness is not established by those windows.')
        return {'evidence':chosen,'passes':pass_log,'notices':notices,'tasks':tasks,'identity':identity,'characters':used,'candidateCount':len(candidates),'projectId':self.key}


def start(root,owner,mode='refresh'):
    if mode not in {'refresh','rebuild','retry'}:raise ValueError('Choose refresh, rebuild or retry.')
    index=Index(root,owner)
    with JOBS_LOCK:
        previous=JOBS.get(index.key)
        if previous and previous['thread'].is_alive():return status(index,owner)
        if sum(job['thread'].is_alive() for job in JOBS.values())>=3:raise ValueError('Wait for the current project indexing jobs to finish, or cancel an indexing job.')
        cancel=threading.Event();job={'owner':str(owner),'index':index,'cancel':cancel,'state':index.snapshot()}
        def publish(state):
            with JOBS_LOCK:job['state']={**state,'projectId':index.key,'projectName':index.root.name}
        def worker():
            try:publish(index.build(cancel,publish,mode))
            except Exception as error:publish({**job['state'],'phase':'error','stage':str(error)[:300],'ready':False})
        thread=threading.Thread(target=worker,name='chopper-project-index',daemon=True);job['thread']=thread;JOBS[index.key]=job;thread.start()
    return status(index,owner)


def status(index,owner):
    if str(owner)!=index.owner:raise PermissionError('Project index belongs to another account.')
    with JOBS_LOCK:
        job=JOBS.get(index.key)
        if job and job['owner']==str(owner) and job['thread'].is_alive():return {**index.snapshot(),**job['state'],'running':True}
    return {**index.snapshot(),'running':False}


def opened(key,owner):
    if not re.fullmatch(r'[a-f0-9]{64}',str(key)):raise ValueError('Invalid project index.')
    path=WORK/'chopper_intelligence'/key/'project.sqlite3'
    if not path.is_file():raise ValueError('Index this uploaded project first.')
    with connection(path) as db:root=metadata(db,'root')
    if not root:
        with JOBS_LOCK:
            job=JOBS.get(key)
            if job and job['owner']==str(owner):return job['index']
        raise ValueError('Project discovery is still in progress.')
    if project_key(root,owner)!=key:raise PermissionError('Project index belongs to another account.')
    return Index(root,owner)


def cancel(key,owner):
    with JOBS_LOCK:
        job=JOBS.get(key)
        if not job or job['owner']!=str(owner):raise ValueError('Project indexing job was not found.')
        job['cancel'].set()
    return {'cancelRequested':True,'projectId':key}
