from io import BytesIO
import json
from pathlib import Path

import pytest
from pypdf import PdfReader,PdfWriter
from pypdf.annotations import Text
from pypdf.generic import DictionaryObject,NameObject,TextStringObject,ArrayObject,FloatObject

from test_edesign import api,upload,mark,pdf_bytes
from python_engine.edesign_pdf import ATTACHMENT,read_review


def external_edit(data,body='Offline PDF reviewer: change pin 2',resolve=False,reply=False):
    # Independent PDF editing path: only standard PDF dictionaries are changed.
    reader=PdfReader(BytesIO(data));writer=PdfWriter();writer.clone_document_from_reader(reader)
    annotation=next(a.get_object() for a in writer.pages[0]['/Annots'] if str(a.get_object().get('/NM','')).startswith('edesign:'))
    annotation[NameObject('/Contents')]=TextStringObject(body)
    annotation[NameObject('/T')]=TextStringObject('External reviewer')
    if resolve:
        state=Text(rect=(20,20,35,35),text='Completed')
        state.update({NameObject('/IRT'):annotation.indirect_reference,NameObject('/RT'):NameObject('/R'),
                      NameObject('/State'):TextStringObject('Completed'),NameObject('/StateModel'):TextStringObject('Review')})
        writer.add_annotation(0,state)
    if reply:
        response=Text(rect=(20,20,35,35),text='Please check wire clearance too.')
        response.update({NameObject('/IRT'):annotation.indirect_reference,NameObject('/RT'):NameObject('/R'),NameObject('/T'):TextStringObject('Site reviewer')})
        writer.add_annotation(0,response)
    output=BytesIO();writer.write(output);return output.getvalue()


def history(client,prefix,saved):return client.get(prefix+'/marks/'+saved['id']+'/history').json()['revisions']


def test_revisions_resolution_restoration_saved_undo_redo(api):
    client,_=api;prefix='/api/e-design/'+upload(client)['id']
    saved=client.post(prefix+'/marks',json=mark()).json()
    client.put(prefix+'/marks/'+saved['id'],json=mark(version=1,body='Second revision'))
    client.put(prefix+'/marks/'+saved['id'],json=mark(version=2,body='Second revision',status='resolved'))
    revisions=history(client,prefix,saved)
    assert [r['version'] for r in revisions]==[3,2,1]
    assert [r['action'] for r in revisions]==['resolve','update','create']
    assert revisions[-1]['snapshot']['body']==mark()['body']
    restored=client.post(prefix+'/marks/'+saved['id']+'/restore',json={'revision':1,'version':3}).json()
    assert restored['marks'][0]['version']==4 and restored['marks'][0]['body']==mark()['body']
    undo=client.post(prefix+'/history/undo',json={'commandId':restored['commands']['undo']['id']}).json()
    assert undo['marks'][0]['version']==5 and undo['marks'][0]['status']=='resolved'
    undo=client.post(prefix+'/history/undo',json={'commandId':undo['commands']['undo']['id']}).json()
    assert undo['marks'][0]['version']==6 and undo['marks'][0]['status']=='open'
    redo=client.post(prefix+'/history/redo',json={'commandId':undo['commands']['redo']['id']}).json()
    assert redo['marks'][0]['version']==7 and redo['marks'][0]['status']=='resolved'
    assert len(history(client,prefix,saved))==7


def test_delete_undo_redo_branch_and_other_reviewers_conflict(api):
    client,_=api;prefix='/api/e-design/'+upload(client)['id']
    saved=client.post(prefix+'/marks',json=mark()).json()
    deleted=client.delete(prefix+'/marks/'+saved['id']+'?version=1').json()
    restored=client.post(prefix+'/history/undo',json={'commandId':deleted['commands']['undo']['id']}).json()
    assert restored['marks'][0]['id']==saved['id'] and restored['marks'][0]['version']==3
    client.put(prefix+'/marks/'+saved['id'],json=mark(version=3,body='New branch'))
    assert client.get(prefix).json()['commands']['redo'] is None
    client.post(prefix+'/share',json={'userId':2,'access':'review'})
    client.put(prefix+'/marks/'+saved['id'],headers={'x-user':'2'},json=mark(version=4,body='Another reviewer changed this'))
    command=client.get(prefix).json()['commands']['undo']['id']
    assert client.post(prefix+'/history/undo',json={'commandId':command}).status_code==409
    assert client.get(prefix).json()['marks'][0]['body']=='Another reviewer changed this'
    assert client.post(prefix+'/history/undo',headers={'x-user':'2'},json={'commandId':command}).status_code==409


