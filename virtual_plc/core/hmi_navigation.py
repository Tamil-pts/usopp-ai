"""VC4 PageCurrent/ChangeDatapoint handshake, scoped to each visualization.

Bundled B&R reference: visualization/ref-visu_pagedatapoint.html. 65535
means no pending page request. Page numbers come from the source Index.
"""
from .hmi_runtime import write_value


def _sessions(runtime):
    if not hasattr(runtime,'_hmi_pages'):runtime._hmi_pages={}
    return runtime._hmi_pages


def activate_page(model,runtime,page,remember=True):
    target=page.get('target') or page['source'].rsplit('/Pages/',1)[0]
    sessions=_sessions(runtime)
    state=sessions.setdefault(target,{'pageId':page['id'],'history':[],'ready':False})
    if remember and state['pageId']!=page['id']:
        state['history']=(state['history']+[state['pageId']])[-32:]
    state['pageId']=page['id']
    _publish(runtime,page,state)
    return page['id']


def _publish(runtime,page,state):
    config=page.get('runtimeBindings',{})
    current=config.get('currentPageBinding')
    index=page.get('properties',{}).get('Index')
    if current and index is not None and runtime.get_value(current)!=int(index):write_value(runtime,current,int(index))
    if not state['ready'] and runtime._initialized:
        if config.get('changePageBinding'):write_value(runtime,config['changePageBinding'],65535)
        state['ready']=True
    state['error']=''


def sync_pages(model,runtime):
    pages=model.get('hmi',{}).get('pages',[])
    for target,state in _sessions(runtime).items():
        page=next((p for p in pages if p['id']==state['pageId']),None)
        if not page:continue
        try:
            if not runtime._initialized:state['ready']=False
            was_ready=state['ready']
            _publish(runtime,page,state)
            change=page.get('runtimeBindings',{}).get('changePageBinding')
            if not was_ready or not change:continue
            value=runtime.get_value(change)
            if value==65535:continue
            choices=[p for p in pages if p.get('target')==target and str(p.get('properties',{}).get('Index'))==str(value)]
            if len(choices)!=1:
                state['error']='PLC requested an unknown or ambiguous page index: '+str(value)
                continue
            activate_page(model,runtime,choices[0])
            write_value(runtime,change,65535)
        except (ValueError,TypeError,KeyError,IndexError,OverflowError) as error:state['error']=str(error)[:300]


def back_page(model,runtime,page):
    state=_sessions(runtime).get(page.get('target'),{})
    history=state.get('history',[])
    if not history:raise ValueError('No previous page has been visited in this HMI target.')
    identity=history[-1]
    previous=next((p for p in model.get('hmi',{}).get('pages',[]) if p['id']==identity and p.get('target')==page.get('target')),None)
    if not previous:raise ValueError('The previous source page is no longer available.')
    activate_page(model,runtime,previous,remember=False)
    history.pop()
    return identity


def navigation_state(runtime,page):
    if not page:return {}
    state=_sessions(runtime).get(page.get('target'),{})
    result={'pageId':state.get('pageId',page['id']),'index':page.get('properties',{}).get('Index'),
            'target':page.get('target'),'error':state.get('error',''),'configured':bool(page.get('runtimeBindings'))}
    for name,binding in page.get('runtimeBindings',{}).items():
        if name not in {'currentPageBinding','changePageBinding'}:continue
        try:result[name]={'binding':binding,'value':runtime.get_value(binding)} if binding else None
        except (ValueError,TypeError,KeyError,IndexError):result[name]={'binding':binding,'error':'Unresolved page datapoint.'}
    return result
