"""Real Chromium checks against an isolated copy of the existing application."""
import os
from pathlib import Path
import json
import socket
import sys
import threading
import tempfile
import time
import uuid
from contextlib import asynccontextmanager

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
OUT=ROOT/'.build/workhub-frd-validation';OUT.mkdir(parents=True,exist_ok=True)
SANDBOX=Path(tempfile.mkdtemp(prefix='ufrd-'))
os.environ.update(USOPP_DATA_ROOT=str(SANDBOX),USOPP_PI_WORKER_MODE='external',USOPP_PI_CHILD='1')


def main():
    import uvicorn
    from backend.app import app
    if '--dist' in sys.argv:
        import importlib
        from fastapi.staticfiles import StaticFiles
        module=importlib.import_module('backend.app');module.DIST=Path(sys.argv[sys.argv.index('--dist')+1]).resolve()
        for route in app.routes:
            if getattr(route,'name','')=='assets':route.app=StaticFiles(directory=module.DIST/'assets')
    from backend.core import accounts
    from backend.core.workhub_quality import store
    from playwright.sync_api import sync_playwright
    if '--saved-state' in sys.argv:
        import sqlite3
        target=SANDBOX/'.usopp_workhub/projects.sqlite3';target.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(ROOT/'.usopp_workhub/projects.sqlite3') as source,sqlite3.connect(target) as destination:source.backup(destination)
    store.initialize()
    user=accounts.store.register('browser_fixture','Browser-fixture-2026!','Test Engineer','Fictional Training','admin')
    if '--saved-state' in sys.argv:
        from backend.core import persistent_store
        persistent_store.initialize()
        with sqlite3.connect(ROOT/'application.sqlite3') as source,persistent_store.db() as destination:
            for row in source.execute('SELECT key,value,revision,updated_at FROM user_settings WHERE user_id=1'):
                destination.execute('INSERT OR REPLACE INTO user_settings VALUES(?,?,?,?,?)',(user['id'],*row))
        with store.hub.db(True) as db:db.execute('UPDATE wh_dashboards SET owner_id=? WHERE owner_id=1',(user['id'],))
    project=store.hub.create(user,{'title':'Fictional browser test project'})
    @asynccontextmanager
    async def lifespan(app):yield
    app.router.lifespan_context=lifespan
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.05)
    events=[];checks=[]
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});page.set_default_timeout(10000)
            page.on('pageerror',lambda error:events.append({'message':str(error),'stack':error.stack}))
            try:
                page.goto(f'http://127.0.0.1:{port}/',wait_until='networkidle')
                page.get_by_label('Username',exact=True).fill(user['username']);page.get_by_label('Password',exact=True).fill('Browser-fixture-2026!')
                page.locator('form').get_by_role('button',name='Sign in',exact=True).click();page.wait_for_timeout(1800)
                body=page.locator('body').inner_text();checks.append({'step':'Admin sign in and WorkHub render','passed':'Project portfolio' in body or 'My Dashboard' in body,'body':body[:1500]})
                page.screenshot(path=str(OUT/'admin-browser.png'),full_page=True)
                if not events:
                    for title in ['FRD','Test Report','Correction Notes','FAT','Quality Approval','Project Closure']:
                        page.get_by_role('button',name='Create FRD / Reports',exact=True).click()
                        dialog=page.get_by_role('dialog',name='Create FRD / Reports',exact=True)
                        dialog.get_by_label('Project for documents').select_option(project['id'])
                        dialog.get_by_role('button',name=title,exact=False).filter(has=page.locator('strong',has_text=title)).click()
                        page.locator('.qc-document-heading h3').filter(has_text=title).wait_for(state='visible')
                        checks.append({'step':'Document shortcut opens '+title,'passed':page.locator('.qc-document-heading h3').inner_text()==title})
                        page.get_by_role('button',name='All projects',exact=True).click()
                    page.get_by_role('button',name='Help · FRD Sample',exact=True).click()
                    sample=page.locator('#help-frd-sample')
                    sample.get_by_role('button',name='View Sample',exact=True).click()
                    sample.get_by_role('button',name='FRD',exact=True).click()
                    sample.get_by_label('Purpose',exact=True).wait_for()
                    checks.append({'step':'Built-in fictional sample is read-only','passed':sample.get_by_label('Purpose',exact=True).is_disabled()})
                    sample.get_by_role('button',name='Try Sample',exact=True).click()
                    page.wait_for_timeout(500)
                    purpose=sample.get_by_label('Purpose',exact=True);purpose.fill('Private browser practice purpose; fictional signals only.')
                    sample.get_by_role('button',name='Save practice',exact=True).click()
                    sample.get_by_text('Practice revision 2 saved.',exact=True).wait_for()
                    key=sample.get_by_label('My saved practice copies').input_value()
                    sample.get_by_role('button',name='View Sample',exact=True).click()
                    sample.get_by_label('My saved practice copies').select_option(key)
                    page.wait_for_timeout(400)
                    checks.append({'step':'Private practice edits save and reopen','passed':purpose.input_value()=='Private browser practice purpose; fictional signals only.'})
                    sample.get_by_role('button',name='Flowchart',exact=True).click()
                    page.wait_for_timeout(700)
                    checks.append({'step':'Embedded sample flowchart renders','passed':sample.locator('.react-flow__node').count()==5})
                    sample.screenshot(path=str(OUT/'sample-flowchart-browser.png'))
                    pdf=page.request.get(f'http://127.0.0.1:{port}/api/workhub/training/frd/copies/{key}/pdf',timeout=60000)
                    checks.append({'step':'Private practice PDF renders through authenticated API','passed':pdf.status==200 and pdf.body().startswith(b'%PDF')})
                    page.get_by_role('button',name='Settings',exact=True).click();page.wait_for_timeout(900)
                    body=page.locator('body').inner_text();checks.append({'step':'Settings branding and user management render','passed':'Organization Branding' in body and 'Users & Roles' in body,'body':body[:2000]})
                    page.screenshot(path=str(OUT/'settings-browser.png'),full_page=True)
            except Exception as error:
                page.screenshot(path=str(OUT/'browser-failure.png'),full_page=True)
                (OUT/'browser-failure.html').write_text(page.content(),encoding='utf-8')
                checks.append({'step':'Browser interaction','passed':False,'error':str(error),'body':page.locator('body').inner_text()[-7000:]})
            finally:
                checks.append({'step':'No uncaught JavaScript errors','passed':not events,'errors':events})
                (OUT/'browser-results.json').write_text(json.dumps(checks,indent=2,ensure_ascii=False),encoding='utf-8')
                print(json.dumps(checks,indent=2,ensure_ascii=False));browser.close()
    finally:server.should_exit=True;thread.join(10)
    return 0 if all(row['passed'] for row in checks) else 1


if __name__=='__main__':raise SystemExit(main())
