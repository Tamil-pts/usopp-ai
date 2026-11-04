"""Editable document facts are revision content; approval identities remain audited."""
from datetime import date
from fastapi import HTTPException
from .workhub import text

FIELDS = ('project_name','project_number','customer','customer_project_reference',
          'project_type','base_reference','developed_reference','document_date')


def links(db,pid):
    row=db.execute('SELECT linked_project_id,linked_document_id,linked_revision_id FROM wh_document_spaces WHERE id=?',(pid,)).fetchone()
    return {'project_id':row[0],'frd_document_id':row[1],'frd_revision_id':row[2]} if row else None


def clean(value):
    if not isinstance(value,dict) or any(k not in FIELDS for k in value):
        raise HTTPException(400,'Use the supported document information fields.')
    result={k:text(v or '',500) for k,v in value.items()}
    if result.get('document_date'):
        try:date.fromisoformat(result['document_date'])
        except ValueError:raise HTTPException(400,'Choose a valid document date.')
    return result


def snapshot(db,p):
    import json
    linked=p.get('linked_project_id') if p.get('is_document_space') else p['id']
    source=dict(db.execute('SELECT * FROM items WHERE id=? AND type=\'project\'',(linked,)).fetchone() or {}) if linked else {}
    raw=db.execute('SELECT context FROM qc_projects WHERE project_id=?',(linked or p['id'],)).fetchone()
    context=json.loads(raw[0]) if raw else {}
    return {**{k:context.get(k,'') for k in FIELDS},'customer':context.get('customer') or source.get('customer',''),'project_name':source.get('title',''),
            'project_number':source.get('project_number',''),'project_type':source.get('kind',''),
            'document_date':date.today().isoformat()}
