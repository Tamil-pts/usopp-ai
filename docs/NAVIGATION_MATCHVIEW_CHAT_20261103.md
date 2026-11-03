# Top submenus, MatchView filters and chat sizing — 3 November 2026

The sidebar contains the main WorkHub, PLC, e-design, AI Assist and Virtual
menus, plus Settings and Help. Each workspace's submenus appear in a persistent
bar below the account header. Document Management and Spin connect retain their
nested choices at the top. Existing module visibility and backend permissions
still govern access. The submenu bar wraps at smaller widths.

MatchView now separates two controls:

- **Tree filter** chooses files in the explorer. **Differences** includes added,
  modified and removed files; **Modified only** excludes added and removed files.
- **Workspace filter** selects source changes inside the selected file. It keeps
  the tree filter and selected file unchanged. Structured HMI and hardware views
  retain their own existing controls.

**Differences** shows all three source-change types with five surrounding source
rows before and after each change, bounded by the start/end of the file. Nearby
windows merge. Omitted regions are marked, original line numbers remain visible,
and both source panes share vertical/horizontal scrolling. **Show all source**
restores the complete aligned source. The explicit resize bar below the workspace
supports dragging and keyboard controls; the workspace-height presets remain.

Export's **Differences** checkbox selects added, modified and removed statuses
together; **Modified only** remains a separate file-status selection. Report
choices wrap without splitting labels into individual letters. HTML, PDF and Word
exports use source context and remove the ruled detail-cell grid. Blank alignment
cells remain blank instead of showing fabricated source labels or configuration
placeholders. Change colors, source references and report headings remain.

Chopper's conversation area has a draggable **Response height** control. Arrow
keys resize it, Home/End select its limits, and **Reset** restores the automatic
layout. The height is saved through existing account settings. The welcome screen
keeps its own layout; attachments, log decoding and the message composer remain
available. Height limits adapt to the viewport.

Validation:

- All four production interface builds and TypeScript checks passed.
- 20 comparison/export tests passed, including context boundaries and HTML/PDF/
  Word source evidence.
- 16 integrated browser checks passed, including a real local comparison and
  background report preparation, independent filters, navigation and resizing.
- Nine chatbot browser checks passed for decoded logs, pointer/keyboard resizing,
  account persistence/isolation, reset, dark mode and responsive layout.
- Navigation and report dialogs were checked at 1600, 1067, 800, 760 and 390 pixels;
  chatbot sizing at 1600, 1067, 800 and 390 pixels.

Artifacts: `.build/navigation-matchview-20261103/` and
`.build/chat-resize-20261103/`. UI/API version: 4.99.3.
