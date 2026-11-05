from __future__ import annotations
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from backend.core.runtime import RESOURCE_ROOT, VERSION, log
from backend.api import assist, comparison, knowledge, rules, system, validation, metadata, validation_source, nami, auth, report_exports, history
from backend.core.run_history import current_user
from backend.core import accounts
from backend.core.web_security import SecurityHeadersMiddleware,response_headers,unsafe_origin
from backend.api import assist_settings, assist_attachments, ladder, mcp_settings, compare_export_jobs, data_models, user_settings, br_help, admin_settings, admin_knowledge
from backend.api import assist_training, assist_flow, project_intelligence, circuit_compare, edesign, virtual_electrical
from backend.api import plc_pdf_comparison
from backend.api import spreadsheet_analysis
from backend.api import live_data, data_simulator, dashboard_layouts
from backend.api import spinconnect_write
from backend.api import nami_edit
from backend.api import document_comparison
from backend.api import workhub,workhub_intelligence,workhub_office,workhub_growth,workhub_dashboards,workhub_quality,workhub_branding,workhub_training,workhub_people,workhub_praxis,workhub_studio
from backend.core.mcp_tools import server as mcp_server, http_app as mcp_app
from contextlib import asynccontextmanager

@asynccontextmanager
async def app_lifespan(app):
    from backend.core.persistent_store import initialize
    from backend.core.local_model_runtime import autostart
    await __import__('asyncio').to_thread(initialize)
    autostart()
    from backend.core.br_help import autostart as start_help_index
    start_help_index()
    from backend.core import live_collection
    from backend.core import data_simulator as virtual_plc
    virtual_plc.autostart()
    live_collection.start()
    from backend.core import workhub_notifications
    workhub_notifications.start()
    from backend.core.workhub_intelligence import jobs as intelligence_jobs
    from backend.core.workhub_quality.store import initialize as initialize_quality
    await __import__('asyncio').to_thread(initialize_quality)
    intelligence_jobs.start()
    from backend.core.workhub_growth import collector as performance_collector
    performance_collector.start()
    async with mcp_server.session_manager.run():
        try:yield
        finally:
            live_collection.shutdown()
            workhub_notifications.shutdown()
            intelligence_jobs.shutdown()
            performance_collector.shutdown()
            virtual_plc.shutdown()
            from backend.core.local_model_runtime import shutdown
            shutdown()

app = FastAPI(title='uSOPp.ai API', version=VERSION, debug=False,lifespan=app_lifespan)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    if request.url.path.startswith('/api/e-design'):
        log.warning('DRAWING_REVIEW_REQUEST_VALIDATION_ERROR method=%s path=%s', request.method, request.url.path)
        return JSONResponse({'detail':'Check the drawing page, selected area and correction comment.'},status_code=400)
    if (request.url.path.startswith('/api/workhub/') and any(part in request.url.path for part in ('/intelligence','/growth','/dashboards','/quality'))) or '/document-branding' in request.url.path or request.url.path.endswith('/engineering-quality'):
        # Do not copy confidential document/meeting payloads into request logs.
        log.warning('INTELLIGENCE_REQUEST_VALIDATION_ERROR method=%s path=%s',request.method,request.url.path)
        return JSONResponse({'detail':'Check the required WorkHub request fields.'},status_code=400)
    if request.url.path.startswith('/api/auth/'):
        log.warning('ACCOUNT_REQUEST_VALIDATION_ERROR method=%s path=%s',request.method,request.url.path)
        return JSONResponse({'detail':'Account request could not be processed. Enter the required fields.'},status_code=400)
    if request.url.path.startswith('/api/local/compare/reports/'):
        fields = '; '.join(f'{" / ".join(str(part) for part in error["loc"] if part != "body")}: {error["msg"]}' for error in exc.errors())
        log.warning('REPORT_REQUEST_VALIDATION_ERROR path=%s fields=%s',request.url.path,fields)
        return JSONResponse({'detail':f'Check the report details. {fields}'},status_code=400)
    fields=[{'loc':list(e['loc']),'type':e['type']} for e in exc.errors()]
    log.warning('REQUEST_VALIDATION_ERROR method=%s path=%s fields=%s',request.method,request.url.path,fields)
    return JSONResponse({'detail':'Check the required request fields.','errors':fields},status_code=400)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.exception('UNHANDLED_EXCEPTION method=%s path=%s error=%s', request.method, request.url.path, exc)
    return JSONResponse({'detail':'An internal error occurred. Contact your administrator and check the server log.'},status_code=500,headers=response_headers(request.url.scheme)|{'Cache-Control':'private, no-store'})

@app.middleware('http')
async def request_logger(request, call_next):
    started=time.perf_counter()
    try:
        response=await call_next(request)
        elapsed=time.perf_counter()-started
        from backend.core.workhub_intelligence.reliability import record_latency
        route=getattr(request.scope.get('route'),'path','')
        record_latency(route,elapsed*1000,response.status_code>=500)
        log.info('HTTP %s %s -> %s (%.3fs)', request.method, request.url.path, response.status_code, elapsed)
        if request.url.path.startswith('/assets/') or response.headers.get('content-type','').startswith('text/html') or request.url.path in ('/api/health','/build-info.json'):
            response.headers['Cache-Control']='no-store'
        response.headers['X-USOPP-Version']=VERSION
        return response
    except Exception:
        from backend.core.workhub_intelligence.reliability import record_latency
        record_latency(getattr(request.scope.get('route'),'path',''),(time.perf_counter()-started)*1000,True)
        log.exception('HTTP ERROR %s %s', request.method, request.url.path)
        raise

