# Native electrical circuit workspace ? 2 November 2026

Open **Virtual ? Electrical**. The active workspace draws editable symbols,
wires, junctions and text on one continuous canvas. Source PDF pages and pictures
are not embedded in this canvas. This replaces the earlier sheet-preview UI.

## Import and exclusions

**Import & redraw** accepts unlocked vector PDFs up to 75 MB / 200 pages. An
existing authorized e-design review can also supply a separate source copy.
Functional vectors from multiple pages become objects in a single flat workspace.
Original page numbers and hashes remain attached to imported objects for review.
Printed references alone do not automatically connect pages electrically.

Cable-kit and connector/terminal assembly pages, cable crimping instructions,
recognized BOM tables, and connector/terminal schedules are excluded. **Import
review** lists exclusions. Functional wiring within a mixed document can remain.
If only excluded content exists, an empty circuit explains what was skipped.

The importer reconstructs vector wires, labels and outlines. A narrowly recognized
IEC resistor rectangle with an unambiguous R-number becomes a resistor candidate;
its resistance still requires confirmation. Other outlines must be classified as
components, unresolved symbols, or reviewed graphics. This does not automatically
recognize every vendor symbol. Raster diagrams and embedded photos need manual
reconstruction with the component palette.

Imported wires, outlines and component candidates require review. Unsupported
symbols and unreviewed functional objects block simulation. Connector hardware
has no simulated device model; reviewed wires and junctions carry connections.

## Editing and simulation

The palette provides R, C, L, voltage sources (DC, sine, pulse), ground, switches,
NO/NC relay contacts, resistive relay coils and lamps, generic diodes, and generic
NPN/PNP transistors. The motor glyph is explicitly unresolved and blocks simulation;
it does not pretend to model a drive or mechanical load.

Use **Wire** to join named pins and add bends. Move, rotate, duplicate or delete
components; attached wire endpoints follow them. Properties edit labels, types,
values and review status. Undo/redo, search, pan/zoom/fit, version-checked saves
and native SVG/JSON export are included. Original PDFs and review comments remain
independent.

**Run simulation** creates a bounded SPICE netlist from reviewed objects and runs
local [ngspice](https://ngspice.sourceforge.io/). Arbitrary user netlists and shell
commands are not accepted. DC operating-point and transient analyses return
actual node voltages and device currents. Plots use the solver's sample times.
Playback displays solved samples; edits invalidate results, including edits
made while a solve is running.

Relay contacts reference a unique coil label and pickup threshold. Successive
runs can seed contact states from the previous coil voltage, supporting the
starter example's start/hold/stop sequence. **Reset simulation** clears that seed.
Capacitor/inductor transients start a new time-zero analysis on each run. Models
are generic: this is not manufacturer drive behavior, motor mechanics, PLC scan
simulation or live equipment feedback.

Endpoints and explicit junctions can join wires. A crossing without an endpoint
or junction does not join automatically. Ideal-wire currents appear only where
the graph determines them uniquely; loops and ambiguous branch currents remain
unresolved. Particle animation uses solved current direction, not charge speed.

Runs allow two concurrent solves, 150 components, 1,500 wires, 800 wire points/pins,
10 seconds of simulated time and 2,000 requested steps. Solver execution has a
12-second wall-time limit. Errors and nonfinite/incomplete results withhold
measurements. Output resampling is reported explicitly.

## Runtime and API

This checkout has ngspice 47 under
`local_simulators/ngspice/Spice64/bin/ngspice_con.exe`. Reproduce the Windows local
installation with `python scripts/install_ngspice.py` (requires 7-Zip). The
installer verifies the official archive's pinned SHA-256:

`59225971bd68cdd1199443649aa4615a9e6d684933f205ab49006a3942518f5a`

Source: [official release](https://sourceforge.net/projects/ngspice/files/ng-spice-rework/47/).
License: `local_simulators/ngspice/Spice64/docs/COPYING`. Alternatively set
`USOPP_NGSPICE` to an installed executable; Linux can use `ngspice` on PATH. This
local Windows runtime is ignored by Git and is not automatically included in
existing release packages. Editing remains available if no solver is installed.

Account-bound routes under `/api/virtual-electrical` include:

- `GET /library` ? symbols, pins, parameter schema and solver availability.
- `POST /projects/native` ? blank, divider, RC or relay-starter circuit.
- `POST /projects`, `POST /projects/from-review` ? import and native redraw.
- `GET /projects`, `GET /sources`, `GET /projects/{id}` ? discovery and progress.
- `GET /projects/{id}/circuit`, `PUT /projects/{id}/circuit` ? versioned document.
- `POST /projects/{id}/simulate` ? saved version, analysis and optional reset.
- `GET /projects/{id}/circuit/export?format=svg|json` ? native vector/model export.

Each account opens only its own electrical workspaces, including simulation and
export. Existing e-design visibility controls access. Source access is checked
before copying. `circuit.json` and `simulation.json` are separate derived artifacts
in owner-scoped `electrical_*` workspaces. Legacy page/scene/layout endpoints
remain for compatibility but do not supply the active circuit canvas.

## Verification

The targeted electrical/e-design regression suite passed **71 tests**. Numerical
checks include the 9 V / 1 k? / 2 k? divider (6 V, 3 mA), RC analytic time constant,
and relay start/hold/stop. Coverage includes native SVG with no images, topology
crossings/junctions, invalid models/geometry, source preservation, owner/module
isolation, version conflicts, and ancillary exclusions. Solver smoke checks also
exercised generic diode, inductor and NPN/PNP models.

The actual 18-page `4C9935069 - 21.08.26-Correction.pdf` has 17 excluded ancillary
pages and one retained connection diagram (page 15). Its 1,145 native objects
require classification/review before simulation. This file is not claimed as an
automatically decoded, runnable machine circuit. The source copy and original
review retained their SHA-256.

All production frontend builds and TypeScript checks passed. Live browser checks
cover native editing, attached wires, save/reload, SVG export, real divider
measurements, RC waveform playback and six light/dark responsive layouts.
Delayed-response checks also confirmed stale simulation results are withheld and
edits made while saving are preserved at the new saved version.
Artifacts: `.build/native-electrical-20261102/`.
