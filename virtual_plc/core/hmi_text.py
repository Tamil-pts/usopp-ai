"""Bounded VC4 text snippets shared by display text and password matching."""
import math
import re


def bound(settings,key,default):
    value=settings.get(key)
    number=default if value in (None,'','None','<None>') else int(value)
    if not 0<=number<=4096:raise ValueError('Text snippet character limit is invalid.')
    return number


def snippet_text(snippet,runtime,require_initialized=False):
    settings=snippet.get('properties',{})
    value=runtime.get_value(snippet.get('binding') or '')
    kind=str(snippet.get('classId','')).lower()
    if kind=='0x00002002':
        if not isinstance(value,str) or (require_initialized and not value):raise ValueError('STRING snippet is uninitialized.')
        text=value
    elif kind=='0x00002001':
        if type(value) not in {int,float} or not math.isfinite(value):raise ValueError('Numeric text snippet is unresolved.')
        if value!=int(value):raise ValueError('Fractional numeric text snippet formatting is not supported.')
        if any(settings.get(k) not in (None,'','None','0') for k in ('FractionDigits','MinFractionDigits','MaxFractionDigits','AdditionalFractionDigits')):
            raise ValueError('Numeric snippet has unsupported fraction formatting.')
        digits=bound(settings,'MinIntegerDigits',1)
        text=('-' if value<0 else '')+str(abs(int(value))).zfill(digits)
    else:raise ValueError('Text snippet type is unsupported.')
    minimum=bound(settings,'MinChars',0);maximum=bound(settings,'MaxChars',4096)
    if maximum<minimum:raise ValueError('Text snippet character range is invalid.')
    text=text[:maximum]
    if len(text)<minimum:
        fill=settings.get('FillCharacter',' ')
        if not isinstance(fill,str) or len(fill)!=1:raise ValueError('Text snippet fill character is unresolved.')
        alignment=str(settings.get('Alignment','Right')).lower()
        if alignment=='left':text=text.ljust(minimum,fill)
        elif alignment=='right':text=text.rjust(minimum,fill)
        elif alignment=='center':text=text.center(minimum,fill)
        else:raise ValueError('Text snippet alignment is unsupported.')
    return text


def expand_text(text,snippets,runtime,require_initialized=False):
    if not isinstance(text,str) or len(text)>16384:raise ValueError('Text template exceeds the supported size.')
    def replace(match):
        snippet=snippets.get(match[1])
        if not snippet:raise ValueError('Text snippet reference is unresolved.')
        return snippet_text(snippet,runtime,require_initialized)
    result=re.sub(r'\{([^{}]+)\}',replace,text)
    if len(result)>16384:raise ValueError('Expanded text exceeds the supported size.')
    return result


def display_text(model,control,runtime):
    props=control.get('properties',{})
    mode=props.get('TextSource','')
    if mode=='SingleString':
        value=runtime.get_value(control.get('textBinding') or '')
        if not isinstance(value,str):raise ValueError('HMI text binding is not a STRING.')
        return value
    if mode=='MultipleTexts':
        path=control.get('textGroup');groups=model.get('hmi',{}).get('textGroups',{})
        raw=runtime.get_value(control['textIndexBinding']) if control.get('textIndexBinding') else 0
        index=int(raw)+int(props.get('TextIndexOffset') or (props.get('TextIndex') if control.get('kind')=='button' else 0) or 0)
        entries=groups.get(path,{}).get(str(index),{})
        text=entries.get('en',next(iter(entries.values()),'')) if isinstance(entries,dict) else str(entries)
        return expand_text(text,model.get('hmi',{}).get('textSnippets',{}).get(path,{}),runtime)
    return None
