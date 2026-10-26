"""Read bounded Simple.dob string tables used by source HMI help programs.

B&R reference: programming/dataobjects/simple/general syntax and special
characters. Double quotes append NUL; single quotes do not. Other data-object
formats remain unresolved rather than being populated with invented bytes.
"""
import base64
from pathlib import Path
import re
import xml.etree.ElementTree as ET

MAX_BYTES=4*1024*1024
TOKEN=re.compile(r'''\s+|,|;[^\n]*|\(\*[\s\S]*?\*\)|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*' ''',re.X)


def string_table(text):
    output=bytearray();position=0
    for token in TOKEN.finditer(text):
        if token.start()!=position:raise ValueError('Only quoted-string data objects are supported.')
        position=token.end();raw=token.group()
        if raw[0] not in "\"'":continue
        value=raw[1:-1];index=0
        while index<len(value):
            char=value[index];index+=1
            if char!='\\':output.extend(char.encode('latin-1'));continue
            if index==len(value):raise ValueError('Incomplete data-object escape.')
            char=value[index];index+=1
            escapes={'a':7,'b':8,'e':27,'f':12,'n':10,'r':13,'t':9,"'":39,'"':34,'\\':92}
            if char in escapes:output.append(escapes[char])
            elif char=='x':
                digits=re.match(r'[0-9a-fA-F]{1,2}',value[index:])
                if not digits:raise ValueError('Invalid hexadecimal escape.')
                output.append(int(digits[0],16));index+=len(digits[0])
            elif char in '01234567':
                digits=re.match(r'[0-7]{0,2}',value[index:])[0]
                output.append(int(char+digits,8));index+=len(digits)
            else:raise ValueError('Unsupported data-object escape.')
        if raw[0]=='"':output.append(0)
        if len(output)>MAX_BYTES:raise ValueError('Data-object byte limit exceeded.')
    if text[position:].strip():raise ValueError('Only quoted-string data objects are supported.')
    return bytes(output)


def read_data_objects(root,sources,diagnostics):
    root=Path(root).resolve();definitions=[Path(p) for p in sources if p.lower().endswith('.dob')]
    # Saved adapters before 7 did not cache the .dob descriptors. Use their
    # available source root only; every referenced file remains inside it.
    if not definitions and (root/'Logical').is_dir():
        for path in (root/'Logical').rglob('*.dob'):
            if len(definitions)>=256:break
            definitions.append(path.relative_to(root))
    result=[];total=0;names=set()
    for source in definitions[:256]:
        try:
            path=(root/source).resolve()
            if not path.is_relative_to(root):continue
            raw=sources.get(source.as_posix())
            if raw is None:
                if path.stat().st_size>1024*1024:raise ValueError('Descriptor size limit exceeded.')
                raw=path.read_bytes()
            doc=ET.fromstring(raw)
            if doc.tag.rsplit('}',1)[-1]!='DataObject':continue
            files=[n.text for n in doc.iter() if n.tag.rsplit('}',1)[-1]=='File' and n.text]
            if not files or any(Path(p).suffix.lower()!='.dat' for p in files):continue
            data=bytearray()
            for filename in files:
                resource=(path.parent/filename.replace('\\','/')).resolve()
                if not resource.is_relative_to(root):raise ValueError('Data-object source leaves the project.')
                relative=resource.relative_to(root).as_posix();text=sources.get(relative)
                if text is None:
                    if resource.stat().st_size>1024*1024:raise ValueError('Source size limit exceeded.')
                    text=resource.read_bytes().decode('latin-1')
                data.extend(string_table(text))
                if len(data)>MAX_BYTES:raise ValueError('Data-object byte limit exceeded.')
            name=path.parent.name
            if name in names:raise ValueError('Duplicate data-object name; source module is ambiguous.')
            if not data or total+len(data)>MAX_BYTES:raise ValueError('Project data-object byte limit exceeded.')
            result.append({'name':name,'source':source.as_posix(),'bytes':len(data),'base64':base64.b64encode(data).decode('ascii')})
            total+=len(data);names.add(name)
        except (OSError,ValueError,UnicodeError,ET.ParseError) as error:
            diagnostics.append({'severity':'warning','code':'hmi-data-object-unresolved','source':source.as_posix(),'message':str(error)[:300]})
    return result
