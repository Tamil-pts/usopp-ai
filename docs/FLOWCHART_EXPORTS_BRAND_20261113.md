# Visual exports and Brand Studio — 13 November 2026

Export visuals in the existing Flowchart Workspace offers Current page and All pages, using the saved revision. Save changes before exporting.

- PDF: one visual page per PDF page, retaining its configured paper dimensions.
- PNG: current page as an image, all pages as a ZIP.
- SVG: current page as a vector file, all pages as a ZIP.
- PowerPoint (.pptx): one widescreen slide per page, fitted proportionally. Shapes, text and connectors are separate editable objects. Path artwork is embedded as PNG imagery. Gradients, shadows, precise routing and some geometry are approximated; no automatic animations are added.
- Editable JSON remains available separately.

Google Slides is not connected. Import the downloaded PPTX into Google Slides manually.

Styles & Brand Studio includes 15 original preset palettes (light, dark, outline, pastel, blueprint and monochrome variants). Styles apply to selected objects, or to editable objects and the background of the current page if nothing is selected. Custom brands store a name, three colors, a supported font and a page background in account settings. Brand selections become ordinary persisted drawing styles.

Drawing page endpoints continue checking project access, the exact saved revision and native document controls. Unknown page IDs are rejected. Tamil direct PDF export is rejected explicitly when unsupported instead of dropping labels; SVG/PNG preserve them.

Checks: browser downloaded a two-slide PPTX and two-image SVG/PNG ZIPs; every XML part parsed and ZIP CRCs passed. The PPTX was opened and round-tripped with an isolated python-pptx installation, confirming editable text and the embedded icon. Backend drawing suite: 13 passed, including Current/All page selection and outsider denial. These checks do not substitute for a desktop PowerPoint visual review. Test artifacts: `.build/flowchart-20261113/`.
