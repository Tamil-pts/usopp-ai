"""Personal live targets and retained report samples."""
from fastapi import APIRouter, Request, HTTPException, Query
from backend.core import live_collection as live, persistent_store

router = APIRouter(prefix='/api/nami/live', tags=['Live PLC dashboards'])


@router.get('/targets')
def targets(request: Request):
    return live.overview(request.state.user['id'])


@router.put('/targets')
def save_targets(request: Request, data: dict):
    if data.get('accountId') != request.state.user['id']:
        raise HTTPException(409, 'The account changed. Reload DataInspect before saving targets.')
    items = data.get('targets')
    if not isinstance(items,list) or any(not isinstance(item,dict) or not isinstance(item.get('plc'),dict) for item in items):
        raise HTTPException(400, 'Supply a list of target configurations.')
    if request.state.user.get('isDemo') and any(item['plc'].get('liveEnabled') or item['plc'].get('storeLiveData') for item in items):
        raise HTTPException(403, 'Live collection requires a personal account.')
    if type(data.get('revision')) is not int:
        raise HTTPException(400, 'Load live target settings before saving.')
    try:
        live.replace_configurations(request.state.user['id'], data.get('targets'), data['revision'])
        from backend.core.data_simulator import reconcile
        reconcile(request.state.user['id'],[item['plc'] for item in items])
        return live.overview(request.state.user['id'])
    except persistent_store.SettingsConflict as error: raise HTTPException(409, str(error))
    except (ValueError, TypeError, OverflowError) as error: raise HTTPException(400, str(error))


@router.get('/targets/{target_id}/latest')
def latest(request: Request, target_id: str):
    try: return live.latest(request.state.user['id'], target_id)
    except KeyError: raise HTTPException(404, 'Live target not configured for this account.')


@router.get('/targets/{target_id}/history')
def history(request: Request, target_id: str, start: float, end: float, limit: int = Query(300, ge=2, le=500)):
    try: return live.history(request.state.user['id'], target_id, start, end, limit)
    except ValueError as error: raise HTTPException(400, str(error))
