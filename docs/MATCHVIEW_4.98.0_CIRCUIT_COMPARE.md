# MatchView 4.98.0 — Circuit Compare

The initial method below is superseded by [4.98.1 accuracy and object-analysis corrections](MATCHVIEW_4.98.1_ACCURACY.md). Its original 394 findings included rendering/extraction artifacts; current results separate those from source-object changes.

MatchView now offers **PLC Project Compare** and **Circuit Compare**. Both views remain mounted when switching types, preserving the current PLC comparison and drawing results.

## Use

1. Open MatchView → Circuit Compare. Select Base and Developed PDF drawings, then Compare drawings.
2. Select a matched sheet. Red indicates removed content, green added content and amber modified fields. Pixel overlay shows the tolerant raster comparison. Fit width, zoom, linked scrolling and a shared resize handle control the two previews.
3. Filter the change register by category, change, review status or reference text. Selecting a change highlights its source regions in both drawings. The detail shows page numbers, before/after values, possible impact and verification checks.
4. Record a review and note. Confirming a difference records a review; it does not approve the electrical design. Original PDFs and detected values remain unchanged.
5. Expand Chopper's source-based engineering checks or request an explanation of the selected change. PDF reports contain original page previews, pixel overlays, the complete change register, source locations and review notes. JSON export preserves the full extracted values and normalized source boxes.

Each PDF is limited to 75 MB / 200 pages. Two comparisons may run concurrently. Completed sessions and reviews survive backend restarts; interrupted jobs report an explicit failure. Sessions and images use existing account ownership checks. Processing stays on the local server; optional Chopper prose uses the configured model provider.

## Comparison evidence

- Page matching uses normalized character n-grams, printed sheet identities where readable, and drawing captions. This handles reordered pages and CAD exports that omit space glyphs. Ambiguous/scanned correspondence is explicitly flagged.
- Ruled BOM and connection tables are extracted geometrically. Stable row IDs and exact headings take priority over uncertain positional matches. Duplicate row IDs retain separate occurrences. Material numbers, quantities, cable fields and terminal text retain their original source values and boxes.
- Annotation comparison recognizes component references, terminal/pin labels, cable dimensions, shielding and revision/date text. Explicit printed destinations are distinguished from inferred electrical nets.
- Raster comparison allows a small global translation and antialias tolerance. Geometry-only findings require review. It cannot establish net connectivity, junction semantics, safety or functional equivalence.
- PDFium calls are serialized across jobs. Text/table extraction uses pdfplumber; rendering uses pypdfium2. NumPy/Pillow perform visual comparison. The Windows packager collects the PDFium native library and PDF extraction resources; containers install the same declared requirements.

## Chopper

Source-based engineering checks cover every non-dismissed finding. Optional model explanations are bounded to the selected finding or the first 20 findings; this scope is visible. Source IDs are checked against the evidence actually supplied to the model. The existing model context fitter remains responsible for the token budget. Invalid/missing citations or model unavailability leave the authoritative change register and deterministic checks available.

## Known limits

There is no OCR in this release. Scanned pages receive visual comparison with explicit extraction notices. CAD text rendered as outlines, corrupted font encodings, changed export scaling and rotated annotations can require manual verification. Text/table comparisons do not prove wire continuity. Page similarity is a content similarity measurement, not a calibrated engineering-confidence score. No inferred electrical behavior is automatically approved.

## Source changes

- `python_engine/circuit_compare.py`: PDF inventory, page matching, table/annotation and visual comparison, engineering checks.
- `python_engine/circuit_report.py`: source-linked PDF report.
- `backend/api/circuit_compare.py`, `backend/app.py`, `backend/api/system.py`: owned background sessions, previews, reviews, export and bounded optional Chopper explanation.
- `src/features/compare/ComparePage.tsx`, `CircuitCompare.tsx`, `circuit-compare.css`: comparison-type selector, split drawing viewer, filters and review controls.
- `backend_requirements.txt`, `build_windows_exe.ps1`, package version files: dependency and packaging integration, UI/API 4.98.0.
- `tests/test_circuit_compare.py`, `scripts/verify_circuit_compare.py`: synthetic reference-PDF regression tests and reproducible real-drawing verification.

The existing PLC comparison engine and Python v1.71 packet validation engine are unchanged.

## Verification — 30 October 2026

- Targeted circuit/PLC comparison/retrieval regression run: **42 passed, 2 skipped**. The skips are pre-existing optional checks. Fourteen tests cover the new PDF engine/API, unchanged PDFs, reordered/added/removed pages, scans, source boxes, material/quantity fields, header correspondence, review persistence, account isolation, export, malformed/encrypted input and model citation handling.
- `npm run build` passed for the main interface, DataInspect and Virtual PLC. Existing Vite chunk-size warnings remain.
- Live authenticated browser upload used `4C9935069 - 21-08-26.pdf` and `4C9935069 - 21.08.26-Correction.pdf`. Both contain 18 pages; all 18 corresponding pairs matched. The review register contains 394 detected text/graphical findings, including export/font differences, and must not be interpreted as 394 verified electrical changes. Eighteen BOM cells show the material replacement `449211590` → `409211590`. The full report has 70 pages with drawing previews, overlays and source-linked register entries.
- Browser checks exercised category/reference filters, paired highlights, fit/zoom, linked scrolling, pixel overlay, resizing, saved pending review notes, comparison-type state preservation, PDF download, 1100px layout and 390px mobile layout. No browser exceptions or document-width overflow were observed.
- The optional live Chopper explanation successfully cited the selected material-number change. The existing model returns already-validated cited prose; the Circuit Compare caller now consumes that interface instead of incorrectly parsing it as JSON again. A regression test covers this interface and rejects invented citations. The tokenizer measured the actual local request within its configured 8192-token context; no model settings were changed by Circuit Compare.
- `/api/health` reports `status: ok`, UI/API **4.98.0** and `circuitCompare: true`. The HTTP POST upload route is registered in the running API. Earlier HTTP 405 came from the still-running 4.97.3 backend after rebuilding the UI.

Local verification artifacts are in `.build/circuit-compare-check/`: `live-result.json`, `live-comparison-report.pdf`, `live-chopper.txt`, desktop/mobile screenshots and report-render checks. No container image or Windows executable was produced as part of this feature verification.

## Deployment check

Rebuild all interfaces with `npm run build`, install backend requirements in the runtime environment, and restart the backend. A browser can load new static UI assets while the old Python process is still running; UI 4.98.0 / API 4.97.3 caused the observed HTTP 405 **Method Not Allowed**. `/api/health` must report `status: ok` and both versions 4.98.0. Circuit Compare now provides a specific restart/session message for unavailable endpoints.

For a reproducible comparison without changing the originals:

```powershell
python scripts/verify_circuit_compare.py --base 'C:\path\base.pdf' --developed 'C:\path\corrected.pdf' --output '.build/circuit-verification'
```
