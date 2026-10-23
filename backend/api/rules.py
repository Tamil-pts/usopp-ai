from __future__ import annotations
from datetime import datetime, timezone
from starlette.concurrency import run_in_threadpool
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from backend.core.runtime import (
    BASE,
    DEFAULT_RULES,
    List,
    Path,
    MAX_PROJECT_FILES,
    Optional,
    RULE_ENGINE,
    WORK,
    find_json,
    json,
    locate_root,
    log,
    re,
    run_engine,
    stage_project,
)

from backend.core.runtime import _local_session, _local_path, VALIDATION_LOCK
from backend.core.rule_checklist import normalize_checklist_bytes
from backend.core.run_history import record_run
from backend.core.rule_learning import (
    LEARNING_DIR,
    append_observation,
    approved_training_examples,
    learning_summary,
    read_observations,
)

router = APIRouter(tags=['Engineering Rules'])

@router.post('/api/rules/next-id')
def next_rule_id():
    from backend.core.identifiers import rule_id
    return {'id':rule_id()}

from backend.core.rule_features import catalog, write_json, safe_id, LOCK, NAMES

@router.get('/api/rules/library')
def feature_rule_library():
    return catalog()


@router.get('/api/rules/references/{filename}/{check_id}')
def reference_definition(filename:str,check_id:str,reference_hash:str=''):
    from python_engine.rule_references import load_reference
    try:return {'definition':load_reference({'referenceFile':filename,'checkId':check_id,'referenceHash':reference_hash})}
    except (ValueError,OSError) as error:raise HTTPException(400,str(error))

@router.delete('/api/rules/library/{rule_id}')
def delete_library_rule(rule_id:str):
    """Remove one rule from defaults/modules and unlink it from features/pipelines."""
    rid=str(rule_id or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,160}',rid):
        raise HTTPException(400,'Choose a valid rule ID.')
    removed_from=[]
    modules_dir=BASE/'rules'/'modules'
    features_dir=BASE/'rules'/'features'
    pipelines_dir=BASE/'rules'/'pipelines'
    with LOCK:
        if DEFAULT_RULES.is_file():
            try:
                defaults=json.loads(DEFAULT_RULES.read_text(encoding='utf-8'))
                existing=defaults.get('rules') if isinstance(defaults,dict) else None
                if isinstance(existing,list):
                    kept=[rule for rule in existing if not (isinstance(rule,dict) and str(rule.get('id'))==rid)]
                    if len(kept)!=len(existing):
                        defaults['rules']=kept
                        write_json(DEFAULT_RULES,defaults)
                        removed_from.append('default rules')
            except (OSError,ValueError) as error:
                raise HTTPException(500,f'Default rules could not be updated: {error}')

        if modules_dir.is_dir():
            for path in modules_dir.glob('*.json'):
                try:
                    module=json.loads(path.read_text(encoding='utf-8'))
                except (OSError,ValueError):
                    continue
                entries=module.get('rules') if isinstance(module,dict) else None
                changed=False
                if isinstance(entries,list):
                    kept=[rule for rule in entries if not (isinstance(rule,dict) and str(rule.get('id'))==rid)]
                    changed=len(kept)!=len(entries)
                    if changed:
                        module['rules']=kept
                        write_json(path,module)
                elif isinstance(module,dict) and str(module.get('id'))==rid:
                    path.unlink()
                    changed=True
                if changed:
                    removed_from.append(path.name)

        if not removed_from:
            raise HTTPException(404,'Rule was not found in the active rule library.')

        if features_dir.is_dir():
            for path in features_dir.glob('*.json'):
                if path.name=='pipeline.json':
                    continue
                try:
                    feature=json.loads(path.read_text(encoding='utf-8'))
                except (OSError,ValueError):
                    continue
                ids=feature.get('ruleIds') if isinstance(feature,dict) else None
                if isinstance(ids,list) and rid in ids:
                    feature['ruleIds']=[value for value in ids if value!=rid]
                    write_json(path,feature)

        def remove_rule_links(value):
            changed=False
            if isinstance(value,dict):
                for key,item in list(value.items()):
                    if key=='ruleIds' and isinstance(item,list):
                        cleaned=[entry for entry in item if entry!=rid]
                        if len(cleaned)!=len(item):
                            value[key]=cleaned
                            changed=True
                    else:
                        changed=remove_rule_links(item) or changed
            elif isinstance(value,list):
                for item in value:
                    changed=remove_rule_links(item) or changed
            return changed

        for directory in (features_dir,pipelines_dir):
            if not directory.is_dir():
                continue
            for path in directory.glob('*.json'):
                if directory==features_dir and path.name!='pipeline.json':
                    continue
                try:
                    pipeline=json.loads(path.read_text(encoding='utf-8'))
                except (OSError,ValueError):
                    continue
                if remove_rule_links(pipeline):
                    write_json(path,pipeline)
                    removed_from.append(f'pipeline {path.stem}')
    return {'deleted':rid,'removedFrom':removed_from}

