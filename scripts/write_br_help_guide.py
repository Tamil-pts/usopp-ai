"""Render the single readable guide from the bundled structured topics."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PIPELINE = {
    'id': 'decoding-pipeline', 'title': 'How uSOPp transforms source files into structured evidence',
    'category': 'Decoding pipeline',
    'keywords': ['decode', 'parser', 'structured', 'format', 'ladder', 'screen', 'st', 'evidence', 'syntax'],
    'summary': 'Read bytes, resolve the active target, parse each format, preserve source locations, then render or retrieve the structured records.',
    'details': [
        'Discovery: compare.project_identity/project_info resolve project descriptors, active Physical configuration, task sources and HMI package. AS 2.7 may use pgm/<program>/<CPU>/*.src and Logical/HMI/Pages. Ambiguous target selection remains unresolved. project_paths.project_files prunes temporary/generated directories before reading files; it does not apply those exclusions to vendor manuals.',
        'Ladder: compare._ladder_networks extracts the <networks> XML section from an .ld source, retaining network order, labels, comments and commented state. ladder_model.network_model records cells with kind, row, logical column, original XML column, span, name, type, attributes, pins and IDs. Functions/function blocks span two logical columns. Header/top/middle/bottom pieces are joined by logical column and type, retaining the instance and block ID. Series wires join adjacent conducting endpoints; OR markers connect the right boundary to the preceding upper junction. Unknown elements, unmatched segments and missing junctions produce warnings. Do not flatten parallel branches into an AND list.',
        'Ladder enrichment/rendering: declaration_symbols/apply_symbols attach declared types, descriptions and source/declaration locations. normalized_model upgrades older saved geometry. primitives creates rails, contact/coil symbols, wires and function blocks for SVG and PNG rendering; diagram_panels splits large networks for reports. Comparison aligns ordered networks and checks cell/pin/geometry signatures. Drawing is a source view, not a PLC simulator. project_knowledge.ladder_behaviour explains only supported simple-series semantics; complex networks keep topology and unresolved block internals.',
        'HMI: compare._xml_controls reads named XML controls, ClassId and direct Property names/values; _page_properties reads screen properties. parse_screen_diff compares control identities and grouped properties. hmi_screen_layout separately resolves layers/references, inherited styles, scoped layer/control IDs, z-order, text/font/bitmap/virtual-key references and preview geometry. The plain control diff is not a complete HMI runtime parser; keep source text chunks for original file/line evidence. Text groups retain numeric text/value IDs and language strings; snippets retain datapoint/type/format details. Preview resolves local datapoints, text/bitmap groups, palette/font references and position. Nested property paths distinguish released/pressed bitmap states. Missing assets remain unresolved; a rendered preview is not a live HMI. Overlapping controls must remain independently selectable in the control/property list.',
        'Structured Text/Automation Basic: decode_bytes handles source encoding; project_knowledge.declarations records names, declaration expressions, inclusive array bounds and lines. Chunking retains original file/line and task ownership. source_calls extracts literal calls; conditional_behaviour extracts a small set of direct IF-branch assignments with comments removed without shifting lines. Deterministic rule engines separately check configured patterns and cross-source requirements. This is bounded static extraction, not a complete ST compiler, execution trace or proof that every statement runs. Preserve language-specific assignment and END_IF/ENDIF syntax.',
        'C: retain _INIT/_CYCLIC/_EXIT entry points, declarations/includes, literal expressions and line references. Resolve B&R generated headers and library declarations before interpreting a pointer or function-block call. Static project retrieval does not execute C or infer the body of an external function.',
        'Evidence: project records use [S1] IDs plus actual source file/line or ladder network and selected target/task ownership. Retrieved help uses [H1] IDs plus document title, local path, help set and digest. Guide examples are labeled illustrative. Vendor documentation can explain syntax or a block contract; project source is required for claims about implementation. Reading limits, unsupported formats and truncation remain visible.',
        'Future editing: keep original files, encoding, comments, namespaces, object IDs, ordering and project wrappers. Propose a patch with exact file/line/network and declarations, review the full affected scope, and build/download using the matching Automation Studio and runtime. The assistant does not automatically write PLC source. Never reconstruct or overwrite a whole project from a bounded retrieval excerpt.'
    ],
    'example': '{"network":1,"commented":false,"cells":[{"id":"1:0:0","kind":"contact","name":"Start","type":"open","row":0,"column":0,"span":1}],"connections":[],"warnings":[]}\n\n{"name":"Numeric_4","properties":{"Left":"296","Top":"158","Datapoint":"Local.DOFFER[2]"}}\n\n{"name":"ShiftValue","declaration":"ARRAY[0..9] OF REAL","file":"Logical/Global.var","line":12}',
    'references': ['python_engine/compare.py', 'python_engine/ladder_model.py', 'python_engine/project_knowledge.py', 'python_engine/project_info.py', 'python_engine/hmi_bitmaps.py', 'backend/core/compare_screen_preview.py', 'AS27_PROJECT_LAYOUT.md', 'LADDER_REFERENCE_REVIEW.md']
}


def main():
    folder = ROOT / 'knowledge/help_index'
    path = folder / 'project_guide.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    data['topics'] = [PIPELINE] + [t for t in data['topics'] if t['id'] != PIPELINE['id']]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = ['# B&R project decoding and engineering help', '',
             'A compact uSOPp reference for engineers and Chopper. Original vendor manuals remain under `knowledge/br_help/`. Examples below illustrate syntax and record shapes; they are not extracted project source.', '',
             '## Contents', '']
    lines += [f'- [{t["title"]}](#{t["id"]})' for t in data['topics']]
    lines += ['', '## How the help reaches Chopper', '',
              'KnowHub → **B&R help index** provides the topic tree, search and this guide download. On startup, the server builds a missing reference index in the background. Admin can rebuild it after replacing or adding help files. The last completed index remains readable while a new one is prepared.', '',
              '`knowledge/help_index/br_help.sqlite3` is a derived full-text index in the persistent data directory. Each readable source topic records its original path, title, category, library, help-set label and SHA-256 digest. Images stay in the original help folder. Search retrieves bounded excerpts and supplies them to the configured model alongside project evidence. This changes the model context; it does not train or modify model weights.', '',
              'The scanner inventories supported `.html`, `.htm`, `.xml`, `.txt`, `.st`, `.ab`, `.c`, `.h`, `.var`, `.typ` and `.ld` files. Files larger than 5 MiB, unreadable files and topics without extracted text are counted as skipped; extracted text beyond 100,000 characters is flagged as truncated. Other assets are not converted into language lessons. The UI reports coverage and indexing progress. A help-set folder label alone does not establish project compatibility.', '',
              'The compact JSON and this guide ship with application releases. The large vendor help installation and derived index are local reference data and stay in the server’s persistent knowledge folder. Keep that folder in backups. Rebuild on the shared server with Admin’s button, or in a source checkout run `python scripts/build_br_help_index.py --data-root <persistent-data-root>`.', '',
              '## Syntax and standards scope', '',
              'Structured Text (ST) and Ladder Diagram (LD) are IEC 61131-3 language families. Automation Basic and B&R project wrappers/tooling require B&R documentation for the installed Automation Studio/runtime version. C entry-point conventions are B&R-specific. This guide is an engineering reference, not an IEC compliance assessment or a replacement for the full language/compiler manuals. Every edit needs review against actual declarations, target configuration and library versions.', '']
    for t in data['topics']:
        lines += [f'<a id="{t["id"]}"></a>', f'## {t["title"]}', '', t['summary'], '']
        lines += ['- ' + d for d in t.get('details', [])]
        lines += ['']
        if t.get('example'):
            language = {'structured-text': 'iecst', 'automation-basic': 'text', 'ansi-c': 'c', 'ladder': 'xml'}.get(t['id'], 'text')
            lines += ['**Illustrative example**', '', f'```{language}', t['example'], '```', '']
        if t.get('references'):
            lines += ['**Source pointers**', ''] + ['- `' + ref + '`' for ref in t['references']] + ['']
    lines += ['## Quick syntax examples', '',
              'These examples are authored illustrations. Declare the variables in the actual program scope and use the matching compiler/library documentation.', '',
              '| Construct | Structured Text | Automation Basic / ladder |',
              '| --- | --- | --- |',
              '| Assignment | `Run := TRUE;` | AB: `Run = TRUE` on its own line |',
              '| Conditional block | `IF condition THEN ... END_IF;` | AB: `IF condition THEN` followed by statement lines and `ENDIF` |',
              '| Statement boundary | Semicolon | AB normally uses a new line; do not translate ST punctuation blindly |',
              '| Boolean condition | `Start AND NOT Stop` | Ladder: normally open Start in series with normally closed Stop |',
              '| Parallel paths | Preserve the full Boolean expression | LD: follow branch junctions and block pins; do not flatten branches |',
              '| Timer | Declared `TON` instance; named `IN`, `PT`, `Q`, `ET` fields | LD: actual timer block and connected pins; AB calls follow the installed library interface |',
              '| Cyclic behavior | Task executes configured program repeatedly | A file name alone does not identify scheduling or task priority |', '',
              '### Structured Text CASE and bounded FOR', '', '```iecst',
              'CASE State OF', '    0: Ready := FALSE;', '    10: Ready := TRUE;', '    ELSE Ready := FALSE;', 'END_CASE;', '',
              'FOR i := 1 TO 8 DO', '    Samples[i] := 0.0;', 'END_FOR;', '```', '',
              'Here `State` and `i` need appropriate integer declarations, `Ready` is BOOL, and `Samples` is `ARRAY[1..8] OF REAL`. Array bounds are inclusive. Loops execute within a task invocation; check execution time and bounds rather than treating each loop iteration as a separate PLC cycle.', '',
              '### Automation Basic conditional layout', '', '```text', 'IF Start THEN', '    Run = TRUE', 'ELSE', '    Run = FALSE', 'ENDIF', '```', '',
              'The supplied B&R AB help requires IF and THEN on the same line, body statements on following lines, and ELSE/ENDIF on their own lines. Keep AB and ST syntax separate.', '',
              '**Local vendor references:**', '',
              '- `br_help/AS12/Help-en/Data/programming/programs/structuredtext/programmingmodel_programs_structuredtext_case.html`',
              '- `br_help/AS12/Help-en/Data/programming/programs/structuredtext/programmingmodel_programs_structuredtext_for.html`',
              '- `br_help/AS12/Help-en/Data/programming/programs/automationbasic/programmingmodel_programs_automationbasic_if.html`', '']
    database = folder / 'br_help.sqlite3'
    if database.is_file():
        from python_engine.br_help_index import metadata
        meta = metadata(database)
        counts = meta['counts']
        lines += ['## Supplied collection coverage', '',
                  f'Local index snapshot: {meta["builtAt"]}. Scanned **{meta["sourceFiles"]:,}** supported source files; indexed **{counts["vendor"]:,}** vendor topics plus **{counts["guide"]}** authored guide topics. **{counts["skipped"]:,}** source files were skipped; **{counts["truncated"]}** indexed topics have truncated text.', '',
                  'Skipped reasons: ' + ', '.join(f'{key}: {value:,}' for key, value in meta.get('skipReasons', {}).items()) + '.', '',
                  'The source inventory table records paths and status for every scanned source file. Navigation XML without extracted text and files beyond the size limit remain recorded rather than silently counted as indexed. Images and binary assets remain in the original corpus. This is a local snapshot; another server reports its own installed collection and index counts.', '']
    (folder / 'BR_PROJECT_HELP.md').write_text('\n'.join(lines), encoding='utf-8')


if __name__ == '__main__': main()
