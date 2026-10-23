"""Verify the compiled interface belongs to this application release."""
import hashlib
import json
from pathlib import Path


def frontend_build_info(distribution, expected_version):
    root=Path(distribution).resolve()
    result={'version':None,'matches':False,'integrity':False,'sourceCommit':None,'error':None}
    try:
        manifest=root/'build-info.json'
        if manifest.stat().st_size>16384:raise ValueError('Interface build information is too large.')
        data=json.loads(manifest.read_text(encoding='utf-8'))
        result.update(version=data['version'],sourceCommit=data.get('sourceCommit'))
        entry=(root/data['entryFile']).resolve()
        if not entry.is_relative_to(root/'assets') or entry.suffix!='.js':raise ValueError('Interface entry must be a compiled asset inside dist/assets.')
        with entry.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        if digest!=data.get('entrySha256'):raise ValueError('Compiled interface checksum does not match its build information.')
        result['integrity']=True
        if data['version']!=expected_version:raise ValueError(f'Compiled UI {data["version"]} does not match API {expected_version}. Rebuild the interface before packaging.')
        result['matches']=True
    except (OSError,ValueError,KeyError,TypeError) as error:result['error']=str(error)
    return result


def require_frontend_build(distribution,expected_version):
    result=frontend_build_info(distribution,expected_version)
    if not result['matches']:raise ValueError('Matching compiled frontend required: '+str(result['error']))
    return result
