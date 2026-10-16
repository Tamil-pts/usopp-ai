"""Load saved expected checks, independently of the project under validation."""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re


def check_hash(check):
    return hashlib.sha256(json.dumps(check,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')).hexdigest()


@lru_cache(maxsize=8)
def _read(path,modified,size):
    if size>32*1024*1024:raise ValueError('Reference definitions exceed 32 MB.')
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schemaVersion')!=1 or not isinstance(data.get('checks'),dict):
        raise ValueError('Invalid saved reference definitions.')
    return data['checks']


def load_reference(check):
    filename=str(check.get('referenceFile') or '')
    if not re.fullmatch(r'[A-Za-z0-9_-]+(?:_v[0-9.]+)?\.json',filename):
        raise ValueError('Invalid reference definition filename.')
    identifier=str(check.get('checkId') or '')
    if not re.fullmatch(r'C-[a-f0-9]{24}',identifier):raise ValueError('Invalid reference check ID.')
    base=Path(os.getenv('USOPP_DATA_ROOT') or Path(__file__).resolve().parents[1])/'rules/references'
    path=base/filename
    if path.is_symlink() or not path.is_file():raise ValueError('Saved reference definitions are unavailable: '+filename)
    stat=path.stat();definition=_read(str(path),stat.st_mtime_ns,stat.st_size).get(identifier)
    if not isinstance(definition,dict):raise ValueError('Saved reference check was not found: '+identifier)
    expected=str(check.get('referenceHash') or '')
    if expected and check_hash(definition)!=expected:raise ValueError('The saved reference changed. Review and reload its rule configuration.')
    return deepcopy(definition)
