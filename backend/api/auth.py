import re
import sqlite3
import shutil
from pathlib import Path
from fastapi import APIRouter, Body, HTTPException, Request, Response, UploadFile, File
from backend.core import accounts

router = APIRouter(prefix='/api/auth', tags=['Accounts'])

def admin(request):
    if getattr(request.state,'user',{}).get('role')!='admin':
        raise HTTPException(403,'Only an administrator can manage user accounts.')

def username_field(data):
    value=field(data,'username',3,40)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',value):
        raise HTTPException(400,'Username can contain letters, numbers, dots, underscores and hyphens.')
    return value

@router.get('/users')
def list_users(request:Request):
    admin(request)
    return {'users':accounts.store.list_users(), 'capacity':accounts.store.capacity()}

@router.post('/users')
def create_user(request:Request,data:dict=Body(...)):
    admin(request)
    try:
        user=accounts.store.register(username_field(data),field(data,'password',8,128),field(data,'designation'),field(data,'company'),data.get('role','user'),data.get('email',''))
    except sqlite3.IntegrityError:
        raise HTTPException(409,'This username already exists.')
    except ValueError as error: raise HTTPException(400,str(error))
    return {'user':user}

@router.post('/users/{user_id}')
def manage_user(user_id:int,request:Request,data:dict=Body(...)):
    admin(request)
    if not isinstance(data.get('active'),bool): raise HTTPException(400,'Choose whether this account is enabled.')
    password=field(data,'password',8,128) if data.get('password') else None
    try:
        user=accounts.store.manage_user(user_id,username_field(data),field(data,'designation'),field(data,'company'),data['active'],password,data.get('role'),request.state.user['id'],data.get('email'))
    except sqlite3.IntegrityError: raise HTTPException(409,'This username already exists.')
    except ValueError as error: raise HTTPException(400,str(error))
    return {'user':user}


@router.post('/profile-email')
def update_email(request:Request,data:dict=Body(...)):
    try:return {'user':accounts.store.set_email(request.state.user['id'],data.get('email',''))}
    except ValueError as error:raise HTTPException(400,str(error)) from None

@router.post('/profile-image')
def upload_profile_image(request:Request,file:UploadFile=File(...)):
    import io
    import warnings
    from PIL import Image, ImageOps, UnidentifiedImageError
    user=request.state.user
    if user.get('isDemo'):raise HTTPException(403,'Sign in with a personal account to add a profile photo.')
    try:
        raw=file.file.read(5*1024*1024+1)
        if not raw or len(raw)>5*1024*1024:raise HTTPException(400,'Choose a PNG, JPEG or WebP image up to 5 MB.')
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in ('PNG','JPEG','WEBP') or source.width*source.height>16000000 or getattr(source,'n_frames',1)!=1:
                    raise HTTPException(400,'Choose a still PNG, JPEG or WebP image up to 16 megapixels.')
                picture=ImageOps.fit(ImageOps.exif_transpose(source).convert('RGB'),(256,256))
                output=io.BytesIO();picture.save(output,format='JPEG',quality=88)
        return {'user':accounts.store.set_profile_image(user['id'],output.getvalue())}
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise HTTPException(400,'This photo could not be read. Choose a valid PNG, JPEG or WebP image.')
    finally:file.file.close()


@router.delete('/profile-image')
def remove_profile_image(request:Request):
    if request.state.user.get('isDemo'):raise HTTPException(403,'Use a personal account to manage your profile photo.')
    return {'user':accounts.store.set_profile_image(request.state.user['id'],None)}