def test_native_annotations_and_embedded_revision_privacy(api,tmp_path):
    client,_=api;prefix='/api/e-design/'+upload(client)['id']
    saved=client.post(prefix+'/marks',json=mark()).json()
    client.put(prefix+'/marks/'+saved['id'],json=mark(version=1,body='PDF revision two'))
    exported=client.get(prefix+'/export/pdf').content
    reader=PdfReader(BytesIO(exported));annotation=next(a.get_object() for a in reader.pages[0]['/Annots'] if str(a.get_object().get('/NM','')).startswith('edesign:'))
    assert annotation['/Contents']=='PDF revision two' and annotation['/F']==4
    assert annotation['/T']=='Engineer 1' and '/AP' in annotation and '/BS' in annotation
    assert not int(annotation['/F'])&(64|128|512)  # no read-only/locked flags
    assert any(a.get_object().get('/IRT') for a in reader.pages[0]['/Annots'])
    envelope=json.loads(reader.attachments[ATTACHMENT][0]);encoded=json.dumps(envelope)
    assert len(envelope['marks'][0]['history'])==2
    assert not any(key in encoded for key in ['author_id','actor_id','ownerId','members','token'])
    path=tmp_path/'review.pdf';path.write_bytes(exported);parsed=read_review(path)
    assert parsed['marks'][0]['id']==saved['id'] and parsed['marks'][0]['body']=='PDF revision two'
    assert parsed['marks'][0]['box']==mark()['box']


def test_offline_reader_edit_reply_resolution_and_idempotent_feedback(api):
    client,_=api;review=upload(client);prefix='/api/e-design/'+review['id']
    saved=client.post(prefix+'/marks',json=mark()).json()
    data=external_edit(client.get(prefix+'/export/pdf').content,resolve=True,reply=True)
    result=client.post(prefix+'/import',files={'file':('returned.pdf',data,'application/pdf')})
    assert result.status_code==200,result.text
    value=result.json();assert value['importSummary']['updated']==1
    assert value['marks'][0]['status']=='resolved' and 'wire clearance' in value['marks'][0]['body']
    revisions=history(client,prefix,saved)
    assert revisions[0]['action']=='import feedback' and revisions[-1]['snapshot']['body']==mark()['body']
    again=client.post(prefix+'/import',files={'file':('same.pdf',data,'application/pdf')})
    assert again.status_code==200 and again.json()['importSummary']['updated']==0
    assert client.get(prefix+'/original').content==pdf_bytes()


def test_pdf_only_handoff_to_different_account_then_back(api):
    client,_=api;review=upload(client);prefix='/api/e-design/'+review['id']
    saved=client.post(prefix+'/marks',json=mark()).json()
    client.put(prefix+'/marks/'+saved['id'],json=mark(version=1,body='Original author revision two'))
    exported=client.get(prefix+'/export/pdf').content
    # No account sharing granted. The receiver imports only the supplied file.
    assert client.get(prefix,headers={'x-user':'2'}).status_code==403
    fork=client.post('/api/e-design',headers={'x-user':'2'},files={'file':('review.pdf',exported,'application/pdf')})
    assert fork.status_code==200,fork.text
    fork=fork.json();other='/api/e-design/'+fork['id'];m=fork['marks'][0]
    assert fork['ownerId']==2 and m['id']==saved['id'] and m['body']=='Original author revision two'
    assert len(client.get(other+'/marks/'+m['id']+'/history',headers={'x-user':'2'}).json()['revisions'])>=3
    edited=client.put(other+'/marks/'+m['id'],headers={'x-user':'2'},json=mark(version=m['version'],body='Receiver feedback')).json()
    returned=client.get(other+'/export/pdf',headers={'x-user':'2'}).content
    merged=client.post(prefix+'/import',files={'file':('feedback.pdf',returned,'application/pdf')})
    assert merged.status_code==200,merged.text
    assert merged.json()['marks'][0]['body']=='Receiver feedback'
    assert client.get(other).status_code==403


