# MatchView screen identification and printable correction notes

Updated 4 November 2026. This change treats the requested restoration as the
screen export presentation: the earlier paired **Base / Developed** arrangement
is retained. The live screen inspector and interactive HTML report keep their
existing control-name checkbox and normally-visible/all-layer selectors.

Project details now has **PDF / Word screen details** options:

- Control names and correction-note references.
- Normally visible layers.
- All layers, shown separately.

At least one layer view must remain selected when exporting screens. Normally
visible uses the saved layer visibility configuration. All layers prints each
layer separately, including hidden layers, so controls are not flattened into
one overlapping image. A single normally visible layer is printed once when both
choices are selected. Layer absence and source visibility are labeled separately
for Base and Developed. These are static project views, not runtime visibility.

PDF and Word provide numbered **Correction notes / Base to Developed**. Each note
contains its scoped control name, layer, type, addition/removal/change description
and a readable Property / Before / After table. Compact numbered screen markers
correspond to the note headings. Values come from the compared source records;
the notes do not classify every difference as an error or invent a required fix.
Existing unchanged/context selections remain available. Detail tables have no
ruled cell grid, and long PDF values can continue across pages.

Export jobs save the screen options and include them in their cache fingerprint.
Named/layer previews use a separate cache identity. An earlier downloaded report
is retained, while preparing a new report uses the new presentation. File-status,
section selection, source hashes, comparison results and access checks remain in
their existing workflows.

Verification: TypeScript, the main production build and the standalone report
viewer build passed. Twenty-five focused export/selection/context/text-group
tests passed, including hidden layers, number/name references, missing controls,
long PDF values, optional names and source immutability. Six browser checks
covered the settings, actual queued PDF/Word APIs, option-sensitive caching,
another-account denial and the existing offline HTML controls. Four dialog
widths passed: 1600, 1067, 800 and 390 pixels. No page errors were recorded.

An actual saved `Process0_1.page` comparison produced PDF and Word samples with
29 correction notes; its source comparison and detail-file hashes were unchanged.
Artifacts and examples: `.build/matchview-corrections-20261104/`.
