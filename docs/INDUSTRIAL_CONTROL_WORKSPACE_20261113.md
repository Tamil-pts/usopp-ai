# Industrial control workspace - 13 November 2026

Virtual Electrical now exposes one industrial workspace. The Electronics/SPICE
mode selector is removed. Existing native circuit files and backend support are
retained so this interface change does not destroy previous data.

The default view is a light circuit canvas with industrial NO/NC contacts,
relay/contactor coils, an indicator lamp and a DC control supply. Symbols can be
added, selected, dragged on a grid, assigned to inputs/coils and deleted. Wires
connect explicit named terminals and can be added/deleted through the inspector.
Zoom/fit, a starter circuit, browser save and JSON download are available.
Drawing reconstruction remains a view within the same industrial workspace and
retains its source evidence, table decoder and verification gates.

## Simulation scope

The new account-authorized POST /api/virtual-electrical/control/simulate endpoint
solves discrete DC contact/coil connectivity from the explicit circuit model.
It supports one supply up to 48 V DC, at most 100 devices and 300 wires, and
bounded relay-feedback convergence. No user SPICE commands or external controller
requests are executed. Contacts reference declared external inputs or existing
coils. Missing terminals, unsupported kinds, short circuits, forced coil inputs
and oscillating relay feedback block the solve.

The starter uses STOP and overload NC contacts, a START NO contact, K1 holding
contact, K1 coil and H1 indicator. Test cases exercise start, hold, stop, overload
trip/reset and no automatic restart after a trip when Start is released. Holding
Start while resetting an overload can restart this particular circuit; it is a
functional example, not a safety control design.

Simulation gives logical energized/off states and supply-connected wire coloring.
It does not calculate current, motor mechanics, timing, analog waveforms, safety
performance or the behavior of arbitrary imported drawings. PDF geometry is not
silently converted into executable contacts. The LC361 drawing remains unresolved.

## Validation

31 targeted backend tests passed, including retained electrical import and native
circuit regressions. TypeScript compilation and production build passed. Browser
tests cover start/hold/stop/overload states, saved drawing reload, source import,
review gates, reconstruction API availability and layouts at 1600, 1024 and 390
pixels. Tests run against isolated data roots, not live account/project records.

Screenshot: .build/electrical-reconstruction-20261113/industrial-control.png.

The reported API-endpoint error is consistent with an already-running backend
that predates the new routes. The current combined application includes the
router and its authorized endpoints. An explicit message now identifies a missing
backend route and asks for the updated backend to be loaded, rather than hiding
the error or reporting a successful import.

Deployment check: restarted the identified application through start_usopp.ps1 on port 8200 after preflight. The live main page returned HTTP 200; /api/health returned status ok, UI/API 4.99.3, industrialElectricalReconstruction=true and industrialDiscreteControlSimulation=true. The final browser run also verified that a direct supply short produces HTTP 409 and a visible error. Existing account/project records were not replaced.
