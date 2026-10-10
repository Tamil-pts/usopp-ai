"""Excel cell types required by the SpinConnect metadata importer."""
import math
import re


def metadata_numeric_value(value):
    """Convert literal numbers to Excel numbers, preserving nulls and expressions."""
    if isinstance(value, str):
        text = value.strip().replace('\u00a0',' ')
        if len(text)>1 and text[0]==text[-1] and text[0] in {'"',"'"}:
            text=text[1:-1].strip()
        text=re.sub(r'^(?:REAL|LREAL|S?INT|U?DINT|U?INT|USINT)\s*#\s*','',text,flags=re.I)
        if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text):
            number = float(text)
            if math.isfinite(number):
                return number
    return value


def normalize_metadata_workbook(workbook):
    """Enforce numeric XML cells and General format at the final export boundary."""
    issues=[]
    for sheet in workbook.worksheets:
        headers={str(c.value or ''):c.column for c in sheet[1]}
        if not any(re.sub(r'[^a-z0-9]','',h.casefold())=='groupcode' for h in headers):
            continue
        for header,column in headers.items():
            if not is_numeric_metadata_header(header): continue
            for cells in sheet.iter_rows(min_row=2,min_col=column,max_col=column):
                cell=cells[0]
                value=metadata_numeric_value(cell.value)
                if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value):
                    cell.value=value
                    cell.number_format='General'
                elif value is None or str(value).strip().casefold() in {'','<null>','null','none'}:
                    cell.value='<null>' if value is not None and str(value).strip() else None
                    cell.number_format='General'
                else:
                    issues.append({'sheet':sheet.title,'cell':cell.coordinate,'column':header,'value':str(value),'issue':'Limit/factor is not a numeric literal; resolve it before importing into SpinConnect.'})
    return issues


def is_numeric_metadata_header(header):
    return re.sub(r"[^a-z0-9]", "", str(header).lower()) in {
        "min", "max", "offsetfactor", "scalefactor",
    }
