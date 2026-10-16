"""Network presence/order checks and structural reference matching for B&R ladder."""
import re
import xml.etree.ElementTree as ET

def tag(node): return node.tag.rsplit('}',1)[-1].lower()

def fragment(text):
    # AS 2.7 .prg files can contain separate XML documents for CODE_INIT,
    # CODE_CYCLIC and CODE_EXIT. Parse each <networks> section independently
    # instead of slicing from the first opening tag to the last closing tag.
    sections=re.findall(r'<networks\b[^>]*>.*?</networks\s*>',text,flags=re.I|re.S)
    if sections:
        result=[]
        for section in sections:
            clean=re.sub(r'<\?.*?\?>','',section,flags=re.S).strip()
            root=ET.fromstring(clean)
            result.extend(node for node in root if tag(node)=='network')
        return result
    network_sections=re.findall(r'<network\b[^>]*>.*?</network\s*>',text,flags=re.I|re.S)
    if network_sections:
        return [ET.fromstring(re.sub(r'<\?.*?\?>','',section,flags=re.S).strip()) for section in network_sections]
    text=re.sub(r'<\?.*?\?>','',text,flags=re.S).strip()
    if not text.startswith('<network'):
        text='<network>'+ (text if text.startswith('<row') else '<row>'+text+'</row>')+'</network>'
    return [ET.fromstring(text)]

def signature(node):
    ignored={'label','comment','row','column','commented'} if tag(node)=='network' else set()
    return (tag(node),tuple(sorted((k,v) for k,v in node.attrib.items() if k not in ignored)),tuple(signature(c) for c in node))

def elements(network):
    headers={};out=[]
    for row in network:
        for column,node in enumerate(row):
            if tag(node) not in {'contact','coil','functionblock'}: continue
            values=dict(node.attrib);values['kind']=tag(node)
            if tag(node)=='functionblock':
                if node.get('position')=='header': headers[column]=node.get('name','')
                values['name']=node.get('name') or headers.get(column,'')
                values['inputs']=[c.get('name','') for c in node if tag(c)=='input']
                values['outputs']=[c.get('name','') for c in node if tag(c)=='output']
            out.append(values)
    return out

def network_errors(networks):
    problems=[]
    ids=[n.get('id') for n in networks]
    if not networks: return ['Add a ladder network check.']
    if len(set(ids))!=len(ids) or not all(ids): return ['Network checks need unique IDs.']
    for n in networks:
        if n.get('relation','presence') not in {'presence','before','after','immediately_before','immediately_after'}: problems.append('Choose a valid network relationship.')
        if n.get('relation','presence')!='presence' and (n.get('relativeTo') not in ids or n.get('relativeTo')==n['id']): problems.append('Choose another network check for the relationship.')
        if n.get('mode')=='exact':
            try:
                parsed=fragment(n.get('xml',''))
                if len(parsed)!=1 or not any(tag(node) in {'contact','coil','functionblock','function','analog'} for node in parsed[0].iter()): problems.append('Select one reference network containing ladder elements per check.')
            except (ET.ParseError,ValueError): problems.append('The reference network XML is incomplete or invalid.')
        elif not n.get('elements'): problems.append('Add a contact, coil or function block.')
        else:
            for e in n['elements']:
                if e.get('kind') not in {'contact','coil','functionblock'}: problems.append('Unsupported ladder element.')
                if not e.get('type'): problems.append('Select an element type.')
                if e.get('kind')!='functionblock' and not e.get('name','').strip(): problems.append('Enter the contact or coil PLC tag.')
    return problems

def errors(check):
    stored=list(check.get('ladderAlternatives') or [])
    variants=[check.get('networks') or []]+[(item.get('networks') or []) if isinstance(item,dict) else item for item in stored]
    problems=[]
    for index,item in enumerate(stored,1):
        if isinstance(item,dict) and not str(item.get('file') or '').strip():
            problems.append(f'Accepted ladder alternative {index}: enter its ladder file or subroutine.')
    for index,networks in enumerate(variants):
        prefix='' if index==0 else f'Accepted ladder alternative {index}: '
        problems.extend(prefix+problem for problem in network_errors(networks))
    return problems

def element_matches(a,e):
    for k in ['kind','type','name','position']:
        if str(e.get(k) or '').strip() and str(a.get(k) or '').casefold()!=str(e[k]).strip().casefold(): return False
    for k in ['inputs','outputs']:
        wanted=e.get(k) or []
        if isinstance(wanted,str): wanted=[x.strip() for x in wanted.split(',') if x.strip()]
        if not {v.casefold() for v in wanted}<={v.casefold() for v in a.get(k,[])}: return False
    return True