@router.get('/profile-image/{user_id}')
def get_profile_image(user_id:int,request:Request):
    if request.state.user['id']!=user_id and request.state.user.get('role')!='admin':raise HTTPException(403,'This profile belongs to another user.')
    image=accounts.store.profile_image(user_id)
    if not image:raise HTTPException(404,'No profile photo.')
    return Response(image,media_type='image/jpeg',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

@router.delete('/users/{user_id}')
def delete_user(user_id:int,request:Request):
    admin(request)
    if request.state.user.get('id') == user_id:
        raise HTTPException(400,'You cannot delete the account you are currently using.')
    try:
        deleted=accounts.store.delete_user(user_id)
    except ValueError as error:
        raise HTTPException(400,str(error))
    from backend.core.runtime import WORK, EXPORTS
    removed=0
    safe_roots=(WORK.resolve(),EXPORTS.resolve())
    paths=sorted((Path(value) for value in deleted['paths']),key=lambda path:len(path.parts))
    removed_roots=[]
    for path in paths:
        try:
            target=path.resolve()
            if not any(target!=root and root in target.parents for root in safe_roots):
                continue
            if any(target==parent or parent in target.parents for parent in removed_roots):
                continue
            if target.is_dir(): shutil.rmtree(target)
            elif target.is_file(): target.unlink()
            else: continue
            removed_roots.append(target); removed+=1
        except OSError:
            continue
    from backend.core.persistent_store import db as persistent_db
    with persistent_db() as connection:
        connection.execute('DELETE FROM user_settings WHERE user_id=?',(user_id,))
        connection.execute('DELETE FROM run_archive WHERE user_id=?',(user_id,))
    from backend.core.live_collection import remove_user
    remove_user(user_id)
    from backend.core.data_simulator import remove_user as remove_simulators
    remove_simulators(user_id)
    from backend.api.dashboard_layouts import remove_user as remove_layouts
    remove_layouts(user_id)
    return {'deleted':True,'username':deleted['username'],'removedWorkspaces':removed}

def field(data, name, minimum=1, maximum=120):
    value = data.get(name)
    if not isinstance(value,str):
        raise HTTPException(400,f'Enter {name}.')
    if name not in ('password','currentPassword','newPassword'):
        value = value.strip()
    if not minimum <= len(value) <= maximum:
        raise HTTPException(400,f'{name} must contain {minimum}–{maximum} characters.')
    return value

def session(response, request, user):
    token = accounts.store.new_session(user['id'])
    response.set_cookie(accounts.COOKIE,token,max_age=accounts.session_seconds(user),
                        httponly=True,samesite='lax',secure=request.url.scheme=='https',path='/')
    response.headers['Cache-Control']='no-store'
    return {'user':accounts.store.user_for_token(token)}

@router.get('/session')
def current_session(request:Request, response:Response):
    response.headers['Cache-Control']='no-store'
    return {'user':accounts.store.user_for_token(request.cookies.get(accounts.COOKIE))}

@router.post('/register', status_code=202)
def register(request:Request,response:Response,data:dict=Body(...)):
    username=field(data,'username',3,40)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',username):
        raise HTTPException(400,'Username can contain letters, numbers, dots, underscores and hyphens.')
    password=field(data,'password',8,128)
    try:
        user=accounts.store.request_account(username,password,field(data,'designation'),field(data,'company'),data.get('email',''))
    except sqlite3.IntegrityError:
        raise HTTPException(409,'This username already exists. Choose another or sign in.')
    except ValueError as error:raise HTTPException(400,str(error)) from None
    response.headers['Cache-Control']='no-store'
    return {'pending':True,'message':'Your account request was sent to the administrator. You can sign in after Admin enables your account.'}

@router.post('/login')
def login(request:Request,response:Response,data:dict=Body(...)):
    user,error=accounts.store.login(field(data,'username',1,40),field(data,'password',1,128),
                                   request.client.host if request.client else 'local')
    if error=='throttled':
        raise HTTPException(429,'Too many unsuccessful attempts. Try again in five minutes.')
    if error=='pending':
        raise HTTPException(403,'Your account request is waiting for Admin approval. You can sign in after your account is enabled.')
    if not user:
        raise HTTPException(401,'Username or password is incorrect.')
    return session(response,request,user)

@router.post('/logout')
def logout(request:Request,response:Response):
    accounts.store.logout(request.cookies.get(accounts.COOKIE))
    response.delete_cookie(accounts.COOKIE,path='/')
    return {'success':True}

@router.post('/password')
def change_password(request:Request,response:Response,data:dict=Body(...)):
    user=request.state.user
    if user.get('isDemo'):
        raise HTTPException(403,'The demo account uses fixed demonstration credentials. Create your own account to set a private password.')
    current=field(data,'currentPassword',1,128)
    replacement=field(data,'newPassword',8,128)
    if current==replacement:
        raise HTTPException(400,'Choose a different new password.')
    if not accounts.store.change_password(user['id'],current,replacement):
        raise HTTPException(403,'Current password is incorrect.')
    session(response,request,user)
    return {'success':True,'message':'Password changed. Other sessions have been signed out.'}
