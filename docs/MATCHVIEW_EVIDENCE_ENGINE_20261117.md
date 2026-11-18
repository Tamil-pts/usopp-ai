# MatchView source evidence and large PLC PDFs - 17 November 2026

MatchView now checks source text, source drawing primitives and aligned raster ink before publishing a comparison decision. This is a deterministic engineering comparison; no LLM decides whether a change passes.

## Decision and evidence

- Existing explicit block/network matching remains the first pass.
- A second pass checks glyph positions, font names/sizes, lines, rectangles, curve control points, path commands, stroke/fill and dash styles. Only a single translation is normalized. Individual branches and operands are never warped into agreement.
- Exact source agreement, or at most eight residual pixels corroborated by matching source labels/styles and every coordinate within 0.25 PDF points, can identify print noise. Small pixel counts alone cannot pass a section.
- Left power-rail extensions outside all other drawing objects are excluded from source fingerprint differences. A rail ending inside the drawing remains evidence.
- Changed text or changed primitive counts with changed rendered ink remains Modified. Equal text with unexplained geometry becomes Needs review, rather than an asserted logic change or equivalence.
- Each matched result retains its reason, checks, raw pixel count, source corroboration and applied source tolerance. Pixel area ratio and registration confidence remain diagnostics. Incomplete curves, raster images and masked paths prevent source corroboration.
- Screen previews and PDF/Word/HTML exports share the decision. Highlight expansion was reduced from seven to three pixels. Corroborated noise is not reintroduced by the pixel overlay.
- Comparison revision 6 invalidates older preview/export caches and requires saved comparisons to be recalculated.

These checks do not prove PLC scan semantics or behavioural equivalence. Drawing moves that cannot be distinguished from a wiring change remain Needs review. Native ST comparisons remain in Project folder mode; printed PLC PDFs require searchable explicit block and Network headings. OCR/scanned and arbitrary ST PDF layouts are not newly supported.

## Capacity and interface

The PLC-specific upload and decoder now accept up to 2,000 pages and 100 MiB per file, with 50,000 networks and 20 million extracted characters. General Document Compare retains its own limits. Page raster caching stays bounded to three pages per source; network crops retain the existing 12-megapixel limit. Network counting and duplicate detection no longer recount every preceding network. Limits are resource bounds, not a promise of constant latency for dense drawings.

Zoom supports 25-250 percent. The canvas can shrink below its container; Fit width restores 100 percent. Existing project records and approval state are unchanged.

## Verification

Automated regressions cover repeated ST/literal/operand edits, unchanged source with injected raster noise, tiny unexplained differences, source print precision and rail extensions, moved geometry, added wires, curve control points, dash styles, native ST control flow, HTTP uploads, owner isolation and report exports. A 1,001-page pair is compared with pixels enabled and a change on its last page; the PLC HTTP upload is separately exercised with 1,001 pages.

The provided 18480.pdf / 18481.pdf pair (194 / 163 pages) produced 422 sections in 53.3 seconds: 308 unchanged, 35 modified, 4 added, 13 removed and 62 needing review. MAIN Network 5 is unchanged with a retained raw one-pixel diagnostic. INPUTS 21 remains modified; INPUTS 22 and 24 remain unchanged. These counts are observations, not an engineer-approved ground truth for every section.

The combined regression suite passed 62 tests; the final API suite passed 22 tests and seven stale-export subtests after adding the cache-version guard. The local server restarted successfully with matching UI/API 4.99.3 and frontend integrity confirmed.

Browser checks cover 50 percent zoom, Fit width, export selections, report cover, Escape/focus, real INPUTS 22 previews and layouts at 390, 760 and 1440 pixels. TypeScript and the production Vite build passed. The regression job is configured as a prerequisite of both private release package builds; GitHub-hosted execution has not been run locally.

Reproduce:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_plc_comparison_evidence.py tests/test_plc_pdf_comparison.py tests/test_compare_context_exports.py tests/test_document_comparison.py -q
.venv/Scripts/python.exe tests/matchview_export_popup_browser.py
```

Artifacts: `.build/matchview-evidence-20261117/`, `.build/matchview-evidence-final-tests.log`, `.build/matchview-evidence-browser.log`, `.build/matchview-evidence-tsc.log`, `.build/matchview-evidence-build.log`.
