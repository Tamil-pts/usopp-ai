# Flowchart ribbon and artwork — 13 November 2026

The workspace uses a compact Office-style ribbon:

- Home: select/select all, copy/paste, duplicate/delete, font family/size, bold/italic/underline, fill/stroke/text colors and themes.
- Insert: process, decision, start/end, I/O, document, subprocess, text box, freehand and templates.
- Arrange: align to left/right/top/bottom/centers; distribute horizontally/vertically; match width/height/size; group/ungroup; bring to front/send to back; flip.
- View: fit drawing, zoom, grid, snapping, smart guides and rulers.

Ctrl-click (or Shift-click) adds/removes objects from the selection. Selection updates now follow React Flow's selection changes directly, avoiding the prior selection callback feedback. Arrange commands are enabled when applicable; matching size uses the first selected object's dimensions. Ungroup removes the whole selected object's group.

The left library opens on Icons & Clip Art, with Shapes & Symbols on a separate tab. Twenty original vector assets cover General, People, Engineering, Technology, Planning and Clip art. They support search, click/drag insertion, recoloring, resizing, existing revision storage and vector export. Original artwork provenance is stored with inserted symbols. Vendor art packs are not claimed.

Visual Assist opens as a floating panel, and closes when a visual is submitted for confirmation, leaving the canvas available. Background color and pages remain accessible below the ribbon. Narrow windows offer library/property switches.

Checks: browser verified generation, Ctrl multi-selection, alignment, same size, group/ungroup, clip art insertion and save without page errors. All 20 artwork paths passed backend validation and SVG export checks. Browser artifacts are under `.build/flowchart-20261113/`.
