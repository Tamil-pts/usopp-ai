"""Versioned organization, customer and PDF layout records in the WorkHub database.

Administrators configure structured layouts; executable template source is shipped
with the application. Assets and historical versions are append only.
"""
import base64
import hashlib
import io
import json
import re
import warnings
from copy import deepcopy
from fastapi import HTTPException
from . import store, configuration
from .store import hub, identity, timestamp, text

KINDS = {**store.STAGES, 'test':'Validation Test Report', 'fat':'Factory Acceptance Test Report', 'frd': 'Functional Requirements Document', 'mom': 'Minutes of Meeting'}
BLOCKS = ['summary', 'purpose', 'scope', 'requirements', 'flowchart', 'changes',
          'cases', 'sections', 'details', 'sources', 'signatures']
ORG = {'name': 'PTPL', 'address': '', 'department': 'ES', 'team': 'PLC',
       'company_code': 'PTPL', 'department_code': 'ES', 'team_code': 'PLC',
       'header': 'ENGINEERING SERVICES / PLC', 'footer': 'Controlled engineering document',
       'header_color': '#112f43', 'accent': '#008c95', 'logo_id': None, 'active': True}
LAYOUT = {'name': 'Engineering document', 'document_kind': 'frd', 'title': '',
          'header_color': '', 'show_company_logo': True, 'show_customer_logo': True,
          'show_metadata': True, 'show_page_numbers': True, 'show_signatures': True,
          'paper': 'A4', 'orientation': 'portrait', 'table_style': 'striped',
          'sections': BLOCKS, 'signature_labels': ['Prepared by', 'Reviewed by', 'Approved by'],
          'header': '', 'footer': '', 'active': True}


