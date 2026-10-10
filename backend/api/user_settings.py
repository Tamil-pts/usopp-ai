from fastapi import APIRouter, HTTPException, Request
from backend.core import persistent_store as store

router = APIRouter(prefix='/api/account/storage', tags=['Saved user settings'])


@router.get('')
def read(request: Request):
    user_id = request.state.user['id']
    return {'accountId': user_id, 'entries': store.settings(user_id)}


@router.post('')
def save(payload: dict, request: Request):
    user_id = request.state.user['id']
    # Pending saves must never cross accounts if a browser session changes.
    if payload.get('accountId') != user_id:
        raise HTTPException(409, 'Account changed. Sign in to the account that owns these settings.')
    try:
        entries = store.save_settings(user_id, payload.get('changes'), payload.get('importMissing') is True)
    except store.SettingsConflict as error:
        raise HTTPException(409, str(error))
    except ValueError as error:
        raise HTTPException(400, str(error))
    return {'accountId': user_id, 'entries': entries}
