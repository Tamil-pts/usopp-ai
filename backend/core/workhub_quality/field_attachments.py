"""Revision-owned attachment links for individual engineering fields."""
import re
from fastapi import HTTPException

ROOT_FIELDS=('summary','purpose','background','expected_outcome','scope','acceptance_summary','conclusion','na_reason','meeting_subject','meeting_date','meeting_mode','location','agenda','follow_up')
ROW_FIELDS={
 'requirement':('requirements',('title','description','trigger','expected_behavior','subsystem','acceptance_criteria')),
 'case':('cases',('objective','procedure','expected_result','acceptance_criteria','actual','observations')),
 'change':('changes',('summary','existing_behavior','expected_behavior','plc_references','impact','before_evidence','after_evidence','verification')),
 'section':('sections',('text',)),
}

def normalize(db,pid,original,content):
    from .documents import file_ids
    allowed=set(ROOT_FIELDS)
    for prefix,(key,fields) in ROW_FIELDS.items():
        allowed.update(prefix+'/'+r['id']+'/'+field for r in content.get(key,[]) for field in fields)
    if original.get('studio'):
        from backend.core.workhub_studio import schema,bindings
        layout=schema.normalize(original['studio'])
        for block in layout['blocks']:
            base='element/'+block['id'];allowed.add(base)
            if block['type'] in {'table','checklist'}:allowed.update(base+'/cell/'+cell['id'] for cell in block['data']['cells'])
            elif block['type']=='metadata':allowed.update(base+'/cell/meta-'+str(y)+'-'+str(x) for y in range(7) for x in range(2))
            elif block['type']=='native_table':
                table=bindings.native_table(content,block['data']['binding'])
                allowed.update(base+'/cell/'+row['id']+':'+column['field'] for row in table['rows'] for column in table['columns'])
    values=original.get('field_files',{})
    if not isinstance(values,dict) or len(values)>3000:raise HTTPException(400,'Use a bounded map of field attachments.')
    result={}
    for path,ids in values.items():
        if not isinstance(path,str) or path not in allowed:raise HTTPException(400,'An attachment refers to a field that is no longer in this document. Remove that link before saving.')
        selected=file_ids(db,pid,ids)
        if selected:result[path]=selected
    content['field_files']=result
    for case in content.get('cases',[]):
        linked={f:result['case/'+case['id']+'/'+f] for f in ROW_FIELDS['case'][1][:4] if 'case/'+case['id']+'/'+f in result}
        if linked:case['field_files']=linked
    # Existing packaging and customer authorization continue to see every file.
    content['file_ids']=file_ids(db,pid,list(dict.fromkeys(content.get('file_ids',[])+[f for ids in result.values() for f in ids])))
    return content

def section_id(value,index):
    key=value or 'SECTION-'+str(index+1).zfill(3)
    if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',key):raise HTTPException(400,'Use a stable section identifier.')
    return key
