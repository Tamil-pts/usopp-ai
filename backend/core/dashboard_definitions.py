"""Resolve workbook formula labels using the supplied database equations."""
import ast
import re
from backend.core.data_models import clean,groups,header,machine_key,plc_type

FUNCTIONS={'abs','min','max','round','floor','ceil','sqrt','gt','gte','lt','lte','eq','neq'}


def arithmetic(value):
    value=clean(value).lstrip('=').strip()
    if value.upper().startswith('MATH(') and value.endswith(')'):value=value[5:-1]
    if not value or len(value)>400:return None
    try:tree=ast.parse(value.replace('^','**'),mode='eval')
    except (ValueError,SyntaxError):return None
    allowed=(ast.Expression,ast.BinOp,ast.UnaryOp,ast.Name,ast.Load,ast.Constant,ast.Add,ast.Sub,ast.Mult,ast.Div,ast.Mod,ast.Pow,ast.UAdd,ast.USub,ast.Call)
    for node in ast.walk(tree):
        if not isinstance(node,allowed):return None
        if isinstance(node,ast.Constant) and (type(node.value) not in (int,float)):return None
        if isinstance(node,ast.Call) and (not isinstance(node.func,ast.Name) or node.func.id not in FUNCTIONS or node.keywords):return None
    # A lone identifier is a label or another collection, not an equation.
    if isinstance(tree.body,ast.Name):return None
    return value


def symbol(value):
    value=header(value)
    value=re.sub(r'formula$','',value)
    return value


def enrich(template,model,view_name,rules):
    rows=[]
    for sheet,items in model.get('databaseModel',{}).get('keysList',{}).items():
        if view_name(sheet)!=template['view']:continue
        for number,row in enumerate(items,1):
            if not row.get('tagName'):continue
            keys=[clean(row.get(key)) for key in ('tdEngineKey','mongoKey') if clean(row.get(key))]
            matching=[p for p in template['parameters'] if header(p['name'])==header(row['tagName'])]
            if not matching and clean(row.get('tdEngineKey')):
                matching=[p for p in template['parameters'] if header(p.get('tdEngineKey'))==header(row['tdEngineKey'])]
            if not matching:matching=[p for p in template['parameters'] if set(map(header,keys))&set(map(header,p['keys']))]
            names=list(dict.fromkeys([row['tagName'],*[p['name'] for p in matching]]))
            dtype=plc_type(row.get('plcDataType') or row.get('dataType'))
            formula=clean(row.get('formula'));derived=bool(row.get('isAutoCalc') or formula or clean(row.get('groupCode')).casefold()=='formula')
            dependency={'id':f'definition-{len(rows)+1}','name':row['tagName'],'dataType':dtype,'groupCodes':groups(row.get('groupCode')),
                'kind':'formula' if derived else 'plc','formula':arithmetic(formula) or formula,'keys':keys,'unit':'',
                'mongoKey':clean(row.get('mongoKey')),'tdEngineKey':clean(row.get('tdEngineKey')),
                'aliases':names,'sourceAliases':names,'dataTypeRole':row.get('dataTypeRole','value'),'numericValueType':row.get('numericValueType',dtype in {'REAL','LREAL'}),
                'ignoreNameSeparators':rules.get('ignoreNameSeparators') is True,
                'bindingRole':'dependency','source':{'workbook':model['sourceRelativePath'],'sheet':sheet,'row':number}}
            dependency['definitionPriority']=1 if row.get('excelReference') else 2
            rows.append(dependency)
    for p in template['parameters']:
        p['sourceAliases']=[]
        p['dataTypeRole']='value';p['numericValueType']=p['dataType'] in {'REAL','LREAL'}
        p['ignoreNameSeparators']=rules.get('ignoreNameSeparators') is True
        for rule in rules.get('aliases',[]):
            if rule['service']==template['service'] and machine_key(template['machine']) in {machine_key(value) for value in rule['departments']} and p['groupCodes']==[rule['groupCode']] and clean(p['name']).casefold() in {clean(value).casefold() for value in rule['names']}:
                p['aliases']=rule['names']
        if p['kind']!='formula':continue
        # Prefer the original database equation over the workbook's function
        # label. Require a unique equation within this department and period.
        wanted={symbol(p['name']),symbol(p['formula']),*[symbol(key) for key in p['keys']]}
        wanted.discard('')
        candidates=[row for row in rows if arithmetic(row['formula']) and
                    wanted & {symbol(row['name']),*[symbol(key) for key in row['keys']]}]
        if candidates:
            priority=max(row['definitionPriority'] for row in candidates)
            candidates=[row for row in candidates if row['definitionPriority']==priority]
        expressions={re.sub(r'\s+','',arithmetic(row['formula'])):arithmetic(row['formula']) for row in candidates}
        if len(expressions)==1:
            p['originalFormula']=p['formula'];p['formula']=next(iter(expressions.values()))
            p['definitionSource']=candidates[0]['source']
        else:p['formula']=arithmetic(p['formula']) or p['formula']
        if p['name'].strip() in {'-','?',''}:
            label=p.get('originalFormula',p['formula'])
            if re.fullmatch(r'[a-z_]+',label):p['name']=label.removesuffix('_formula').replace('_',' ').capitalize()
    # Dependencies carry database keys without replacing the raw PLC fields
    # shown in workbook tables. Resolve formula variables against these first.
    template['parameters'].extend(rows)
    from backend.core.data_model_rules import apply_starter
    return apply_starter(template,rules)
