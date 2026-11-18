"""Explicit model roles. Cloud transports require global policy and per-run consent."""
import json
import os
import re
from backend.core import assist_model
from backend.core.chopper_chain import strict_json


def validate_profiles(profiles):
    if not isinstance(profiles,list) or len(profiles)>5:raise ValueError('Configure at most five model profiles.')
    result=[]
    for p in profiles:
        if not isinstance(p,dict):raise ValueError('Each model profile must be an object.')
        key=p.get('id','');provider=p.get('provider','');model=p.get('model','');env=p.get('keyEnv','')
        if not re.fullmatch(r'[a-z][a-z0-9_-]{1,30}',key) or key=='local':raise ValueError('Use a unique model profile ID such as cloud-reviewer.')
        if provider not in {'openai','anthropic','compatible'}:raise ValueError('Choose openai, anthropic or compatible.')
        if not isinstance(model,str) or not model.strip() or len(model)>160:raise ValueError('Enter the provider model ID.')
        if not re.fullmatch(r'USOPP_AGENT_[A-Z0-9_]+_KEY',env):raise ValueError('API keys must reference a server environment variable such as USOPP_AGENT_CLAUDE_KEY.')
        base=p.get('baseUrl','').rstrip('/')
        if provider=='compatible':
            from backend.core.chopper_web import public_url
            from urllib.parse import urlsplit
            parsed=urlsplit(base)
            public_url(base,[parsed.hostname])
            if parsed.query:raise ValueError('The model base URL must not contain a query.')
        else:base={'openai':'https://api.openai.com/v1','anthropic':'https://api.anthropic.com/v1'}[provider]
        result.append({'id':key,'provider':provider,'model':model.strip(),'keyEnv':env,'baseUrl':base})
    if len({p['id'] for p in result})!=len(result):raise ValueError('Model profile IDs must be unique.')
    return result


def complete(role,system,prompt,settings,remote_consent=False):
    profile_id=settings['roles'].get(role,'local')
    if profile_id=='local':
        cfg=assist_model.configuration()
        if not cfg.get('localOnly',True) and not remote_consent:
            from backend.core.model_policy import loopback_url
            if not loopback_url(cfg.get('baseUrl','')):raise ValueError('This installation uses a remote default model. Approve remote evidence sharing for this run first.')
        schema={'type':'object','properties':{'sql':{'type':'string'}},'required':['sql'],'additionalProperties':False} if role=='planner' else {
            'type':'object','properties':{'factIds':{'type':'array','items':{'type':'string'}},'abstain':{'type':'boolean'}},
            'required':['factIds','abstain'],'additionalProperties':False}
        result=assist_model.chat_model(system,prompt,max_tokens=300,timeout=45,output_schema=schema)
        if not result:raise ValueError('A model is not enabled. Use deterministic evidence or configure the local model.')
        return strict_json(result['answer']),{'role':role,'profile':'local','model':result.get('model'),'provider':result.get('provider')}
    profile=next((p for p in settings['profiles'] if p['id']==profile_id),None)
    if not profile:raise ValueError('This agent role references a missing model profile.')
    if assist_model.configuration().get('localOnly',True):raise ValueError('The shared local-only model policy blocks external agent models.')
    if remote_consent is not True:raise ValueError('Approve sending the selected evidence to remote models for this run.')
    key=os.getenv(profile['keyEnv'],'')
    if not key:raise ValueError('The selected model profile has no server API key configured.')
    # Do not inherit proxy settings, send cookies, execute model tools or follow redirects.
    if len(prompt)>22000:raise ValueError('Agent model context exceeds the bounded evidence limit.')
    from backend.core.chopper_web import public_url
    from urllib.parse import urlsplit
    public_url(profile['baseUrl'],[urlsplit(profile['baseUrl']).hostname])
    anthropic=profile['provider']=='anthropic'
    url=profile['baseUrl']+('/messages' if anthropic else '/chat/completions')
    body={'model':profile['model'],'messages':[{'role':'user','content':prompt}],'max_tokens':300}
    if anthropic:body['system']=system
    else:
        body['messages'].insert(0,{'role':'system','content':system})
        if profile['provider']=='openai':body['max_completion_tokens']=body.pop('max_tokens')
    headers={'x-api-key':key,'anthropic-version':'2023-06-01'} if anthropic else {'Authorization':'Bearer '+key}
    from backend.core.chopper_web import get_bytes
    _,raw,_=get_bytes(url,[urlsplit(url).hostname],headers={**headers,'Content-Type':'application/json'},
                       method='POST',body=json.dumps(body).encode(),timeout=45)
    if len(raw)>256000:raise ValueError('Remote model response exceeds the output limit.')
    data=json.loads(raw)
    answer=''.join(block.get('text','') for block in data.get('content',[]) if block.get('type')=='text') if anthropic else data['choices'][0]['message']['content']
    return strict_json(answer),{'role':role,'profile':profile_id,'model':profile['model'],'provider':profile['provider']}
