"""Structured validation flows: ordered steps, decisions and parallel forks."""
from concurrent.futures import ThreadPoolExecutor

def validate_graph(flow, stages):
    known={s['id']:s for s in stages}
    seen=set(); features=set()
    def walk(sequence, available, depth=0):
        if not isinstance(sequence,list) or depth>12: raise ValueError('Invalid flow or too many nested branches.')
        ready=set(available)
        for index,node in enumerate(sequence):
            if not isinstance(node,dict): raise ValueError('Invalid flow node.')
            nid=node.get('id'); kind=node.get('kind')
            if not isinstance(nid,str) or not nid or nid in seen: raise ValueError('Flow nodes require unique IDs.')
            seen.add(nid)
            if len(seen)>150: raise ValueError('Limit the flow to 150 nodes.')
            if kind=='feature':
                if nid not in known: raise ValueError('Flow references an unknown feature stage.')
                features.add(nid);ready.add(nid)
            elif kind=='end':
                if index != len(sequence)-1: raise ValueError('End / Results must be the last step in its path.')
            elif kind=='decision':
                check=node.get('check')
                if check=='department_is':
                    if not isinstance(node.get('value'),str) or not node['value'].strip(): raise ValueError('Choose a department for the decision.')
                elif check in ('all_pass','any_fail','any_warning','any_not_found'):
                    if node.get('sourceId') not in ready: raise ValueError('A decision must use a feature that runs before it on every incoming path.')
                else: raise ValueError('Choose a supported Yes/No condition.')
                yes=walk(node.get('yes'),ready,depth+1);no=walk(node.get('no'),ready,depth+1)
                ready=yes & no
            elif kind=='parallel':
                paths=node.get('paths')
                if not isinstance(paths,list) or not 2<=len(paths)<=8: raise ValueError('A parallel fork needs 2 to 8 paths.')
                outputs=[walk(path,ready,depth+1) for path in paths]
                ready=set.union(ready,*outputs)
            else: raise ValueError('Unknown flow node type.')
        return ready
    walk(flow,set())
    if not features: raise ValueError('Add at least one feature to the flow.')
    return features

def evaluate_graph(root, config, output_dir, evaluate):
    flow=config.get('pipelineFlow'); stages=config.get('pipelineStages',[])
    used=validate_graph(flow,stages)
    stage_map={s['id']:s for s in stages}; lookup={r['id']:r for r in config.get('rules',[])}
    for sid in used:
        ids=stage_map[sid].get('ruleIds')
        if not isinstance(ids,list) or not ids or any(rid not in lookup for rid in ids): raise ValueError('Every feature needs ready rules before running.')
    ordinal={sid:i+1 for i,sid in enumerate(stage_map)}
    output_dir.mkdir(parents=True,exist_ok=True)
    def skipped(sequence):
        records=[]
        for n in sequence:
            records.append({'id':n['id'],'label':stage_map.get(n['id'],{}).get('label',n['kind'].title()),'status':'Skipped','reason':'Condition selected the other path.'})
            if n['kind']=='decision': records+=skipped(n['yes'])+skipped(n['no'])
            if n['kind']=='parallel':
                for path in n['paths']: records+=skipped(path)
        return records
    def walk(sequence, inherited):
        evidence=dict(inherited);results=[];reports=[];runs=[]
        for node in sequence:
            nid=node['id'];kind=node['kind']
            if kind=='feature':
                stage=stage_map[nid];folder=output_dir/f"flow_stage_{ordinal[nid]}"
                data=evaluate(root,[lookup[r] for r in stage['ruleIds']],folder,'sequential')
                rows=data['results']; evidence[nid]=rows
                for row in rows: row.update({'pipelineStageId':nid,'pipelineStageName':stage.get('label','')})
                results.extend(rows)
                for name in data.get('moduleReports',[]):
                    source=folder/name;destination=output_dir/f"flow_{ordinal[nid]}_{source.name}"
                    source.replace(destination);reports.append(destination.name)
                status='Pass' if rows and all(r['status']=='PASS' for r in rows) else 'Fail' if any(r['status']=='FAIL' for r in rows) else 'Warning / not found'
                runs.append({'id':nid,'label':stage.get('label','Feature'),'status':status})
            elif kind=='decision':
                check=node['check'];rows=evidence.get(node.get('sourceId'),[])
                if check=='department_is': answer=str(config.get('machineDepartment','All')).casefold()==node['value'].casefold()
                elif check=='all_pass': answer=bool(rows) and all(r['status']=='PASS' for r in rows)
                else: answer=any(r['status'].upper().replace('_',' ') in {'any_fail':['FAIL'],'any_warning':['WARN','WARNING'],'any_not_found':['NOT FOUND']}[check] for r in rows)
                runs.append({'id':nid,'label':('Department is '+node['value']) if check=='department_is' else stage_map[node['sourceId']].get('label','Feature')+' / '+check.replace('_',' '),'status':'Yes' if answer else 'No'})
                chosen,other=(node['yes'],node['no']) if answer else (node['no'],node['yes'])
                child=walk(chosen,evidence);evidence.update(child[0]);results+=child[1];reports+=child[2];runs+=child[3]+skipped(other)
            elif kind=='end':
                runs.append({'id':nid,'label':'End / Results','status':'Complete','reason':'Path closed. Results are available after all active paths finish.'})
                break
            else:
                with ThreadPoolExecutor(max_workers=len(node['paths']),thread_name_prefix='flow-path') as pool:
                    children=list(pool.map(lambda path:walk(path,evidence),node['paths']))
                for child in children: evidence.update(child[0]);results+=child[1];reports+=child[2];runs+=child[3]
                runs.append({'id':nid,'label':'Parallel paths','status':'Complete'})
        return evidence,results,reports,runs
    _,results,reports,runs=walk(flow,{})
    return {'version':'4.58','pipelineMode':'graph','ruleCount':len(results),'results':results,'moduleReports':reports,'stageRuns':runs,
            'counts':{'pass':sum(r['status']=='PASS' for r in results),'fail':sum(r['status']=='FAIL' for r in results),'not_found':sum(r['status']=='NOT FOUND' for r in results)}}
