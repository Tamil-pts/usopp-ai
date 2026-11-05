"""Source-based HMI correction notes and named static layer views for print."""
from .compare_screen_preview import screen_previews


def options(result):
    selection=result.get('reportSelection') or {}
    return {'show_names':selection.get('screenControlNames',True),
            'views':selection.get('screenLayerViews',['visible','all'])}


def notes(diff,blocks,number):
    layouts=(diff.get('parsed_screen') or {}).get('layouts') or {}
    controls={str(c.get('id')):(layer,c) for layout in layouts.values() if layout
              for layer in layout.get('layers',[]) for c in layer.get('controls',[]) if c.get('id')}
    result=[];markers={}
    for block in blocks:
        rows=[row for row in block.get('rows',[]) if row.get('state')!='unchanged']
        if not rows:continue
        title=str(block.get('title') or 'Screen properties')
        match=controls.get(title)
        if not match:
            matches=[value for key,value in controls.items() if value[1].get('name')==title]
            if len(matches)==1:match=matches[0]
        note_id=f'CN-{number:03d}-{len(result)+1:03d}'
        status=block.get('status','modified')
        if match:
            layer,control=match;layer_name=str(layer.get('name') or layer.get('id'))
            control_name=str(control.get('name') or title);identity=title
            markers[str(control['id'])]=str(len(result)+1)
        else:layer_name='Page / configuration';control_name=title;identity=title
        action={'added':'Control added in Developed; not present in Base.',
                'removed':'Control removed from Developed; present in Base.',
                'modified':'Configured properties changed from Base to Developed.'}.get(status,'Configuration difference recorded.')
        result.append({'id':note_id,'marker':str(len(result)+1),'name':control_name,'identity':identity,'layer':layer_name,
                       'class':block.get('subtitle',''),'status':status,'summary':action,'rows':rows})
    return result,markers


def views(diff,settings,markers):
    layouts=(diff.get('parsed_screen') or {}).get('layouts') or {}
    if not any(layout and layout.get('layers') for layout in layouts.values()):return []
    layers={str(layer['id']):layer for layout in layouts.values() if layout for layer in layout.get('layers',[])}
    selected=settings['views'];result=[]
    if 'visible' in selected:
        result.append({'title':'Normally visible layers','note':'Layers not marked hidden in the saved project configuration.',
                       'previews':screen_previews(diff,show_control_names=settings['show_names'],annotations=markers)})
    if 'all' in selected:
        # Separate layer images retain covered controls instead of flattening all
        # hidden layers over one another. Presence is resolved independently per side.
        single=len(layers)==1 and all(not l.get('hidden') for layout in layouts.values() if layout for l in layout.get('layers',[]))
        if single and result:
            result[0]['title']='Normally visible layers / All layers (single layer)'
        else:
            for key,layer in layers.items():
                states=[]
                for side,layout in [('Base',layouts.get('base')),('Developed',layouts.get('new'))]:
                    found=next((l for l in (layout or {}).get('layers',[]) if str(l.get('id'))==key),None)
                    states.append(side+': '+('not present' if found is None else 'hidden in configuration' if found.get('hidden') else 'normally visible'))
                result.append({'title':'All layers / '+str(layer.get('name') or key),'note':' / '.join(states),
                               'previews':screen_previews(diff,layer_id=key,show_control_names=settings['show_names'],annotations=markers)})
    return result
