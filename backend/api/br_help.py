from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from backend.core import br_help

router = APIRouter(prefix='/api/knowledge/br-help', tags=['B&R help'])


@router.get('')
def status(): return br_help.status()


@router.get('/search')
def search(q: str = Query('', max_length=1000), category: str = Query('', max_length=80), limit: int = Query(20, ge=1, le=40)):
    return {'results': br_help.search(q, category, limit)}


@router.get('/guide')
def guide():
    return FileResponse(br_help.MANUAL, media_type='text/markdown', filename='BR_PROJECT_HELP.md')


@router.get('/document/{identifier}')
def document(identifier: str):
    result = br_help.document(identifier[:100])
    if not result: raise HTTPException(404, 'Reference topic not found.')
    return result


@router.get('/image/{identifier}/{number}')
def image(identifier: str, number: int):
    result = br_help.document(identifier[:100])
    images = result.get('images', []) if result else []
    if number < 0 or number >= len(images): raise HTTPException(404, 'Reference image not found.')
    target = (br_help.ROOT / images[number]['file']).resolve()
    if not target.is_relative_to(br_help.ROOT.resolve()) or target.suffix.casefold() not in {'.png', '.gif', '.jpg', '.jpeg'} or not target.is_file():
        raise HTTPException(404, 'Reference image unavailable.')
    return FileResponse(target)


@router.post('/rebuild')
def rebuild(request: Request):
    if getattr(request.state, 'user', {}).get('role') != 'admin': raise HTTPException(403, 'Only Admin can rebuild the shared reference index.')
    return br_help.rebuild()