DEV_ORIGINS=[f'http://{host}:{os.getenv("USOPP_FRONTEND_PORT","8201")}' for host in ('localhost','127.0.0.1')]
app.add_middleware(CORSMiddleware, allow_origins=DEV_ORIGINS, allow_credentials=True, allow_methods=['*'], allow_headers=['*'])

@app.middleware('http')
async def account_session(request:Request,call_next):
    public={'/api/health','/api/auth/session','/api/auth/login','/api/auth/register','/api/auth/logout'}
    path=request.url.path
    office_callback=path.startswith(('/api/workhub/intelligence/office/files/','/api/workhub/intelligence/office/callback/'))
    api_docs=path in {'/docs','/docs/oauth2-redirect','/redoc','/openapi.json'}
    if (path.startswith('/api/') or api_docs) and request.method!='OPTIONS':
        if request.method not in ('GET','HEAD') and not office_callback:
            if unsafe_origin(request,DEV_ORIGINS):
                return JSONResponse({'detail':'Request origin does not match this application.'},status_code=403)
        if path not in public and not office_callback:
            from starlette.concurrency import run_in_threadpool
            token_value=request.cookies.get(accounts.COOKIE)
            if path.startswith('/api/mcp') and request.headers.get('authorization','').startswith('Bearer '):token_value=request.headers['authorization'][7:]
            user=await run_in_threadpool(accounts.store.user_for_token,token_value)
            if not user:
                return JSONResponse({'detail':'Sign in to uSOPp.ai to continue.'},status_code=401)
            if api_docs and user.get('role')!='admin':return JSONResponse({'detail':'API documentation is available to administrators.'},status_code=403)
            request.state.user=user
    token=current_user.set(getattr(request.state,'user',None))
    from backend.core.workhub_tool_context import selection,validate as validate_test_project
    project_token=selection.set(None)
    try:
        if getattr(request.state,'user',None):
            from backend.core.access import authorize_request
            from fastapi import HTTPException
            try:
                await authorize_request(request)
                selected=request.headers.get('x-workhub-project')
                if selected is not None and request.method=='POST':
                    context=await run_in_threadpool(validate_test_project,request.state.user,selected)
                    selection.set(context)
            except HTTPException as error:
                return JSONResponse({'detail':error.detail},status_code=error.status_code)
        return await call_next(request)
    finally:
        selection.reset(project_token)
        current_user.reset(token)

app.add_middleware(SecurityHeadersMiddleware)

for feature_router in (system.router, validation.router, metadata.router, knowledge.router, compare_export_jobs.router, comparison.router, rules.router, assist.router, validation_source.router, nami.router, auth.router, report_exports.router, history.router,data_models.router):
    app.include_router(feature_router)
app.include_router(circuit_compare.router)
app.include_router(plc_pdf_comparison.router)
app.include_router(spreadsheet_analysis.router)
app.include_router(edesign.router)
app.include_router(virtual_electrical.router)

# Reports and workbook sessions remain available until explicitly cleared.

DIST=RESOURCE_ROOT/'dist'
app.include_router(assist_settings.router)
app.include_router(user_settings.router)
app.include_router(live_data.router)
app.include_router(data_simulator.router)
app.include_router(dashboard_layouts.router)
app.include_router(spinconnect_write.router)
app.include_router(workhub_people.router)
app.include_router(workhub_praxis.router)
app.include_router(workhub_studio.router)
app.include_router(nami_edit.router)
app.include_router(document_comparison.router)
app.include_router(workhub.router)
app.include_router(workhub_intelligence.router)
app.include_router(workhub_office.router)
app.include_router(workhub_growth.router)
app.include_router(workhub_dashboards.router)
app.include_router(workhub_quality.router)
app.include_router(workhub_branding.router)
app.include_router(workhub_training.router)
app.include_router(br_help.router)
app.include_router(admin_settings.router)
app.include_router(admin_knowledge.router)
app.include_router(assist_training.router)
app.include_router(assist_attachments.router)
app.include_router(assist_flow.router)
app.include_router(project_intelligence.router)
app.include_router(ladder.router)
app.include_router(mcp_settings.router)
app.mount('/api/mcp',mcp_app)
if DIST.exists():
    app.mount('/assets', StaticFiles(directory=DIST/'assets'), name='assets')
    if (DIST/'nami').exists():
        app.mount('/nami', StaticFiles(directory=DIST/'nami', html=True), name='nami')
    @app.get('/{path:path}')
    def spa(path:str):
        if path == 'nami' or path.startswith('nami/'):
            from fastapi import HTTPException
            raise HTTPException(503, 'DataInspect interface is missing. Build the frontend and restart uSOPp.ai.')
        if path.startswith('api/'):
            from fastapi import HTTPException
            raise HTTPException(404,'API endpoint not found')
        target=(DIST/path).resolve()
        if DIST.resolve() not in target.parents: target=DIST/'index.html'
        resolved = target if target.exists() and target.is_file() else DIST/'index.html'
        return FileResponse(resolved, headers={'Cache-Control':'no-store'} if resolved.suffix == '.html' else None)