def test_stale_feedback_cannot_overwrite_newer_local_comment(api):
    client,_=api;prefix='/api/e-design/'+upload(client)['id']
    saved=client.post(prefix+'/marks',json=mark()).json();exported=client.get(prefix+'/export/pdf').content
    client.put(prefix+'/marks/'+saved['id'],json=mark(version=1,body='New local revision'))
    stale=client.post(prefix+'/import',files={'file':('old.pdf',exported,'application/pdf')})
    assert stale.status_code==200 and stale.json()['marks'][0]['body']=='New local revision'
    conflict=client.post(prefix+'/import',files={'file':('conflict.pdf',external_edit(exported),'application/pdf')})
    assert conflict.status_code==409 and client.get(prefix).json()['marks'][0]['body']=='New local revision'
    other='/api/e-design/'+upload(client)['id']
    assert client.post(other+'/import',files={'file':('wrong.pdf',exported,'application/pdf')}).status_code==400


def test_standard_pdf_comment_without_envelope_and_no_implicit_deletion(api):
    client,_=api;writer=PdfWriter();writer.append(PdfReader(BytesIO(pdf_bytes())))
    writer.add_annotation(1,Text(rect=(100,150,160,200),text='External note on rotated crop'))
    output=BytesIO();writer.write(output)
    review=client.post('/api/e-design',files={'file':('external.pdf',output.getvalue(),'application/pdf')}).json()
    assert len(review['marks'])==1 and review['marks'][0]['page']==2 and review['marks'][0]['shape']=='note'
    assert all(0<=v<=1 for v in review['marks'][0]['box'])
    prefix='/api/e-design/'+review['id'];data=client.get(prefix+'/export/pdf').content
    writer=PdfWriter();writer.clone_document_from_reader(PdfReader(BytesIO(data)))
    for p in writer.pages:p[NameObject('/Annots')]=ArrayObject()
    output=BytesIO();writer.write(output)
    rejected=client.post(prefix+'/import',files={'file':('flattened.pdf',output.getvalue(),'application/pdf')})
    assert rejected.status_code==400 and len(client.get(prefix).json()['marks'])==1


def test_pre_upgrade_history_migration_preserves_existing_comments(api):
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor
    client,module=api;review=upload(client);prefix='/api/e-design/'+review['id']
    saved=client.post(prefix+'/marks',json=mark()).json()
    client.put(prefix+'/marks/'+saved['id'],json=mark(version=1,body='Existing saved comment'))
    path=module.WORK/review['id']/'review.sqlite3'
    with sqlite3.connect(path) as db:
        for table in ('revisions','commands','portable_bases','foreign_history'):db.execute('DROP TABLE '+table)
        db.execute('ALTER TABLE marks DROP COLUMN deleted')
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses=list(pool.map(lambda _:client.get(prefix),range(4)))
    assert all(r.status_code==200 for r in responses)
    migrated=responses[0].json()
    assert migrated['marks'][0]['body']=='Existing saved comment' and migrated['marks'][0]['version']==2
    versions=client.get(prefix+'/marks/'+saved['id']+'/history').json()['revisions']
    assert [v['version'] for v in versions]==[2,1]
    assert versions[-1]['snapshot']['body']==mark()['body']
    assert migrated['commands']=={'undo':None,'redo':None}


def test_feedback_does_not_silently_truncate_long_comments(api):
    client,_=api;prefix='/api/e-design/'+upload(client)['id'];saved=client.post(prefix+'/marks',json=mark()).json()
    data=external_edit(client.get(prefix+'/export/pdf').content,body='x'*6001)
    result=client.post(prefix+'/import',files={'file':('long.pdf',data,'application/pdf')})
    assert result.status_code==400 and client.get(prefix).json()['marks'][0]['body']==mark()['body']
