# Offline B&R service models

The Virtual PLC implements the following public B&R interfaces in Python. The
interfaces and error numbers are taken from the bundled B&R Automation Studio
help under `knowledge/br_help/AS12/Help-en/Data/libraries` and the project's
library `.fun`, `.typ`, and `.var` declarations. The original project is read
only. These models do not load vendor binaries or contact host devices.

| Service | Implemented simulation behavior |
| --- | --- |
| `FRM_xopen`, `FRM_gbuf`, `FRM_write`, `FRM_robuf`, `FRM_read`, `FRM_rbuf`, `FRM_close` | Virtual serial interfaces, configured transmit/receive buffer pools, buffer ownership, transmitted frame history, explicit injected receive frames, and documented missing data/invalid handle/buffer statuses. No reply is invented. |
| `TcpOpen`, `TcpClient`, `TcpServer`, `TcpSend`, `TcpRecv`, `TcpClose`, `TcpIoctl` | Bounded sockets entirely within a workspace, virtual listeners and clients, byte queues, peek, connection lifecycle, common 32 bit socket options, and documented errors. A listener without a peer returns `tcpERR_NOCLIENT`. No OS socket is opened. |
| `DatObjCreate`, `DatObjInfo`, `DatObjRead`, `DatObjWrite`, `DatObjDelete` | Actual bounded byte objects with identity, offsets, timestamps, memory type and warm/cold reset lifetime. Missing objects and invalid ranges return documented statuses. |
| `AsIOMMCreate`, `AsIOMMRemove` | A virtual installed-module registry containing the source data object's actual bytes. Missing data objects and invalid module kinds/names return documented errors. Native `.br` payloads are not loaded or executed; these operations do not reconfigure physical I/O. |
| `DevLink`, `DevUnlink` | Named virtual file devices and handle lifetime linked to the in-memory FileIO store. Device parameter strings do not mount any host disk or network share. |
| `UsbNodeListGet`, `UsbNodeGet`, `UsbDescriptorGet` | Explicit virtual USB nodes, filtered node IDs, exact documented node/device-descriptor buffers, attachment count and bounded pointer errors. The default has no USB node and returns `asusbERR_USB_NOTFOUND`. Host USB is never enumerated. |
| `TMP_alloc`, `TMP_free` | Library-owned byte regions from the 4 MiB virtual address pool; exact allocation/free matching. Invalid pointer use faults with a source location. Simulation initializes allocated bytes to zero for deterministic behavior; the vendor function itself does not promise initialization. |
| `LCRLimScal` | Linear REAL scaling, limiting, reversed coordinates and the documented zero result for equal input coordinates. |
| `LogIdleShow` | A measurement over virtual scan time using one virtual microsecond per emitted IR event. It reports simulated work; it does not measure host CPU usage or reproduce Automation Runtime scheduling costs. |
| `MEMxInfo` | DRAM reports the defined 4 MiB virtual byte pool and its actual remaining allocated capacity. Memory types for which the model cannot determine a size report the documented `0xFFFFFFFF` value. These values do not represent physical controller or host RAM. |
| `SYSreset` | Requests the selected virtual warm/cold restart or shutdown at a scan boundary. The host machine is never restarted. |
| `VA_Setup`, `VA_Saccess`, `VA_Srelease`, brightness/contrast getters and setters, `VA_Line`, `VA_Redraw` | Per-visualization handles, access ownership, brightness/contrast state and a bounded drawing command frame. Commands are available in the service snapshot. These calls do not alter the host screen. |

Asynchronous blocks return busy on the initial scan and finish on a later scan.
Their request inputs are captured, preventing edits while busy from silently
changing an in-flight request. `LogIdleShow` waits for the configured virtual
measurement period. A disabled block cancels its pending operation.

Only documented public input/output fields are executable service memory. Native
library instance internals are not interpreted as PLC programs. Supported C
instance aliases such as `UsbNodeListGet_typ` share the same public interface.

The virtual serial adapter supports the base `XOPENCONFIG` structure and bounded
standard serial mode parameters. Extension arguments in `argc`/`argv` are
rejected with a mode error. Unsupported TCP ioctls return their documented
status. An error status is a simulation result that the source program handles;
it is never replaced with fabricated device data or a forced success value.

The Python service object offers `configure_usb(nodes)` and
`inject_serial(ident, bytes)` for explicit device scenarios. Neither operation
discovers or modifies host equipment.

Focused coverage is in `virtual_plc/tests/test_vendor_services.py`, including
real buffer transfer, invalid handles, absent devices, scaling and allocation
lifetimes.
