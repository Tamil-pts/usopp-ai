"""Read B&R _GLOBAL declarations without compiling or executing C code."""
from pathlib import PurePosixPath
import re

SCALARS={'char':'SINT','short':'INT','int':'DINT','long':'DINT','float':'REAL','double':'LREAL','plcbit':'BOOL','plcstring':'USINT','plcdt':'DATE_AND_TIME'}


def c_type(dtype, dimensions=(), pointers=0):
    dtype=SCALARS.get(dtype,dtype)
    if pointers:return dtype+'*'*pointers
    dims=list(dimensions)
    if dtype=='STRING' and dims:
        dtype='STRING['+str(dims.pop()-1)+']'
    if dims:dtype='ARRAY['+','.join('0..'+str(n-1) for n in dims)+'] OF '+dtype
    return dtype


def c_items(text,constants):
    for item in text.split(','):
        found=re.fullmatch(r'\s*(\*+)?\s*([A-Za-z_]\w*)\s*((?:\[[\w\d\s]+\]\s*)*)',item)
        if not found:continue
        dimensions=[]
        for raw in re.findall(r'\[\s*(\w+)\s*\]',found[3]):
            value=constants.get(raw,raw)
            if not str(value).isdigit() or not 1<=int(value)<=65536:break
            dimensions.append(int(value))
        else:yield found[2],dimensions,len(found[1] or '')


def structure_types(sources):
    result={}
    for source,text in sources.items():
        if PurePosixPath(source).suffix.lower() not in {'.c','.h'}:continue
        text=re.sub(r'/\*[\s\S]*?\*/|//[^\n]*',lambda m:''.join('\n' if c=='\n' else ' ' for c in m[0]),text)
        constants=dict(re.findall(r'^\s*#\s*define\s+(\w+)\s+(\d+)\s*$',text,re.M))
        for match in re.finditer(r'typedef\s+struct\s*(?:\w+\s*)?\{([^{}]*)\}\s*(\w+)\s*;',text,re.S):
            fields=[]
            for declaration in match[1].split(';'):
                field=re.fullmatch(r'\s*([A-Za-z_]\w*)\s+(.+?)\s*',declaration,re.S)
                if not field:continue
                for name,dims,pointers in c_items(field[2],constants):fields.append({'name':name,'type':c_type(field[1],dims,pointers)})
            if fields:
                spec={'kind':'struct','fields':fields,'cLayout':{'pack':4,'pointerBytes':4,'byteOrder':'little'}}
                if match[2] in result and result[match[2]]!=spec:
                    result[match[2]]={'kind':'unresolved','message':'Conflicting C structure definitions: '+match[2]}
                else:result[match[2]]=spec
    return result


def declarations(sources,selected=None):
    if selected:
        sources={k:v for k,v in sources.items() if not (len(PurePosixPath(k).parts)>1 and
            PurePosixPath(k).parts[0].lower()=='physical' and PurePosixPath(k).parts[1].casefold()!=selected.casefold())}
    headers=set()
    for source,text in sources.items():
        if PurePosixPath(source).suffix.lower()!='.c':continue
        for match in re.finditer(r'^\s*#\s*include\s*"([^"<>]+\.h)"',text,re.M):
            candidate=str(PurePosixPath(source).parent/match[1])
            if candidate in sources:headers.add(candidate)
    for source,text in sources.items():
        if PurePosixPath(source).suffix.lower()!='.c' and source not in headers:continue
        clean=re.sub(r'/\*[\s\S]*?\*/|//[^\n]*',lambda m:''.join('\n' if c=='\n' else ' ' for c in m[0]),text)
        constants=dict(re.findall(r'^\s*#\s*define\s+(\w+)\s+(\d+)\s*$',clean,re.M))
        clean=re.sub(r'(?m)^(\s*)(\w+)\s+(_LOCAL|_GLOBAL)\s+',r'\1\3 \2 ',clean)
        for match in re.finditer(r'^\s*(_GLOBAL(?:_RETAIN)?|_LOCAL)\s+([A-Za-z_]\w*)\s*(\*+)?\s+([^;{}]+);',clean,re.M):
            raw_type=match[2];dtype=SCALARS.get(raw_type,raw_type)
            for name,dims,pointers in c_items(match[4],constants):
                typename=c_type(dtype,dims,pointers+len(match[3] or ''))
                scope=PurePosixPath(source).parent.as_posix().casefold() if match[1]=='_LOCAL' else '@global'
                yield {'id':scope+':'+name,'name':name,'scope':scope,'type':typename,
                       'source':source,'line':clean.count('\n',0,match.start(2))+1,
                       'retain':match[1]=='_GLOBAL_RETAIN','declarationKind':'C '+match[1]}


def merge(model,sources):
    selected=model.get('projectInfo',{}).get('activeConfiguration')
    if selected:
        sources={k:v for k,v in sources.items() if not (len(PurePosixPath(k).parts)>1 and PurePosixPath(k).parts[0].lower()=='physical' and PurePosixPath(k).parts[1].casefold()!=selected.casefold())}
    types=model.setdefault('types',{})
    for name,spec in structure_types(sources).items():
        if types.get(name,{}).get('source','').lower().endswith(('.typ','.fun')):continue
        types[name]=spec
    existing={v['id']:v for v in model.get('variables',[])}
    def key(dtype):return re.sub(r'\s+','',dtype)
    for variable in declarations(sources,model.get('projectInfo',{}).get('activeConfiguration')):
        current=existing.get(variable['id'])
        if current:
            if current.get('source')==variable['source'] and PurePosixPath(variable['source']).suffix.lower()=='.c':
                current.update(type=variable['type'],retain=variable['retain'])
            reference={k:variable[k] for k in ('source','line','type')}
            if key(current['type'])!=key(variable['type']):
                current['ambiguous']=True
                if reference not in current.setdefault('conflictingDeclarations',[]):
                    current['conflictingDeclarations'].append(reference)
                    model.setdefault('diagnostics',[]).append({'severity':'error','code':'variable-conflict',
                        **reference,'message':'Conflicting C/IEC global declaration: '+variable['name']})
            elif reference not in current.setdefault('declarationReferences',[]):
                current['declarationReferences'].append(reference)
        else:
            model.setdefault('variables',[]).append(variable);existing[variable['id']]=variable
    model['declarationAdapterVersion']=4
    model.setdefault('statistics',{})['variables']=len(model.get('variables',[]))
