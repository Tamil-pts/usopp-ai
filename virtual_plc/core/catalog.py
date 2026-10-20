"""Portable, versioned B&R reference registry. Metadata never executes code.

Rebuild: python -m virtual_plc.core.catalog
Every implementation remains an ordinary reviewed Python function/block.
Unimplemented help entries are explicitly marked unsupported.
"""
from html.parser import HTMLParser
import json
from pathlib import Path
import re

SCHEMA_VERSION=1


class ReferenceHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows=[];self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.row=[]
        if tag in {'td','th'}:self.cell=[]
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in {'td','th'} and self.cell is not None:
            if self.row is not None:self.row.append(re.sub(r'\s+',' ',''.join(self.cell)).strip())
            self.cell=None
        if tag=='tr' and self.row is not None:
            self.rows.append(self.row);self.row=None


def implementation_index():
    from .vendor import CALLS,FILE_BLOCKS,ALIASES
    from .cpu import CALLS as CPU_CALLS,BLOCKS as CPU_BLOCKS
    from .vendor_services import CALLS as SERVICES,BLOCKS
    from .compiler import BUILTINS,IEC_BLOCKS,STATEFUL_CALLS
    from .libraries import BLOCK_INPUTS,BLOCK_OUTPUTS,block_field_type
    result={}
    for module,functions,blocks in [('vendor',CALLS,FILE_BLOCKS),('cpu',CPU_CALLS,CPU_BLOCKS),('vendor_services',SERVICES,BLOCKS)]:
        for name,arity in functions.items():result[name.casefold()]={'module':'virtual_plc.core.'+module,'kind':'function','arity':list(arity)}
        for name,(inputs,outputs) in blocks.items():result[name.casefold()]={'module':'virtual_plc.core.'+module,'kind':'function_block','inputs':inputs,'outputs':outputs}
    for name in sorted(BUILTINS):
        if name in {'ROL','ROR'}:continue
        result.setdefault(name.casefold(),{'module':'virtual_plc.core.libraries','kind':'function','syntax':'positional IEC inputs'})
    for name in sorted(IEC_BLOCKS):result[name.casefold()]={'module':'virtual_plc.core.libraries','kind':'function_block','inputs':{p:block_field_type(name,p) for p in sorted(BLOCK_INPUTS[name])},'outputs':{p:block_field_type(name,p) for p in sorted(BLOCK_OUTPUTS[name])}}
    for name in sorted(STATEFUL_CALLS):result[name.casefold()]={'module':'virtual_plc.core.runtime','kind':'function','arity':[1,1],'instanceState':'per lexical call and function-block instance'}
    sources=['BOOL','SINT','INT','USINT','UINT','DINT','UDINT','REAL','LREAL','TIME','DT','DATE_AND_TIME','BYTE','WORD','DWORD']
    targets=[n for n in sources if n not in {'DT','DATE_AND_TIME'}]+['STRING']
    for source in sources:
        for target in targets:result[(source+'_TO_'+target).casefold()]={'module':'virtual_plc.core.libraries','kind':'function','arity':[1,1],'conversion':{'from':source,'to':target}}
    for alias,name in ALIASES.items():result[alias.casefold()]={**result[name.casefold()],'aliasOf':name}
    return result


def build_catalog(help_root, output):
    help_root=Path(help_root).resolve();implementations=implementation_index();entries=[]
    for path in sorted((help_root/'libraries').glob('*/fbks/*.html')):
        parser=ReferenceHTML();parser.feed(path.read_text(encoding='utf-8-sig',errors='replace'))
        parameters=[]
        for row in parser.rows:
            if len(row)<3 or row[0].replace(' ','').upper() not in {'IN','OUT','IN/OUT','INOUT'}:continue
            parameters.append({'direction':row[0],'name':row[1],'type':row[2],'description':' '.join(row[3:])})
        if not parameters:continue
        name=path.stem;implementation=implementations.get(name.casefold())
        entries.append({'id':path.parent.parent.name+':'+name,'name':name,'library':path.parent.parent.name,
                        'reference':path.relative_to(help_root).as_posix(),'parameters':parameters,
                        'implemented':bool(implementation),'implementation':implementation})
    from virtual_plc import __version__
    catalog={'schemaVersion':SCHEMA_VERSION,'moduleVersion':__version__,'runtimeABI':'bounded virtual PLC memory; no host I/O',
             'referenceRoot':'knowledge/br_help/AS12/Help-en/Data','entries':entries,
             'implementations':implementations,'entryCount':len(entries)}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    temporary=output.with_suffix(output.suffix+'.tmp')
    temporary.write_text(json.dumps(catalog,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    temporary.replace(output)
    return catalog


def load_catalog(path):
    result=json.loads(Path(path).read_text(encoding='utf-8'))
    if result.get('schemaVersion')!=SCHEMA_VERSION:raise ValueError('Unsupported B&R catalog schema')
    return result


if __name__=='__main__':
    root=Path(__file__).resolve().parents[2]
    result=build_catalog(root/'knowledge/br_help/AS12/Help-en/Data',root/'knowledge/virtual_plc/br_catalog.json')
    print(json.dumps({'entries':result['entryCount'],'implementations':len(result['implementations'])}))
