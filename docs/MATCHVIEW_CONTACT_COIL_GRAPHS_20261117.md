# MatchView contact/coil recognition and connection graphs - 17 November 2026

This adds a bounded structural layer to the existing source/vector/raster engine. It is enabled for fully covered contact/coil diagrams; unsupported formats continue through the existing engine and explicit review checks. No model training, external AI calls or additional Python dependencies were introduced.

## Supported evidence

- Paired vertical contact bars with attached rung wires and an unambiguous operand above.
- Normally open versus normally closed contacts, including vector diagonals and printed slash glyphs.
- Ordinary coils represented by two outward-facing Bezier arcs, with an incoming wire and an operand.
- Series/parallel connections and T junctions built from axis-aligned vector wires.
- Added/removed contacts, operand changes and changed terminal connections.
- One network relocated on the page: complete contact/coil types, operands and net incidence can establish unchanged recognized structure without warping the drawing.

Each recognized element retains its source page, bounding box and terminal coordinates. Each wire net retains its operand/port incidence. Connections are electrical continuity evidence, not PLC execution or scan-timing simulation.

Wire-to-wire joins use 0.05 PDF points. Estimated symbol-terminal attachment uses 1.0 point for the supported print profile. Free conductor ends, unmarked four-way crossings, repeated operand instances, unsupported styles, raster content, unknown text, rectangles and unrecognized curves prevent a fully covered graph. Timer/counter/vendor function-block semantics, reset/set coil variants, arbitrary rotated/scanned layouts and cross-page network reconstruction are not automatically classified.

## Decision boundary

Structural classification applies only when both sides are completely covered and drawing comparison is enabled. Symbol/type or connection changes produce Modified with an explicit reason, such as `I0.4: NO -> absent`. Complete matching graphs can identify layout-only differences. When a previously covered network becomes incomplete, pixel agreement alone cannot accept it. Partial candidates on both sides cannot overrule the existing source/raster comparison.

This scope was retained because it passed synthetic regressions and recognized real sample networks. Broader instruction recognition and ML learning are deferred; unsupported symbols are not assigned guessed semantics.

Comparison revision 7 invalidates earlier cached decisions and all preview/export paths require recalculation. Existing native ST comparison remains intact; timer literals and control-flow changes continue through source comparison.

## Verification and reproduction

Regression cases include NO-to-NC with deliberately inconclusive raster evidence, slash-glyph NC contacts, series-to-parallel rewiring, added/removed contacts, moved networks, renamed operands, a half-point broken wire, missing coils, repeated operands and unsupported timer boxes. The existing 1,001-page, source-integrity, account-isolation, native ST and export regressions remain part of the release prerequisite job.

The provided 194/163-page PDFs are exercised as a full local comparison. INPUTS 11 recognizes I0.2 (NO) and M13.7 (coil); INPUTS 21 identifies removal of the I0.4 branch. The full 422-section run took 68.33 seconds: 303 unchanged, 35 modified, 13 removed, four added and 67 needing review. Fifteen pairs were fully covered by the new structural profile. Recognition is partial across the full project and does not certify every network.

The combined regression suite passed 73 tests and seven subtests; the final focused suite passed 24 tests, including repeated operands, ST timer literals, unsupported-format fallback, shared PDF behavior and a Windows concurrent-cache-publisher regression. The production build and TypeScript checks passed. Browser checks also passed the NO-to-NC explanation and its PDF export. A Windows preview-cache sharing race found during this check was corrected with bounded retry and identical-byte cache reuse.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_plc_ladder_structure.py tests/test_plc_comparison_evidence.py tests/test_plc_pdf_comparison.py tests/test_compare_context_exports.py tests/test_document_comparison.py -q
.venv/Scripts/python.exe tests/matchview_export_popup_browser.py
```

Artifacts: `.build/matchview-structure-20261117/`, `.build/matchview-structure-regression.log`, `.build/matchview-structure-real.log`, `.build/matchview-structure-browser.log`, `.build/matchview-structure-tsc.log`, `.build/matchview-structure-build.log`.
