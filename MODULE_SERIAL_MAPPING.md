# Module serial no mapping

Open AI Assistant / Rule configuration and select `BR_MODULE_SERIAL_420`.
The review shows the complete GC 420 requirement and its related source checks.
Click **Configure serial requirements / cross references** to change the packet
source and optional I/O, hardware and declaration file scopes. Blank scopes mean
automatic discovery. Use project-relative paths or filename patterns.

This rule uses the dedicated serial-number validator. Editing it does not convert
it into a generic empty exact-logic rule. Scalar variables, individual array
elements and bulk array copies are supported. The actual variable names come
from SerialNumber bindings; they are not fixed to one machine's names.

The required trace is:

1. Controller and electronic module inventory for the active physical configuration.
2. Exactly one SerialNumber I/O binding per module, with distinct variable or
   array-element ownership.
3. The bound variable's UDINT / DINT / DWORD declaration and array bounds.
4. The corresponding PLC packet task and every applicable GC 420 path.
5. Four bytes per serial, complete copy bounds, cursor increments, payload
   header and response length/trigger setup.

These stages use AND: all must pass. An exact literal code block is unnecessary
because different projects use different names and valid scalar/array layouts.
Additional unrelated data in GC 420 remains part of the packet-length checks.

The active configuration comes from `LastUser.set`. Inactive configurations are
excluded, including when an optional file pattern names an inactive target.
AS 2.7 uses its single `pgm` CPU configuration. Without settings, a single
physical configuration can be resolved automatically; multiple configurations
without a valid active selection produce a selection finding instead of a scan
of all targets.

Run the draft against the selected project and review the output before saving
and enabling. A correctly configured requirement can still return FAIL when the
project violates it. Missing inventory or ambiguous PLC ownership is reported;
it does not establish that every module is correctly mapped.

## Source checks on 2026-10-07

- Project 2: only active `LDF3S_WO_SUCTION` is checked. Its PLC1 controller lacks
  a SerialNumber binding; the X20PS9600 power supply binding does not represent
  the controller. The inactive with-suction configuration is excluded.
- The staged NM_V2121 AS 2.7 project: 3 checks, 2 failed. Its CPU/IOMap.iom has no
  supported SerialNumber bindings. Its legacy hardware inventory is not resolved
  by this rule's Hardware.hw reader, so complete module coverage is unverified.

The checks read project files and do not require a connected physical PLC.
Detailed evidence is in `.build/module-serial-review-project2.json` and
`.build/module-serial-review-nm-v2121.json`.

## Verification on 2026-10-11

Two validator defects were reproduced and corrected:

- The backend starts `rule_engine_v4_30.py` as a script. The serial validator
  previously imported `python_engine.project_info` without its script-mode
  fallback, producing `Rule evaluation error: No module named 'python_engine'`.
  Both package and direct-script execution now work.
- Project 3's `4PP065.IF23-1` Power Panel interface accessory was counted as a
  second controller. Interface accessories are now excluded from the serial
  inventory along with passive terminals/bases. Actual additional controllers
  still require explicit target ownership.

| Project | Active configuration | Result | Checks |
| --- | --- | --- | --- |
| Project 2 / LDF3S_16480 | LDF3S_WO_SUCTION | FAIL: missing PLC1 SerialNumber binding | 33 passed, 1 failed |
| Project 3 / LR9SXPV6338 | Config7_REG_MCMT_CTL_HPM_ECS | PASS | 125 passed, 0 failed |

Project 2 binds `HW_100_X20PS9600_SerialNo` to `X20PS9600.SerialNumber`
in `Physical/LDF3S_WO_SUCTION/PLC1/IoMap.iom`, line 126. Its GC 420 copy
is labelled "CPU Module" at `mms_nw_rCyclic.st`, line 2173, but that binding
identifies the X20PS9600 power supply. There is no `PLC1.SerialNumber`
binding. The 16 mapped scalar values, declarations and 64-byte payload pass;
the separate required controller binding still fails. Review that requirement
and the intended controller serial before changing PLC source or packet size.

Project 3 has 41 SerialNumber bindings. GC 420 copies 200 bytes from
`BR_HW_SR_NO[0]`, covering indices 0 through 49 inside the declared 0..50
UDINT array. All bound elements, including controller index 45, are included.
Five additional 50-byte drive strings give a 450-byte payload, matching the
configured header (`1 * 256 + 194`) and response setup.

The real API flow was checked using isolated test accounts, workspaces and
history databases. Both projects returned their structured findings; their
separate test/history IDs and results survived history retrieval and SQLite
archiving. Existing user accounts and live histories were not changed.

22 related regression tests pass, including 12 serial-mapping tests. They cover
script execution, the interface accessory, real multiple-controller ambiguity,
scalar and bulk-array copies, bounds, missing bindings, duplicate ownership,
datatype errors, packet headers and active configuration selection.

Detailed results are saved in `.build/module-serial-project2-api.json`,
`.build/module-serial-project3-api.json`, `.build/module-serial-api-summary.json`
and `.build/module-serial-regression.log`. These are source-file checks and
API integration checks; they do not read serial values from a live PLC.

Rerun the rule in LogicScan to create a fresh result. Previous history entries
retain their original findings.
