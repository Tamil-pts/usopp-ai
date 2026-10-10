# Multiple users and saved tests - 4.65.6

## 1. Account capacity

The default is **five enabled regular users plus Admin: six accounts total**.
Admin can check usage in **WorkHub → User management**. Self-registration and
Admin account creation use the same limit. Disabling an account frees a slot
and preserves its historical results. Re-enabling it requires an available slot.
Existing usernames, password hashes, roles and results are preserved. If an
existing installation already has more than six enabled accounts, they remain
enabled; further creation or re-enabling is blocked until capacity is available.

Users can change their own password through **Settings → My account**.
Shared model connection settings and account administration stay Admin-only.

Use separate computers or browser profiles for independent simultaneous logins.
Tabs in the same browser profile share the application session cookie.

## 2. Test identity and history

Every new test receives a unique public `testId`, an internal `historyId`, an
owner's stable account ID, and a timestamp. Results are stored on the server.

| Activity | Retained result |
| --- | --- |
| ByteMap | Packet/metadata validation, findings, source snapshot and Excel report |
| MetaWorks | Generated metadata workbook, findings and source snapshot |
| LogicScan | Rule outcomes, evidence, source snapshot and generated reports |
| MatchView | Comparison result, saved source/HMI/ladder details and prepared report versions |
| DataInspect | PLC target, metadata, sent/received bytes, transport outcome and browser-decoded parameter checks |
| DataInspect manual data | Supplied bytes, metadata and decoded results, explicitly marked manual |
| Data model validation | Reference model, metadata, exact name/type/group checks and result summary |
| RTC / manual frame sending | Sent frame, response and outcome; acknowledgements do not prove the clock changed |

Open **WorkHub → Test history**:

1. Admin sees all users' tests; regular users see their own.
2. Search a test ID, project, PLC or username. Filter by activity, status or user.
3. Choose **Open result** or a saved download.
4. DataInspect opens the original target, metadata and captured values in a
   read-only view. Generate its Excel/JSON report from those saved values.
5. Choose **New live test** to make another PLC request.
6. Reuse an available project snapshot to start a new validation or rule test.

`Completed` means processing finished. Review the pass/fail/mismatch findings
to determine the validation outcome. Engine errors are retained as failed runs.
A server restart marks unfinished runs as interrupted; start another test.

Each DataInspect read, Run All, connection check, manual decode or transmission
has its own test ID. Collected reports can contain several reads; each group
keeps its original ID in Excel and JSON. Raw captures are archived first. If
the browser closes before saving decoded values, the history viewer decodes
the archived bytes using the saved metadata and the installed decoder.

Earlier DataInspect values existed only in browser memory and cannot be
recovered automatically. Earlier saved validation/rule/comparison sessions
remain available to Admin, with ownership marked as not previously recorded.

## 3. Concurrent processing and account separation

- Up to five project engine jobs can run concurrently by default. Additional
  requests wait for a slot; jobs using the same source project are serialized.
- Source saves are blocked while that project is being processed. Cache
  clearing skips queued/active tests and other users' uploaded sources.
- Uploaded workspaces, saved results and downloads have persistent ownership
  checks. Admin can review every user's results.
- Browser PLC targets, metadata selections, covers and layout preferences are
  stored per account. Each account has its own simulator state.
- Requests to the same real PLC are serialized to preserve protocol framing.
- Server-local project folders and shared engineering libraries are shared
  resources. Per-account isolation applies to staged uploads and result records.
- Run one backend process; its thread pools and project locks handle concurrent
  users. Multiple Uvicorn workers or replicated servers need an external job
  queue and coordinated locks before use.

## 4. Ubuntu update and configuration

Complete current jobs and back up the data as described in [UBUNTU_DEMO.md](UBUNTU_DEMO.md).
Copy the updated source into the existing application folder while preserving
`accounts.sqlite3*`, `.usopp_workspaces`, `.usopp_exports`, `knowledge` and `rules`.
Do not replace an existing account database with a distribution copy.

