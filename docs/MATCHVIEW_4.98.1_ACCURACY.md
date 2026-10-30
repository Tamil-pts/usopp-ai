# Circuit Compare accuracy correction — 4.98.1

Implemented against the two supplied `4C9935069` cable-kit PDFs. Comparison engine version is **2.1**; the page-object schema is **1.1**. This supersedes the initial 4.98.0 comparison method.

## Why unchanged pages were yellow

1. The old raster check grouped connected border/rendering pixels into a page-sized rectangle. The frontend filled that rectangle amber, covering unchanged content.
2. The corrected PDF omits some `ToUnicode` maps. Its embedded fonts draw readable labels, but the extractor returned `(cid:...)` strings instead of the same letters and values. Those extraction failures were wrongly counted as changed content.
3. Space glyphs, text fragmentation, rotated pin numbers, PDF export scale, photo compression and moved annotations generated extra before/after mismatches. A moved equal label was incorrectly reported as removed and added.
4. Geometric primitives were insufficiently separated from electrical meaning. A cable housing outline can be a continuous path between pin labels without representing an electrical connection.

## Current processing method

- Decode the PDF text and source boxes. Missing Identity-CID Unicode maps are recovered only from that PDF's embedded TrueType cmap and CID-to-glyph mapping. No character is guessed from the other drawing; no OCR or original-file edit is performed. Ambiguous mappings stay unresolved.
- Identify corresponding pages and normalize global export scale/translation using the inner vector drawing frame. Bounded text/pixel registration is a fallback. This avoids fitting a distorted transform from only a few footer labels.
- Compare engineering tables by stable row and column identities, not their changed screen positions. Preserve material numbers, quantities, units, conductor counts and terminal references. Equivalent numeric formatting such as `3.15`/`3.150` is ignored.
- Match equal labels across the whole page before assigning additions/removals. Split/merged numeric fragments and rotated reference candidates are handled separately. Unique moved cable specifications can be compared as one changed field.
- Inspect independent PDF objects: text labels, component references, terminal/pin references, unclassified symbol shapes, line segments and path nodes. Compare collinear line coverage independently of how an exporter splits primitives.
- Build an inspectable page graph. Endpoints and explicit dots can join paths; a plain crossing does not. Proximity-based terminal associations stay inferred. Ambiguous associations, unsupported symbols and partial graph coverage are visible.
- Keep **geometric paths** separate from **connection candidates**. Cable-assembly/cyclic outlines are not treated as electrical nets. A uniquely printed SIDE-A/SIDE-B or source/destination table supplies a stronger mapping source than proximity. Unknown symbol/pin semantics are not filled in by Chopper.
- Use registered local raster residuals as a diagnostic channel. Mask already-compared text/tables, normalize matching photos, and separate uncertain uncorroborated appearance from detected source-object changes. Text-layer mismatches with matching visible marks are suppressed as render diagnostics.

## Frontend and saved sessions

Highlights are outline-only; there is no page-sized yellow fill. Uncertain extraction/layout checks are hidden by default and have a separate count and filter. They do not inflate the engineering change count. Diagnostic pixel overlay remains optional.

Change outlines use red for removed objects, green for added objects and amber for modified objects. Uncertain geometry uses the same status colour with a dashed outline. Selection and keyboard focus preserve the status colour, and all highlight backgrounds remain transparent.

**Drawing objects & connection paths** opens the source-object inspector for the selected page pair. Filter labels, references, terminals, symbols, nodes, lines, geometric paths or connection candidates. Selecting a unique reference highlights it on both drawings; selecting a path traces its actual source geometry. Page-local `W1`/`N1` IDs are never treated as cross-version identities.

**Recompare original drawings** creates a new owned comparison from the retained PDFs. Earlier results/reviews remain unchanged. Older engine versions show a recompare notice. No PLC files, existing project comparisons, packet-validator code or approval records are edited.

## Verification

The synthetic PDF tests cover missing Unicode maps, identical rendering with/without a map, global export scale/translation, stroke and JPEG differences, equal moved labels, split pin numbers, changed moved cable specifications, collinear primitive splitting, clear terminal paths, unjoined crossings, explicit dots/T endpoints, ambiguous proximity, cable-assembly/cyclic-outline rejection and printed connection-table mapping. Existing comparison/API tests cover owned graph access, recompare, original/review preservation, reports and source citation checks.

Combined targeted regression run: **53 passed, 2 skipped**. All three production interfaces built successfully. UI/API are **4.98.1**; the Python v1.71 packet validator and existing PLC comparison engine are unchanged.

On the actual drawings:

- All **18 page pairs** match.
- **Page 2: zero detected changes and zero uncertain checks**, with highlights enabled. Its extraction-only label mismatch is recorded as a suppressed render diagnostic.
- The source-object change register is **112**, compared with the earlier **394** mixed findings. Nine page pairs have detected source-object changes; unverified geometry/extraction is separate.
- All **18 BOM cells** changing `449211590` to `409211590` remain detected.
- The **16 × 0.75 → 12 × 0.75** cable change remains one modified specification.
- Inspectable labels, references and geometric paths are available without claiming a verified electrical netlist. The actual cable-assembly paths are explicitly kept out of electrical connection candidates.

Artifacts are under `.build/circuit-accuracy/`: real results, browser screenshots, source-path inspection and exported PDF. Original input hashes are checked independently.

## Practical limits

A flat PDF may encode a wire, dimension, cable sheath or symbol boundary as the same kind of line primitive. This implementation does not certify complete electrical connectivity or component function from that geometry. For authoritative pin/net semantics, use native CAD connectivity exports or engineer-confirmed mappings. Scanned pages still use visual comparison; there is no OCR in this correction. A larger LLM or a citation cannot resolve missing drawing semantics.
