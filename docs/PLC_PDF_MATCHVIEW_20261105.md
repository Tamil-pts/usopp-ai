# PLC MatchView: printed blocks, networks and pixels

Implemented on 5 November 2026. PLC MatchView now offers **Project folder** and
**PDF files · Block / network** input modes. Existing project comparison is retained.
AI Assist's general Document Compare includes a shortcut to the PLC PDF mode.

Choose two searchable PLC program PDFs, select **Compare pixels (wiring and
symbols)** and **Ignore printed page numbers** as required, then compare.
The result opens with **all networks** in a continuous, paired Before/After
workspace. One shared vertical and horizontal scroll keeps the two sides together;
networks remain visible without selecting each one. A continued network retains
every source-page segment. Block information remains a separately labelled section.

The left block, network/operand search and **Tree: show** controls filter only the
navigation list. Clicking an item jumps to its section without replacing the
comparison. **Workspace: show** independently supports All, Differences, Modified,
Added, Removed, Unchanged and Needs review. Differences includes added, modified
and removed sections, as well as unresolved items. Jumping to a network hidden by
the workspace filter restores All and scrolls to that network. Previous/next change,
fit width and zoom work across the complete stream.

**Highlight changes** is on by default: modified sections are yellow, added green,
removed red, and unresolved identities explicitly labelled Needs review. With pixel
evidence, yellow halos mark observed changed pixels on both network crops while
retaining source ink. Without pixel comparison, the whole changed network receives
a status tint; the interface explicitly says individual wire changes were not
located. Unchanged images remain uncoloured. The optional red pixel overlay remains
available for the compared side. These are evidence colours, not execution claims.

All section headings remain in the scroll document. Raster previews load near the
viewport and unload outside it, retaining their measured height, so a large program
does not load hundreds of network images at once. Extracted text opens per section.

The parser uses explicit printed block headings, such as `TUBELOADER (SBR20)`,
and `Network 1` headings. It matches exact network-text anchors within each
block, then matches remaining unique network numbers. Unmatched networks remain
added/removed. Printed project headers identify the source; their changed project
revision does not turn every network into a logic difference. Network operands,
titles and block references remain compared. Duplicate identities and pages with
unrecognised block headings remain unresolved. A PDF without recognisable
searchable PLC headings is rejected rather than assigned invented blocks.

Optional pixel comparison renders at 1,000 pixels per page width, joins the
network's page segments, removes outer whitespace, pads unequal crops with white,
and records grayscale pixel differences above 32/255. The red overlay shows those
observed differences. Disabling pixel comparison leaves wiring and symbol geometry
unchecked. Pixel changes can include print/layout differences; they are review
findings, not a proof of changed execution or behavioural equivalence. No model
generates the comparison evidence or infers PLC state from the PDF.

Exports include **PDF, Word, HTML, CSV**, and both marked original PDFs. They retain
before/after evidence, source pages, comparison options and source SHA256 hashes.
Long networks are tiled into readable parts in PDF/Word reports. Annotated originals
mark changed network regions; the workspace's pixel overlay is a separate view.

The API is under `/api/local/compare/plc-pdf`: `uploads`, `run`, `results/{id}`,
`results/{id}/networks/{row}/{side}.png`, `report.pdf`, `report.docx`, `report.html`,
`export.csv`, and `highlighted-{side}.pdf`. It uses existing authenticated,
account-owned immutable document snapshots. Changed snapshots block review,
rendering and export, including cached output. Inputs are read-only.

## Verification

- Production builds: main interface, standalone MatchView report, DataInspect and
  Virtual PLC. UI/API version remains 4.99.3.
- 40 comparison API/regression tests, including ten PLC PDF tests: identical
  networks, printed revision changes, inserted/renumbered networks, visual-only
  wiring changes, continuation, duplicate identity, exports, ownership, stale
  sources, unsupported formats and option validation.
- Eight browser checks with the actual `TSV9444.pdf` and `TSV9445.pdf`, including
  all six downloads, persisted mode/result, original project mode and pixel controls.
- Five responsive widths: 1,600, 1,024, 800, 390 and 320 pixels, without page overflow.
- Actual samples: 181 versus 183 pages; 16 blocks; 409 compared sections, including
  block information; 405 unchanged and four modified sections. One network has
  changed extracted logic text, one has pixel-only differences, and two changes
  are block information. No unsupported execution claim is inferred from these counts.
- `INV_COMM` Network 3 retains pages 84–86 versus 84–88 as one matched network.
  `TUBELOADER` Network 1 stays matched despite later page numbers shifting by two.
- Final tiled PDF/Word/HTML exports were checked again against the full authenticated
  sample result in isolated storage with identical source hashes. The PDF has 15
  pages, including readable network parts and complete before/after text.
- Local installation restarted through `start_usopp.ps1` after confirming idle
  jobs/model. Health is 4.99.3; main, DataInspect, report and Virtual PLC assets
  return successfully. The 53 projects and 34 accounts remain unchanged. The model
  remains idle with its 8,192-token context.

Artifacts: `.build/plc-pdf-networks-20261105/`. These checks cover this feature;
they do not certify all application APIs or all PLC PDF dialects.

### Continuous workspace verification

The 5 November follow-up passed 42 targeted comparison tests, including source
ownership/staleness, exports, visual-only changes, status colours, preservation of
unchanged pixels and original crops. Main TypeScript/production, DataInspect and
standalone MatchView viewer builds passed.

Eleven browser scenarios passed, including the actual TSV9444/TSV9445 PDFs with
all 409 sections present together, independent tree/workspace filters, continuous
scrolling, joined multi-page networks, highlights, pixel overlay, change navigation,
all six existing downloads, saved-result restoration and original project mode.
Five widths (320, 390, 800, 1024 and 1600 pixels) and light/dark themes were checked.
There were no browser page errors. Counts remain four modified and 405 unchanged;
the presentation change does not reclassify source evidence.

Follow-up artifacts: `.build/plc-pdf-continuous-20261105/`.

The follow-up build is running locally on port 8200 at UI/API 4.99.3. Health and
main/DataInspect/report/Virtual PLC assets returned HTTP 200 after the supported
restart. Anonymous highlighted-image requests remain denied. The pre-restart
53 projects and 12 accounts were retained, and the model remains idle with its
8192-token context. These current counts supersede the earlier installation check.
