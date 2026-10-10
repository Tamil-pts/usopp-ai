from fastapi import APIRouter,HTTPException
from fastapi.responses import Response
from python_engine.ladder_model import render_svg,render_png,normalized_model,primitives,RENDER_VERSION

router=APIRouter(tags=['Ladder diagrams'])

@router.post('/api/ladder/render/{fmt}')
def render(payload:dict,fmt:str):
    if fmt not in {'svg','png','view'}: raise HTTPException(400,'Choose SVG or PNG')
    record=payload.get('network') or {};other=payload.get('other')
    for value in (record,other):
        if value is None:continue
        model=value.get('diagram') or value
        if not isinstance(model,dict) or not isinstance(model.get('cells'),list) or len(model['cells'])>10000:
            raise HTTPException(400,'A supported ladder network model is required.')
        if not all(isinstance(model.get(k),int) and not isinstance(model[k],bool) and 0<=model[k]<=limit for k,limit in [('rows',250),('columns',150)]):raise HTTPException(400,'Invalid network dimensions.')
        for cell in model['cells']:
            if not isinstance(cell,dict) or not all(isinstance(cell.get(k),int) and not isinstance(cell[k],bool) and 0<=cell[k]<model[bound] for k,bound in [('row','rows'),('column','columns')]):raise HTTPException(400,'Invalid ladder cell position.')
            if not all(isinstance(cell.get(k,''),str) for k in ['id','kind','name','type','position','instance']):raise HTTPException(400,'Invalid ladder element.')
            if not all(isinstance(cell.get(k,[]),list) and all(isinstance(v,str) for v in cell.get(k,[])) for k in ['inputs','outputs']):raise HTTPException(400,'Invalid ladder pins.')
    side='base' if payload.get('side')=='base' else 'developed'
    if fmt=='view':
        width,height,_=primitives(record,other,side)
        return {'svg':render_svg(record,other,side),'model':normalized_model(record),
                'width':width,'height':height,'renderVersion':RENDER_VERSION}
    data=render_svg(record,other,side) if fmt=='svg' else render_png(record,other,side)
    return Response(data,media_type='image/svg+xml' if fmt=='svg' else 'image/png',headers={'Cache-Control':'no-store'})
