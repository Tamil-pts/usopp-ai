"""Read-only SpinConnect source study and copy/download ST generation."""
from fastapi import APIRouter, HTTPException
from backend.core.runtime import _local_path, locate_root
from python_engine.spinconnect_write import Study, generate, discover

router=APIRouter(prefix='/api/spinconnect/write-st',tags=['ByteMap Write ST'])


@router.post('/discover')
def discover_write_st(payload:dict):
    return discover(locate_root(_local_path(payload.get('project_path',''),True,True)))


def study(payload):
    root=locate_root(_local_path(payload.get('project_path',''),True,True))
    return Study(root,str(payload.get('readSource') or ''),str(payload.get('writeSource') or ''),str(payload.get('hmiTarget') or ''))


@router.post('/analyze')
def analyze_write_st(payload:dict):
    try:return study(payload).public()
    except ValueError as error:raise HTTPException(400,str(error))


@router.post('/generate')
def generate_write_st(payload:dict):
    try:
        source=study(payload)
        if not payload.get('fingerprint') or source.fingerprint!=payload['fingerprint']:
            raise HTTPException(409,'The project or HMI sources changed. Analyze again and review the current field map.')
        return generate(source,payload.get('groups'),payload.get('fields'),payload.get('reviewed') is True)
    except ValueError as error:raise HTTPException(400,str(error))