def schema(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS wh_brand_records(kind TEXT NOT NULL,id TEXT NOT NULL,version INTEGER NOT NULL,
      data TEXT NOT NULL,created_by INTEGER NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(kind,id,version));
    CREATE TABLE IF NOT EXISTS wh_brand_defaults(id INTEGER PRIMARY KEY CHECK(id=1),organization_id TEXT);
    CREATE TABLE IF NOT EXISTS wh_brand_assets(id TEXT PRIMARY KEY,owner_kind TEXT NOT NULL,owner_id TEXT NOT NULL,
      version INTEGER NOT NULL,name TEXT NOT NULL,mime TEXT NOT NULL,sha256 TEXT NOT NULL,data BLOB NOT NULL,
      created_by INTEGER NOT NULL,created_at TEXT NOT NULL,UNIQUE(owner_kind,owner_id,version));
    CREATE TABLE IF NOT EXISTS wh_pdf_snapshots(revision_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,
      source_hash TEXT NOT NULL,context TEXT NOT NULL,context_hash TEXT NOT NULL,pdf BLOB,pdf_hash TEXT,
      renderer TEXT,created_at TEXT NOT NULL,rendered_at TEXT);
    CREATE INDEX IF NOT EXISTS wh_pdf_project ON wh_pdf_snapshots(project_id,revision_id);
    ''')
    if 'template_ids' not in {r[1] for r in db.execute('PRAGMA table_info(wh_brand_defaults)')}:
        db.execute("ALTER TABLE wh_brand_defaults ADD COLUMN template_ids TEXT NOT NULL DEFAULT '{}'")


def record(db, kind, key, version=None):
    if kind not in {'organization','customer','template'} or not isinstance(key,str) or not re.fullmatch('[0-9a-f]{32}',key):
        raise HTTPException(400,'Select an existing saved profile or template.')
    if version is not None and (type(version) is not int or version<1):raise HTTPException(400,'Select a valid version.')
    sql = 'SELECT * FROM wh_brand_records WHERE kind=? AND id=?'
    args = [kind, key]
    if version is not None: sql += ' AND version=?'; args.append(version)
    row = db.execute(sql+' ORDER BY version DESC LIMIT 1', args).fetchone()
    if not row: raise HTTPException(404, 'This saved profile or template was not found.')
    return {**dict(row), 'data': json.loads(row['data'])}


def records(db, kind):
    return [{**dict(r), 'data': json.loads(r['data'])} for r in db.execute('''SELECT r.* FROM wh_brand_records r
      WHERE kind=? AND version=(SELECT max(version) FROM wh_brand_records v WHERE v.kind=r.kind AND v.id=r.id)
      ORDER BY json_extract(data,'$.name'),id LIMIT 500''', (kind,))]


def color(value, empty=False):
    if empty and value == '': return value
    if not isinstance(value, str) or not re.fullmatch('#[0-9a-fA-F]{6}', value):
        raise HTTPException(400, 'Choose a six digit hex color.')
    return value


def validate(db, kind, value, key):
    if not isinstance(value, dict): raise HTTPException(400, 'Provide structured profile settings.')
    if kind == 'organization':
        result = {k: text(value.get(k, v), 1000 if k in {'address','header','footer'} else 180)
                  for k,v in ORG.items() if isinstance(v,str)}
        result['name'] = text(result['name'],180,True)
        for k in ['company_code','department_code','team_code']:
            if not re.fullmatch('[A-Za-z0-9_]{1,24}',result[k]): raise HTTPException(400,'Use letters, numbers or underscores for document codes.')
        for k in ['header_color','accent']: color(result[k])
    elif kind == 'customer':
        result = {k:text(value.get(k,''),1000 if k in {'address','notes'} else 180)
                  for k in ['name','address','contact','email','phone','reference','notes']}
        result['name'] = text(result['name'],180,True)
        if result['email']:
            from backend.core.accounts import email_address
            try:result['email'] = email_address(result['email'])
            except ValueError as error:raise HTTPException(400,str(error)) from None
    elif kind == 'template':
        if any(k in value for k in ['html','source','javascript','css','jinja']):
            raise HTTPException(400,'Configure the supported layout fields; executable template content cannot be uploaded.')
        result = deepcopy(LAYOUT)
        for k in ['name','title','header','footer']: result[k]=text(value.get(k,result[k]),1000 if k in {'header','footer'} else 180)
        result['name']=text(result['name'],180,True)
        if value.get('document_kind') not in KINDS: raise HTTPException(400,'Choose a supported document type.')
        result['document_kind']=value['document_kind']; result['header_color']=color(value.get('header_color',''),True)
        for k in ['show_company_logo','show_customer_logo','show_metadata','show_page_numbers','show_signatures']:
            if type(value.get(k,result[k])) is not bool: raise HTTPException(400,'Use true or false for layout options.')
            result[k]=value.get(k,result[k])
        for k,allowed in [('paper',{'A4','Letter'}),('orientation',{'portrait','landscape'}),('table_style',{'striped','grid','minimal'})]:
            result[k]=value.get(k,result[k])
            if result[k] not in allowed: raise HTTPException(400,'Choose a supported '+k+'.')
        sections=value.get('sections',BLOCKS)
        # Content cannot be hidden by accident in a controlled engineering PDF.
        if not isinstance(sections,list) or len(sections)!=len(BLOCKS) or any(not isinstance(k,str) for k in sections) or set(sections)!=set(BLOCKS):
            raise HTTPException(400,'Arrange each document section exactly once.')
        result['sections']=sections
        labels=value.get('signature_labels',LAYOUT['signature_labels'])
        if not isinstance(labels,list) or len(labels)!=3: raise HTTPException(400,'Configure three signature block labels.')
        result['signature_labels']=[text(v,80,True) for v in labels]
    else: raise HTTPException(400,'Choose organizations, customers or templates.')
    if kind != 'template':
        logo=value.get('logo_id') or None
        if logo and not db.execute('SELECT 1 FROM wh_brand_assets WHERE id=? AND owner_kind=? AND owner_id=?',(logo,kind,key)).fetchone():
            raise HTTPException(400,'Select a logo uploaded for this profile.')
        result['logo_id']=logo
    if type(value.get('active',True)) is not bool: raise HTTPException(400,'Choose whether this profile is active.')
    result['active']=value.get('active',True)
    return result


def save(user, kind, payload, key=None):
    configuration.admin(user); store.initialize(); key=key or identity()
    if kind not in {'organization','customer','template'} or not isinstance(key,str) or not re.fullmatch('[0-9a-f]{32}',key):raise HTTPException(400,'Select a supported profile or template.')
    with hub.db(True) as db:
        current=db.execute('SELECT max(version) FROM wh_brand_records WHERE kind=? AND id=?',(kind,key)).fetchone()[0] or 0
        if type(payload.get('version',0)) is not int or payload.get('version',0)!=current: raise HTTPException(409,'These settings changed. Reload before saving.')
        value=validate(db,kind,payload.get('data'),key)
        if current and kind=='template' and record(db,kind,key)['data']['document_kind']!=value['document_kind']:
            raise HTTPException(409,'Create a new template for a different document type. Existing project links retain their document type.')
        if current==0 and db.execute('SELECT count(DISTINCT id) FROM wh_brand_records WHERE kind=?',(kind,)).fetchone()[0]>=500:
            raise HTTPException(409,'Archive or reuse an existing profile; the profile limit is 500.')
        version=current+1
        db.execute('INSERT INTO wh_brand_records VALUES(?,?,?,?,?,?)',(kind,key,version,store.bounded(value),user['id'],timestamp()))
        defaults=db.execute('SELECT * FROM wh_brand_defaults WHERE id=1').fetchone()
        if kind=='organization' and (payload.get('make_default') is True or not defaults or not defaults['organization_id']):
            if not value['active']: raise HTTPException(400,'The default organization must be active.')
            db.execute('INSERT INTO wh_brand_defaults(id,organization_id) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET organization_id=excluded.organization_id',(key,))
        elif kind=='organization' and not value['active'] and db.execute('SELECT 1 FROM wh_brand_defaults WHERE organization_id=?',(key,)).fetchone():
            raise HTTPException(409,'Choose another default organization before archiving this profile.')
        if kind=='template':
            default_templates=json.loads(defaults['template_ids']) if defaults else {}
            doc_kind=value['document_kind']
            if payload.get('make_default') is True or doc_kind not in default_templates:
                if not value['active']:raise HTTPException(400,'The shared default template must be active.')
                default_templates[doc_kind]=key
                db.execute('INSERT INTO wh_brand_defaults(id,template_ids) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET template_ids=excluded.template_ids',(store.bounded(default_templates),))
            elif not value['active'] and default_templates.get(doc_kind)==key:
                raise HTTPException(409,'Choose another shared default before archiving this template.')
        store.audit(db,user,None,'branding_'+kind+'_saved',{'id':key,'version':version})
        return record(db,kind,key)


def upload(user, kind, key, raw, name):
    configuration.admin(user);store.initialize()
    if kind not in {'organization','customer'}: raise HTTPException(400,'Upload a company or customer logo.')
    if not raw or len(raw)>2*1024*1024: raise HTTPException(413,'Choose a PNG, JPEG or WebP logo up to 2 MB.')
    from PIL import Image,ImageOps,UnidentifiedImageError
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in {'PNG','JPEG','WEBP'} or image.width*image.height>4000000 or getattr(image,'n_frames',1)!=1:
                    raise ValueError('Unsupported image')
                image=ImageOps.exif_transpose(image).convert('RGBA');image.thumbnail((1600,1000))
                output=io.BytesIO();image.save(output,format='PNG');data=output.getvalue()
                if len(data)>2*1024*1024: raise ValueError('Image too large after decoding')
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise HTTPException(400,'Choose a valid still PNG, JPEG or WebP logo up to 4 megapixels.') from None
    with hub.db(True) as db:
        record(db,kind,key)
        version=db.execute('SELECT coalesce(max(version),0)+1 FROM wh_brand_assets WHERE owner_kind=? AND owner_id=?',(kind,key)).fetchone()[0]
        asset=identity();sha=hashlib.sha256(data).hexdigest()
        db.execute('INSERT INTO wh_brand_assets VALUES(?,?,?,?,?,?,?,?,?,?)',(asset,kind,key,version,text(name or 'logo',180),'image/png',sha,data,user['id'],timestamp()))
        store.audit(db,user,None,'branding_logo_uploaded',{'asset_id':asset,'profile_id':key,'version':version,'sha256':sha})
        return {'id':asset,'version':version,'sha256':sha}


def asset(db, key):
    if not key:return None
    if not isinstance(key,str) or not re.fullmatch('[0-9a-f]{32}',key):raise HTTPException(400,'Select a saved logo version.')
    row=db.execute('SELECT * FROM wh_brand_assets WHERE id=?',(key,)).fetchone()
    if not row:raise HTTPException(409,'The versioned logo is unavailable; restore it before exporting.')
    if hashlib.sha256(row['data']).hexdigest()!=row['sha256']:raise HTTPException(409,'Logo integrity verification failed.')
    return dict(row)


def organization(db, context):
    key=context.get('organization_id')
    if not key:
        row=db.execute('SELECT organization_id FROM wh_brand_defaults WHERE id=1').fetchone();key=row[0] if row else None
    if key:return record(db,'organization',key)
    legacy=configuration.current(db)['configuration'];brand=legacy['branding']
    return {'id':'builtin','version':0,'data':{**ORG,'name':brand.get('name','PTPL'),'header':brand.get('subtitle',''),
      'accent':brand.get('accent',ORG['accent']),'company_code':legacy['company'],'department_code':legacy['department'],
      'team_code':legacy['team'],'legacy_logo_file_id':brand.get('logo_file_id')}}


def template(db, kind, context):
    key=(context.get('template_ids') or {}).get(kind)
    if not key:
        defaults=db.execute('SELECT template_ids FROM wh_brand_defaults WHERE id=1').fetchone()
        key=json.loads(defaults[0]).get(kind) if defaults else None
    if key:return record(db,'template',key)
    # First saved active layout of this type is the default; a project can override it.
    rows=[r for r in records(db,'template') if r['data']['document_kind']==kind and r['data']['active']]
    if rows:return rows[0]
    return {'id':'builtin-'+kind,'version':1,'data':{**LAYOUT,'document_kind':kind,'name':KINDS.get(kind,'Engineering Document')}}


def choices(db):
    return {k:[{'id':r['id'],'version':r['version'],'name':r['data']['name'],
                **({'document_kind':r['data']['document_kind']} if k=='template' else {})}
               for r in records(db,k) if r['data']['active']] for k in ['organization','customer','template']}


def link_context(db, values, payload):
    for field,kind in [('organization_id','organization'),('customer_id','customer')]:
        key=payload.get(field,values.get(field)) or None
        if key:
            selected=record(db,kind,key)
            if not selected['data']['active'] and key!=values.get(field):raise HTTPException(400,'Select an active profile.')
            if kind=='customer':values['customer']=selected['data']['name']
        values[field]=key
    mapping=payload.get('template_ids',values.get('template_ids',{}))
    if not isinstance(mapping,dict) or any(k not in KINDS for k in mapping):raise HTTPException(400,'Choose supported project templates.')
    for kind,key in mapping.items():
        if key and record(db,'template',key)['data']['document_kind']!=kind:raise HTTPException(400,'The template belongs to another document type.')
    values['template_ids']={k:v for k,v in mapping.items() if v}
    return values


def numbering(db,p,setting):
    """Reuse the existing atomic allocator and scopes with profile prefix tokens."""
    result=deepcopy(setting);org=organization(db,store.policy_row(db,p)['context'])
    if org['id']!='builtin':
        for target,source in [('company','company_code'),('department','department_code'),('team','team_code')]:
            result['configuration'][target]=org['data'][source]
    return result
