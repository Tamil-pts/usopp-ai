from fastapi import APIRouter,Request
from backend.core import accounts

router=APIRouter(tags=['Chopper MCP'])

@router.get('/api/assist/mcp')
def settings(request:Request):
    return {'endpoint':str(request.base_url).rstrip('/')+'/api/mcp/','protocol':'MCP Streamable HTTP (2025-11-25)','authentication':'Bearer token or signed-in session',
            'tools':['project_context','understand_project','compare_explanation','read_source','find_variable','ladder_networks','validate_project','prepare_rule',
                     'build_engineering_model','get_project_structure','get_function_block','find_machine_function','trace_signal','get_execution_flow',
                     'validate_graph','get_engineering_blocks','get_engineering_relationships','get_engineering_tokens','compare_engineering_models','investigate_engineering_project'],
            'engineeringFoundation':{'automaticChatEnabled':False,'buildRequired':True,'validation':'Structural validity and unresolved semantics are reported separately.'},
            'sourceWrites':'Review and save in the uSOPp source editor.'}

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
