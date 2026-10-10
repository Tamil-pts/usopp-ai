# uSOPp.ai application architecture

The application is split by engineering responsibility so a change in project comparison can be reviewed and maintained without editing validation code.

## Frontend

- `src/app/App.tsx` owns application navigation, theme and composition of Home, Packet Lens, Nami Live, Twin Scope, Rule Pilot, Chopper Desk, Settings and Help. `src/shared/features.ts` defines the visible feature names and shared guidance.
- `src/features/account/` gates the whole app with login/account creation and provides password change in Settings. `src/features/help/` provides the shared Help page linked below Settings at the bottom left.
- `src/features/plc/` hosts the Nami interface from `dist/nami` in one isolated frame with a shared theme and session. `nami/src/` retains the original Nami components, packet parser, presets and reports.
- `src/features/validation/` owns PLC packet/offset result presentation, metadata comparison, dropdown views and result normalization. `useValidationWorkspace.ts` owns validation inputs and results; `WorkbookViewer.tsx` keeps edits across worksheets and exports complete workbook copies.
- `src/features/compare/` owns the two-project comparison screen, comparison state, progress polling, comparison requests and its own `compare.css`. It does not import validation state or normalization.
- `src/features/rules/` owns engineering rule setup and rule-validation requests.
- `src/features/assist/` owns evidence-based chatbot presentation. Assisted rule configuration belongs to the Rules page.
- `src/features/settings/` owns preferences and knowledge-base configuration UI.
- `src/shared/` contains UI primitives, common types, logging, local filesystem selection, project upload helpers and the table layout provider used across features.

## Backend

- `backend/app.py` assembles FastAPI middleware and the feature routers.
- `backend/api/auth.py` owns account registration, login, session lookup, logout and password changes. `backend/core/accounts.py` stores salted password hashes, profile fields and revocable sessions in SQLite at the writable runtime root. Authentication middleware protects engineering APIs; health and account entry routes remain public. Accounts share engineering resources; there is no per-user project ownership or administrator-only editing policy yet.
- `backend/api/nami.py` owns live PLC, simulator and manual frame APIs; native TCP operations are in `backend/core/nami_transport.py` and `backend/core/nami_simulator.py`.
- `backend/api/validation.py` owns validation and metadata generation through a common execution path for uploaded and local projects.
- `backend/api/metadata.py` owns explicit workbook lookup and complete-workbook copy/edit/export endpoints.
- `backend/api/comparison.py` owns only two-project comparison endpoints and comparison job handling.
- `backend/api/rules.py`, `backend/api/assist.py`, and `backend/api/knowledge.py` own their respective API areas.
- `backend/api/system.py` owns health, logging, local browsing, cache, and download endpoints.
- `backend/core/project_info.py` reexports `python_engine/project_info.py`, the identity reader shared by local project details, comparison and validation discovery. AS 2.7 uses its sole user Physical configuration and resolved `pgm/<project>/CPU` folder when `LastUser.set` is absent; HMI type comes from the active `hw.cfg`. See [AS27_PROJECT_LAYOUT.md](AS27_PROJECT_LAYOUT.md). The Validation page does not display `LastUser.set` content.
- `backend/core/runtime.py` owns shared workspace paths, staging, safe project paths, logging configuration, and engine process helpers.
- `server.py` remains the Python server entry point. `Start_uSOPp.bat` delegates to `start_usopp.ps1`; production serves the built React interface and API from the same localhost server. `setup_usopp.ps1` manages dependencies and builds.

## Engineering boundaries

The Python v1.71 packet validator remains the source of truth for packet, offset, metadata, dropdown, and generated-workbook behavior. Feature modules call it through the validation API; the frontend does not recreate its engineering checks. The comparison engine remains called only by the comparison API.

Future AI or learning features should add reviewed knowledge records and explicit workflows in the knowledge/assist areas. They should not silently change deterministic validator results. A proposed rule, mapping, or learned relationship should remain reviewable before it becomes reusable engineering knowledge.

## Extending a feature

Add UI and requests within its `src/features/<feature>/` directory. Add the matching router under `backend/api/` and register it in `backend/app.py`. Keep shared filesystem/workspace helpers in `backend/core/`. Changes to a feature should not import another feature's state or engine.

Generated workbook paths and validation input manifests are explicit. Do not select a metadata workbook by newest-file timestamp. Store edits as new copies and keep knowledge scoped by project name. Changes to validation algorithms require separate engineering review; all three current engine implementations are unchanged by this restructure.

## Retention and versioning

`package.json` is the application version source; Python reads it at startup. `CHANGELOG.md` contains current and historical revisions. Engine filenames and rule schema versions identify separate compatibility contracts. Runtime session files and persistent exports are not removed by an automatic timer.
