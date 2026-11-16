# PLC PDF network alignment - 16 November 2026

Fixed two faults reproduced with Downloads/18480.pdf and 18481.pdf and the supplied PLC_MatchView_66489001_all_report.pdf example.

- STEP7 running headers in the form `project / block` now identify continuation pages even without a parenthesized block address. Explicit block and network identity remains the comparison boundary. Unidentified or ambiguous content still needs review.
- Raster comparison registers each matched network with one rigid translation before finding changed ink. It never independently moves operands, branches or function blocks. One pixel of tolerance suppresses antialiasing and raster rounding. A common-ink anchor is required; weak matches remain unregistered.
- The same registered masks drive the workspace highlights and side-by-side PDF, Word and HTML exports. Original crop geometry remains available. Old saved comparison results ask users to recalculate; preview/report caches have new versions.

The supplied 194-page and 163-page PDFs produced 420 sections: 399 modified, 1 added, 10 removed, 9 unchanged and 0 unresolved. These are observed text/graphic differences, including symbol reference tables; they do not certify semantic equivalence or classify every difference as a logic change. The POWERON Network 1 alignment moved the compared raster by 33 pixels vertically. The real `18480` to `+18481` operand edit remains highlighted; unchanged MOV blocks and contacts no longer receive the broad displacement halos shown in the original report. Symbol-table differences remain review evidence.

Validation: 18 PLC PDF regression tests passed, including translation, operand changes, visual-only wire changes, continuation headers, ignored metadata/comments, selected exports and ownership checks. TypeScript and the production frontend build passed. The actual complete PDF pair was compared, and PDF, Word and HTML exports were generated. Artifacts are in `.build/pdf-layout-fix/final/`; the full extracted comparison is `.build/pdf-layout-fix/real-result.json`.

This corrects rigid position changes. Local spacing changes, different symbol styles, scaling and genuinely different print layouts can still need visual review. No PLC source, project records or validation rules were changed.
