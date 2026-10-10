# Nami PLC Data Verification V1.5 in uSOPp.ai

The frontend was copied from `NAmi_plc-data-verifier_v1.5`. Its layout,
components, packet parsing, machine presets, metadata import and reports are
retained. An isolated frontend bundle keeps its Tailwind styles separate from
the uSOPp interface. Integration changes are the API/static URL prefixes and
the same LAN HTTP UUID compatibility shim used by uSOPp.

## Open

Start uSOPp using the existing Windows launcher, sign in, then select **Nami Live**.
The original Nami screen is also served at `http://127.0.0.1:8200/nami/`.
Use the configured application port if it differs from 8200. There is no
separate port 3000 server or Node process. Nami uses the same uSOPp account session.

The workspace follows uSOPp's shared light/dark theme. **Help** explains the
connection, metadata, polling, report and protocol workflows. Application ports
are restricted to 8200–8500 (production 8200; optional frontend development 8201).
PLC TCP ports are independent and must match the controller configuration.

PLC Settings resets to saved values whenever reopened. Cancel discards edits
and target selection. Save & Apply validates and persists the draft; opening
Metadata or RTC from this dialog also applies the draft first.

PLC TCP connections originate from the computer running the Python backend.
That computer must be able to reach the configured PLC IP and port.
Simulator state is shared within that backend process, as in Nami V1.5;
PLC configurations remain in browser local storage. Leaving PLC Data unmounts
the screen and stops its automatic frontend polling.

## Build and package

From the uSOPp directory, run `npm run build`. It builds uSOPp first and then
Nami into `dist/nami`. On the first build the helper installs Nami's locked
dependencies automatically; this requires network access. Node is used only
for the frontend build.

The existing `build_windows_exe.ps1 -RebuildFrontend` includes both bundles
and the Python PLC API in the optional executable. Existing release executables
must be rebuilt to include this integration. A running source application must
be restarted to load the new API routes.

Native backend: `backend/api/nami.py`, `backend/core/nami_transport.py`, and
`backend/core/nami_simulator.py`. Reads use one connection per sequence and
send Group 11 after the requested groups. Requests to the same PLC IP/port are
serialized; requests to different targets can run independently. RTC and
manual writes are sent once without automatic retries.

## Verification

Local API regression checks: `python -m unittest discover -s tests -p test_nami_integration.py -v`.
These cover simulator groups, frame validation, invalid settings, manual/RTC
simulation, fragmented loopback TCP replies and the automatic Group 11 close.

With a local test server on 8300 and Playwright installed for development,
`python tests/nami_browser_check.py` checks the Edge UI, shared themes, Help,
Cancel, Save and simulator handshake. Browser screenshots are in
`.build/nami-checks`. No live controller is contacted by these checks.

Real-controller reads and writes still require hardware verification.