@router.get('/api/rules/features')
def rule_features():
    data = catalog()
    for feature in data['features']:
        feature['canDelete']=not feature.get('ruleIds') and feature['id'] not in NAMES
    path = BASE/'rules'/'features'/'pipeline.json'
    data['pipeline'] = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    data['pipelines'] = [json.loads(p.read_text(encoding='utf-8')) for p in sorted((BASE/'rules'/'pipelines').glob('*.json'))]
    return data

@router.post('/api/rules/features/{feature_id}')
def save_rule_feature(feature_id:str,payload:dict):
    fid = safe_id(feature_id)
    if not fid or fid == 'pipeline': raise HTTPException(400,'Choose a feature name.')
    ids = payload.get('ruleIds',[])
    if not isinstance(ids,list) or any(not isinstance(x,str) for x in ids): raise HTTPException(400,'ruleIds must be a list of rule IDs.')
    with LOCK:
        data = catalog()
        if set(ids)-{r['id'] for r in data['rules']}: raise HTTPException(400,'Unknown rule ID.')
        path = BASE/'rules'/'features'/f'{fid}.json'
        feature = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'id':fid}
        feature.update({'name':str(payload.get('name') or feature.get('name') or fid),'description':str(payload.get('description') or feature.get('description') or ''),'ruleIds':list(dict.fromkeys(ids))})
        write_json(path,feature)
        return feature

@router.delete('/api/rules/features/{feature_id}')
def delete_rule_feature(feature_id:str):
    fid=safe_id(feature_id)
    folder=BASE/'rules'/'features'; path=folder/f'{fid}.json'
    if not path.is_file(): raise HTTPException(404,'Feature was not found.')
    with LOCK:
        data=catalog(); feature=next((item for item in data['features'] if item['id']==fid),None)
        if feature is None: raise HTTPException(404,'Feature was not found.')
        if fid in NAMES: raise HTTPException(409,'Built-in feature categories stay in the library. Remove a feature stage from the pipeline instead.')
        if feature.get('ruleIds'): raise HTTPException(409,'This feature contains rules. Remove its stages from pipelines first; the rule definitions stay in the rule library.')
        path.unlink()
        stages_to_remove={stage['id'] for directory in (BASE/'rules'/'pipelines',folder) for file in directory.glob('*.json') if file.name!='pipeline.json' for stage in (json.loads(file.read_text(encoding='utf-8')).get('stages') or []) if stage.get('featureId')==fid}
        def prune(nodes):
            kept=[]
            for node in nodes or []:
                if node.get('kind')=='feature' and node.get('id') in stages_to_remove: continue
                item=dict(node)
                for key in ('yes','no'):
                    if key in item: item[key]=prune(item[key])
                if 'paths' in item: item['paths']=[prune(path) for path in item['paths']]
                kept.append(item)
            return kept
        for directory in (BASE/'rules'/'pipelines',folder):
            for file in directory.glob('*.json'):
                if file.name=='pipeline.json' or file.stem in {'pipeline'}: continue
                try: config=json.loads(file.read_text(encoding='utf-8'))
                except (OSError,ValueError): continue
                if any(stage.get('featureId')==fid for stage in config.get('stages') or []):
                    config['stages']=[stage for stage in config['stages'] if stage.get('featureId')!=fid]
                    if isinstance(config.get('flow'),list): config['flow']=prune(config['flow'])
                    write_json(file,config)
        active=folder/'pipeline.json'
        if active.is_file():
            try:
                config=json.loads(active.read_text(encoding='utf-8'))
                if any(stage.get('featureId')==fid for stage in config.get('stages') or []):
                    config['stages']=[stage for stage in config['stages'] if stage.get('featureId')!=fid]
                    if isinstance(config.get('flow'),list): config['flow']=prune(config['flow'])
                    write_json(active,config)
            except (OSError,ValueError): pass
        return {'deleted':fid}