def matches(network,expected):
    if expected.get('mode')=='exact': return signature(network)==signature(fragment(expected['xml'])[0])
    actual=elements(network)
    choices=[[i for i,a in enumerate(actual) if element_matches(a,e)] for e in expected.get('elements',[])]
    def assign(index,used):
        return index==len(choices) or any(assign(index+1,used|{i}) for i in choices[index] if i not in used)
    return bool(choices) and assign(0,set())

def mismatch_details(active,expected):
    """Explain the closest active network when strict element matching fails."""
    wanted=expected.get('elements') or []
    if expected.get('mode')=='exact':
        return 'No active network has the configured complete network structure.'
    ranked=[]
    for number,network in active:
        actual=elements(network);score=0;details=[]
        for item in wanted:
            exact=next((a for a in actual if element_matches(a,item)),None)
            kind=str(item.get('kind') or 'element')
            name=str(item.get('name') or '').strip()
            expected_type=str(item.get('type') or '').strip()
            if exact is not None:
                score+=3
                details.append(f'{kind} {name or expected_type}: matched ({expected_type})')
                continue
            same_name=next((a for a in actual if str(a.get('kind') or '').casefold()==kind.casefold() and name and str(a.get('name') or '').casefold()==name.casefold()),None)
            if same_name is not None:
                score+=2
                found_type=str(same_name.get('type') or 'unspecified')
                details.append(f'{kind} {name}: expected type {expected_type or "any"}; found {found_type}')
            else:
                details.append(f'{kind} {name or expected_type}: missing')
        ranked.append((score,number,details))
    if not ranked:
        return 'No active ladder networks were found.'
    score,number,details=max(ranked,key=lambda item:(item[0],-item[1]))
    return f'Closest active network {number}: ' + '; '.join(details)

def evaluate_networks(active,expected,alternative):
    choices={e['id']:[i for i,n in active if matches(n,e)] for e in expected}
    def ordered(a,b,relation):
        return {'before':a<b,'after':a>b,'immediately_before':a+1==b,'immediately_after':a==b+1}.get(relation,True)
    def search(index,selected):
        if index==len(expected): return selected
        e=expected[index]
        for value in choices[e['id']]:
            chosen={**selected,e['id']:value}
            if all(n.get('relation','presence')=='presence' or n['id'] not in chosen or n.get('relativeTo') not in chosen or ordered(chosen[n['id']],chosen[n['relativeTo']],n['relation']) for n in expected):
                found=search(index+1,chosen)
                if found is not None:return found
        return None
    found=search(0,{})
    rows=[{'ladderAlternative':alternative,'networkCheck':i+1,'matchingNetworks':choices[e['id']],'matchedNetwork':(found or {}).get(e['id']),'relationship':e.get('relation','presence'),'relativeTo':e.get('relativeTo'),'expected':e,'actual':mismatch_details(active,e) if not choices[e['id']] else 'Matched' if found is not None else 'Network order requirements could not be satisfied'} for i,e in enumerate(expected)]
    names={e['id']:str(e.get('label') or '').strip() or f'Network check {i+1}' for i,e in enumerate(expected)}
    for row,e in zip(rows,expected):
        name=names[e['id']]
        row['networkName']=name
        relation=e.get('relation','presence')
        if relation=='presence':
            row['expectedOrder']=f'{name} must be present; no additional order constraint.'
        else:
            other=e['relativeTo']
            first,second=(e['id'],other) if relation.endswith('before') else (other,e['id'])
            qualifier='immediately ' if relation.startswith('immediately') else ''
            row['expectedOrder']=f'{names[first]} must come {qualifier}before {names[second]}. First: {names[first]}. Then: {names[second]}.'
            row['actualOrder']=(f'{names[first]}: network {found[first]}; {names[second]}: network {found[second]}.' if found is not None
                                else f'{names[first]} found in networks {choices[first] or "none"}; {names[second]} found in networks {choices[second] or "none"}. No assignment satisfies all configured order requirements.')
    return found is not None,rows

def evaluate(source,check):
    problems=errors(check)
    if problems: return False,[{'actual':problem} for problem in problems]
    try: networks=fragment(source)
    except (ET.ParseError,ValueError) as error: return False,[{'actual':'Invalid ladder source: '+str(error)}]
    active=[(i,n) for i,n in enumerate(networks,1) if n.get('commented','0').lower() in {'0','false',''}]
    variants=[check.get('networks') or []]+[(item.get('networks') or []) if isinstance(item,dict) else item for item in check.get('ladderAlternatives') or []]
    failures=[]
    for alternative,expected in enumerate(variants,1):
        passed,rows=evaluate_networks(active,expected,alternative)
        if passed:
            for row in rows: row['matchedAlternative']=alternative
            return True,rows
        failures.extend(rows)
    return False,failures
