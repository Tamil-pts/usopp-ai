# Browser navigation — 13 November 2026

The existing React state navigation is integrated with the browser History API. No additional router or frontend replacement was introduced.

Module navigation writes `page`; Assist writes `assistTab`. WorkHub records `hubView`, `workhubProject`, `workhubItem`, `workhubSection`, `documentStage`, `hubTab`, `documentScope` and document-list kind. Existing WorkHub query links remain supported. Copy the current address to bookmark an authorized project or independent document. Authentication leaves the requested URL intact, and data still loads through authenticated APIs.

Back and Forward restore route selections. Refresh uses the current URL. Once application history is exhausted, normal browser navigation can leave the application. Backspace outside an editable field does not trigger legacy browser navigation.

WorkHub breadcrumbs provide Overview/Projects/Documents/project navigation. Project search, stage/type/owner, date selection and table/cards/timeline presentation persist through the existing account storage mechanism. The current project, task, document stage and workspace tab are URL state. Uploaded browser File objects and unsaved tool execution results are not serialized into URLs.

Unsaved-state registration covers document drafts (including MOM), document studio, quality reports/FRD, drawing edits and drawing document information. Internal navigation and browser history prompt before leaving dirty state; refresh/closing uses the browser's native warning. Existing save/flush and approval rules remain in place. Browsers control the wording of native refresh warnings.

The existing Python SPA fallback continues serving frontend URLs. Both `/api` and unknown `/api/*` return API 404s rather than frontend HTML. Reverse proxies must forward frontend query strings and route API requests to the backend; a static-only host requires its own fallback to `index.html`.

Verification uses an isolated temporary database and accounts, plus the production frontend build. Run the browser check from the repository root with `.venv/Scripts/python.exe tests/browser_history_check.py` after building the main interface. It covers authorized project links, refresh, Back/Forward, module navigation, retained filters, direct drawings, unsaved-navigation cancellation, breadcrumbs, private document denial and SPA/API separation.

Follow-up verification: Assist module and tab selection now creates one history entry and respects cancelled unsaved navigation. My Work/Approvals mode is URL state; project list page number is retained with filters. Project overview and FRD/MOM breadcrumb/tab switches now honor the unsaved guard. The browser verification checks both cancelled Back and cancelled module navigation, plus Backspace outside inputs.
