"""Bounded image snapshots; never accepts remote URLs or filesystem paths."""
import base64,hashlib,io
from PIL import Image,ImageOps
from fastapi import HTTPException
from . import store

def image_bytes(path):
    try:
        with Image.open(path) as original:
            if original.format not in {'PNG','JPEG','WEBP'} or original.width*original.height>24000000:raise ValueError()
            image=ImageOps.exif_transpose(original).convert('RGBA');image.thumbnail((2600,2600))
            output=io.BytesIO();image.save(output,format='PNG',optimize=True);raw=output.getvalue()
            if len(raw)>3*1024*1024:
                image.thumbnail((1800,1800));output=io.BytesIO();image.save(output,format='PNG',optimize=True);raw=output.getvalue()
            if len(raw)>4*1024*1024:raise ValueError()
            return raw
    except Exception:raise HTTPException(400,'This image cannot be safely embedded. Use a PNG/JPEG/WebP up to 10 MiB and 24 megapixels.') from None

def references(layout):
    ids=set()
    for b in layout['blocks']:
        if b['type'] in {'image','signature','approval'} and b['data'].get('file_id'):ids.add(b['data']['file_id'])
        if b['type']=='section_break':
            for part in ('header','footer'):
                for v in b['data'][part]['variants'].values():ids.update(i['file_id'] for i in v['items'] if i['type']=='logo' and i.get('source')=='file' and i.get('file_id'))
    for part in ('header','footer'):
        for v in layout[part]['variants'].values():ids.update(i['file_id'] for i in v['items'] if i['type']=='logo' and i.get('source')=='file' and i.get('file_id'))
    return ids

def snapshot(pid,layout):
    from backend.core.workhub_files import file_record
    result={};total=0
    for key in sorted(references(layout)):
        row,path=file_record(key,pid)
        if row['size']>10*1024*1024:raise HTTPException(413,'Use images up to 10 MiB.')
        raw=image_bytes(path);total+=len(raw)
        if total>10*1024*1024:raise HTTPException(413,'Reduce the embedded image sizes before exporting this layout; originals are retained.')
        result[key]={'name':row['name'],'data':base64.b64encode(raw).decode(),'sha256':hashlib.sha256(raw).hexdigest()}
    return result

def restore(user,pid,layout,assets):
    """Copy explicitly shared template/snippet images into the target project."""
    import json
    from backend.core.workhub_intelligence.documents import generated_file
    result=json.loads(json.dumps(layout));mapping={}
    for key,value in assets.items():
        raw=base64.b64decode(value['data'],validate=True)
        if hashlib.sha256(raw).hexdigest()!=value['sha256']:raise HTTPException(409,'The reusable image snapshot failed integrity verification.')
        mapping[key]=generated_file(user,pid,'Studio-'+value['name'].rsplit('.',1)[0]+'.png',raw)['id']
    def replace(value):
        if isinstance(value,dict):
            for k,v in list(value.items()):
                if k=='file_id' and isinstance(v,str) and v in mapping:value[k]=mapping[v]
                else:replace(v)
        elif isinstance(value,list):
            for item in value:replace(item)
    replace(result);return result
