# Reusable B&R Python library

The executable library is Python. The portable, versioned interface registry is
[br_catalog.json](../knowledge/virtual_plc/br_catalog.json). It records 2,278
documented B&R help entries, public parameters, source references and current
implementation status. A database is unnecessary for this registry.

## Python use

Run from the uSOPp application directory with its Python environment:

```python
from virtual_plc.br_library import BRLibrarySession, catalog

plc = BRLibrarySession([
    {"name": "Message", "type": "STRING[32]", "initial": "Ready"},
])
length = plc.call("strlen", plc.address("Message"))
scaled = plc.block("LCRLimScal", "speed",
                   x=5, x1=0, y1=0, x2=10, y2=100)
timer = plc.block("TON", "delay", IN=True, PT=20)
plc.scan(2)
timer = plc.block("TON", "delay", IN=True, PT=20)
assert timer["Q"]
```

Instances retain independent state. All addresses are handles to bounded virtual
memory. FileIO, serial, USB, TCP, CAN and Modbus operate on simulated state. A
missing peer returns an error/no-data status; it does not generate a successful
reply. The native vendor runtime and physical equipment are never invoked.

Implementation modules:

- `core/libraries.py`: IEC math, conversions, strings, timers, counters and edges.
- `core/vendor.py`: address, size, strings, byte copies and virtual FileIO.
- `core/cpu.py`: RTC, battery, system information and Ethernet settings.
- `core/vendor_services.py`: serial, TCP, USB, data objects, visualization and
  other documented services. Calibration stays active until a virtual operator
  completes it; a physical touch screen is not calibrated.
- `core/fieldbus_services.py`: bounded CAN/CANopen frames and objects, Modbus
  register commands 3/4/6/16 and timeout behavior. Automatic native Modbus
  configuration-object polling and other Modbus function codes remain outside
  this model. Register values require explicit virtual-node configuration.
- `core/csv_services.py`: CSV allocation, cells, open/save and array transfer,
  translated from the supplied BRSE_CSV public C sources and interfaces.

The registry distinguishes documented entries from implemented entries. It is
not a claim that every B&R library or native implementation is supported. Python
floating point calculations and library timing are simulation behavior; exact
machine timing and all native REAL rounding details are not asserted.

Rebuild the registry after adding a documented implementation:

```powershell
.\.venv\Scripts\python.exe -m virtual_plc.core.catalog
```

Authenticated lookup: `/api/virtual-plc/library-reference?name=IcmpPing`.
The executable inventory is `/api/virtual-plc/library-support`.

## Full-project verification

```powershell
.\.venv\Scripts\python.exe -m virtual_plc.verify_project '..\project 2' `
  --configuration LDF3S_WO_SUCTION --milliseconds 3000 `
  --corrections virtual_plc/examples/project2-source-corrections.json `
  --output .build/virtual-plc/project2-readiness
```

This checks the entire assigned configuration, source hashes, compile blockers,
runtime faults and whether every cyclic class executed. Use at least the longest
configured task period. `--cached` reuses a saved analyzed model while compiling
the current Python implementation; omit it after source/declaration changes.

### Project 2 source correction

The original `COMMUNICATION/Cyclic.ab:104` copies the 255-byte serial-buffer
capacity from `CS1030_SENDBUFFER`, declared as 17 bytes. The recorded correction
uses `SIZEOF(CS1030_SENDBUFFER)`. It changes the in-memory simulation copy only,
requires the exact original code hash, and appears in the console and workspace
banner. The original PLC file stays unchanged. Removing the correction restores
the original unsafe operation and the bounded-memory fault.

### Project 3 initial settings

`Config7_REG_MCMT_CTL_HPM_ECS` compiles without active blockers. Its original
startup state has `FRD_VW1904=0`; `can_nwCyclic.st:263` divides by that value.
The commented Test Values in `main/mainInit.ab` contain an example value of 270
and other machine settings. They are not active source initialization or
confirmed retained machine data.

Under the user's instruction to use representative textile values,
`examples/project3-textile-baseline.json` selects only the missing front roller
diameter: **27.0 mm**, encoded as **270**. The original `set_logCyclic.ab:3-4`
divides this tag by 10 for display; `MACHINE_SETTINGS1.page` also configures one
additional fractional digit. Rieter documents 27 mm as a regular bottom roller
size, and CTMTC lists 27 mm rollers for its JWF1590 frame. These manufacturer
examples support a simulation assumption; they do not establish a universal
textile standard or confirm the installed geometry of this machine. Exact URLs,
scaling evidence and the retrieval date are stored in the JSON profile.

```powershell
.\.venv\Scripts\python.exe -m virtual_plc.verify_project '..\Project 3\LR9SXPV6338' `
  --configuration Config7_REG_MCMT_CTL_HPM_ECS --milliseconds 3000 `
  --profile virtual_plc/examples/project3-textile-baseline.json `
  --corrections virtual_plc/examples/project3-source-corrections.json `
  --output .build/virtual-plc/project3-readiness
```

The larger `examples/project3-source-test-values.json` remains a separate,
unselected example containing the commented source settings. Derived values and
other machine settings are left to the original initialization/task logic.
Profiles are separate from declarations and are reapplied on reset.

Project 3 also contains four serial transmit copies in
`cs_read/cs_readCyclic.ab:98,197,420,554` that request the 255-byte destination
capacity from the 25-byte `SENDBUFFER` source. The recorded corrections use
`SIZEOF(SENDBUFFER)` at all four sites in the simulation copy. The original
`FRM_write` message length stays 16 bytes. All corrections require the exact
original source hash and are listed in `examples/project3-source-corrections.json`.
Removing these corrections restores the original out-of-bounds copy fault.

In **Workspace settings**, reusable overrides can contain `sourceCorrections`
and `simulationProfile` documents. Both travel with exported workspaces. Full
source files and their original hashes remain separately available for review.