@router.post('/api/rules/feature-pipeline')
def save_rule_pipeline(payload:dict):
    mode = payload.get('executionMode','sequential')
    if mode not in ('sequential','parallel','branches','graph'): raise HTTPException(400,'Choose series, parallel or branches.')
    name = str(payload.get('name') or 'My pipeline').strip()
    pid = safe_id(payload.get('id') or name)
    stages = payload.get('stages',[])
    if not pid or not isinstance(stages,list) or not stages: raise HTTPException(400,'Name the pipeline and add features.')
    data = catalog(); known = {f['id']:set(f['ruleIds']) for f in data['features']}
    stage_ids = set()
    for stage in stages:
        if not isinstance(stage,dict) or not isinstance(stage.get('id'),str) or stage['id'] in stage_ids or stage.get('featureId') not in known:
            raise HTTPException(400,'Each stage needs a unique ID and a known feature.')
        if type(stage.get('branch',1)) is not int or not 1<=stage.get('branch',1)<=100: raise HTTPException(400,'Branch must be between 1 and 100.')
        stage_ids.add(stage['id'])
        ids=stage.get('ruleIds',[])
        if not isinstance(ids,list) or any(not isinstance(x,str) for x in ids) or set(ids)-known[stage['featureId']]: raise HTTPException(400,'Stage rules must belong to its feature.')
    config={'id':pid,'name':name,'machineDepartment':payload.get('machineDepartment','All'),'executionMode':mode,'stages':stages}
    if mode=='graph':
        from python_engine.pipeline_graph import validate_graph
        try: validate_graph(payload.get('flow'),stages)
        except ValueError as error: raise HTTPException(400,str(error))
        config['flow']=payload['flow']
    with LOCK:
        write_json(BASE/'rules'/'pipelines'/f'{pid}.json',config)
        write_json(BASE/'rules'/'features'/'pipeline.json',config)
    return config

@router.delete('/api/rules/pipelines/{pipeline_id}')
def delete_rule_pipeline(pipeline_id:str):
    pid=safe_id(pipeline_id)
    if not pid: raise HTTPException(400,'Choose a saved pipeline.')
    path=BASE/'rules'/'pipelines'/f'{pid}.json'
    if not path.is_file(): raise HTTPException(404,'Saved pipeline was not found.')
    with LOCK:
        path.unlink()
        active=BASE/'rules'/'features'/'pipeline.json'
        if active.is_file():
            try:
                current=json.loads(active.read_text(encoding='utf-8'))
                if current.get('id')==pid: active.unlink()
            except (OSError,ValueError):
                pass
    return {'deleted':pid}

def _run_rule_engine(args, identity, local=False):
    from backend.core.jobs import project_job
    from backend.core.runtime import VERSION
    project=locate_root(Path(args[args.index('--project')+1]))
    work=WORK/identity['sessionId']
    with project_job(project):
        run_engine(args,BASE)
        data=find_json(work,'rule_results.json')
        data.update({**identity,'projectPath':str(project),'version':VERSION,'localMode':local})
        reports=data.get('moduleReports') or []
        data['reportStatus']='Packet Validation Report Generated Successfully' if reports else None
        record_run('rules',data,project)
        return data

@router.post('/api/local/rules/validate')
def local_rules_validate(payload:dict):
    sid,work=_local_session()
    try:
        root=_local_path(payload.get('project_path',''),True,True); project_name=str(payload.get('project_name') or root.name); rules=payload.get('rules') or {}
        from backend.core.run_history import begin_run
        identity={'sessionId':sid,'projectName':project_name,'machineDepartment':rules.get('machineDepartment','All')}
        begin_run('rules',identity,locate_root(root))
        write_json(work/'inputs.json',{'project':str(locate_root(root))})
        rules_path=work/'rules.json'; out=work/'rule_results.json'; rules_path.write_text(json.dumps(rules,ensure_ascii=False,indent=2),encoding='utf-8')
        log.info('LOCAL_RULE_VALIDATE_START session=%s project=%r path=%s',sid,project_name,root)
        data=_run_rule_engine([str(RULE_ENGINE),'--project',str(locate_root(root)),'--rules',str(rules_path),'--output-json',str(out),'--output-dir',str(work)],identity,True)
        return JSONResponse(data)
    except HTTPException: raise
    except Exception as e:
        if 'identity' in locals(): record_run('rules',{**identity,'runStatus':'failed','error':str(e)},locate_root(root))
        log.exception('LOCAL_RULE_VALIDATE_ERROR session=%s',sid); raise HTTPException(500,str(e))
