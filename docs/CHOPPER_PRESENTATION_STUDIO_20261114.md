# Chopper Presentation Studio - 14 November 2026

Open **AI Assist > Presentation Studio**, or select **Create presentation** from
the top-bar Chopper task launcher. This is the first working presentation release,
with a native editor in addition to the requested outline-to-PPTX MVP.

## Available now

- A topic, audience and brief generate a 2-12 slide outline using the configured
  local/private-network Chopper model. There is no external AI fallback or model
  download. **Start without AI** explicitly creates a starter draft from inputs.
- Attach up to four PDF, DOCX, XLS, XLSX, CSV or TXT sources, each below 20 MB.
  Existing readers retain their limits: readable PDF text (up to 50 pages), Word
  paragraphs/tables, and spreadsheet previews (up to 10 sheets, 1,000 rows and
  40 columns per sheet). Reader notices and local-context reductions are shown.
  Scanned PDF OCR and exhaustive workbook summarization are not claimed.
- For source-based decks, the planner selects validated source IDs. The server
  inserts their source excerpts into the slide bodies and notes. Model-written
  bodies are discarded, with a notice; unknown IDs prevent publication. Titles
  are draft editorial labels. This protects source wording and numeric values
  without claiming that a model has verified the underlying project.
- Prompt-only prose is explicitly a review draft, without verified project
  evidence. Generated content does not approve a project or create test results.
- Bullet, card and timeline layouts, alternate slide backgrounds, editable text
  and boxes, dragging, corner resizing, position/size fields, colors, bold text,
  speaker notes, undo, slide duplication, ordering and deletion.
- A shared catalog of **15 font choices and 12 palettes**, also used by drawing
  font selectors and the flowchart Text to Visual palette selector. Existing
  font names and original Ocean/Meadow/Sunset palettes remain supported.
- Private saved decks with immutable revision snapshots, account-identity
  ownership, atomic file publication and a cross-process revision lock. Stale
  saves/exports are rejected. Editing warns before navigation. Saved decks reopen
  after refresh and through their bookmarked URLs.
- Editable PPTX, vector PDF, PNG slide ZIP, SVG slide ZIP and JSON snapshot
  downloads. Exports use the saved revision. PPTX contains separate editable
  shapes/text and source-linked speaker notes, rather than flattened slide images.
- Original source snapshots can be downloaded from the evidence panel. Source
  names, SHA256 hashes, selected excerpts and reader notices remain with the deck.

Fonts are not downloaded or embedded into the PPTX. Browser/PowerPoint font
availability depends on the viewing computer. PDF/PNG use available server fonts
with standard fallbacks, and block unsupported characters instead of silently
publishing missing glyphs. SVG and PPTX remain alternatives for those cases.

## Shared foundation and validation

`knowledge/master/visual_tokens.json` is the common font/palette catalog.
`backend/core/visual_content.py` validates bounded slide objects and creates
layout geometry. `presentation_exports.py` renders that same slide schema.
The existing FRD/flowchart schema, files, packet validation engine and document
approvals are preserved.

Layout checks flag likely text overflow, overlapping object bounds and low text
contrast. These conservative checks do not prove that every font will wrap the
same way in every Office installation. Users should review the downloaded slides.
PPTX creation uses [python-pptx](https://python-pptx.readthedocs.io/en/latest/user/quickstart.html),
including its editable text and [speaker notes](https://python-pptx.readthedocs.io/en/latest/user/notes.html).

The Windows packaging configuration includes python-pptx templates/modules and
XlsxWriter. The container frontend receives the shared knowledge assets before
building, and the Python requirements include python-pptx. This change does not
claim that a new Windows package or Docker image was built locally.

## Verification

- 15 Presentation Studio API/model-boundary/export checks passed, including
  actual source parsing for PDF, DOCX, CSV and XLSX, account isolation, immutable
  source access, stale revisions, fabricated source IDs, discarded model prose,
  editable PPTX reopening, notes and all export formats.
- 30 existing drawing/document-studio regressions passed after sharing the font
  catalog, including existing geometry, revisions and export behavior.
- Browser checks cover source upload, starter creation, text editing, native
  object movement, saving, PPTX/PDF downloads, direct URLs, refresh and layouts
  from 390 to 1,600 pixels. Tests use isolated accounts and storage.
- Real inference on the installed local model passed for both two-slide source
  planning (5.36 seconds) and a two-slide prompt-only deck (8.33 seconds), with no
  layout warnings in either final fixture. Larger decks are schema-bounded, but
  these timings are not a performance guarantee for all prompts or slide counts.
- TypeScript compilation and the main production Vite build passed.

Artifacts: `.build/presentation-final-tests.log`,
`.build/presentation-regression.log`, `.build/presentation-browser.log`,
`.build/presentation-real-model.json` and `.build/presentation-studio-20261114/`.

## Remaining phases

Natural-language editing of individual slides, native analytic chart objects,
company-logo/brand-template management, PPTX import, automatic infographic/symbol
selection and direct WorkHub report-to-deck actions remain subsequent work.
Upload a saved project report to use its readable content today. Presentation
drafts do not inherit WorkHub document approval or release acceptance.
