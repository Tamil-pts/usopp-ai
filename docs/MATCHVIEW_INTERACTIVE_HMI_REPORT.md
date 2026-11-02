# MatchView HMI report screen

Updated 2 November 2026 using the Existing / How actual need screenshots in `match view report screen sample.docx` as the visual reference.

This updates the existing **MatchView → Reports / download → HTML** export through the existing export handler. There is no additional report type, menu or separate authoring workflow.

HTML reports now embed the same `HmiScreenPreview` and `HmiPropertyComparison` components as the MatchView workspace. Selecting a control on either screen highlights its paired control and shows the full categorized properties below. Added and removed objects identify the absent side. Unchanged controls remain selectable for context. Property groups expand together across both columns; changed groups open automatically and changed values remain highlighted. Preview height supports pointer and keyboard resizing, paired scrolling is linked, and zoom, layer, language, font, bitmap-state and control selectors remain available.

The renderer, CSS, layouts and available bitmap assets are embedded into the downloaded HTML. Reports work offline without account, API or external script requests. Controls use the existing scoped IDs; report rendering does not change comparison results or PLC source. Source strings are JSON-escaped and rendered as text. The standalone viewer uses document-local preferences rather than account storage. Screens mount near the viewport to avoid rendering every control in a large report at once. A render failure or disabled JavaScript leaves the original static screen and change details available.

PDF and Word remain printable exports. Browser printing of HTML also uses the static screen images and all selected change details, independent of the currently selected control or collapsed property groups. The existing skip-layout setting still filters inspector properties while preserving the source geometry. New report fingerprints prevent an older cached HTML report from being reused after this update; earlier downloaded files are retained.

`npm run build` now builds the portable viewer through `scripts/build_compare_report.mjs` into `dist/report-assets/`. Deployment packages already include `dist`. A backend started without built viewer assets can still produce the static report. Build the frontend before deploying interactive reports.

Verification: **35 passed, 2 skipped** across HMI export, report selection, text groups, bitmaps and Ladder report tests. The standalone browser checks use the actual LR9SXV6318 / LR9SXV6319 `Process0_1.page` comparison from the reference: paired selection, Left 143 versus 116, control clicking, expand/collapse, pointer and keyboard resizing, 200% zoom, linked scrolling, 1500/1050/850/390 CSS-pixel layouts, added and unchanged controls, browser printing, disabled-JavaScript fallback, and zero HTTP requests or JavaScript errors. All three production interfaces built successfully.

Evidence and generated review files are under `.build/matchview-report-reference/`. `live-result.json` records the regenerated report job and source-hash preservation. The latest report retains the existing project cover and section/status selections; its HTML screen view is updated without rerunning the source comparison.
