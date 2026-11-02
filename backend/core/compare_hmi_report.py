"""Embed the shared MatchView inspector in a portable, offline HTML report."""
import json
import re
from pathlib import Path


def interactive_screen(diff, base_name, developed_name, fallback, *, skip_layout=False):
    layouts=(diff.get('parsed_screen') or {}).get('layouts') or {}
    if not any((layout or {}).get('layers') for layout in layouts.values()):return fallback
    # Escape HTML delimiters even though this is a non-executable JSON script.
    # PLC text, labels and configured properties are evidence, never markup.
    payload=json.dumps({'screen':{'layouts':layouts},'baseLabel':base_name,'newLabel':developed_name,
                        'skipLayout':skip_layout},ensure_ascii=True,separators=(',',':'))
    payload=payload.replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e')
    return ('<div class="report-hmi" data-hmi-report><div data-hmi-mount></div>'
            '<script type="application/json" data-hmi-data>'+payload+'</script>'
            '<div class="report-hmi-static">'+fallback+'</div></div>')


def viewer_assets():
    from backend.core.runtime import RESOURCE_ROOT
    directory=RESOURCE_ROOT/'dist'/'report-assets'
    script=directory/'hmi-report.js';style=directory/'hmi-report.css'
    if not script.is_file() or not style.is_file():return ''
    # Inline both assets: downloaded reports work without the server or internet.
    source=re.sub(r'</script',r'<\\/script',script.read_text(encoding='utf-8'),flags=re.I)
    return '<style>'+style.read_text(encoding='utf-8')+'</style><script>'+source+'</script>'
