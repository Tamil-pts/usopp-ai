"""Authenticated MCP access to existing local engineering tools."""
import json
import re
import socket
from pathlib import Path
from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP,Context
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from backend.core.runtime import WORK,locate_root

hosts={'localhost','127.0.0.1','[::1]',socket.gethostname()}
try:hosts.update(row[4][0] for row in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET))
except OSError:pass
server=FastMCP('Chopper / uSOPp.ai',instructions='Use deterministic project tools for engineering evidence. Model suggestions do not change validation verdicts. Source writes require review in the application.',streamable_http_path='/',stateless_http=True,json_response=True,
    transport_security=TransportSecuritySettings(allowed_hosts=[h+':*' for h in hosts],allowed_origins=[f'http://{h}:*' for h in hosts]+[f'https://{h}:*' for h in hosts]))
http_app=server.streamable_http_app()

def session_root(session_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',session_id):raise ValueError('Invalid session ID')
    from backend.core.access import require_session
    require_session(session_id)
    manifest=WORK/session_id/'inputs.json'
    if not manifest.is_file():raise ValueError('Select/upload a project in uSOPp first, then use its session ID.')
    root=locate_root(Path(json.loads(manifest.read_text(encoding='utf-8'))['project']))
    return root

@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def project_context(session_id:str)->dict:
    """Read project identity, active configuration and completed validation summaries."""
    from python_engine.project_info import local_project_details
    root=session_root(session_id);data=local_project_details(root)
    for name in ('validation_results.json','generated_metadata.json','rule_results.json'):
        path=WORK/session_id/name
        if path.is_file():
            result=json.loads(path.read_text(encoding='utf-8'))
            data[name]={'testId':result.get('testId'),'summary':result.get('summary') or result.get('counts'),'results':[{k:r.get(k) for k in ('standardId','id','name','status','actual')} for r in result.get('results',[])][:200]}
    return data

@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def understand_project(session_id:str,question:str='Explain machine functions and operating sequence')->dict:
    """Index selected configuration and retrieve source-backed machine logic, tasks and cross references."""
    from python_engine.project_knowledge import build_index,retrieve,module_overview
    index=build_index(session_root(session_id),WORK/'chopper_knowledge')
    return {'identity':index['identity'],'counts':index['counts'],'tasks':index['tasks'],
            'modules':module_overview(index,question),'evidence':retrieve(index,question),
            'notices':index['notices'],'coverage':index['coverage']}


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def compare_explanation(session_id:str)->dict:
    """Categorise a completed MatchView run into variable, logic, ladder, HMI and hardware changes."""
    from backend.api.comparison import _comparison_result_for_export
    from python_engine.project_knowledge import comparison_knowledge
    result,work=_comparison_result_for_export(session_id)
    return comparison_knowledge(result,work)


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def read_source(session_id:str,path:str)->dict:
    """Read a project-relative B&R source file with an edit-version hash; no writes."""
    from backend.api.validation_source import read_source
    return read_source({'session_id':session_id,'path':path})

@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def find_variable(session_id:str,variable:str)->dict:
    """Find exact variable references in ST, LD, AB, I/O and declaration sources."""
    if not re.fullmatch(r'[A-Za-z_][\w.\[\]#]*',variable) or len(variable)>200:raise ValueError('Enter a variable name, not a source expression.')
    from python_engine.rule_engine_v4_30 import all_files,read_text
    root=session_root(session_id);matches=[]
    for path in all_files(root):
        if path.suffix.casefold() not in {'.st','.src','.ld','.ab','.var','.typ','.iom','.txt','.page','.dso'} or path.stat().st_size>5*1024*1024:continue
        for number,line in enumerate(read_text(path).splitlines(),1):
            if re.search(r'(?<!\w)'+re.escape(variable)+r'(?!\w)',line):
                matches.append({'file':path.relative_to(root).as_posix(),'line':number,'text':line[:1200]})
                if len(matches)>=200:return {'matches':matches,'truncated':True}
    return {'matches':matches,'truncated':False}

@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def ladder_networks(session_id:str,path:str)->dict:
    """Extract a ladder source into row/column networks, instances, pins and connections."""
    from python_engine.compare import _ladder_networks
    source=read_source(session_id,path)
    return {'file':path,'networks':[{k:v for k,v in n.items() if k!='_signature'} for n in _ladder_networks(source['content'])]}

@server.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=False))
def validate_project(session_id:str,department:str='All',generate_metadata:bool=False)->dict:
    """Run ByteMap validation or generate MetaWorks metadata on a selected project; save a new report/history run."""
    from backend.api.validation import _execute
    from backend.core.runtime import _local_session
    root=session_root(session_id);sid,_=_local_session()
    return _execute(sid,root,root.name,generate=generate_metadata,local=True,machine_department=department)