```bash
cd "$HOME/usopp-demo/usopp_ai_2.0"
source .venv-ubuntu/bin/activate
npm stop
npm run server:install
export USOPP_MAX_USERS=6
export USOPP_MAX_PARALLEL_TESTS=5
npm start -- --port 8201
npm run status
```

Open `http://<server-IP>:8201`. The UI and API badges should match the updated
`package.json` version (currently **4.65.5**). For 4.65.3 and later, also copy the bundled
data model references as described in [UBUNTU_DEMO.md](UBUNTU_DEMO.md).
Restart the backend after updating source or changing either capacity setting.

`USOPP_MAX_USERS` counts all enabled accounts, including Admin. Its default
is `6`; replace an older explicit setting of `5` with `6`. To increase account
capacity later, set a larger positive integer before starting. Keep
`USOPP_MAX_PARALLEL_TESTS` independent; raising it increases CPU/memory demand.
Store these exports in the server's startup script or service environment so
they persist after reboot. Default values require no environment variables.

The data root defaults to the source application folder on Ubuntu. EXE launches
default to `%LOCALAPPDATA%\uSOPp.ai`. `USOPP_DATA_ROOT` can select a persistent
directory. Changing that path creates a separate installation unless the
existing data is transferred first.

| Persistent location | Contents |
| --- | --- |
| `accounts.sqlite3*` | Accounts, sessions and resource ownership |
| `.usopp_exports/history/` | Test records, results, metadata inputs and archived downloads |
| `.usopp_workspaces/history/` | Project source snapshots |
| `.usopp_exports/compare/` | Background report manifests and original exported versions |
| `.usopp_exports/identifiers.sqlite3` | Stable engineering rule IDs |
| `knowledge/`, `rules/` | Engineering references and settings |

Back up the same data root with the server stopped. Retained tests and live-read
captures accumulate on disk; monitor available space. Browser preferences are
account-scoped but remain local to each browser. Restoring server history does
not restore a browser's local preferences.

## 5. Implementation checks

The six-account checks (five regular users plus Admin) use a separate temporary
server, account database, uploads and results. They exercise real engines and
six independent browser profiles. No physical controller is contacted.

Verified scenarios:

- Six ByteMap and MetaWorks requests, with five engines overlapping and the
  sixth waiting for a slot. Each generated workbook has its own source marker.
- Six LogicScan and MatchView runs, plus different validation tools submitted
  together. Each run keeps its own ID, account and archived result.
- Private data model imports/checks, simulator values and decoded DataInspect
  history. Other users cannot read the uploads, source, results or downloads.
- Six background comparison report jobs with individual HTML/PDF/JSON
  downloads, and separate versions of LogicScan reports.
- Six browser profiles using the normal **Run validation** button, per-account
  history/settings, and saved DataInspect results with live reads disabled.
- Six requests to one loopback TCP controller: complete request/response and
  close sequences remain separate. Requests to one physical PLC use this same
  serialization path, but a physical-controller load test is still pending.
- Source-save rejection during validation, cache clearing by another account,
  same-project queuing, the five-engine limit, failure isolation and retained
  accounts/results/downloads after restarting the temporary backend.

The focused checks are reproducible from the application folder:

```bash
python -m unittest tests.test_multi_user -v
```

Use the application virtual environment. Browser checks require Microsoft Edge
on Windows, or an installed Playwright Chromium browser on Linux. The checks
create and remove their own temporary installation; existing accounts and
projects are not used. They use small deterministic project fixtures and a
loopback PLC, so they establish correctness rather than production throughput.

On 2026-10-10, all **156 regression checks** passed, including the 16
concurrency/browser checks and **85 retained runs** from five regular users
plus Admin across a backend restart. The browser checks also verified the
regular-user capacity display. Python compilation, both TypeScript checks and
both production builds passed.
Deployment and load testing of **4.65.2** on the Ubuntu server
remain pending; copying source does not update an already running process.

## Git packages and container deployments

Use GIT_DISTRIBUTION.md for private GitHub downloads and distribution/README.md for installation. The container uses six enabled accounts, five engine slots and one backend worker. A persistent named volume retains accounts, user ownership, unique test IDs, reports and Admin history across image upgrades. Native Windows and container installations use separate stores.
