from fastapi import APIRouter,Depends,File,Form,UploadFile,Request,HTTPException
from backend.core import chopper_speech as speech

def actor(request:Request):
    user=getattr(request.state,'user',None)
    if not user:raise HTTPException(401,'Sign in to use Chopper audio.')
    if user.get('isDemo') or user.get('role')!='admin' and 'assistant' not in user.get('workspaceModules',[]):raise HTTPException(403,'Chopper audio requires an authorized personal account.')
    return user
router=APIRouter(prefix='/api/assist/speech',tags=['Chopper local speech'],dependencies=[Depends(actor)])

@router.get('/status')
def status():return speech.status()

@router.post('/transcriptions')
def transcribe(request:Request,file:UploadFile=File(...),language:str=Form('auto')):return speech.start(file,language,actor(request))

@router.get('/transcriptions/{key}')
def transcript(key:str,request:Request):return speech.public(speech.opened(key,actor(request))[1])

@router.delete('/transcriptions/{key}')
def cancel(key:str,request:Request):
    with speech.LOCK:
        folder,value=speech.opened(key,actor(request));value.update(status='cancelled');value.pop('result',None);speech.write(folder,value)
    return {'status':'cancelled'}
