"""Use only retrieval options supported by the loaded Index implementation.

An application process may still hold the pre-pagination Index class during an
upgrade. Never catch/retry an internal TypeError or pretend that class paginates.
"""
import inspect


def retrieve_page(index,question,characters=18000,passes=3,offset=0,limit=14):
    try:
        offset=max(0,min(100000,int(offset)))
        limit=max(1,min(200,int(limit)))
        characters=max(1000,min(2000000,int(characters)))
        passes=max(1,min(4,int(passes)))
    except (TypeError,ValueError) as error:
        raise ValueError('Retrieval offset, limit, character budget and passes must be numeric.') from error
    signature=inspect.signature(index.retrieve)
    supported={key for key,value in signature.parameters.items()
               if value.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD,inspect.Parameter.KEYWORD_ONLY)}
    accepts_options=any(value.kind==inspect.Parameter.VAR_KEYWORD for value in signature.parameters.values())
    paginated='offset' in supported or accepts_options
    limited='limit' in supported or accepts_options
    notice='The loaded project index uses the legacy retrieval interface. Restart the backend to enable section pagination; graph-based analysis remains available.'
    if offset and not paginated:
        return {'evidence':[],'notices':[notice],'passes':[],'tasks':[],'identity':{},'candidateCount':0,
                'projectId':index.key,'offset':offset,'nextOffset':None,'retrievalInterface':'legacy'}
    options={'characters':characters,'passes':passes,'offset':offset,'limit':limit}
    result=dict(index.retrieve(question,**{key:value for key,value in options.items() if key in supported or accepts_options}))
    result['evidence']=list(result.get('evidence',[]))[:limit]
    result['notices']=list(result.get('notices',[]))
    if not paginated or not limited:
        result['nextOffset']=None
        result['notices'].append(notice)
    result['retrievalInterface']='paginated' if paginated and limited else 'legacy'
    return result
