"""Source-derived SpinConnect write ST drafts. Never modifies the PLC project."""
from __future__ import annotations

import ast
import base64
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import re
import textwrap
import xml.etree.ElementTree as ET
import zipfile

from python_engine.compare import decode_project_text
from python_engine.project_analysis import _mask
from python_engine.project_info import local_project_details
from python_engine.project_paths import project_files

WIDTHS = {'BOOL':1,'USINT':1,'SINT':1,'BYTE':1,'UINT':2,'INT':2,'WORD':2,
          'UDINT':4,'DINT':4,'DWORD':4,'REAL':4,'TIME':4,'LREAL':8,'LINT':8,'ULINT':8}
IDENT = r'[A-Za-z_]\w*(?:\[\d+\]|\.[A-Za-z_]\w*)*'
RECV = re.compile(r'memcpy\s*\(\s*ADR\(([^()]+)\)\s*,\s*ADR\(nw_rcv_buffer\[nw_i\]\)\s*,\s*(\d+)\s*\)\s*;',re.I)
SEND = re.compile(r'memcpy\s*\(\s*ADR\(nw_snd_buffer\[nw_i\]\)\s*,\s*ADR\(([^()]+)\)\s*,\s*(\d+)\s*\)\s*;',re.I)


def number(expression):
    """Small arithmetic literals only; no calls, attributes, indexing or eval."""
    try:
        node=ast.parse(str(expression).strip(),mode='eval').body
        def visit(item):
            if isinstance(item,ast.Constant) and type(item.value) in (int,float):return Decimal(str(item.value))
            if isinstance(item,ast.UnaryOp) and isinstance(item.op,(ast.UAdd,ast.USub)):
                value=visit(item.operand);return -value if isinstance(item.op,ast.USub) else value
            if isinstance(item,ast.BinOp) and isinstance(item.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
                a,b=visit(item.left),visit(item.right)
                if isinstance(item.op,ast.Add):return a+b
                if isinstance(item.op,ast.Sub):return a-b
                if isinstance(item.op,ast.Mult):return a*b
                return a/b
            raise ValueError()
        value=visit(node)
        return value if value.is_finite() else None
    except (ValueError,TypeError,SyntaxError,ArithmeticError,InvalidOperation):return None


def literal(value):
    value=Decimal(str(value));return format(value.normalize(),'f')


def properties(node):return {p.get('Name'):p.get('Value','') for p in node.findall('./{*}Property')}
def valid(value):return str(value or '').strip().casefold() not in ('','none','null','<null>')
def source_text(path):return decode_project_text(path).replace('\r\n','\n').replace('\r','\n')
def variable(value):
    match=re.search(r'Variable\[(.*)\]$',str(value or ''))
    value=match.group(1) if match else str(value or '')
    return re.sub(r'^(?:Local|Internal)\.', '',value,flags=re.I) if re.fullmatch(r'(?:Local|Internal)\.'+IDENT,value,re.I) else value


@dataclass
class Branch:
    code:int
    start:int
    body_start:int
    end:int
    description:str


@dataclass
class GroupCase:
    function:int
    start:int
    body_start:int
    body_end:int
    end:int
    branches:list[Branch]
    otherwise:str


def cases(text, default_function=1):
    """Keep nested CASE/IF scopes and positions, excluding comments and strings."""
    clean=_mask(text,strings=True); result=[]
    for start in re.finditer(r'\bCASE\s+nw_group_code\s+OF\b',clean,re.I):
        depth=1; tokens=list(re.finditer(r'\bCASE\b|\bEND_CASE\b',clean[start.end():],re.I));end=None
        for token in tokens:
            depth += 1 if token.group().upper()=='CASE' else -1
            if depth==0:end=start.end()+token.start();break
        if end is None:raise ValueError('An nw_group_code CASE has no matching END_CASE.')
        # Track nested CASE and IF scopes so their ELSE is not the CASE default.
        inner=clean[start.end():end]; nesting=[];labels=[];otherwise=end
        pattern=r'\bEND_IF\b|\bEND_CASE\b|\bCASE\b|\bIF\b|\bELSE\b|^\s*(\d+)\s*:(?![=])'
        for token in re.finditer(pattern,inner,re.I|re.M):
            word=token.group().strip().upper();at=start.end()+token.start()
            if word in ('IF','CASE'):nesting.append(word)
            elif word in ('END_IF','END_CASE'):
                expected='IF' if word=='END_IF' else 'CASE'
                if not nesting or nesting.pop()!=expected:raise ValueError('Unbalanced IF/CASE in group source.')
            elif not nesting and token.group(1):labels.append((int(token.group(1)),at,start.end()+token.end()))
            elif not nesting and word=='ELSE':otherwise=at;break
        branches=[]
        for i,(code,at,body) in enumerate(labels):
            stop=labels[i+1][1] if i+1<len(labels) else otherwise
            comment=re.match(r'\s*\(\*(.*?)\*\)',text[body:stop],re.S)
            branches.append(Branch(code,at,body,stop,comment.group(1).strip() if comment else f'Group {code}'))
        preceding=list(re.finditer(r'nw_rcv_buffer\[2\]\s*=\s*([12])\b',clean[:start.start()],re.I))
        function=int(preceding[-1].group(1)) if preceding else default_function
        result.append(GroupCase(function,start.start(),start.end(),end,end+len('END_CASE'),branches,text[otherwise:end]))
    return result


def declarations(text):
    result={};clean=_mask(text)
    # Match the declaration terminator too; assignments and structure members
    # are never guessed to be declarations.
    for match in re.finditer(r'\b([A-Za-z_]\w*)\s*:\s*((?:ARRAY\s*\[[^\]]+\]\s*OF\s*)?(?:STRING\s*\[\s*\d+\s*\]|[A-Za-z_]\w*))\s*(?::=[^;]*)?;',clean,re.I):
        expression=match.group(2).upper();base=re.sub(r'^ARRAY\s*\[[^\]]+\]\s*OF\s*','',expression,flags=re.I)
        size=WIDTHS.get(base)
        if base.startswith('STRING'):size=int(re.search(r'\d+',base).group())+1
        result[match.group(1).casefold()]={'type':base,'size':size,'declaration':expression}
    return result


def array_capacity(symbol):
    match=re.fullmatch(r'ARRAY\s*\[\s*0\s*\.\.\s*(\d+)\s*\]\s*OF\s*(?:USINT|BYTE)',symbol.get('declaration',''),re.I)
    return int(match.group(1))+1 if match else None


def layout_tree(text):
    """Keep conditional cursor changes; prune conditions without wire fields."""
    clean=_mask(text,strings=True)
    pattern=r'\b(?:ELSIF|IF)\b.*?\bTHEN\b|\bELSE\b|\bEND_IF\b|'+RECV.pattern+r'|\bnw_i\s*:=\s*nw_i\s*\+\s*\d+\s*;'
    tokens=list(re.finditer(pattern,clean,re.I|re.S))
    def sequence(at):
        items=[]
        while at<len(tokens):
            token=tokens[at];word=token.group().strip().upper()
            if word=='ELSE' or word.startswith(('ELSIF','END_IF')):break
            if word.startswith('IF'):
                node,at=conditional(at)
                if node['yes'] or node['no']:items.append(node)
            else:
                items.append({'kind':'copy' if word.startswith('MEMCPY') else 'increment','text':token.group(),'position':token.start()});at+=1
        return items,at
    def conditional(at):
        header=tokens[at].group();condition=re.sub(r'^(?:ELSIF|IF)\b|\bTHEN\s*$','',header,flags=re.I).strip()
        yes,at=sequence(at+1);no=[]
        if at<len(tokens) and tokens[at].group().strip().upper().startswith('ELSIF'):
            child,at=conditional(at)
            if child['yes'] or child['no']:no=[child]
        else:
            if at<len(tokens) and tokens[at].group().strip().upper()=='ELSE':no,at=sequence(at+1)
            if at>=len(tokens) or tokens[at].group().strip().upper()!='END_IF':raise ValueError('Unbalanced IF in write source.')
            at+=1
        return {'kind':'if','condition':condition,'yes':yes,'no':no},at
    result,at=sequence(0)
    if at!=len(tokens):raise ValueError('Unbalanced conditional wire layout.')
    return result


def layout_sizes(nodes):
    sizes={0}
    for node in nodes:
        if node['kind']=='increment':sizes={s+int(re.search(r'\+\s*(\d+)',node['text']).group(1)) for s in sizes}
        elif node['kind']=='if':sizes={s+t for s in sizes for t in layout_sizes(node['yes'])|layout_sizes(node['no'])}
    return sizes


def wire_positions(nodes):
    positions={}
    def walk(items,states):
        for node in items:
            if node['kind']=='copy':
                for offset,index,conditions in states:positions.setdefault(node['position'],set()).add((offset,index+1,conditions))
                states={(offset,index+1,conditions) for offset,index,conditions in states}
            elif node['kind']=='increment':
                size=int(re.search(r'\+\s*(\d+)',node['text']).group(1));states={(offset+size,index,conditions) for offset,index,conditions in states}
            else:
                yes={(o,i,(*c,node['condition'])) for o,i,c in states};no={(o,i,(*c,'NOT ('+node['condition']+')')) for o,i,c in states}
                states=walk(node['yes'],yes)|walk(node['no'],no)
            if len(states)>128:raise ValueError('Too many wire-layout variants to generate without a reviewed layout.')
        return states
    endings=walk(nodes,{(0,0,())});return positions,endings


def read_structure(body):
    adapted=re.sub(SEND.pattern,lambda m:'memcpy(ADR('+m.group(1)+'),ADR(nw_rcv_buffer[nw_i]),'+m.group(2)+');',body,flags=re.I)
    tree=layout_tree(adapted);positions,_=wire_positions(tree);refs={}
    def visit(nodes):
        for node in nodes:
            if node['kind']=='if':visit(node['yes']);visit(node['no'])
            elif node['kind']=='copy':
                match=RECV.fullmatch(node['text'])
                for offset,index,conditions in positions.get(node['position'],set()):
                    refs.setdefault((offset,int(match.group(2))),set()).add(match.group(1).strip())
    visit(tree)
    return tree,refs


def discover(root):
    root=Path(root).resolve();files=list(project_files(root));details=local_project_details(root)
    return {'readSources':[p.relative_to(root).as_posix() for p in candidates(files,'mms_nw_r')],
            'writeSources':[p.relative_to(root).as_posix() for p in candidates(files,'mms_nw_w')],
            'hmiTargets':sorted({p.relative_to(root).parts[1] for p in files if p.suffix.casefold()=='.page' and len(p.relative_to(root).parts)>2 and p.relative_to(root).parts[0].casefold()=='logical'}),
            'hmiTarget':details.get('screenFolder') or '', 'activeConfiguration':details.get('activeConfiguration')}


def candidates(files,task):
    return [p for p in files if p.suffix.casefold() in ('.st','.src') and
            (p.parent.name.casefold()==task or p.stem.casefold() in (task,task+'cyclic')) and
            ('cyclic' in p.stem.casefold() or p.stem.casefold() in (task,'main'))]


def read_layout(text,branch):
    body=text[branch.body_start:branch.end];clean=_mask(body,strings=True);rows=[];offset=0;previous=0;issues=[]
    for inc in re.finditer(r'\bnw_i\s*:=\s*nw_i\s*\+\s*(\d+)\s*;',clean,re.I):
        segment=clean[previous:inc.start()];width=int(inc.group(1));copies=list(SEND.finditer(segment))
        expr=copies[-1].group(1).strip() if copies else ''
        if not expr:
            condition=re.search(r'\bIF\s*\(*\s*('+IDENT+r')\s*(?:=|<>|>=|<=|>|<)',segment,re.I)
            if 'nw_snd_buffer[nw_i]' in segment and condition:expr=condition.group(1)
        if not expr:issues.append(f'Payload offset {offset}: read expression needs review.')
        rows.append({'offset':offset,'size':width,'readVariable':expr,'line':text.count('\n',0,branch.body_start+previous)+1})
        offset+=width;previous=inc.end()
    if re.search(r'\b(?:FOR|WHILE|REPEAT)\b',clean,re.I):issues.append('Loop-dependent packet layout requires a reviewed mapping.')
    # Branch-dependent cursor increments cannot be flattened into one layout.
    if any(not re.fullmatch(r'5|nw_i\s*\+\s*\d+',m.group(1).strip(),re.I) for m in re.finditer(r'\bnw_i\s*:=\s*([^;]+);',clean,re.I)):
        issues.append('Nonlinear packet cursor requires a reviewed mapping.')
    sizes=[int(x) for x in re.findall(r'nw_snd_buffer\[4\]\s*:=\s*(\d+)\s*;',clean,re.I)]
    highs=[int(x) for x in re.findall(r'nw_snd_buffer\[3\]\s*:=\s*(\d+)\s*;',clean,re.I)]
    declared=(highs[-1]*256+sizes[-1]) if highs and sizes else None
    return rows,offset,issues


def hmi_limits(root,files,target):
    """Exact datapoint identity, one HMI target, datasource and explicit units."""
    units={};sources={};rows={};used=[]
    eligible=[p for p in files if p.suffix.casefold() in ('.vcug','.dso') and (target in p.relative_to(root).parts or 'VCShared' in p.relative_to(root).parts)]
    # Shared resources first; target-specific resources override by identity.
    eligible.sort(key=lambda p:(target in p.relative_to(root).parts,p.as_posix().casefold()))
    for path in eligible:
        try:tree=ET.parse(path).getroot()
        except (ET.ParseError,OSError):continue
        used.append(path)
        if path.suffix.casefold()=='.vcug':
            group=tree.get('Name',path.stem);props=properties(tree);entries={}
            for entry in tree.findall('./{*}Units/{*}Unit'):
                prop=properties(entry);entries[entry.get('Name')]=prop
            units[group]={'properties':props,'entries':entries,'file':path.relative_to(root).as_posix()}
        else:
            source=tree.get('Name',path.stem)
            for entry in tree.findall('.//{*}DataPoint'):
                sources[(source.casefold(),entry.get('Name','').casefold())]=(properties(entry),path.relative_to(root).as_posix())
    pages=[p for p in files if p.suffix.casefold()=='.page' and target in p.relative_to(root).parts]
    for path in pages:
        try:tree=ET.parse(path).getroot()
        except (ET.ParseError,OSError):continue
        used.append(path)
        for control in tree.findall('.//{*}Controls/{*}Control'):
            prop=properties(control);binding=prop.get('ValueDatapoint','')
            if not valid(binding):continue
            if prop.get('Input','').casefold()=='false':continue
            style=prop.get('StyleClass','').casefold()
            if not ('input' in style or 'InputNext' in prop or valid(prop.get('InputTouchpad'))):continue
            var=variable(binding)
            if not re.fullmatch(IDENT,var):continue
            key=re.search(r'Variable\[([A-Za-z_]\w*)\.(.*)\]$',binding)
            if not key:continue
            dso,dso_path=sources.get((key.group(1).casefold(),key.group(2).casefold()),({},''))
            item={'id':f'{path.relative_to(root).as_posix()}#{control.get("Name")}',
                  'target':target,'page':path.relative_to(root).as_posix(),'control':control.get('Name'),
                  'variable':var,'displayMin':prop.get('MinValue'),'displayMax':prop.get('MaxValue'),
                  'minDatapoint':variable(prop['MinDatapoint']) if valid(prop.get('MinDatapoint')) else None,
                  'maxDatapoint':variable(prop['MaxDatapoint']) if valid(prop.get('MaxDatapoint')) else None,
                  'datasource':dso_path,'scale':'1','min':None,'max':None,'issues':[]}
            factor=Decimal(1);group_match=re.search(r'UnitGroup\[([^\]]+)\]',dso.get('UnitGroup',''))
            group=units.get(group_match.group(1)) if group_match else None
            unit_match=re.search(r'Unit\[([^\]]+)\]',dso.get('PLCUnit',''))
            if unit_match or group:
                if not group:item['issues'].append('Unit group is unresolved. Enter reviewed PLC-unit limits.')
                else:
                    gp=group['properties'];name=unit_match.group(1) if unit_match else None
                    if name is None:
                        default=re.search(r'Unit\[([^\]]+)\]',gp.get('DefaultPLCUnit',''));name=default.group(1) if default else None
                    display=re.search(r'Unit\[([^\]]+)\]',prop.get('DisplayUnit') or gp.get('DefaultDisplayUnit',''))
                    plc=group['entries'].get(name,{'Factor':'1','Offset':'0'}) if name is None else group['entries'].get(name)
                    disp=group['entries'].get(display.group(1)) if display else {'Factor':'1','Offset':'0'}
                    if not plc or not disp or any(number(p.get('Offset','0'))!=0 for p in (plc,disp)) or valid(gp.get('RuntimeUnitChange')):
                        item['issues'].append('Unit conversion needs review. Enter PLC-unit limits.')
                    else:
                        a,b=number(plc.get('Factor','1')),number(disp.get('Factor','1'))
                        if a is None or b is None or a<=0 or b<=0:item['issues'].append('Unit factors are unresolved.')
                        else:factor=a/b;item['unitSource']=group['file']
            item['scale']=literal(factor)
            if not item['issues']:
                for side in ('min','max'):
                    value=number(item['display'+side.title()])
                    if value is not None:item[side]=literal(value*factor)
                    elif valid(item['display'+side.title()]):item['issues'].append('The HMI '+side+' limit needs a reviewed PLC-unit value.')
            # Dynamic bound datapoints are already in PLC units. Keep these
            # alongside literal bounds; do not multiply their raw values again.
            rows.setdefault(var.casefold(),[]).append(item)
    return rows,used


class Study:
    def __init__(self,root,read_source='',write_source='',target=''):
        self.root=Path(root).resolve();self.files=list(project_files(self.root));self.details=local_project_details(self.root)
        self.read_candidates=candidates(self.files,'mms_nw_r');self.write_candidates=candidates(self.files,'mms_nw_w')
        def choose(options,selected,label):
            match=next((p for p in options if p.relative_to(self.root).as_posix()==selected),None) if selected else (options[0] if len(options)==1 else None)
            if match is None:raise ValueError(f'Select one {label} cyclic source. Found {len(options)} matching files.')
            if match.stat().st_size>8*1024*1024:raise ValueError('The selected ST source exceeds 8 MB.')
            return match
        self.r=choose(self.read_candidates,read_source,'mms_nw_r');self.w=choose(self.write_candidates,write_source,'mms_nw_w')
        self.rt=source_text(self.r);self.wt=source_text(self.w)
        self.rcases=cases(self.rt);self.wcases=cases(self.wt)
        reads=[c for c in self.wcases if c.function==1];writes=[c for c in self.wcases if c.function==2]
        if len(reads)!=1 or len(writes)!=1:raise ValueError('Select a writer with one function 1 and one function 2 nw_group_code CASE. Multiple handlers need a reviewed selection.')
        self.wread=reads[0];self.wwrite=writes[0]
        self.targets=sorted({p.relative_to(self.root).parts[1] for p in self.files if p.suffix.casefold()=='.page' and len(p.relative_to(self.root).parts)>2 and p.relative_to(self.root).parts[0].casefold()=='logical'})
        self.target=target or self.details.get('screenFolder') or (self.targets[0] if len(self.targets)==1 else '')
        if self.target and self.target not in self.targets:raise ValueError('Choose an HMI target from the selected project.')
        self.hmi,self.hmi_files=hmi_limits(self.root,self.files,self.target) if self.target else ({},[])
        self.support=[p for p in self.files if p.parent==self.w.parent and p!=self.w and p.suffix.casefold() in ('.var','.typ','.st','.src')]
        self.vars={}
        for p in self.support:
            if p.suffix.casefold()=='.var':self.vars.update(declarations(source_text(p)))
        self.known=set()
        for p in self.files:
            if p.suffix.casefold()=='.var':
                names=declarations(source_text(p));self.known.update(names)
                if p.parent.name.casefold()!='logical':self.known.update(p.parent.name.casefold()+'.'+name for name in names)
        tracked=sorted(set([self.r,self.w,*self.support,*self.hmi_files,*[p for p in self.files if p.name.casefold()=='lastuser.set' or p.suffix.casefold() in ('.var','.typ')]]),key=str)
        digest=hashlib.sha256()
        for p in tracked:digest.update(p.relative_to(self.root).as_posix().encode());digest.update(p.read_bytes())
        self.fingerprint=digest.hexdigest();self.groups=self._groups()

    def _groups(self):
        result=[];rmap={b.code:b for c in self.rcases if c.function==1 for b in c.branches};wrmap={b.code:b for b in self.wread.branches}
        for branch in self.wwrite.branches:
            code=branch.code;issues=[];warnings=[];read=wrmap.get(code);rread=rmap.get(code)
            layout,size,read_issues=read_layout(self.wt,read) if read else ([],0,['No function 1 read case in the writer.'])
            read_body=self.wt[read.body_start:read.end] if read else ''
            read_tree,read_refs=read_structure(read_body) if read else ([],{})
            issues.extend(read_issues);body=self.wt[branch.body_start:branch.end];clean=_mask(body,strings=True);matches=list(RECV.finditer(clean));fields=[];offset=0
            if len(re.findall(r'\bmemcpy\s*\(',clean,re.I))!=len(matches):issues.append('Write case contains extra memory copies. Review its layout before generation.')
            receive_regions=[]
            for i,match in enumerate(matches):
                stop=matches[i+1].start() if i+1<len(matches) else len(body);segment=clean[match.end():stop]
                temp=match.group(1).strip();width=int(match.group(2));type_info=self.vars.get(temp.casefold(),{});typ=type_info.get('type','')
                increments=list(re.finditer(r'\bnw_i\s*:=\s*nw_i\s*\+\s*(\d+)\s*;',segment,re.I))
                if len(increments)!=1 or int(increments[0].group(1))!=width:issues.append(f'Field {i+1}: receive cursor increment differs from the copied width.')
                if type_info.get('size') is None or (width!=type_info.get('size') and not (typ.startswith('STRING') and width<=type_info['size'])):issues.append(f'Field {i+1}: memcpy copies {width} bytes into {temp} ({typ or "unknown"}, {type_info.get("size")} bytes).')
                assigned=[]
                for dest in re.findall(r'\b('+IDENT+r')\s*:=',segment,re.I):
                    if not dest.casefold().startswith(('nw_','scw_')) and dest.casefold() not in ('step','nxt_adr','current_password_level','stringlength') and dest.casefold() not in self.vars:
                        if dest not in assigned:assigned.append(dest)
                source_assignments=list(assigned)
                # A recipe commit or staging assignment after the last copied
                # field is not a write of that field's incoming value.
                assigned=[dest for dest in assigned if re.search(r'\b'+re.escape(dest)+r'\s*:=\s*[^;]*\b'+re.escape(temp)+r'\b',segment,re.I)
                          or (typ in ('BOOL','USINT','SINT') and re.search(r'\bIF\b[^;]*\b'+re.escape(temp)+r'\b',segment,re.I)
                              and re.search(r'\b'+re.escape(dest)+r'\s*:=\s*[01]\s*;',segment,re.I))]
                rfield=next((row for row in layout if row['offset']==offset and row['size']==width),{})
                readvar=rfield.get('readVariable','');dest=assigned[0] if assigned else ''
                comment=re.search(r'\(\*(.*?)\*\)',body[match.end():].split('\n',1)[0],re.S)
                direct=re.search(r'\b'+re.escape(dest)+r'\s*:=\s*[^;]*\b'+re.escape(temp)+r'\b',segment,re.I) if dest else None
                primary=dest if direct or typ=='BOOL' or (typ in ('USINT','SINT') and assigned) else readvar or dest
                limits=self.hmi.get(primary.casefold(),[])
                unique={(item['min'],item['max'],item['minDatapoint'],item['maxDatapoint'],tuple(item['issues'])) for item in limits}
                hmi=limits[0] if len(unique)==1 and limits else None
                fields.append({'id':f'{code}:{i+1}','index':i+1,'size':width,'type':typ,
                    'readVariable':readvar,'destinations':assigned,'sourceAssignments':source_assignments,'writable':bool(assigned),'temporary':temp,
                    'description':comment.group(1).strip() if comment else dest or readvar or temp,'position':match.start(),
                    'line':self.wt.count('\n',0,branch.body_start+match.start())+1,'hmiOptions':limits,'hmiId':hmi['id'] if hmi else '',
                    'min':hmi['min'] if hmi else None,'max':hmi['max'] if hmi else None,
                    'sourceChecks':[m.group(0).strip() for m in re.finditer(r'\bIF\b[^;]*?\bTHEN\b',segment,re.I|re.S) if re.search(r'\b'+re.escape(temp)+r'\b',m.group(0),re.I)]})
                receive_regions.append(match.start());offset+=width
            tree=layout_tree(body);write_sizes=layout_sizes(tree)-{0}
            positions,endings=wire_positions(tree)
            for field in fields:
                found=sorted(positions.get(field['position'],set()))
                field['writeOffsets']=sorted({offset+7 for offset,index,conditions in found})
                field['errorPositions']=sorted({index for offset,index,conditions in found})
                field['paths']=[{'offset':o+7,'errorPosition':i,'when':' AND '.join('('+c+')' for c in conditions)} for o,i,conditions in found]
                actual_refs=set().union(*(read_refs.get((o,field['size']),set()) for o,i,c in found))
                if actual_refs:field['readVariable']=' / '.join(sorted(actual_refs))
            # A machine-state gate is not a zero-byte protocol variant.
            read_sizes=layout_sizes(read_tree)-{0}
            if read_sizes!=write_sizes:warnings.append(f'Read/write payload variants differ: read {sorted(read_sizes)}, write {sorted(write_sizes)}. Construct function 2 from the write field map, not by copying the complete read reply.')
            receive_capacity=array_capacity(self.vars.get('nw_rcv_buffer',{}));send_capacity=array_capacity(self.vars.get('nw_snd_buffer',{}));error_capacity=array_capacity(self.vars.get('nw_error_code',{}))
            if receive_capacity is None or max(write_sizes or {0})+9>receive_capacity:issues.append('The requested payload exceeds the declared receive buffer, or its bounds are unresolved.')
            if send_capacity is None or max(read_sizes or {0})+7>send_capacity:issues.append('The read response exceeds the declared send buffer, or its bounds are unresolved.')
            if error_capacity is None or max((i for o,i,c in endings),default=0)>=error_capacity:issues.append('Parameter error positions exceed the declared error buffer, or its bounds are unresolved.')
            if not read_sizes:issues.append('The fixed-address read case needs a reviewed cursor mapping before full ST generation.')
            if not matches:issues.append('No sequential received fields were found.')
            if re.search(r'\b(?:FOR|WHILE|REPEAT)\b',clean,re.I):issues.append('Loop-dependent write layout needs a reviewed mapping.')
            if re.search(r'\bCASE\b',clean,re.I):issues.append('Nested CASE-dependent write fields need a reviewed mapping.')
            assignments=[m.group(1).strip() for m in re.finditer(r'\bnw_i\s*:=\s*([^;]+);',clean,re.I)]
            if not assignments or assignments[0]!='7' or any(not re.fullmatch(r'nw_i\s*\+\s*\d+',value,re.I) for value in assignments[1:]):
                issues.append('The write cursor must start at byte 7 and advance by the copied field widths.')
            conditions=re.findall(r'IF\s*(\([^;\n]*MACHINE_STATUS[^;\n]*?)\s+THEN',clean,re.I)
            if rread:
                rlayout,rsize,rissues=read_layout(self.rt,rread)
                if rsize!=size:warnings.append(f'mms_nw_r layout totals {rsize} bytes; write-port function 1 totals {size}. Read settings from the write port before writing.')
                mismatch=[row['offset'] for row,other in zip(rlayout,layout) if row['size']!=other['size'] or row['readVariable'].casefold()!=other['readVariable'].casefold()]
            else:mismatch=[]
            header_match=re.search(r'nw_snd_buffer\[4\]\s*:=\s*(\d+)',_mask(read_body,strings=True),re.I)
            if header_match:warnings.append(f'The draft computes read response length from the actual cursor for every conditional variant; original low length byte is {header_match.group(1)}.')
            result.append({'code':code,'description':branch.description,
                'payloadVariants':sorted(write_sizes),'readPayloadVariants':sorted(read_sizes),'warnings':warnings,
                'wireLayouts':[{'payloadBytes':o,'requestBytes':o+9,'fieldCount':i,'when':' AND '.join('('+x+')' for x in c)} for o,i,c in sorted(endings) if o],
                'readLine':self.wt.count('\n',0,read.start)+1 if read else None,'writeLine':self.wt.count('\n',0,branch.start)+1,
                'readSourceLine':self.rt.count('\n',0,rread.start)+1 if rread else None,'machineConditions':list(dict.fromkeys(conditions)),
                'readDifferences':mismatch,'fields':fields,'issues':list(dict.fromkeys(issues))})
        return result

    def public(self):
        return {'projectName':self.details.get('projectFiles',[self.root.name])[0] if self.details.get('projectFiles') else self.root.name,
            'activeConfiguration':self.details.get('activeConfiguration'),'hmiTarget':self.target,'hmiTargets':self.targets,
            'readSource':self.r.relative_to(self.root).as_posix(),'writeSource':self.w.relative_to(self.root).as_posix(),
            'readSources':[p.relative_to(self.root).as_posix() for p in self.read_candidates],
            'writeSources':[p.relative_to(self.root).as_posix() for p in self.write_candidates],
            'fingerprint':self.fingerprint,'groups':self.groups,
            'notes':['Function 1 reads current PLC settings; function 2 submits the selected group values for writing.',
                     'Response payload starts at byte 5. Write values start at byte 7 after the group code. Review any read/write layout differences.',
                     'Existing machine interlocks, readonly fields, assignments and per-parameter result codes are retained.',
                     'Only the selected HMI target supplies limits. Literal limits use the datasource/unit-group scaling.']}


def bound(expression,known):
    if not valid(expression):return None
    if len(str(expression))>160:raise ValueError('A PLC-unit limit must contain at most 160 characters.')
    value=number(expression)
    if value is not None:return literal(value)
    value=str(expression).strip()
    if len(value)<=160 and re.fullmatch(IDENT,value) and (value.casefold() in known or re.split(r'[.\[]',value)[0].casefold() in known):return value
    raise ValueError('A PLC-unit limit must be a finite number, arithmetic literal, or a declared PLC variable.')


def generate(study,selected,overrides=None,reviewed=False):
    if not reviewed:raise ValueError('Review the field map, HMI limits, source checks and payload variants before generating.')
    if not study.target:raise ValueError('Select one HMI target before generating write code.')
    if not isinstance(selected,list) or not selected or len(selected)>100 or any(type(code) is not int for code in selected):raise ValueError('Select at least one group code.')
    selected=set(selected);groups=[g for g in study.groups if g['code'] in selected]
    if len(groups)!=len(selected):raise ValueError('A selected group has no existing function 2 write mapping.')
    blocking=[f'GC {g["code"]}: {issue}' for g in groups for issue in g['issues']]
    if blocking:raise ValueError('Resolve source layout findings before generating: '+' '.join(blocking))
    overrides=overrides or {}
    if not isinstance(overrides,dict) or len(overrides)>3000:raise ValueError('Invalid field review settings.')
    additions=['scw_allow : BOOL;','scw_field_ok : BOOL;','scw_pos : UINT;','scw_bool : USINT;'];write_bodies={};review=[]
    for group in groups:
        field_checks={};code=group['code']
        for field in group['fields']:
            if not field['writable']:continue
            config=overrides.get(field['id'],{})
            if not isinstance(config,dict):raise ValueError('Invalid field options.')
            hmi_id=config.get('hmiId',field['hmiId']);hmi=next((x for x in field['hmiOptions'] if x['id']==hmi_id),None)
            if field['hmiOptions'] and hmi is None:raise ValueError(f'GC {code}, field {field["index"]}: choose an HMI control for {field["destinations"][0]}.')
            try:
                lo=bound(config.get('min',hmi['min'] if hmi else None),study.known)
                hi=bound(config.get('max',hmi['max'] if hmi else None),study.known)
            except ValueError as error:raise ValueError(f'GC {code}, field {field["index"]}: {error}') from error
            if hmi and hmi['issues'] and not (lo is not None and hi is not None):raise ValueError(f'{field["destinations"][0]}: enter both reviewed PLC-unit limits; unit conversion is unresolved.')
            if lo is not None and hi is not None and number(lo) is not None and number(hi) is not None and number(lo)>number(hi):raise ValueError('Minimum limit must not exceed maximum.')
            typ=field['type'];temp=field['temporary'];clauses=[]
            if typ=='BOOL':temp='scw_bool';clauses.append('(scw_bool <= 1)')
            if typ in WIDTHS and (lo is not None or hi is not None or (hmi and any(hmi[k] is not None for k in ('min','max','minDatapoint','maxDatapoint'))) or field['type']=='BOOL'):
                if lo is not None:clauses.append(f'({temp} >= ({lo}))')
                if hi is not None:clauses.append(f'({temp} <= ({hi}))')
                if hmi:
                    for side,operator,current in (('min','>=',lo),('max','<=',hi)):
                        if hmi[side] is not None and current!=hmi[side]:clauses.append(f'({temp} {operator} ({bound(hmi[side],study.known)}))')
                    for side,operator in (('min','>='),('max','<=')):
                        if hmi[side+'Datapoint']:
                            dynamic=bound(hmi[side+'Datapoint'],study.known);clauses.append(f'({temp} {operator} ({dynamic}))')
                field_checks[field['position']]=[f'scw_field_ok := {" AND ".join(clauses)};',
                    'IF NOT scw_field_ok THEN','    nw_error_code[scw_pos] := 1;','    scw_allow := FALSE;','END_IF;']
            elif not field['sourceChecks']:raise ValueError(f'{field["destinations"][0]} has no HMI or source limit. Enter reviewed PLC-unit bounds.')
            review.append({'groupCode':code,**field,'selectedHmi':hmi,'appliedMin':lo,'appliedMax':hi,
                           'limitOrigin':'Reviewed PLC-unit override' if 'min' in config or 'max' in config else 'HMI + original write checks' if hmi else 'Original write checks'})
        branch=next(b for b in study.wwrite.branches if b.code==code);body=textwrap.dedent(study.wt[branch.body_start:branch.end]).strip()
        raw_body=study.wt[branch.body_start:branch.end]
        by_position={field['position']:field for field in group['fields']}
        def emit(nodes):
            lines=[]
            for node in nodes:
                if node['kind']=='if':
                    lines.append('IF '+node['condition']+' THEN');lines.extend('    '+x for x in emit(node['yes']))
                    if node['no']:lines.append('ELSE');lines.extend('    '+x for x in emit(node['no']))
                    lines.append('END_IF;')
                elif node['kind']=='increment':lines.append(node['text'])
                else:
                    field=by_position[node['position']];lines.append('scw_pos := scw_pos + 1;')
                    lines.append(f'IF (nw_i + {field["size"]}) <= (nw_rcv_buffer_length - 2) THEN')
                    if field['type']=='BOOL':
                        lines.append('    memcpy(ADR(scw_bool), ADR(nw_rcv_buffer[nw_i]), 1);')
                        lines.append(f'    {field["temporary"]} := (scw_bool <> 0);')
                    else:lines.append('    '+node['text'])
                    lines.extend('    '+line for line in field_checks.get(node['position'],[]))
                    lines.extend(['ELSE','    scw_allow := FALSE;','END_IF;'])
            return lines
        # Source results set status inside the original branch. Additional HMI
        # checks run first, so rejected HMI values cannot reach those writes.
        pre=[f'(* GC {code}: exact frame size and HMI limits, before source writes. *)',
             'nw_snd_buffer[2] := 0;','nw_snd_buffer[3] := 0;','nw_snd_buffer[4] := 0;',
             'nw_snd_buffer_length := 5;','nw_snd_response := TRUE;',
             'nxt_adr := memset(ADR(nw_error_code), 0, SIZEOF(nw_error_code));',
             'IF NOT HMI_EN_Write THEN','    nw_snd_buffer[2] := 18;']
        if group['machineConditions']:pre.extend(['ELSIF NOT ('+group['machineConditions'][0]+') THEN','    nw_snd_buffer[2] := 18;'])
        pre.extend(['ELSE','    nw_i := 7;','    scw_pos := 0;','    scw_allow := TRUE;'])
        pre.extend('    '+line for line in emit(layout_tree(raw_body)))
        pre.extend(['    IF (nw_i + 2) <> nw_rcv_buffer_length THEN','        nw_snd_buffer[2] := 13;',
                    '    ELSIF scw_allow THEN',textwrap.indent(body,'        '),'    ELSE','        nw_snd_buffer[2] := 16;',
                    '    END_IF;','END_IF;'])
        write_bodies[code]='\n'.join(pre)
    replacements=[]
    for case in (study.wread,study.wwrite):
        branches=[]
        for b in case.branches:
            if b.code not in selected and not (case.function==1 and b.code in (10,11)):continue
            body=write_bodies[b.code] if case.function==2 else textwrap.dedent(study.wt[b.body_start:b.end]).strip()
            if case.function==1:
                if b.code in selected:
                    body=re.sub(r'nw_snd_buffer\[([34])\]\s*:=\s*[^;]+;',lambda m:'nw_snd_buffer['+m.group(1)+'] := 0;',body,flags=re.I)
                    body=re.sub(r'nw_snd_buffer_length\s*:=\s*[^;]+;',
                        'nw_snd_buffer[3] := UINT_TO_USINT(SHR(nw_i - 5, 8));\n'
                        'nw_snd_buffer[4] := UINT_TO_USINT((nw_i - 5) MOD 256);\n'
                        'nw_snd_buffer_length := nw_i;',body,flags=re.I)
                # Read requests contain a two-byte group and no setting values.
                body='IF nw_rcv_buffer_length = 9 THEN\n'+textwrap.indent(body,'    ')+'\nELSE\n    nw_snd_buffer[2] := 13;\n    nw_snd_buffer[3] := 0;\n    nw_snd_buffer[4] := 0;\n    nw_snd_buffer_length := 5;\n    nw_snd_response := TRUE;\nEND_IF;'
            branches.append(f'{b.code}:\n'+textwrap.indent(body,'    '))
        otherwise=textwrap.dedent(case.otherwise).strip()
        replacements.append((case.start,case.end,'CASE nw_group_code OF\n'+textwrap.indent('\n\n'.join(branches),'    ')+'\n'+otherwise+'\nEND_CASE'))
    cyclic=study.wt
    for start,end,value in sorted(replacements,reverse=True):cyclic=cyclic[:start]+value+cyclic[end:]
    # Preserve the project transport/state machine; prevent undersized requests
    # from addressing the group bytes and refuse unsupported function codes.
    cyclic=re.sub(r'nw_rcv_buffer_length\s*>\s*0', 'nw_rcv_buffer_length >= 9',cyclic,count=1,flags=re.I)
    cyclic=re.sub(r'\(nw_rcv_buffer\[2\]\s*>=\s*16#01\)\s+AND\s+\(nw_rcv_buffer\[2\]\s*<=\s*16#04\)',
                  '(nw_rcv_buffer[2] = 1) OR (nw_rcv_buffer[2] = 2)',cyclic,flags=re.I)
    header=f'(* usop.ai SpinConnect write draft\n * HMI target: {study.target}\n * Groups: {", ".join(map(str,sorted(selected)))}\n * Source SHA256: {study.fingerprint}\n * Review alongside the original declarations and compile in Automation Studio.\n *)\n'
    files=[{'name':study.w.name,'text':header+cyclic}]
    added=False
    for declaration in additions:
        name,typ=declaration.rstrip(';').split(' : ')
        if name.casefold() in study.vars:raise ValueError(f'{name} is reserved for the generated guards. Use the original writer source and declarations as the reference.')
    for p in study.support:
        content=source_text(p)
        if p.suffix.casefold()=='.var' and not added:
            content+='\nVAR\n'+textwrap.indent('\n'.join(additions),'    ')+'\nEND_VAR\n';added=True
        files.append({'name':p.name,'text':content})
    if not any(p.suffix.casefold()=='.var' for p in study.support):raise ValueError('The writer variable declarations could not be found.')
    summary={'project':study.root.name,'readSource':study.r.relative_to(study.root).as_posix(),'writeSource':study.w.relative_to(study.root).as_posix(),
        'hmiTarget':study.target,'activeConfiguration':study.details.get('activeConfiguration'),'sourceFingerprint':study.fingerprint,
        'groups':sorted(selected),'layouts':[{k:g[k] for k in ('code','readPayloadVariants','payloadVariants','wireLayouts','machineConditions','warnings')} for g in groups],
        'wireFields':[{'groupCode':g['code'],**f} for g in groups for f in g['fields']],'fields':review}
    from python_engine.spinconnect_edit_map import build_edit_map
    summary['dataInspect']=build_edit_map(study,groups,review)
    files.append({'name':'write_mapping.json','text':json.dumps(summary,indent=2,ensure_ascii=False)})
    files.append({'name':'READ_ME.txt','text':
        'SpinConnect write ST draft\n\n1. Back up the selected Automation Studio project.\n'
        '2. Review write_mapping.json: group order, raw PLC units, HMI target and limits.\n'
        '3. Replace the corresponding mms_nw_w source and declaration files with the reviewed files. Keep the original program/task name and its global/retained dependencies.\n'
        '4. Compile in Automation Studio for the selected CPU configuration.\n'
        '5. Read current settings from the WRITE port using function 1 and the selected group code. Compare read/write payload variants in write_mapping.json.\n'
        '6. Build function 2 using the WRITE field order and active conditional variant. Include its readonly positions. The read reply can contain extra fields; do not copy it blindly.\n'
        '7. Check the response and read back to confirm the resulting values.\n\n'
        'The existing TCP state machine, machine-state checks, completion actions and source value checks are retained. '
        'Additional HMI checks reject the request before the original write branch. Source checks retain the original per-parameter commit behavior; a source failure can follow earlier accepted parameters. '
        'Frame assembly and timeout behavior follow the selected project transport. No PLC connection or project edit is performed by this generator.\n'
        'The r and w program names do not determine TCP direction alone: the write port also supports function 1 for reading settings.\n'})
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for item in files:archive.writestr(item['name'],item['text'].encode('utf-8'))
    return {'files':files,'groups':sorted(selected),'fingerprint':study.fingerprint,'reviewedFields':len(review),
            'bundleName':'SpinConnect_Write_ST.zip','bundleBase64':base64.b64encode(stream.getvalue()).decode('ascii')}
