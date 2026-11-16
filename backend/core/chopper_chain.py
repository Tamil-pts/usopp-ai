"""Local prompt orchestration; no agents, remote callbacks or publication bypass."""
import json

def messages(system,prompt,history=None):
    from langchain_core.prompts import ChatPromptTemplate,MessagesPlaceholder
    from langsmith import tracing_context
    safe=[{'role':item['role'],'content':item['content'][:8000]} for item in (history if isinstance(history,list) else [])[-12:]
          if isinstance(item,dict) and item.get('role') in {'user','assistant'} and isinstance(item.get('content'),str)]
    template=ChatPromptTemplate.from_messages([('system','{instructions}'),MessagesPlaceholder('history'),('human','{question}')])
    # Disable tracing even when a deployment environment enables LangSmith globally.
    with tracing_context(enabled=False):
        value=template.invoke({'instructions':system,'history':safe,'question':prompt},config={'callbacks':[]})
    roles={'system':'system','human':'user','ai':'assistant'}
    return [{'role':roles[item.type],'content':item.content} for item in value.to_messages()]

def strict_json(answer):
    """LangChain parses only after strict JSON validation: no partial-JSON repair."""
    from langchain_core.output_parsers import JsonOutputParser
    from langsmith import tracing_context
    json.loads(answer)
    with tracing_context(enabled=False):return JsonOutputParser().invoke(answer,config={'callbacks':[]})
