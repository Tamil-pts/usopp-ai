# Compact workspace controls — 3 November 2026

The PLC submenu now calls its packet tools **Spin Connect Workspace**. Its
dropdown opens beside the trigger and exposes **ByteMap** and **DataInspect**
according to the signed-in account's existing module permissions. The dropdown
supports keyboard focus, Escape and outside-click dismissal.

**Project number / assigned project** now appears in the submenu bar for
ByteMap, MatchView and embedded DataInspect. The large project-link cards are
removed from those workspace headers. Recording, refresh, selection details and
load errors remain available under **Project recording options**. Each tool
retains its own saved selection and existing request attribution. An empty
selection or disabled recording continues to run as a separate test.

DataInspect renders its own selector into the same-origin shell toolbar, so its
request headers use the same settings as its displayed control. Leaving the
workspace disposes that interface and its external controls. Opening DataInspect
directly retains its original standalone selector. Archived tests retain their
original attribution and do not offer a new recording selection.

The account header has a centred **How can I help?** launcher. It opens Chopper
over the workspace with the current page context, the existing window guide and
a link to full Chat. It opens on request; loading the page does not ask the
model a question. Narrow layouts use the labelled chatbot icon. Build details
remain accessible in the account menu when the compact version badge is hidden.

Verification:

- All four production interfaces built successfully, including TypeScript checks.
- Ten integrated browser checks covered both dropdown tools, actual comparison
  requests with selected/separate-test headers, saved selections, DataInspect
  remounting and standalone mode, a real window-guide response and restricted
  account visibility.
- Eighteen light/dark layout checks covered widths 1600, 1280, 1067, 950, 800,
  760, 600, 390 and 320 pixels. The header stayed 64 pixels on desktop and 60
  pixels on small screens; the submenu bar stayed 49 pixels. Popups fit the
  viewport. At narrow widths, submenu entries scroll horizontally.
- Seven existing project-attribution, permissions and competency regressions
  passed using isolated data. No controller I/O or model inference was requested.
- The local server serves the new built assets and matching UI/API **4.99.3**
  from this checkout. Existing 53 projects and 34 accounts remain intact.

Artifacts: `.build/compact-workspace-bar-20261103/`. This change requires a browser
refresh and does not require a backend restart or database migration.
