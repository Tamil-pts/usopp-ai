from __future__ import annotations
import os
import threading
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
from backend.api import assist_settings, assist_attachments, ladder, mcp_settings, compare_export_jobs, data_models, user_settings, br_help
from backend.api import assist_training
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
    async with mcp_server.session_manager.run():
        try:yield
        finally:
            from backend.core.local_model_runtime import shutdown
            shutdown()

app = FastAPI(title='uSOPp.ai API', version=VERSION, debug=False,lifespan=app_lifespan)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    if request.url.path.startswith('/api/auth/'):
        log.warning('ACCOUNT_REQUEST_VALIDATION_ERROR method=%s path=%s',request.method,request.url.path)
        return JSONResponse({'detail':'Account request could not be processed. Enter the required fields.'},status_code=400)
    if request.url.path.startswith('/api/local/compare/reports/'):
        fields = '; '.join(f'{" / ".join(str(part) for part in error["loc"] if part != "body")}: {error["msg"]}' for error in exc.errors())
        log.warning('REPORT_REQUEST_VALIDATION_ERROR path=%s fields=%s',request.url.path,fields)
        return JSONResponse({'detail':f'Check the report details. {fields}'},status_code=400)
    log.error('REQUEST_VALIDATION_ERROR method=%s path=%s errors=%s', request.method, request.url.path, exc.errors())
    return JSONResponse({'detail':'Request could not be processed. See backend log for details.','errors':exc.errors()}, status_code=400)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.exception('UNHANDLED_EXCEPTION method=%s path=%s error=%s', request.method, request.url.path, exc)
    return JSONResponse({'detail': f'Backend error: {type(exc).__name__}: {exc}'}, status_code=500)

@app.middleware('http')
async def request_logger(request, call_next):
    started=datetime.now()
    try:
        response=await call_next(request)
        elapsed=(datetime.now()-started).total_seconds()
        log.info('HTTP %s %s -> %s (%.3fs)', request.method, request.url.path, response.status_code, elapsed)
        if request.url.path.startswith('/assets/'):
            response.headers['Cache-Control']='no-store'
        return response
    except Exception:
        log.exception('HTTP ERROR %s %s', request.method, request.url.path)
        raise

DEV_ORIGINS=[f'http://{host}:{os.getenv("USOPP_FRONTEND_PORT","8201")}' for host in ('localhost','127.0.0.1')]
app.add_middleware(CORSMiddleware, allow_origins=DEV_ORIGINS, allow_credentials=True, allow_methods=['*'], allow_headers=['*'])

@app.middleware('http')
async def account_session(request:Request,call_next):
    public={'/api/health','/api/auth/session','/api/auth/login','/api/auth/register','/api/auth/logout'}
    path=request.url.path
    if path.startswith('/api/') and request.method!='OPTIONS':
        if request.method not in ('GET','HEAD'):
            origin=request.headers.get('origin')
            if origin and origin not in DEV_ORIGINS and origin != f'{request.url.scheme}://{request.headers.get("host")}':
                return JSONResponse({'detail':'Request origin does not match this application.'},status_code=403)
        if path not in public:
            from starlette.concurrency import run_in_threadpool
            token_value=request.cookies.get(accounts.COOKIE)
            if path.startswith('/api/mcp') and request.headers.get('authorization','').startswith('Bearer '):token_value=request.headers['authorization'][7:]
            user=await run_in_threadpool(accounts.store.user_for_token,token_value)
            if not user:
                return JSONResponse({'detail':'Sign in to uSOPp.ai to continue.'},status_code=401)
            request.state.user=user
    token=current_user.set(getattr(request.state,'user',None))
    try:
        if getattr(request.state,'user',None):
            from backend.core.access import authorize_request
            from fastapi import HTTPException
            try: await authorize_request(request)
            except HTTPException as error:
                return JSONResponse({'detail':error.detail},status_code=error.status_code)
        return await call_next(request)
    finally:
        current_user.reset(token)

for feature_router in (system.router, validation.router, metadata.router, knowledge.router, compare_export_jobs.router, comparison.router, rules.router, assist.router, validation_source.router, nami.router, auth.router, report_exports.router, history.router,data_models.router):
    app.include_router(feature_router)

# Reports and workbook sessions remain available until explicitly cleared.

DIST=RESOURCE_ROOT/'dist'
app.include_router(assist_settings.router)
app.include_router(user_settings.router)
app.include_router(br_help.router)
app.include_router(assist_training.router)
app.include_router(assist_attachments.router)
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
            raise HTTPException(503, 'PLC Data interface is missing. Build the frontend and restart uSOPp.ai.')
        if path.startswith('api/'):
            from fastapi import HTTPException
            raise HTTPException(404,'API endpoint not found')
        target=(DIST/path).resolve()
        if DIST.resolve() not in target.parents: target=DIST/'index.html'
        resolved = target if target.exists() and target.is_file() else DIST/'index.html'
        return FileResponse(resolved, headers={'Cache-Control':'no-store'} if resolved.suffix == '.html' else None)