@router.get('/api/rules/modules')
def rule_modules():
    modules_dir=BASE/'rules'/'modules'
    modules=[]
    if modules_dir.exists():
        for p in sorted(modules_dir.glob('*.json')):
            try:
                cfg=json.loads(p.read_text(encoding='utf-8'))
                modules.append({
                    'id':cfg.get('id'),
                    'name':cfg.get('name'),
                    'version':cfg.get('version'),
                    'kind':cfg.get('kind'),
                    'enabled':cfg.get('enabled',False),
                    'ruleCount':len(cfg.get('rules') or []) if isinstance(cfg.get('rules'),list) else 1,
                    'machineScope':cfg.get('machineScope') or [],
                    'importSummary':cfg.get('importSummary') or None,
                    'file':p.name
                })
            except Exception:
                log.exception('RULE_MODULE_READ_ERROR file=%s',p)
    return {'version':'4.52','modules':modules}
@router.get('/api/rules/modules/{module_id}')
def rule_module(module_id:str):
    safe=re.sub(r'[^A-Za-z0-9_.-]','_',module_id)
    modules_dir=BASE/'rules'/'modules'
    matches=sorted(modules_dir.glob(f'{safe}_v*.json'),key=lambda p:p.stat().st_mtime_ns,reverse=True) if modules_dir.exists() else []
    if not matches:
        raise HTTPException(404,'Rule module not found.')
    try:
        return json.loads(matches[0].read_text(encoding='utf-8'))
    except Exception:
        log.exception('RULE_MODULE_READ_ERROR module=%s',module_id)
        raise HTTPException(500,'Rule module could not be loaded.')
@router.post('/api/rules/modules')
def save_rule_module(payload:dict):
    """Save a reviewed AI-generated rule as a reusable rule module."""
    cfg = payload.get('config') if isinstance(payload, dict) and 'config' in payload else payload
    if not isinstance(cfg, dict):
        raise HTTPException(400, 'Rule configuration must be an object.')
    rules = cfg.get('rules')
    if not isinstance(rules, list) or not rules:
        raise HTTPException(400, 'Rule configuration must contain at least one rule.')
    from python_engine.rule_evidence import expected_logic, cross_function_configuration_error, LOGIC_KINDS
    if payload.get('createOnly'):
        known={str(rule.get('id')) for rule in catalog().get('rules',[])}
        if any(rule.get('id') in known for rule in rules):
            raise HTTPException(409,'A rule with this ID already exists. Reopen it to edit, or create a new rule.')
    for rule in rules:
        if isinstance(rule,dict) and (rule.get('kind')=='module_serial_mapping' or rule.get('id')=='BR_MODULE_SERIAL_420'):
            from python_engine.module_serial_mapping import normalize_configuration, configuration_errors
            problems=configuration_errors(rule)
            if problems: raise HTTPException(400,'; '.join(problems))
            normalized=normalize_configuration(rule)
            rule.clear();rule.update(normalized)
        if isinstance(rule,dict) and rule.get('kind')=='structured_requirements':
            from python_engine.structured_requirements import configuration
            try:
                normalized=configuration({**rule,'ruleId':rule.get('id')})['rules'][0]
            except (ValueError,TypeError) as error: raise HTTPException(400,str(error))
            rule['checks']=normalized['checks']
            rule['needsRuleConfiguration']=normalized['needsRuleConfiguration']
        if isinstance(rule,dict) and rule.get('kind')=='structured_checks':
            from python_engine.structured_rule_checks import configuration_errors
            try: problems=configuration_errors(rule.get('checks') or [])
            except (ValueError,TypeError) as error: raise HTTPException(400,str(error))
            if rule.get('enabled') and problems: raise HTTPException(400,'; '.join(problems))
        if isinstance(rule,dict) and rule.get('enabled') and rule.get('needsRuleConfiguration'):
            raise HTTPException(400,'Complete the skipped rule details before enabling this rule.')
        if isinstance(rule,dict) and rule.get('enabled') and (rule.get('needsLogicConfiguration') or (rule.get('kind') in LOGIC_KINDS and not expected_logic(rule))):
            raise HTTPException(400,'Configure expected source logic before enabling this rule.')
        if isinstance(rule,dict) and rule.get('enabled'):
            problem=cross_function_configuration_error(rule)
            if problem: raise HTTPException(400,problem)
    saved=[]
    modules_dir=BASE/'rules'/'modules'; modules_dir.mkdir(parents=True, exist_ok=True)
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rid=str(rule.get('id') or '').strip()
        if not rid:
            raise HTTPException(400, 'Each rule must have an id.')
        version=str(rule.get('version') or cfg.get('version') or '1.0').strip()
        safe_id=re.sub(r'[^A-Za-z0-9_.-]','_',rid)
        safe_ver=re.sub(r'[^A-Za-z0-9_.-]','_',version)
        path=modules_dir/f'{safe_id}_v{safe_ver}.json'
        module=dict(rule)
        module.setdefault('version', version)
        module.setdefault('enabled', False)
        path.write_text(json.dumps(module, ensure_ascii=False, indent=2), encoding='utf-8')
        saved.append({'id':rid,'name':module.get('name'), 'version':version, 'file':path.name})
    if not saved:
        raise HTTPException(400, 'No valid rules to save.')
    # Persist configured feature links as part of saving, before the client refreshes.
    catalog()
    log.info('RULE_MODULE_SAVE count=%d modules=%s', len(saved), saved)
    return {'saved':saved,'count':len(saved),'version':'4.52'}


