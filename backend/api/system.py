from __future__ import annotations
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from backend.core.runtime import (
    CACHE_TTL_SECONDS,
    LOG_FILE,
    WORK,
    datetime,
    json,
    log,
    os,
    shutil,
    time,
    clear_temporary_workspaces,
)

from backend.core.runtime import BASE, VERSION, _local_path, _local_roots, _local_entries, locate_root
from backend.core.runtime import RESOURCE_ROOT
from backend.core.build_info import frontend_build_info

router = APIRouter(tags=['System'])

@router.get('/api/health')
def health():
    build=frontend_build_info(RESOURCE_ROOT/'dist',VERSION)
    strict=os.getenv('USOPP_REQUIRE_FRONTEND_BUILD')=='1' or (RESOURCE_ROOT/'dist/build-info.json').is_file()
    good=build['matches'] or not strict
    data={'status':'ok' if good else 'version-mismatch','version':VERSION,'apiVersion':VERSION,'uiVersion':build['version'],'frontendBuild':build,'capabilities':{'accounts':True,'chopperTools':True,'assistJobs':True,'projectAttachments':True,'userManagement':True,'functionFlows':True,'reportAnalysis':True,'performanceDashboard':True,'workhubPerformanceCapability':True,'contributionPassport':True,'workhubDashboardBuilder':True,'engineeringQualityClosure':True,'workhubUnifiedProjectWorkspace':True,'workhubDefaultDashboardTemplate':True,'workhubReliableBackgroundJobs':True,'workhubRevisionProcessingCache':True},'applicationRoot':str(BASE),'frontend':'React + TypeScript + Vite','engine':'Python v1.71 base (modified)','ruleEngine':'v4.30','logFile':str(LOG_FILE)}
    data['capabilities']['circuitCompare']=True
    data['capabilities']['eDesignReview']=True
    data['capabilities']['eDesignInlineCallouts']=True
    data['capabilities']['workhubProjectWorkflowSettings']=True
    data['capabilities']['workhubStructuredProjectFRD']=True
    data['capabilities']['workhubValidationFatReports']=True
    data['capabilities']['workhubWorkflowApprovalDocuments']=True
    data['capabilities']['workhubPersonalInbox']=True
    data['capabilities']['workhubBillingHours']=True
    data['capabilities']['workhubDefaultDashboard']=True
    data['capabilities']['workhubMomStructuredReport']=True
    data['capabilities']['workhubReviewSignoff']=True
    data['capabilities']['workhubDocumentActions']=True
    data['capabilities']['workhubCustomProjectFields']=True
    data['capabilities']['workhubProjectExports']=True
    return JSONResponse(data,status_code=200 if good else 503,headers={'Cache-Control':'no-store'})
@router.post('/api/log')
def frontend_log(payload:dict):
    event=str(payload.get('event','frontend_event'))[:100]
    details=payload.get('details',{})
    try: details=json.dumps(details,ensure_ascii=False)[:8000]
    except Exception: details=str(details)[:8000]
    log.info('FRONTEND %s | %s', event, details)
    return {'status':'ok'}
@router.get('/api/logs/today')
def today_log():
    from backend.core.run_history import current_user
    if (current_user.get() or {}).get('role')!='admin': raise HTTPException(403,'Only Admin can view shared server logs.')
    if not LOG_FILE.exists(): return PlainTextResponse('')
    return PlainTextResponse(LOG_FILE.read_text(encoding='utf-8',errors='replace'))
@router.get('/api/local/browse')
def local_browse(path:str='', files:bool=False, ext:str=''):
    """Browse the local PC for project folders or Excel metadata files."""
    if not path:
        return {'path':'','entries':[{'name':p.name or str(p),'path':str(p),'has_children':True} for p in _local_roots()]}
    p=_local_path(path,True,True)
    exts={x.strip().lower() if x.strip().startswith('.') else '.'+x.strip().lower() for x in ext.split(',') if x.strip()} if ext else {'.xlsx','.xls'}
    return {'path':str(p),'parent':str(p.parent) if p.parent!=p else '', 'entries':_local_entries(p, include_files=files, file_exts=exts)}
@router.post('/api/local/path/check')
def check_path(payload:dict):
    kind=payload.get('kind','folder')
    path=_local_path(payload.get('path',''),True,kind=='folder')
    if kind=='folder': path=locate_root(path)
    elif not path.is_file(): raise HTTPException(400,'Select a file, not a folder.')
    allowed=payload.get('extensions') or []
    if kind=='file' and allowed and path.suffix.lower() not in allowed:
        raise HTTPException(400,'Allowed file types: '+', '.join(allowed))
    return {'path':str(path),'name':path.name}

@router.post('/api/cache/clear')
def cache_clear():
    cleared=clear_temporary_workspaces()
    return {'status':'ok',**cleared,'message':'Your temporary project sources were cleared. Saved results, history and exported reports are retained.'}

@router.get('/api/download/{sid}/{filename}')
def download(sid:str,filename:str):
    if '/' in sid or '\\' in sid or '/' in filename or '\\' in filename or '..' in filename or '..' in sid: raise HTTPException(400,'Invalid download path')
    p=WORK/sid/filename
    if not p.exists(): raise HTTPException(404,'Workbook not found')
    return FileResponse(p,filename=filename,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
