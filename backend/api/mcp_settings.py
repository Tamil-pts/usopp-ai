from fastapi import APIRouter,Request
from backend.core import accounts

router=APIRouter(tags=['Chopper MCP'])

@router.get('/api/assist/mcp')
def settings(request:Request):
    return {'endpoint':str(request.base_url).rstrip('/')+'/api/mcp/','protocol':'MCP Streamable HTTP (2025-11-25)','authentication':'Bearer token or signed-in session','tools':['project_context','read_source','find_variable','ladder_networks','validate_project','prepare_rule'],'sourceWrites':'Review and save in the uSOPp source editor.'}

@router.post('/api/assist/mcp/token')
def token(request:Request):
    from backend.core.accounts import SESSION_SECONDS
    return {'token':accounts.store.new_session(request.state.user['id']),'expiresInSeconds':SESSION_SECONDS,'message':'Copy this token now. It grants your account permissions and expires like an application session.'}

@router.post('/api/assist/mcp/revoke')
def revoke(payload:dict,request:Request):
    token=str(payload.get('token') or '')
    owner=accounts.store.user_for_token(token)
    if owner and owner['id']==request.state.user['id']:accounts.store.logout(token)
    return {'revoked':True}
