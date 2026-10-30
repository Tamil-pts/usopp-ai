"""Recover PDF text from embedded font maps, without OCR or editing originals."""
from collections import defaultdict
from io import BytesIO
import unicodedata

from fontTools.ttLib import TTFont,TTLibError
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject


def extraction_copy(reader):
    """Build missing Identity-CID ToUnicode maps from the embedded TrueType cmap.

    Never infer a character from the other drawing or from a fixed CID offset.
    Ambiguous glyphs remain undecoded. Non-Identity/custom encodings are left to
    the PDF parser. The returned in-memory copy is for extraction only.
    """
    writer = PdfWriter(); writer.clone_document_from_reader(reader)
    visited = set();visited_resources=set(); recovered = []; unresolved = []

    def visit(resources):
        if not resources: return
        resources = resources.get_object()
        if id(resources) in visited_resources:return
        visited_resources.add(id(resources))
        fonts=resources.get('/Font') or {}
        if hasattr(fonts,'get_object'):fonts=fonts.get_object()
        for _, reference in fonts.items():
            font = reference.get_object()
            identity = id(font)
            if identity in visited: continue
            visited.add(identity)
            if font.get('/ToUnicode') or font.get('/Subtype') != '/Type0' or str(font.get('/Encoding')) not in {'/Identity-H', '/Identity-V'}:
                continue
            try:
                descendant = font['/DescendantFonts'][0].get_object()
                descriptor = descendant['/FontDescriptor'].get_object()
                blob = descriptor['/FontFile2'].get_object().get_data()
                if len(blob) > 20 * 1024 * 1024: raise ValueError('Embedded font exceeds extraction limit')
                with TTFont(BytesIO(blob), lazy=False) as ttf:
                    by_gid = defaultdict(set)
                    for codepoint, glyph in (ttf.getBestCmap() or {}).items():
                        value = unicodedata.normalize('NFKC', chr(codepoint)).translate(str.maketrans({'\u00ad': '-', '\u2010': '-', '\u2011': '-'}))
                        by_gid[ttf.getGlyphID(glyph)].add(value)
                    glyphs = {gid: next(iter(values)) for gid, values in by_gid.items() if len(values) == 1}
                gid_map = descendant.get('/CIDToGIDMap')
                if gid_map and str(gid_map) != '/Identity':
                    raw = gid_map.get_object().get_data()
                    mapping = {cid: glyphs[gid] for cid in range(min(65536, len(raw) // 2))
                               if (gid := int.from_bytes(raw[cid * 2:cid * 2 + 2], 'big')) in glyphs}
                else:
                    mapping = {gid: value for gid, value in glyphs.items() if gid <= 65535}
                if not mapping: raise ValueError('No unambiguous Unicode glyph mappings')
                lines = ['/CIDInit /ProcSet findresource begin', '12 dict begin', 'begincmap',
                         '/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def',
                         '/CMapName /CircuitExtractionUnicode def', '/CMapType 2 def',
                         '1 begincodespacerange', '<0000> <ffff>', 'endcodespacerange']
                pairs = sorted(mapping.items())
                for start in range(0, len(pairs), 100):
                    chunk = pairs[start:start + 100]; lines.append(f'{len(chunk)} beginbfchar')
                    lines.extend(f'<{cid:04x}> <{value.encode("utf-16-be").hex()}>' for cid, value in chunk)
                    lines.append('endbfchar')
                lines.extend(['endcmap', 'CMapName currentdict /CMap defineresource pop', 'end', 'end'])
                stream = DecodedStreamObject(); stream.set_data('\n'.join(lines).encode('ascii'))
                font[NameObject('/ToUnicode')] = writer._add_object(stream)
                recovered.append({'font': str(font.get('/BaseFont')), 'mappings': len(mapping),
                                  'method': 'embedded TrueType cmap and CID-to-glyph mapping'})
            except (KeyError, ValueError, TypeError, OSError,TTLibError) as exc:
                unresolved.append({'font': str(font.get('/BaseFont')), 'reason': str(exc)[:180]})
        forms=resources.get('/XObject') or {}
        if hasattr(forms,'get_object'):forms=forms.get_object()
        for _, reference in forms.items():
            form = reference.get_object()
            if form.get('/Subtype') == '/Form': visit(form.get('/Resources'))

    for page in writer.pages: visit(page.get('/Resources'))
    info = {'recoveredFonts': recovered, 'unresolvedFonts': unresolved, 'originalModified': False}
    if not recovered: return None, info
    buffer = BytesIO(); writer.write(buffer); buffer.seek(0)
    return buffer, info
