"""Bounded ngspice runs from validated native circuit objects, never user SPICE commands."""
from collections import defaultdict
from pathlib import Path
import hashlib
import math
import os
import shutil
import subprocess
import tempfile
import threading
import time

import numpy as np
from .electrical_library import BY_KIND,pin
from .electrical_native import validate

SLOTS=threading.BoundedSemaphore(2)


def executable():
    from backend.core.runtime import RESOURCE_ROOT
    configured=os.getenv('USOPP_NGSPICE')
    candidates=[Path(configured)] if configured else []
    candidates.extend([RESOURCE_ROOT/'local_simulators/ngspice/Spice64/bin/ngspice_con.exe'])
    return next((str(p.resolve()) for p in candidates if p.is_file()),None) or shutil.which('ngspice_con') or shutil.which('ngspice')


def topology(elements):
    vertices=[];cells=defaultdict(list)
    def vertex(p):
        cell=(math.floor(p[0]*4),math.floor(p[1]*4))
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for i in cells[(cell[0]+dx,cell[1]+dy)]:
                    if math.dist(vertices[i],p)<=.25:return i
        i=len(vertices);vertices.append(p);cells[cell].append(i);return i
    pins={};wire_ids={}
    for e in elements:
        if e['kind'] in BY_KIND:
            for p in BY_KIND[e['kind']]['ports']:pins[e['id']+':'+p['id']]=vertex(pin(e,p['id']))
        elif e['kind']=='wire':wire_ids[e['id']]=[vertex(p) for p in e['points']]
    parent=list(range(len(vertices)))
    def root(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    edges=[]
    for e in elements:
        if e['kind']!='wire':continue
        for first,last in zip(e['points'],e['points'][1:]):
            dx,dy=last[0]-first[0],last[1]-first[1];length=dx*dx+dy*dy
            if length<1e-10:continue
            # Endpoints/pins can form T junctions; two interior crossings do not.
            cuts=[]
            for i,p in enumerate(vertices):
                t=((p[0]-first[0])*dx+(p[1]-first[1])*dy)/length
                if -.00001<=t<=1.00001 and math.hypot(p[0]-first[0]-t*dx,p[1]-first[1]-t*dy)<=.25:cuts.append((t,i))
            cuts.sort()
            for (_,a),(_,b) in zip(cuts,cuts[1:]):
                if a==b:continue
                parent[root(a)]=root(b);edges.append((a,b,e['id']))
    grounds=[pins[e['id']+':g'] for e in elements if e['kind']=='ground']
    grounded={root(i) for i in grounds};groups={};nodes={}
    for i in range(len(vertices)):
        r=root(i)
        if r not in groups:groups[r]='0' if r in grounded else 'n'+str(len(groups)+1)
        nodes[i]=groups[r]
    return {'vertices':vertices,'pins':pins,'wireVertices':wire_ids,'edges':edges,'nodes':nodes,'hasGround':bool(grounds)}


def netlist(document,options,previous=None):
    elements=validate(document);issues=[]
    devices=[e for e in elements if e['kind'] in BY_KIND and e['kind'] not in {'ground','terminal'}]
    wires=[e for e in elements if e['kind']=='wire']
    if len(devices)>150 or len(wires)>1500:issues.append('Simulation supports up to 150 components and 1,500 wires per run. Select a smaller reviewed circuit.')
    if sum(len(e['points']) for e in wires)+sum(len(BY_KIND[e['kind']]['ports']) for e in elements if e['kind'] in BY_KIND)>800:
        issues.append('Simulation supports up to 800 wire points and component pins. Simplify the reviewed circuit first.')
    for e in elements:
        if e['kind']=='unknown' or e['kind']=='motor':issues.append(e.get('label',e['id'])+': component model unresolved.')
        elif e['kind'] not in {'drawing','text'} and not e.get('reviewed'):issues.append((e.get('label') or e['id'])+': imported object needs review.')
        elif e['kind']=='drawing' and e.get('source') and not e.get('reviewed'):issues.append(e['id']+': classify this imported outline or confirm it is graphics only.')
    if issues:return None,{'issues':issues[:100],'issueCount':len(issues)}
    graph=topology(elements)
    if not graph['hasGround']:issues.append('Add a ground/reference terminal.')
    if not any(e['kind']=='voltage' for e in devices):issues.append('Add a supported voltage source.')
    degree=defaultdict(int)
    for a,b,_ in graph['edges']:degree[a]+=1;degree[b]+=1
    all_pins=list(graph['pins'].values())
    for e in devices:
        for p in BY_KIND[e['kind']]['ports']:
            v=graph['pins'][e['id']+':'+p['id']]
            if not degree[v] and all_pins.count(v)<2:issues.append(f'{e.get("label",e["id"])}: pin {p["id"]} is not wired.')
    if issues:return None,{'issues':issues[:100],'issueCount':len(issues)}
    def node(e,p):return graph['nodes'][graph['pins'][e['id']+':'+p]]
    lines=['uSOPp native reviewed circuit','.options noacct']
    records=[];probes=[];coils=[e for e in devices if e['kind']=='coil'];by_label={e.get('label'):e for e in coils}
    if len(by_label)!=len(coils):return None,{'issues':['Give each relay coil a unique label before linking contacts.'],'issueCount':1}
    for i,e in enumerate(devices,1):
        kind=e['kind'];p=e['params'];a=node(e,'c' if kind in {'npn','pnp'} else 'p');b=node(e,'b' if kind in {'npn','pnp'} else 'n')
        prefix={'resistor':'r','coil':'r','lamp':'r','capacitor':'c','inductor':'l','voltage':'v','switch':'r','contact_no':'s','contact_nc':'s','diode':'d','npn':'q','pnp':'q'}[kind]
        name=prefix+str(i);record={'id':e['id'],'kind':kind,'name':name,'label':e.get('label',e['id']),'nodes':{'p':a,'n':b},'params':p}
        if kind in {'resistor','coil','lamp','capacitor','inductor'}:lines.append(f'{name} {a} {b} {p["value"]:.12g}');probes.append('@'+name+'[i]')
        elif kind=='switch':lines.append(f'{name} {a} {b} '+('0.01' if p['closed'] else '1e12'));probes.append('@'+name+'[i]')
        elif kind=='voltage':
            value=p['value'];wave=p.get('waveform','dc');spec=f'DC {value:.12g}'
            if wave=='sine':spec+=f' SIN(0 {value:.12g} {p["frequency"]:.12g})'
            elif wave=='pulse':
                if p['width']>p['period']:issues.append(record['label']+': pulse width must not exceed its period.')
                spec=f'DC 0 PULSE(0 {value:.12g} 0 1e-7 1e-7 {p["width"]:.12g} {p["period"]:.12g})'
            lines.append(f'{name} {a} {b} {spec}')
        elif kind=='diode':
            model='dm'+str(i);lines.extend([f'{name} {a} {b} {model}',f'.model {model} D(Is={"1e-20 N=2" if p["model"]=="led" else "1e-14 N=1"})']);probes.append('@'+name+'[id]')
        elif kind in {'npn','pnp'}:
            c=node(e,'e');model='qm'+str(i);lines.extend([f'{name} {a} {b} {c} {model}',f'.model {model} {kind.upper()}(Is=1e-15 Bf={p["beta"]:.12g} Vaf=100)'])
            probes.extend('@'+name+'['+v+']' for v in ('ic','ib','ie'));record['nodes']={'c':a,'b':b,'e':c}
        elif kind in {'contact_no','contact_nc'}:
            coil=by_label.get(p.get('control'))
            if not coil:issues.append(record['label']+': select an existing coil label.');continue
            ca,cb=node(coil,'p'),node(coil,'n');threshold=p['threshold']
            if kind=='contact_nc':ca,cb=cb,ca;threshold=-threshold
            prior=(previous or {}).get('measurements',{}).get(coil['id'],{}).get('voltage',[])
            active=bool(prior and abs(prior[-1])>=p['threshold']);closed=active if kind=='contact_no' else not active
            model='sm'+str(i);lines.extend([f'{name} {a} {b} {ca} {cb} {model} '+('ON' if closed else 'OFF'),f'.model {model} SW(Ron=0.01 Roff=1e12 Vt={threshold:.12g} Vh=0.1)']);probes.append('@'+name+'[i]')
        records.append(record)
    if issues:return None,{'issues':issues,'issueCount':len(issues)}
    mode=options.get('mode','op')
    if mode not in {'op','tran'}:return None,{'issues':['Choose DC operating point or Transient.'],'issueCount':1}
    if mode=='tran':
        stop=options.get('duration',.1);step=options.get('step',.0001)
        if any(type(v)not in (int,float) or not math.isfinite(v) for v in (stop,step)) or not 1e-8<=step<=stop<=10 or stop/step>2000:return None,{'issues':['Use a duration up to 10 seconds and at most 2,000 requested time steps.'],'issueCount':1}
    lines+=['.save all '+' '.join(probes),'.control','set filetype=ascii','op','write op.raw all']
    if mode=='tran':lines+=[f'tran {step:.12g} {stop:.12g}','write tran.raw all']
    lines+=['quit','.endc','.end']
    return '\n'.join(lines)+'\n',{'graph':graph,'records':records,'elements':elements,'mode':mode}


def raw(path):
    if not path.is_file() or path.stat().st_size>64*1024*1024:raise ValueError('The solver did not return a bounded result file.')
    text=path.read_text(encoding='utf-8',errors='replace');lines=text.splitlines()
    nv=int(next(l.split(':',1)[1] for l in lines if l.startswith('No. Variables:')));np_=int(next(l.split(':',1)[1] for l in lines if l.startswith('No. Points:')))
    if not 0<nv<=1000 or not 0<np_<=10000:raise ValueError('The solver result exceeds the sample budget.')
    vi=lines.index('Variables:');names=[lines[vi+i+1].split()[1].lower() for i in range(nv)]
    values='\n'.join(lines[lines.index('Values:')+1:]).split();expected=np_*(nv+1)
    if len(values)!=expected:raise ValueError('Incomplete solver output; measurements withheld.')
    array=np.asarray([float(v) for i,v in enumerate(values) if i%(nv+1)],dtype=float).reshape(np_,nv)
    if not np.isfinite(array).all():raise ValueError('Non-finite solver measurements were rejected.')
    indices=np.unique(np.linspace(0,np_-1,min(np_,1200),dtype=int))
    return {name:array[indices,i] for i,name in enumerate(names)},np_>1200


def solve(document,options=None,previous=None):
    options=options or {};net,meta=netlist(document,options,previous)
    if net is None:return {'status':'blocked',**meta,'physicalController':False}
    exe=executable()
    if not exe:return {'status':'blocked','issues':['ngspice is not installed. Run scripts/install_ngspice.py or configure USOPP_NGSPICE.'],'issueCount':1}
    if not SLOTS.acquire(blocking=False):return {'status':'blocked','issues':['Two circuit simulations are already running. Retry when one finishes.'],'issueCount':1}
    start=time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix='usopp-spice-') as temporary:
            folder=Path(temporary);(folder/'circuit.cir').write_text(net,encoding='ascii')
            result=subprocess.run([exe,'-n','-b','-o','simulation.log','circuit.cir'],cwd=folder,capture_output=True,timeout=12,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            log=(folder/'simulation.log').read_text(encoding='utf-8',errors='replace') if (folder/'simulation.log').exists() else ''
            if result.returncode or any(s in log.lower() for s in ('timestep too small','simulation interrupted','doanalyses:','fatal error')):raise ValueError('Circuit did not converge. Check grounding, source conflicts and device values. '+log[-700:])
            vectors,reduced=raw(folder/('tran.raw' if meta['mode']=='tran' else 'op.raw'))
        count=len(next(iter(vectors.values())));zero=np.zeros(count)
        voltage=lambda n:zero if n=='0' else vectors.get('v('+n+')')
        measured={};coils={};injections=defaultdict(lambda:np.zeros(count))
        for r in meta['records']:
            names=r['nodes'];values={p:voltage(n) for p,n in names.items()}
            if any(v is None for v in values.values()):raise ValueError('A required node measurement is missing.')
            name=r['name'];kind=r['kind'];current=None
            if kind=='voltage':current=vectors.get('i('+name+')')
            else:
                suffix='id' if kind=='diode' else 'ic' if kind in {'npn','pnp'} else 'i'
                current=vectors.get('i(@'+name+'['+suffix+'])')
            if current is None:raise ValueError('A component current measurement is missing: '+r['label'])
            diff=values.get('p',values.get('c'))-values.get('n',values.get('e'))
            measured[r['id']]={'voltage':diff.tolist(),'current':current.tolist(),'pins':{p:v.tolist() for p,v in values.items()}}
            if kind in {'npn','pnp'}:
                for p,suffix in [('c','ic'),('b','ib'),('e','ie')]:
                    vector=vectors.get('i(@'+name+'['+suffix+'])')
                    if vector is not None:injections[meta['graph']['pins'][r['id']+':'+p]]+=vector
            else:
                injections[meta['graph']['pins'][r['id']+':p']]+=current;injections[meta['graph']['pins'][r['id']+':n']]-=current
            if kind=='coil':coils[r['id']]=abs(float(diff[-1]))>=12
        wire_values=wire_currents(meta['graph'],injections,count)
        for identity,vertices in meta['graph']['wireVertices'].items():
            n=meta['graph']['nodes'][vertices[0]];v=voltage(n)
            if v is not None:measured[identity]={'voltage':v.tolist(),'current':wire_values.get(identity)}
        return {'status':'complete','engine':'ngspice','analysis':meta['mode'],'version':document.get('version'),
                'time':vectors.get('time',zero).tolist(),'measurements':measured,'coils':coils,'seconds':round(time.monotonic()-start,3),
                'downsampled':reduced,'netlist':net,'modelNotice':document.get('modelNotice'),'physicalController':False}
    except (ValueError,StopIteration,subprocess.TimeoutExpired,OSError) as error:return {'status':'failed','issues':[str(error)[:1400]],'issueCount':1,'physicalController':False}
    finally:SLOTS.release()


def wire_currents(graph,injections,count):
    """Only report uniquely determined ideal-wire branch currents (bridge cuts)."""
    adjacency=defaultdict(list)
    for i,(a,b,_) in enumerate(graph['edges']):adjacency[a].append((b,i));adjacency[b].append((a,i))
    seen={};low={};totals={};currents={};clock=[0]
    def visit(v,parent_edge=-1):
        clock[0]+=1;seen[v]=low[v]=clock[0];total=injections[v].copy()
        for u,eid in adjacency[v]:
            if eid==parent_edge:continue
            if u not in seen:
                child=visit(u,eid);total+=child;low[v]=min(low[v],low[u])
                if low[u]>seen[v]:
                    a,_,_=graph['edges'][eid];currents[eid]=child if a==v else -child
            else:low[v]=min(low[v],seen[u])
        totals[v]=total;return total
    # Budgets avoid an unbounded recursive traversal on imported line drawings.
    if len(graph['vertices'])>800:return {}
    for v in adjacency:
        if v not in seen:visit(v)
    grouped=defaultdict(list)
    for i,(_,_,identity) in enumerate(graph['edges']):grouped[identity].append(currents.get(i))
    return {identity:values[0].tolist() for identity,values in grouped.items() if values and all(v is not None for v in values) and all(np.allclose(values[0],v,atol=1e-9,rtol=1e-5) for v in values)}
