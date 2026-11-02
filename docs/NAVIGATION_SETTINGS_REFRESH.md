# Navigation, Settings and account directory

Implemented on 2 November 2026 in the current uSOPp checkout.

The sidebar flyouts use the same `#073b4c` background as the main rail in light and dark mode. Nested links use contrasting text, hover and keyboard focus states.

The Three.js scenes were removed from the landing page and sidebar on 2 November 2026 at the user's request. The landing page uses its original static engineering image, and the sidebar uses its standard menu layout. The Three.js runtime and type dependencies were removed.

Settings now has a searchable category menu, an overview with colored cards and direct links such as `#settings/document-studio`. Previously visited sections stay mounted to preserve unfinished entries while moving between settings. The account avatar opens My account; WorkHub connection shortcuts open Notifications & sharing. Account and Admin restrictions remain in the existing APIs.

User management provides account search, role/access filters, pagination, pending-request enablement and a focused Create/Manage account dialog. Workspace visibility, password reset and enable/disable controls use the existing account APIs. Departments, teams and work profiles remain available through the organization directory.

Document Studio is available in **Settings > Document Studio**. The library separates template drafts and saved templates, with search, document type selection and a direct editor. Saving a template does not require document approval. Project documents continue to use their structured document forms.

Verification:

- Account API regression suite: **8 passed**.
- Production builds: main uSOPp, Nami and Virtual PLC succeeded.
- Isolated browser checks: light/dark submenu colors, 390/1280 px landing layouts, Settings search and category persistence, template creation and saving, account creation/editing/access, pending account enablement, work profiles, organization directory, mobile dialogs and Admin restrictions.
- Final smoke check: static production landing page, mobile template library, account/connection shortcuts and removal of Settings links when navigating away all pass.

Evidence is under `.build/workhub-project-reference/`: `navigation-settings-result.json`, `navigation-settings-smoke-result.json`, `navigation-settings-tests.log`, `navigation-settings-build.log` and browser screenshots. Browser mutations use the isolated fixture on port 8203, separate from installed account and project data.
