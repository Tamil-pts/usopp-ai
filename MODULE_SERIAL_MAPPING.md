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
