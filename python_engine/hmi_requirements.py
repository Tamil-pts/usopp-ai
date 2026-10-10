"""Readable HMI property requirements; match properties on a single control."""
import re
import xml.etree.ElementTree as ET

ALIASES={'runtime/controlid':'ControlID','runtime/controllD'.lower():'ControlID','runtime/statusdatapoint':'StatusDatapoint',
         'completion/datapoint':'CompletionDatapoint','completion/value':'CompletionValue','completion/locking':'CompletionLocking'}

def property_value(name,value):
    value=str(value).strip()
    if value.casefold() in {'<none>','none'}: return 'None'
    if name=='InputTouchpad' and value and not value.startswith('Source['):return f'Source[local].TouchPad[{value}]'
    if name.endswith('Datapoint') and value and not value.startswith('Source['):return f'Source[global].Variable[{value}]'
    return value

def parse_requirements(text):
    text=str(text or '').strip()
    if text.startswith('<') and not text.startswith('<None>'):
        root=ET.fromstring('<Reference>'+re.sub(r'<\?xml.*?\?>','',text,flags=re.S)+'</Reference>')
        records=[]
        for control in root.iter():
            if control.tag.split('}')[-1]!='Control':continue
            records.append({'name':control.get('Name',''),'nameMode':'exact','properties':{node.get('Name'):node.get('Value','') for node in control if node.tag.split('}')[-1]=='Property'}})
        if not records:raise ValueError('The reference must contain a Control, or enter Name = String and property = value lines.')
        return records
    records=[];current={'name':'','nameMode':'prefix','properties':{}}
    for number,line in enumerate(text.splitlines(),1):
        line=line.strip()
        if not line or line=='---':continue
        if '=' not in line:
            if re.fullmatch(r'[\w/ ]+',line):continue # a blank property field is not a requirement
            raise ValueError(f'HMI line {number}: use Property = Value.')
        name,value=(part.strip() for part in line.split('=',1))
        if name.casefold()=='name':
            if current['name'] or current['properties']:records.append(current);current={'name':'','nameMode':'prefix','properties':{}}
            current['name']=value
        elif name.casefold() in {'name matching','namematching'}:
            if value.casefold() not in {'prefix','exact'}:raise ValueError('Name matching must be Prefix or Exact.')
            current['nameMode']=value.casefold()
        elif value:
            name=ALIASES.get(name.casefold(),name)
            if name in current['properties']:raise ValueError(f'Duplicate HMI property: {name}')
            current['properties'][name]=property_value(name,value)
    if current['name'] or current['properties']:records.append(current)
    if not records:raise ValueError('Enter a control Name and at least one Property = Value requirement.')
    return records

def reference_xml(records):
    root=ET.Element('Reference')
    for record in records:
        control=ET.SubElement(root,'Control',Name=record['name'])
        for key,value in record['properties'].items():ET.SubElement(control,'Property',Name=key,Value=value)
    return ''.join(ET.tostring(child,encoding='unicode') for child in root)

def compare_control(control,requirement):
    props={node.get('Name'):node.get('Value','') for node in control if node.tag.split('}')[-1]=='Property'}
    def normalized(key,value):
        value=property_value(key,value)
        if key.endswith('Datapoint') or key=='InputTouchpad':return value.casefold()
        if value.casefold() in {'true','false','none'}:return value.casefold()
        return value
    return {key:{'expected':value,'actual':props.get(key),'status':'PASS' if key in props and normalized(key,props[key])==normalized(key,value) else 'FAIL'} for key,value in requirement['properties'].items()}

def control_candidates(text,requirement):
    root=ET.fromstring(text);name=requirement.get('name','').casefold()
    for control in root.iter():
        if control.tag.split('}')[-1]!='Control':continue
        actual=control.get('Name','').casefold()
        if name and not (actual.startswith(name) if requirement.get('nameMode')=='prefix' else actual==name):continue
        yield control,compare_control(control,requirement)
