"""A consistent page snapshot after polling or an HMI action."""
from .hmi_runtime import control_state,password_source_status,covering_control
from .hmi_text import display_text
from .hmi_limits import numeric_status
from .hmi_selection import selection_options
from .preview import value_preview


def page_state(model,page,runtime,names=None):
    objects=(page or {}).get('objects',[])
    if names is None:
        names=set()
        for item in objects:
            for key in ('binding','textBinding','textIndexBinding','statusBinding','lockingBinding',
                        'passwordLevelBinding','visibilityBinding','minBinding','maxBinding','bitmapIndexBinding'):
                if item.get(key):names.add(item[key])
            layer=item.get('layerState') or {}
            if layer.get('statusBinding'):names.add(layer['statusBinding'])
            for action in [*item.get('actions',[]),item.get('completion') or {}]:
                if action.get('variable'):names.add(action['variable'])
        names=sorted(names)[:1024]
    result={key:{} for key in ('values','errors','controls','texts','layers','passwordSources','numericInputs','selections')}
    for name in set(names):
        try:
            value,complete=value_preview(runtime.get_value(name))
            if not complete:raise ValueError('Select a specific scalar array or structure member.')
            result['values'][name]=value
        except (ValueError,TypeError,KeyError,IndexError) as error:result['errors'][name]=str(error)[:300]
    result['controls']={item['id']:control_state(item,runtime) for item in objects}
    result['layers']={item['id']:control_state({'layerState':item},runtime) for item in (page or {}).get('layers',[])}
    for item in objects:
        if not result['controls'][item['id']]['visible']:continue
        try:
            kind=item.get('kind')
            if kind=='numeric' and item.get('input'):result['numericInputs'][item['id']]=numeric_status(item,runtime)
            if kind=='password':result['passwordSources'][item['id']]=password_source_status(model,item,runtime)
            if kind=='dropdown':result['selections'][item['id']]={'options':selection_options(model,item,runtime)}
            if kind in {'text','listbox','datetime','button'}:
                rendered=display_text(model,item,runtime)
                if rendered is not None:result['texts'][item['id']]=rendered
        except (ValueError,TypeError,KeyError,IndexError) as error:
            result['errors'][item['id']]=str(error)[:300]
            if item.get('kind')=='dropdown':result['selections'][item['id']]={'options':[],'error':str(error)[:300]}
    for item in objects:
        if item.get('kind') not in {'button','hotspot','numeric','dropdown','string','password'}:continue
        cover=covering_control(page,item,runtime)
        if cover:result['controls'][item['id']]['coveredBy']={'id':cover['id'],'name':cover['name'],'layer':cover['layer'],'statusBinding':cover.get('statusBinding')}
    from .hmi_navigation import navigation_state
    result['pageRuntime']=navigation_state(runtime,page)
    result['alarmCursors']=getattr(runtime,'_hmi_alarm_cursors',{})
    return result
