# Flowchart workspace repair and Visual Assist — 13 November 2026

The React Flow selection callback now has a stable identity and does not update selection state when the selected IDs are unchanged. Display nodes and edges are memoized. This removes the render feedback path behind the reported maximum-update-depth error. Resize undo checkpoints remain connected through a ref.

The existing editor retains alignment/distribution, grouping/ungrouping, layers, locking, typography, connectors, undo/redo, templates and SVG/PNG/PDF/JSON export. Canvas background color is directly accessible in the page toolbar and applies to infinite canvases too.

Chopper Visual Assist is an optional panel in this same editor. Paste sentences or bullet points, preview Process, Cycle, Timeline, Mind map, Infographic or Comparison arrangements, choose Ocean/Meadow/Sunset colors, and confirm replacing the draft. Generated shapes and connectors remain editable and use existing revision/export paths. Original text and layout choices are saved with the drawing.

Generation currently uses local sentence splitting and layout rules, preserving source wording. It does not infer validated PLC behavior, summarize engineering requirements, generate numerical charts, select semantic icons or implement the complete Napkin product. Existing symbol libraries remain available for manual insertion. External asset libraries, arbitrary SVG/image uploads and PPT export are not added by this change.

Verification: TypeScript compilation and the main Vite production build passed. Drawing/independent-document regressions: 38 passed. Browser check passed: opening, local text generation, four editable shapes, selection and save with no page errors. Evidence: `.build/flowchart-20261113/editor.png`.
