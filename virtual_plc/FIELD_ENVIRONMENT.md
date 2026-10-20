# Field environment - Virtual PLC 0.8.0

## Project 2

Open the current **project 2** workspace or the saved **Project 2 - full configuration and field environment** workspace.
Go to **Controller layout > Virtual wiring / Configure devices**.

- **Operator controls:** Start/inch, Fast and Machine Off contacts, using their original PLC tag names.
- **Drives, motors and encoders:** VFD and servo symbols, animated shafts, shaft links and live feedback.
- **Sensor inputs:** Boolean contacts and editable analog values. Module presence is also editable.
- **Output indicators:** Lamps, relays and analog output monitors.
- **Alarm feedback:** 173 original alarm definitions with their current PLC states, related scalar inputs and source locations.
- **PLC timers:** 219 declared TON/TOF/TP instances; IN, preset PT, elapsed ET and Q come from PLC memory.

Switch **Simulation jig ON** in the top toolbar to supply the field inputs.
On first activation the jig resets the virtual PLC, applies the matching
fingerprinted healthy profile and clears injected drive faults. Then click
**Run PLC** to start the PLC scheduler. The two controls are independent.
Switching the jig OFF freezes automatic field feedback while PLC execution
continues. **Restore healthy defaults** rebuilds the field bench and resets and stops
the virtual PLC; retained operator settings are preserved.

For Project 2, wait for **Machine ready: TRUE**, then press
`DI_MAIN_MOTOR_FAST`. The jig holds this virtual press for 2,000 ms so the
source's drafting-load confirmation timer can complete. A configured sensor
rule changes `DI_TOP_ARM` to 0 after `DO_DRAFTING_LOAD` goes on (150 ms travel).
The raw drafting-door closed input is 1. Drafting and scanning load switches
follow their actuator commands. The VFD and servo respond to their original PLC
commands; delivery, scanning and coiler encoders return shaft feedback. Fan
pressure ramps toward the source's requested pressure using its ADC scaling.
The original PLC code continues to evaluate these inputs and its alarm timers.

Use **Hold contact** on
`DI_MAIN_MOTOR_SLOW` for inching, allowing the original load and drive delays to
elapse in virtual time. Use **Release held contact** or press a `DI_MACHINE_OFF`
button to stop the command. A press uses the configured momentary duration.
The Machine Off contacts are normally 1 and become 0 when pressed in this
configuration. VFD ramp-down and mechanical shaft deceleration are separate
from the PLC command transition.

Select a device for the exact PLC signal trace. Drive fault injection changes
its modeled feedback, allowing the original PLC interlocks to respond. Clearing
an injected fault restores that modeled feedback; the PLC may still require its
normal alarm reset sequence.

Use **Operate** for live controls, **Move** to drag by the header handle, or
**Edit** to change connections. Moving automatically saves positions and keeps
PLC scans and device state running. **Configure** and **Edit** pause the PLC
before changing bindings, names or model parameters; finish with **Save
connections**. Clicking a port inspects its signal even while running. User
forces take precedence over simulated feedback. Reset/reopen releases held
buttons and reconstructs motion from the saved configuration.

## Source identity and reusable generation

`core/io_bindings.py` resolves selected task-qualified I/O aliases such as
`Cyclic#3.DI_MAIN_MOTOR_SLOW` to their exact declared global identity. It preserves
case, member/index suffixes, original hardware addresses and source evidence.

`core/environment.py` builds field components from the selected hardware I/O.
Unresolved mappings stay visible. Existing user components and settings are
preserved on rebuild. A compatible input can read another device's output using
**Device link**, or bind an exact declared PLC variable.

Project-specific defaults live in JSON:
[Project 2 bench](examples/project2-field-bench.json).
They apply only when project name, configuration and the listed source hashes
match. A changed or different project receives the generic inventory and needs
its own reviewed commissioning values. The profile stores the source references
and assumptions with each affected component. Original PLC files are untouched.

The delivery-counter model writes `HSC_1_CURRENTVALUE` and its mapped
`DI_DELIVERY_COUNTER` input. Its 16-bit rollover follows the declared UINT and
hardware counter mapping. Delivery uses one effective pulse per modeled shaft
revolution with the active `len_delCyclic.ab` default 0.00999 metres/pulse
(14.985 m/min at 1500 RPM). This conservative bench coupling keeps the short
default recipe usable; enter the actual gearing for production-speed checks.
Scanning uses 1024 pulses/revolution. These are editable bench assumptions.
Confirm gearing and sensor calibration before
using the simulation for quantitative delivery checks. Other sensors remain
explicit field controls until their physical relationships are configured.

Serial-number channels stay with CPU services. ModuleOk starts at 1 for a
present virtual module and can be toggled to simulate module loss, consistent
with the [B&R diagnostic datapoint explanation](https://community.br-automation.com/t/helpful-i-o-datapoints-for-machine-diagnostics/655).

Logic traces follow compiled assignments, conditions and Ladder wire graphs.
They show related conditions, with bounded depth and source links. They do not
claim that every listed input is a failing interlock. Position/velocity models
are generic simulations; they do not emulate a vendor fieldbus or calibrated
machine mechanics.

## Responsiveness

The device list displays 24 devices per page and supports category/search filters.
Runtime polling uses bounded value previews and cached interface references;
configuration saves omit the full engineering model when it has not changed.
The background worker yields CPU time between completed PLC scans. Workspace
settings offer Responsive, Balanced and Fast modes. These trade wall-clock
simulation speed against application responsiveness; the PLC clock remains
virtual. The prepared jig uses Fast mode unless an operator has already selected
a background load setting. Execution can run slower than wall time; device
delays and the PLC task intervals use the same virtual clock.

Build output is limited to `virtual_plc/dist`. Continue using the existing single
`Start_uSOPp.bat` launcher, including its `stop` and `restart` commands.

## HMI input and local virtual keys

HMI buttons resolve global virtual keys or the owning layer's local KeyMapping
when the central key is a stub. This follows bundled B&R VC4 help on local and
global key actions. Project 2's export popup START writes `ah_usb.ah_enable`;
CANCEL writes `ah_msg_popup = 1`, hiding the layer through its StatusDatapoint.
Other login/status permissions continue to follow the source.

The password keypad shows initialized levels and their original producer
source/task. Project 2 initializes its STRING credential sources in the
1,000 ms `Cyclic#7` task. A stopped or newly started full machine may not yet
have executed that task. **Run PLC to initialize login sources** starts the
normal scheduler. There is no forced credential initialization or login bypass.
Pending levels do not prevent matching an already initialized source level.

## Automatic and manual feedback

A DI can read an actuator command through its optional `command` port. Set
`automatic = 1`, contact polarity and on/off delays in Configure. Manual sensor
changes set `automatic = 0` for that sensor, persist the override, and leave
other sensors automatic. An analog input can follow an enable and process
reference with editable gain, offset, limits and slew rate. **Resume auto**
returns an overridden sensor to its configured rule.
PLC forces take precedence over both modes. Timing uses completed PLC scan
time; the CPU RTC independently reads PC wall time.

## CPU clock

**Controller layout > CPU services** selects PC local date/time or a custom
virtual RTC. The PC mode runs even while the PLC is paused. A custom clock
advances with simulation time. A PLC RTC_settime/DTSetTime call changes only
the virtual clock and switches it to custom mode; the PC clock is never set.