@router.post('/api/rules/checklists/normalize')
async def normalize_rule_checklist(file:UploadFile=File(...), machine:str=Form('Finisher')):
    filename=str(file.filename or 'engineering_checklist.csv')
    if not filename.casefold().endswith('.csv'):
        raise HTTPException(400,'Select a CSV engineering checklist.')
    try:
        module=normalize_checklist_bytes(await file.read(),filename,machine=str(machine or 'Finisher'))
    except ValueError as error:
        raise HTTPException(400,str(error))
    log.info('RULE_CHECKLIST_NORMALIZED file=%r summary=%s',filename,module.get('importSummary'))
    return {'version':'4.52','module':module,'summary':module.get('importSummary')}


@router.post('/api/rules/feedback')
def save_rule_feedback(payload:dict):
    """Record reviewed engineer feedback without changing a deterministic verdict."""
    allowed={'Correct','Incorrect','Partially correct','Ignore','Create rule from this'}
    label=str(payload.get('label') or '').strip()
    rule_id=str(payload.get('ruleId') or '').strip()
    if label not in allowed:
        raise HTTPException(400,'Select a supported feedback decision.')
    if not rule_id:
        raise HTTPException(400,'Rule ID is required.')
    record={
        'schemaVersion':'1.0',
        'createdAt':datetime.now(timezone.utc).isoformat(),
        'ruleId':rule_id,
        'ruleVersion':str(payload.get('ruleVersion') or ''),
        'projectName':str(payload.get('projectName') or ''),
        'resultStatus':str(payload.get('resultStatus') or ''),
        'label':label,
        'machineDepartment':str(payload.get('machineDepartment') or ''),
        'category':str(payload.get('category') or ''),
        'scope':str(payload.get('scope') or ''),
        'comment':str(payload.get('comment') or '').strip()[:4000],
        'evidence':payload.get('evidence') if isinstance(payload.get('evidence'),list) else [],
    }
    feedback_dir=BASE/'rules'/'feedback'; feedback_dir.mkdir(parents=True,exist_ok=True)
    feedback_file=feedback_dir/'rule_feedback.jsonl'
    with feedback_file.open('a',encoding='utf-8') as stream:
        stream.write(json.dumps(record,ensure_ascii=False)+'\n')
    learning=append_observation({**payload,**record},'engineer_feedback')
    draft_config=None
    if label=='Create rule from this':
        source=payload.get('ruleDefinition') if isinstance(payload.get('ruleDefinition'),dict) else {}
        learned_id='LEARNED-'+re.sub(r'[^A-Za-z0-9]+','-',rule_id).strip('-')+'-'+learning['id'][:6].upper()
        draft={**source,
            'id':learned_id,
            'name':str(source.get('name') or f'Review finding from {rule_id}'),
            'version':'1.0','enabled':False,
            'reviewStatus':'Needs engineer review',
            'reviewReason':'Created from engineer feedback. Confirm all rule fields before enabling.',
            'sourceFinding':{'ruleId':rule_id,'projectName':record['projectName'],'learningId':learning['id']},
        }
        draft_config={'version':'4.52','rules':[draft]}
    log.info('RULE_FEEDBACK_SAVED rule=%s label=%s project=%r',rule_id,label,record['projectName'])
    return {'saved':True,'feedback':record,'learning':learning,'draftConfig':draft_config}