@server.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=False))
def prepare_rule(answers:dict)->dict:
    """Prepare an engineer-reviewable rule draft; does not save or enable it."""
    from backend.core.rule_configuration import guided_configuration
    return guided_configuration(answers)


@server.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=False))
def build_engineering_model(project_id:str)->dict:
    """Explicitly build versioned source blocks/relationships for an indexed project. No PLC, validation or chat state writes."""
    from backend.core.engineering_foundation import build_model
    return build_model(project_id)


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_project_structure(project_id:str)->dict:
    """Read engineering inventory, layers, configured task roots and validation. Never assume a routine named main is an entry point."""
    from backend.core.engineering_foundation import model
    return model(project_id).structure()


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_function_block(project_id:str,block_id:str,include_ir:bool=False)->dict:
    """Inspect one scoped routine/function/instance block. Optional IR is Python data, never translated executable PLC code."""
    from backend.core.engineering_foundation import model
    return model(project_id).block(block_id,include_ir)


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def find_machine_function(project_id:str,question:str,limit:int=20)->dict:
    """Discover source candidates by concept words. Candidates are not verified machine-function classifications."""
    from backend.core.engineering_foundation import model
    return model(project_id).find_function(question,limit)


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def trace_signal(project_id:str,signal:str,scope:str='',limit:int=100)->dict:
    """Trace typed writer/read/control/HMI/I-O links. Ambiguous scoped tags require selection; no live states are inferred."""
    from backend.core.engineering_foundation import model
    return model(project_id).trace_signal(signal,scope,limit)


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_execution_flow(project_id:str,task_id:str='',limit:int=200)->dict:
    """Read configured task entries, lifecycle routines and call reachability. Concurrent tasks remain separate contexts."""
    from backend.core.engineering_foundation import model
    return model(project_id).execution_flow(task_id,limit)


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def validate_graph(project_id:str,offset:int=0,limit:int=100)->dict:
    """Validate graph structure/provenance and page unresolved checks. Structural validity never proves complete PLC semantics."""
    from backend.core.engineering_foundation import model
    return model(project_id).validate(offset,limit)


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_engineering_blocks(project_id:str,kind:str='',file:str='',query:str='',offset:int=0,limit:int=100)->dict:
    """Page individually inspectable engineering blocks; avoids serializing the entire graph into an LLM prompt."""
    from backend.core.engineering_foundation import model
    return model(project_id).blocks(kind,file,query,offset,limit)


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_engineering_relationships(project_id:str,block_id:str='',kind:str='',offset:int=0,limit:int=100)->dict:
    """Page all typed relationships, including links beyond initial result limits."""
    from backend.core.engineering_foundation import model
    return model(project_id).relations(block_id,kind,offset,limit)


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_engineering_tokens(project_id:str,file:str,offset:int=0,limit:int=100)->dict:
    """Read source lexical tokens with exact line/column positions. These are not model tokens or learned embeddings."""
    from backend.core.engineering_foundation import model
    return model(project_id).tokens(file,offset,limit)


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def compare_engineering_models(project_id:str,other_project_id:str,limit:int=100)->dict:
    """Compare source block revisions from two projects owned by this account; does not prove behavioral equivalence."""
    from backend.core.engineering_foundation import model
    return model(project_id).compare(model(other_project_id),limit)


@server.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=False))
def investigate_engineering_project(project_id:str,question:str,use_model:bool=True,max_passes:int=2)->dict:
    """Run bounded Think-Act-Check graph RAG. Model selects only verified fact IDs; stores diagnostic memory, never approved training."""
    from backend.core.engineering_harness import investigate
    return investigate(project_id,question,use_model=use_model,max_passes=max_passes)


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_machine_context(project_id:str,question:str='',limit:int=60)->dict:
    """Decode active hardware, conditional HMI names/settings, typed calls with local B&R help and source state/dependency links. No PLC execution."""
    from backend.core.project_intelligence import opened
    from backend.core.run_history import current_user
    from backend.core.machine_context import view
    return view(opened(project_id,(current_user.get() or {})['id']),question[:6000],limit)
