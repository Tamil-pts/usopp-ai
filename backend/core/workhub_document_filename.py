"""Portable download names use the document's issued identity and revision."""
import re


def filename(document,revision,format):
    number=str(document.get('number') or 'Native-'+str(document.get('id','document'))[:8].upper())
    label=str(revision.get('label') or 'R'+str(revision.get('number',1)).zfill(2))
    def safe(value,limit):
        return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-',value).strip(' .')[:limit].rstrip(' .') or 'Document'
    return safe(number,150)+'-'+safe(label,30)+'.'+format
