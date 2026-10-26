"""Admin branding and template configuration; project permissions stay in WorkHub."""
from fastapi import APIRouter,Body,Request,Response,UploadFile,File,HTTPException
from backend.core.workhub_quality import store,branding,configuration,pdf_templates
from backend.core.workhub_quality.store import hub

router=APIRouter(tags=['WorkHub document settings'])
PREFIX='/api/admin/settings/document-branding'


def admin(request):
    configuration.admin(request.state.user);store.initialize();return request.state.user


@router.get(PREFIX)
def settings(request:Request):
    admin(request)
    with hub.db() as db:
        default=db.execute('SELECT organization_id,template_ids FROM wh_brand_defaults WHERE id=1').fetchone()
        return {'organizations':branding.records(db,'organization'),'customers':branding.records(db,'customer'),
                'templates':branding.records(db,'template'),'default_organization_id':default[0] if default else None,
                'default_template_ids':__import__('json').loads(default['template_ids']) if default else {},
                'defaults':{'organization':branding.ORG,'customer':{'name':'','address':'','contact':'','email':'','phone':'','reference':'','notes':'','logo_id':None,'active':True},
                            'template':branding.LAYOUT},'document_kinds':branding.KINDS,'sections':branding.BLOCKS,
                'renderer':'Jinja2 / Chromium, with ReportLab compatibility rendering when Chromium is unavailable'}


@router.post(PREFIX+'/preview')
def preview(request:Request,payload:dict=Body(...)):
    admin(request)
    with hub.db() as db:
        layout=branding.validate(db,'template',payload.get('data'),payload.get('id','preview'))
        value=pdf_templates.preview(db,layout,payload.get('organization_id'),payload.get('customer_id'))
    return {'html':pdf_templates.html(value),'sample':True}


@router.post(PREFIX+'/{kind}')
def create(kind:str,request:Request,payload:dict=Body(...)):
    return branding.save(admin(request),kind,payload)


@router.put(PREFIX+'/{kind}/{key}')
def update(kind:str,key:str,request:Request,payload:dict=Body(...)):
    return branding.save(admin(request),kind,payload,key)


@router.get(PREFIX+'/{kind}/{key}/history')
def history(kind:str,key:str,request:Request):
    admin(request)
    with hub.db() as db:
        branding.record(db,kind,key)
        rows=[{**dict(r),'data':__import__('json').loads(r['data'])} for r in db.execute('SELECT * FROM wh_brand_records WHERE kind=? AND id=? ORDER BY version DESC LIMIT 100',(kind,key))]
        assets=[dict(r) for r in db.execute('SELECT id,version,name,mime,sha256,created_by,created_at FROM wh_brand_assets WHERE owner_kind=? AND owner_id=? ORDER BY version DESC LIMIT 100',(kind,key))]
        return {'versions':rows,'logos':assets}


@router.post(PREFIX+'/{kind}/{key}/logo')
def logo(kind:str,key:str,request:Request,file:UploadFile=File(...)):
    user=admin(request)
    try:return branding.upload(user,kind,key,file.file.read(2*1024*1024+1),file.filename)
    finally:file.file.close()


@router.get(PREFIX+'/assets/{key}')
def image(key:str,request:Request):
    admin(request)
    with hub.db() as db:value=branding.asset(db,key)
    if not value:raise HTTPException(404,'Logo not found.')
    return Response(value['data'],media_type='image/png',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})


@router.get('/api/workhub/projects/{pid}/quality/pdf-snapshots/{revision_id}')
def snapshot(pid:str,revision_id:str,request:Request):
    store.initialize()
    with hub.db() as db:
        store.project(db,pid,request.state.user)
        row=db.execute('SELECT source_hash,context_hash,pdf_hash,renderer,created_at,rendered_at,context FROM wh_pdf_snapshots WHERE revision_id=? AND project_id=?',(revision_id,pid)).fetchone()
        if not row:raise HTTPException(404,'No approved PDF snapshot is recorded for this revision.')
        value=dict(row);context=__import__('json').loads(value.pop('context'));value['manifest']=context['manifest']
        return value
