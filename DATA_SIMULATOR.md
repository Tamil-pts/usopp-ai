# Metadata data simulator and Automation Studio targets

## Target modes

Manage targets provides **Real PLC (Network TCP)**, **Automation Studio simulation**,
and **Data simulator (metadata-driven TCP)**. The previous Simulated (Internal)
option is removed from the interface. Old internal targets become stopped data
simulator targets; review their address and port before starting them.

All three current modes use the actual TCP packet transport for reads. A data
simulator opens a virtual PLC listener on the uSOPp server's loopback address.
Automation Studio mode connects to the actual ARsim application you are running.
Neither mode starts Automation Studio or uploads a PLC project for you.

## Start a metadata data simulator

1. In **Manage targets**, select the machine department and **Data simulator**.
   Use `127.0.0.1` and a free TCP port, e.g. `21210`. Save and apply.
2. Open **PLC details → Data simulator** for that target.
3. **Upload / change metadata** opens the existing metadata uploader. Its groups,
   tag codes, payload-relative offsets, types and array widths define the packets.
4. Open the simulator again and **Preview profiles**. Review the automatic
   behavior assigned to each parameter. Unknown names are identified as generic.
5. Override numeric fields with **Constant**, **Changing wave**, or **Increasing
   counter** behaviors as needed. Configure bounds, value or period. Configure
   time speed, machine cycle length, initial elapsed time and program version.
6. **Save configuration** retains the configuration without opening a listener.
   **Start virtual PLC** opens the TCP listener. Test GC 10 or read the metadata
   groups in DataInspect. The same target can feed live dashboards and storage.
7. **Stop virtual PLC** closes the listener. Stop it before editing a running
   configuration. Optional **Start this virtual PLC when the server starts**
   controls restart behavior; stopping does not clear that saved option.

Each simulator has its own metadata, settings, clock, start time, request count
and port. Multiple departments can run concurrently. Configuration belongs to
the signed-in account. At most 16 simulators can listen on the server at once.
They are off by default and listen only on `127.0.0.1`. No physical PLC is used.
Choose distinct ports for separate virtual PLCs.

### Automatic textile profiles

Illustrative department defaults are provided for Carding, Finisher, Breaker,
Comber, Lapformer, Ring Frame, Speed Frame, Blow Room, Auto Winder, RAP and Custom.
These are synthetic example bands, not engineering acceptance limits or a
simulation of the selected project's ladder / ST program. Numeric limits in
metadata remain references; simulator overrides specify the generated range.

| Parameter family | Behavior |
| --- | --- |
| Hank, CV%, U%, TPI, draft | Changing department-based values |
| Delivery speed, spindle / cylinder RPM | Varies while running; stops during the stopped phase |
| Doff count, production, energy | Accumulates over simulated cycles / running time |
| Run / idle / doff time | Related elapsed timers; hour/minute/second components |
| HMS text | `HH:MM:SS` running-time string when metadata declares STRING |
| Humidification monitoring | Changing humidity, temperature and air pressure |
| RTC / calendar | Time and date components; synthetic clock can receive RTC packets |
| Unknown parameter | Identified generic waveform; configure an override |

The cycle runs for 85% of its configured duration and stops for 15%. Time speed
can accelerate the cycle. Separate minute/second component names wrap at 60;
names containing "total" use total elapsed units. Packet integers are constrained
to their PLC datatype. Unsupported types, duplicate identities and overlapping
payload ranges are rejected rather than producing an ambiguous packet.
Arrays are encoded at their declared widths. STRING values are ASCII terminated
and bounded by the metadata width. GC 10 has a program-version fallback, and
GC 11 closes the TCP session without a response. Unsupported groups return a PLC
error. PLC functions outside reads and synthetic RTC updates are not simulated.

## Connect to Automation Studio simulation

Set **Activate simulation** to **on** in Automation Studio, build and transfer
the project to ARsim, then run it with the project's SpinConnect TCP server enabled.
Choose **Automation Studio simulation** and enter the ARsim computer's address
and the TCP listening port configured by that PLC program, plus matching machine
ID and byte order. Upload matching metadata and test GC 10 before the other groups.

`127.0.0.1` refers to the computer running the uSOPp backend, which may differ
from the browser computer. For ARsim on another computer, enter its reachable IP.

The screenshot's `11160` is the ARsim INA/UDP online connection port. It is not
automatically the SpinConnect TCP application port. DataInspect sends SpinConnect
packets; it does not implement INA/PVI variable access. Keep the PLC TCP port
editable and use the port that the simulated project actually opens.

Source: bundled B&R help,
`knowledge/br_help/AS12/Help-en/Data/automationnet/pvibase/lines/lnina2/pvilnina2commar000.htm`
and `automationruntime/targets/ar000/onlineconnection/lan_ethernet.htm`.
