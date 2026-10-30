"""Conservative C control structures in the existing function-flow representation.

No preprocessing, pointer aliasing, macro execution or runtime simulation is
performed. Unsupported constructs stay visible as semantic coverage notices.
"""
import re
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path

from python_engine.project_analysis import _mask
from python_engine.function_flow import _names
from python_engine.working_sequence import records

TOKEN=re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_]\w*|\d+(?:\.\d+)?|==|!=|<=|>=|&&|\|\||\+\+|--|->|\+=|-=|\*=|/=|[^\s]')


def c_flow(text,file):
    clean=_mask(text);notices=[]
    executable_directives=re.sub(r'^[ \t]*#(?:ifdef|ifndef)[^\n]*\n(?:[ \t]*#include[^\n]*\n|[ \t]*\n)+[ \t]*#endif[^\n]*','',clean,flags=re.M)
    if re.search(r'^\s*#\s*(?:if|ifdef|ifndef|elif|else)\b',executable_directives,re.M):
        notices.append('C conditional preprocessing is unresolved; branch availability depends on build definitions.')
    clean=re.sub(r'^\s*#[^\n]*(?:\\\n[^\n]*)*',lambda match:''.join('\n' if c=='\n' else ' ' for c in match[0]),clean,flags=re.M)
    tokens=list(TOKEN.finditer(clean));newlines=[match.start() for match in re.finditer('\n',text)]
    position=0;serial=0;sections=[]
    def token():return tokens[position][0] if position<len(tokens) else ''
    def line(index):return bisect_right(newlines,tokens[min(index,len(tokens)-1)].start())+1 if tokens else 1
    def code(first,last):
        return clean[tokens[first].start():tokens[last-1].end()].strip() if first<last else ''
    def node(kind,start,**extra):
        nonlocal serial
        serial+=1
        return {'id':f'c{serial}','kind':kind,'line':line(start),'endLine':line(max(start,position-1)),**extra}
    def parentheses():
        nonlocal position
        if token()!='(':raise ValueError(f'C condition lacks parentheses at line {line(position)}')
        position+=1;start=position;depth=1
        while position<len(tokens):
            value=token()
            if value=='(':depth+=1
            if value==')':
                depth-=1
                if not depth:
                    result=code(start,position);position+=1;return result
            position+=1
        raise ValueError('Unclosed C condition')
    def sequence(depth=0):
        nonlocal position
        if depth>80:raise ValueError('C nesting exceeds the supported bound')
        result=[]
        while token() and token()!='}':
            previous=position;result.extend(statement(depth))
            if position==previous:raise ValueError('C parser made no progress')
        return result
    def statement(depth=0):
        nonlocal position
        start=position;word=token()
        if word=='{':
            position+=1;result=sequence(depth+1)
            if token()!='}':raise ValueError('Unclosed C block')
            position+=1;return result
        if word=='if':
            position+=1;condition=parentheses();branch_line=line(start);body=statement(depth+1)
            branches=[{'label':'TRUE','condition':condition,'line':branch_line,'nodes':body}]
            if token()=='else':
                position+=1;branches.append({'label':'ELSE','condition':'','line':line(position),'nodes':statement(depth+1)})
            return [node('condition',start,condition=condition,branches=branches)]
        if word in {'while','for'}:
            position+=1;condition=parentheses();body=statement(depth+1)
            if word=='for':notices.append(f'C for-loop induction/write ordering near line {line(start)} is not simulated.')
            return [node('loop',start,condition=condition,children=body)]
        if word=='switch':
            position+=1;selector=parentheses()
            if token()!='{':raise ValueError('C switch body is unresolved')
            position+=1;branches=[];branch=None;terminated=True
            while token() and token()!='}':
                if token() in {'case','default'}:
                    default=token()=='default';label_start=position;position+=1;label_first=position
                    while token() and token()!=':':position+=1
                    label='ELSE' if default else code(label_first,position)
                    if token()!=':':raise ValueError('C case label is unresolved')
                    position+=1
                    if branch and branch['nodes'] and not terminated:
                        notices.append(f'C switch fall-through near line {line(label_start)} is unresolved.')
                    branch={'label':label,'condition':'','line':line(label_start),'nodes':[]};branches.append(branch);terminated=False
                else:
                    if branch is None:raise ValueError('C switch statement precedes a case label')
                    current=token();branch['nodes'].extend(statement(depth+1));terminated=current in {'break','return','goto'}
            if token()!='}':raise ValueError('Unclosed C switch')
            position+=1;return [node('case',start,condition=selector,branches=branches)]
        # Scan one declaration, function definition or executable statement.
        balance=0
        while token():
            value=token()
            if not balance and value in {';','{','}'}:break
            if value in {'(','['}:balance+=1
            elif value in {')',']'}:balance-=1
            position+=1
        header=code(start,position)
        if token()=='{':
            if re.match(r'^(?:typedef\s+)?(?:struct|union|enum)\b',header):
                nesting=0
                while token():
                    if token()=='{':nesting+=1
                    elif token()=='}':
                        nesting-=1
                        if not nesting:position+=1;break
                    position+=1
                while token() and token()!=';':position+=1
                if token()==';':position+=1
                return []
            body=statement(depth+1)
            function=re.search(r'\b([A-Za-z_]\w*)\s*\([^;]*\)\s*$',header,re.S)
            if function:
                sections.append({'name':function[1],'kind':'function','line':line(start),'nodes':body})
                return []
            notices.append(f'C aggregate, macro or unsupported block near line {line(start)} needs review.')
            return body
        if token()==';':position+=1
        elif token()=='}' and not header:return []
        if not header:return []
        if re.search(r'\b(?:goto|do)\b|\?|->|\*\s*[A-Za-z_]\w*\s*=',header):
            notices.append(f'C pointer, conditional expression or nonlocal control flow near line {line(start)} is unresolved.')
        if re.search(r'\+\+|--|[+*/-]=',header):notices.append(f'C compound or increment write near line {line(start)} is unresolved.')
        if word=='return' and depth>2:
            notices.append(f'C early return near line {line(start)}: subsequent path reachability is unresolved.')
        if word in {'return','break','continue','goto'}:return [node('exit',start,condition=header)]
        row={'code':header,'line':line(start),'endLine':line(max(start,position-1)),'kind':'assignment' if re.match(r'^[\w.\[\]]+\s*=(?!=)',header) else 'source'}
        return [node('action',start,label='C source statements',statements=[row])]
    try:
        top=sequence()
        if top:sections.insert(0,{'name':Path(file).stem,'nodes':top})
        if token():notices.append(f'Unmatched C closing block at line {line(position)}')
    except (ValueError,RecursionError) as error:
        notices.append(str(error))
    variables=defaultdict(lambda:{'reads':set(),'writes':set()});calls=[]
    for section in sections:
        for record in records(section['nodes']):
            row=record['row'];assignment=re.match(r'^([A-Za-z_]\w*(?:\.\w+|\[[^]]+\])*)\s*=(?!=)\s*(.+)$',row['code'],re.S)
            if assignment:variables[assignment[1]]['writes'].add(row['line'])
            for name in _names(assignment[2] if assignment else row['code']):variables[name]['reads'].add(row['line'])
            for name in re.findall(r'\b([A-Za-z_]\w*)\s*\(',_mask(row['code'],strings=True)):
                if name not in {'sizeof','if','while','for','switch'}:calls.append({'name':name,'instance':name,'line':row['line'],'code':row['code']})
    variable_rows=[{'name':name,'reads':sorted(value['reads']),'writes':sorted(value['writes'])} for name,value in variables.items()]
    return sections,variable_rows,calls,list(dict.fromkeys(notices))
