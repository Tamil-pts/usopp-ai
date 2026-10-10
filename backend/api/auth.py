import re
import sqlite3
from fastapi import APIRouter, Body, HTTPException, Request, Response
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
        user=accounts.store.register(username_field(data),field(data,'password',8,128),field(data,'designation'),field(data,'company'))
    except sqlite3.IntegrityError:
        raise HTTPException(409,'This username already exists.')
    except accounts.AccountCapacityError as error:
        raise HTTPException(409,str(error))
    return {'user':user}

@router.post('/users/{user_id}')
def manage_user(user_id:int,request:Request,data:dict=Body(...)):
    admin(request)
    if not isinstance(data.get('active'),bool): raise HTTPException(400,'Choose whether this account is enabled.')
    password=field(data,'password',8,128) if data.get('password') else None
    try:
        user=accounts.store.manage_user(user_id,username_field(data),field(data,'designation'),field(data,'company'),data['active'],password)
    except sqlite3.IntegrityError: raise HTTPException(409,'This username already exists.')
    except ValueError as error: raise HTTPException(400,str(error))
    return {'user':user}

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
    response.set_cookie(accounts.COOKIE,token,max_age=accounts.SESSION_SECONDS,
                        httponly=True,samesite='lax',secure=request.url.scheme=='https',path='/')
    response.headers['Cache-Control']='no-store'
    return {'user':user}

@router.get('/session')
def current_session(request:Request, response:Response):
    response.headers['Cache-Control']='no-store'
    return {'user':accounts.store.user_for_token(request.cookies.get(accounts.COOKIE))}

@router.post('/register')
def register(request:Request,response:Response,data:dict=Body(...)):
    username=field(data,'username',3,40)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',username):
        raise HTTPException(400,'Username can contain letters, numbers, dots, underscores and hyphens.')
    password=field(data,'password',8,128)
    try:
        user=accounts.store.register(username,password,field(data,'designation'),field(data,'company'))
    except sqlite3.IntegrityError:
        raise HTTPException(409,'This username already exists. Choose another or sign in.')
    except accounts.AccountCapacityError as error:
        raise HTTPException(409,str(error))
    return session(response,request,user)

@router.post('/login')
def login(request:Request,response:Response,data:dict=Body(...)):
    user,error=accounts.store.login(field(data,'username',1,40),field(data,'password',1,128),
                                   request.client.host if request.client else 'local')
    if error=='throttled':
        raise HTTPException(429,'Too many unsuccessful attempts. Try again in five minutes.')
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
    current=field(data,'currentPassword',1,128)
    replacement=field(data,'newPassword',8,128)
    if current==replacement:
        raise HTTPException(400,'Choose a different new password.')
    if not accounts.store.change_password(user['id'],current,replacement):
        raise HTTPException(403,'Current password is incorrect.')
    session(response,request,user)
    return {'success':True,'message':'Password changed. Other sessions have been signed out.'}
