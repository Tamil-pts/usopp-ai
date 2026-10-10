from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
from itertools import chain
import json
from backend.core import assist_training as store

router = APIRouter(prefix='/api/assist/training', tags=['Chopper training'])


def admin(request):
    if request.state.user.get('role') != 'admin': raise HTTPException(403, 'Only Admin can approve or export shared model training data.')


@router.get('')
def status(request: Request): return store.summary(request.state.user)


@router.get('/examples')
def examples(request: Request): return {'examples': store.records(request.state.user)}


@router.get('/guide')
def guide():
    return FileResponse(store.PLAYBOOK.parent / 'CHOPPER_TRAINING.md', media_type='text/markdown', filename='CHOPPER_TRAINING.md')


@router.post('/examples/{identifier}/review')
def review(identifier: str, payload: dict, request: Request):
    admin(request)
    try: store.review(identifier, request.state.user, payload.get('revision'), payload.get('status'), payload.get('answer', ''))
    except LookupError as error: raise HTTPException(404, str(error))
    except RuntimeError as error: raise HTTPException(409, str(error))
    except ValueError as error: raise HTTPException(400, str(error))
    return {'saved': True, 'weightsTrained': False}


@router.get('/export')
def export(request: Request):
    admin(request)
    examples = store.export_examples()
    first = next(examples, None)
    if first is None: raise HTTPException(404, 'Approve source-backed project answers before exporting a training dataset.')
    return StreamingResponse((json.dumps(row, ensure_ascii=False)+'\n' for row in chain([first], examples)), media_type='application/x-ndjson',
                    headers={'Content-Disposition': 'attachment; filename="chopper_reviewed_project_training.jsonl"', 'Cache-Control': 'no-store'})
