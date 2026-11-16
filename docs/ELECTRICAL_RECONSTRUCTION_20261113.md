# Industrial reconstruction foundation — 13 November 2026

Implemented milestone 1 inside Virtual Electrical, retaining Electronics/SPICE as a separate mode and its existing native circuits. Industrial imports retain cable, connector and BOM pages rather than applying the older functional-circuit exclusions.

## Implemented

- Background PDF import through existing account-bound job slots; original file and SHA256 retained; 1–200 pages and 75 MB upload bound.
- Per-page evidence: dimensions, rotation, source type (vector/scanned/mixed/empty), deterministic category, text coordinates, lines, curves and image locations. Page caches released during processing.
- Explicit terminal-table reconstruction using terminal syntax and common source rows; no electrical nets inferred from touching source graphics.
- uSOPp electrical model 1.0: project/source identity, scoped devices and pins, connection candidates, source locations and revisioned review history. Short connector names are scoped to their source page/table; cross-page associations are not merged.
- Original page preview alongside a normalized editable connection diagram; source row highlight; terminal corrections restricted to known pins on that page.
- Three review states: verified, needs_review, unresolved. Engineering comments and account identity recorded; stale revisions and changed source hashes rejected.
- Selected-page continuity validation and compile gate; unreviewed/unknown/duplicate/self-terminal assignments blocked. Whole-source unresolved content remains visible.
- Electrical JSON export; account isolation reused by all endpoints. Existing Electronics solver is unchanged.

## Actual LC361 inspection

Source: `4C9935069 - 21-08-26.pdf`, found in Downloads. Actual inspected file: **18 pages, 2,950,721 bytes**, not the attachment's claimed 1.18 MB. SHA256: `1d275418984e779a8815732606ec06d47b02ba8ebef39cb8825dab41bfc8b30f`.

The decoder retained all 18 pages and extracted 25 terminal-table candidates. Page 16 includes all **16 X9 → X13 pin pairs**, 1→1 through 16→16, plus nine X7/XJ7 assignments. All start Needs Review. Original soft-hyphen separators and conductor annotations remain source evidence; conductor number and device pin number are separate fields.

Artifacts: `.build/electrical-reconstruction-20261113/sample/`. These are inspection artifacts, not engineer-approved machine data or an imported live account project.

## Remaining milestones

The full requested architecture is not complete. General IEC symbol recognition, raster OCR/deskew, region classification, geometric wire/junction interpretation, complete device designations, cross-page reference resolution, graphical symbol correction, voltage/domain rules, cable-capacity checks, discrete industrial control-state simulation, fault injection and validated 100+ page performance fixtures remain open. Geometry extraction is not proof of electrical connectivity. Confidence scores are uncalibrated and reported as absent.

The LC361 sample demonstrates connector assignments and review/continuity only. It cannot establish relay or motor behavior. The compiler always reports `simulation_ready=false`. No trained recognizer, PaddleOCR, PyMuPDF, Celery or additional database was installed; existing PDF extraction, worker slots and atomic account-bound workspace storage were reused.

## Independent vector tracing and verification levels

Decoder revision 2 adds a separate graphical pipeline alongside the unchanged
terminal-table decoder. PDF vector endpoints retain direction and source line
indices. Endpoint snapping uses 0.5 PDF points. Paths stop at branches; geometric
crossings, curves, closed shapes, cable bundles and break symbols are not treated
as electrical junctions. A candidate connection requires an unbranched vector path
and unique full terminal labels at both endpoints. No table assignment is supplied
to this tracer. The workspace can overlay these independently extracted paths.

Cross-page reconciliation compares independent terminal-pair outputs. Agreement
is Corroborated, conflicts are unresolved, and neither grants engineering approval.
Correction of table endpoints recalculates corroboration and invalidates the page
review. Old decoder revisions require reimport before verification.

Verification levels are separate: individual connection reviews; page validation
including unresolved graphics; and project-scope validation including dependencies.
Pages containing graphics need a separate recorded page review after connections
are verified. This cannot clear missing wiring or unsupported recognition. Pages
without assignments remain unresolved. Scope validation expands connector source
occurrences conservatively and reports omitted dependency pages. It does not
merge same-named devices across pages or enable executable industrial simulation.

### Page 6 measurable result

Actual source inspection shows an abbreviated cable assembly with a cable break,
selected leads, three connector pin-layout drawings, and two REFER TABLE 4 notes.
It does not draw 16 individually traceable, labelled pin-to-pin conductors across
the cable. Revision 2 extracted 342 usable straight vector segments and 219 path
candidates, but **0 complete independent terminal-to-terminal connections** on
page 6. The 25 table candidates remain intact, including page 16's 16 X9-X13
assignments. None is claimed graphically corroborated. This does **not** satisfy
an independent recovery of 16 conductor paths; such paths are not present in this
abbreviated drawing. A detailed wiring drawing or other independent evidence is
needed to establish those mappings. Matching connector pin inventories alone is
not proof of conductor continuity.

Artifact: `.build/electrical-reconstruction-20261113/graphical-result.json`.
Synthetic regression fixtures verify a real path, missing-path rejection, branch
and crossing handling, table isolation, conflict/corroboration distinction,
dependent-page scope rejection and account restrictions. General graphical
recognition, motor/pneumatic interpretation and complete simulation remain open.

Verification completed: 20 targeted backend tests passed; TypeScript compilation and main Vite production build passed. Isolated browser check passed using the actual 18-page sample: import, page selection, 25 table candidates, source highlight, saved connection review, page/project gates, page-6 vector overlay (219 paths), and switching to the existing Electronics editor. No browser page errors. Screenshot: `.build/electrical-reconstruction-20261113/workspace.png`. Project records in the running installation were not changed.

Subsequent interface update: [single industrial control workspace and discrete relay simulation](INDUSTRIAL_CONTROL_WORKSPACE_20261113.md). The Electronics mode is no longer exposed in the UI. Existing native circuit records remain retained.