@router.get('/api/rules/feedback')
def rule_feedback(rule_id:str='', project_name:str=''):
    feedback_file=BASE/'rules'/'feedback'/'rule_feedback.jsonl'
    if not feedback_file.exists():
        return {'feedback':[]}
    records=[]
    for line in feedback_file.read_text(encoding='utf-8',errors='ignore').splitlines():
        try: record=json.loads(line)
        except json.JSONDecodeError: continue
        if rule_id and record.get('ruleId')!=rule_id: continue
        if project_name and record.get('projectName')!=project_name: continue
        records.append(record)
    return {'feedback':records[-500:]}


@router.get('/api/rules/learning')
def rule_learning(rule_id:str='', project_name:str='', limit:int=500):
    records=read_observations(rule_id,project_name,limit)
    return {'version':'4.52','count':len(records),'summary':learning_summary(),'observations':records}


@router.get('/api/rules/learning/model')
def rule_learning_model():
    return {'version':'4.52',**learning_summary()}


@router.get('/api/rules/learning/export')
def export_rule_learning():
    examples=approved_training_examples()
    if not examples:
        raise HTTPException(404,'No engineer-approved learning examples are ready for export.')
    LEARNING_DIR.mkdir(parents=True,exist_ok=True)
    path=LEARNING_DIR/'approved_training_dataset.jsonl'
    with path.open('w',encoding='utf-8') as stream:
        for example in examples:
            stream.write(json.dumps(example,ensure_ascii=False)+'\n')
    return FileResponse(path,media_type='application/x-ndjson',filename='chopper_approved_training_dataset.jsonl')
@router.get('/api/rules/default')
def default_rules():
    log.info('RULES_DEFAULT_LOAD file=%s', DEFAULT_RULES)
    try:
        data=json.loads(DEFAULT_RULES.read_text(encoding='utf-8'))
        log.info('RULES_DEFAULT_SUCCESS count=%d', len(data.get('rules',[])))
        return data
    except Exception:
        log.exception('RULES_DEFAULT_ERROR file=%s', DEFAULT_RULES)
        raise HTTPException(500,'Default rule configuration could not be loaded. Check the backend log.')
@router.post('/api/rules/validate')
async def validate_rules(project_files:Optional[List[UploadFile]]=File(None), rules_json:str=Form(...), project_name:str=Form('')):
    sid,root=await stage_project(project_files,project_name); work=WORK/sid; rules_path=work/'rules.json'; out=work/'rule_results.json'
    log.info('RULE_VALIDATE_START session=%s project=%s rules_bytes=%d', sid, project_name, len(rules_json or ''))
    try:
        write_json(work/'inputs.json',{'project':str(root)})
        cfg=json.loads(rules_json); rules_path.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
        from backend.core.run_history import begin_run
        identity={'sessionId':sid,'projectName':project_name or root.name,'machineDepartment':cfg.get('machineDepartment','All')}
        begin_run('rules',identity,root)
        data=await run_in_threadpool(_run_rule_engine,[str(RULE_ENGINE),'--project',str(root),'--rules',str(rules_path),'--output-json',str(out),'--output-dir',str(work)],identity)
        return JSONResponse(data)
    except HTTPException: raise
    except Exception as e:
        if 'identity' in locals(): record_run('rules',{**identity,'runStatus':'failed','error':str(e)},root)
        log.exception('RULE_VALIDATE_ERROR session=%s project=%s', sid, project_name)
        raise HTTPException(500,str(e))
