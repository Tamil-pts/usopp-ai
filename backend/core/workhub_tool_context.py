"""Explicit project attribution, captured once when an engineering run starts."""
from contextvars import ContextVar
from fastapi import HTTPException
from .workhub import store as hub

selection=ContextVar('workhub_test_selection',default=None)


def validate(user,key):
    if key=='-':return {'capture':False}
    if not user or user.get('isDemo'):raise HTTPException(403,'Use a personal assigned account to record project activity.')
    if not isinstance(key,str) or len(key)>80:raise HTTPException(400,'Choose an assigned WorkHub project.')
    with hub.db() as db:
        p=hub.contribute(db,key,user)
        if p.get('is_document_space') or p.get('assignment_state')=='unassigned' or p.get('exception_status') in {'on_hold','cancelled'} or p['stage']=='released':raise HTTPException(409,'Choose an active assigned project. This project is completed, unassigned or on hold.')
        return {'capture':True,'project_id':p['id'],'project_number':p.get('project_number',''),'project_title':p['title']}


def options(user):
    hub.actor(user);values=[]
    with hub.db() as db:
        for r in db.execute("SELECT * FROM items WHERE type='project' AND stage!='released' ORDER BY project_number,title"):
            p=dict(r)
            try:v=validate(user,p['id'])
            except HTTPException as e:
                if e.status_code in {403,409}:continue
                raise
            values.append({**v,'stage':p['stage']})
    return {'user_id':user['id'],'projects':values,'note':'Selected project runs update recorded activity. Approved assessments determine Competency Index and Performance Index.'}


def capture(data,record=None):
    context=selection.get()
    if not context:return
    # Opt-outs inside automatic polling remain opt-outs even when a project is
    # selected. Later requests may never reassign an existing run.
    if data.get('workhubCapture') is False or context['capture'] is False:
        data['workhubCapture']=False
        if record is not None:record['workhubCapture']=False
        return
    values={'workhubCapture':True,'workhubProjectId':context['project_id'],'workhubProjectNumber':context['project_number'],'workhubProjectTitle':context['project_title']}
    data.update(values)
    if record is not None:record.update(values)
