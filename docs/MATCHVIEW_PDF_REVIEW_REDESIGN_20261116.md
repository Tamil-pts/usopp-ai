# PLC PDF MatchView review redesign - 16 November 2026

Reproduced the reported INPUTS network examples using the supplied 18480.pdf and 18481.pdf.

## Comparison and display

Both columns now receive equally sized, padded images at the same rendering scale. The interface no longer independently enlarges a narrow compared crop. The same shared geometry drives highlights and PDF/Word/HTML exports.

Explicit trailing Symbol / Address / Comment reference tables are retained separately. Their comparison is optional and off by default in the interface. They remain inspectable in a separate disclosure. Only an exact three-column heading is recognized; arbitrary comments mentioning these words are not treated as tables. The printed left power rail's blank extension does not determine the crop height. Connected branches, contacts, coils, instructions and operands remain in the drawing.

Verified examples: INPUTS Network 22 and Network 24 return unchanged with zero changed ink pixels when optional references/comments are excluded. Network 21 stays modified and its removed I0.4 branch remains visible. Side-by-side removed/added source-text summaries make the reason inspectable.

The basic controls retain drawing comparison and page-number exclusion. Author, created/modified dates, comments and reference tables are grouped under Optional details. Existing independent tree/workspace filters, continuous networks, source-page references, cover fields and export status selections are retained. Old comparison versions require recalculation before export.

The complete supplied pair produced 112 modified, 4 added, 13 removed, 293 unchanged and zero unresolved sections with these optional details excluded. These are static text/graphic classifications, not a proof of runtime equivalence. Different local spacing, unsupported printed formats and symbols can still require engineering review.

## Export performance and feedback

Each export shares bounded page caches and open PDF documents across selected networks. Pages are rendered directly into owned images without a PNG encode/decode round trip. Both marked sides are generated once per pair. Source ownership/hashes are checked before and after publication, rather than once per image. Progress records are private to the account and comparison, validate their identifiers, and report prepared section counts followed by document formatting and completion. The dialog also shows elapsed time; no guessed completion time is displayed.

A fresh corrected 129-section, 214-page PDF export took 112.72 seconds versus 151.89 seconds before direct rendering, on this installation under its current load. Its page count, every page's extracted report text and 241 matching network PNG files were unchanged. Repeated identical exports reuse the saved report. The earlier 410-section report included optional reference/layout differences and had 815 pages, so its 342.94-second timing is a different workload and is not used as a like-for-like speed claim.

## Verification

20 targeted regression tests passed. Coverage includes source isolation/staleness, bounded export source checks, owned progress, optional reference tables, rail extension, shared image dimensions, real wire/operand changes, metadata/comment exclusions and selected export formats. TypeScript and the production build passed. Browser checks passed for retained cover details, options, first-page metadata, actual INPUTS Network 22, equal natural image sizes and 390/760/1440 layouts. PDF, Word and HTML artifacts were generated for the actual corrected full result.

Artifacts: .build/pdf-export-speed/ and .build/matchview-export-redesign-20261116/. The live UI/API version remains 4.99.3. Existing PLC source, project records and approval logic were not changed.
