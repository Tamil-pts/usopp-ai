# Simulation jig and component library

## Run a machine with field feedback

1. Upload or open the PLC project. Wait for analysis to complete and review any execution blockers.
2. Open **Components** and use **Build from project** if no field devices are configured. Automatic mappings require selected hardware I/O and compiled logic evidence. Existing manual connections remain available.
3. Click any amber action symbol at the top right of a component. Review the exact command and feedback tags, source location and explanation. Confirm the mapping, or edit its connections and model settings. Pause the PLC before saving changed connections.
4. Press **Run PLC** and switch **Simulation jig ON**. Enabling the jig preserves the current PLC task state. Motors and actuators respond only when their PLC output commands become active. Their configured feedback is returned to the same PLC memory.
5. Use the machine's explicit START/FAST button or a configured scenario. The jig does not press START automatically. Doors, material and operator contacts can be changed individually. User forces take precedence over simulated feedback.
6. Watch command values, feedback, component status and virtual PLC time. Waiting for a command means the PLC has not commanded that device; inspect its start conditions. A model delay or fault can also prevent feedback.
7. Use STOP and observe outputs and motion settle. Pause freezes virtual device progression. Turning the jig off leaves PLC execution independent and freezes its automatic feedback.

**Restore healthy defaults** deliberately resets and stops the virtual PLC and restores the reviewed bench defaults. Review custom settings before using it, then press Run again. It is separate from simply enabling the jig.

## Project 2

For the exact `LDF3S_WO_SUCTION` project supported by the reviewed bench profile, use **Restore healthy defaults** once after upgrading an older saved jig. This installs profile version 5, including the original reviewed virtual source correction already used by this project's bench. Original PLC files are unchanged.

The top arm starts closed, `DI_TOP_ARM = 0`, and remains an editable operator contact. It must not follow `DO_DRAFTING_LOAD` with a delay: that creates a temporary loss of `M1200` and resets the FAST latch `M1231`. Drafting/scanning feedback still follows actual PLC outputs. After Run, allow initialization in virtual time, then press the FAST control. A wall-clock speed selection cannot skip original PLC timers; this project's 0.4 ms task can make interpreted virtual time advance slower than real time.

## One topology canvas

1. Select **Topology** to view every matching component on one canvas.
2. Choose **Fit all** for the complete layout, or **Fit width** for larger symbols with vertical scrolling.
3. Zoom in to operate small controls. Search or filter to focus on a device group.
4. Use **Edit** to configure devices. Use **Move** to drag and save positions. Saved layouts remain with the workspace.

## Save a reusable model or layout

1. Configure the component models and save connections in the current project.
2. Open **Component library**. Select one device, several connected devices, or the complete layout.
3. Enter a library name, manufacturer, model/part number and description.
4. Add terminals: DI, DO, AI, AO, COMM, POWER or OTHER. Record terminal number, signal, unit and communication protocol as appropriate. These document the model; they do not create a physical connection.
5. Keep **Save layout positions** selected to reuse placement and internal model links.
6. Optionally attach a vendor PDF, CAD drawing, EPLAN archive or image. References are stored for review; automatic drawing interpretation is not included. Confirm the vendor's terminal and model data before configuring it.
7. Save the item. It is available across your projects under your account.

## Reuse in another project

1. Open the target project and its Component library. Choose the saved item.
2. Optionally suggest exact saved PLC addresses. Only existing tags with compatible types are proposed. By default all PLC bindings are detached.
3. Enter layout offsets if needed and choose **Add models and layout to this project**. The PLC pauses for the configuration change.
4. Reused devices start disabled. Review each required PLC tag, internal link, unit, timing and fault setting in Configure.
5. Enable the required devices, save connections, turn the jig on and Run PLC. Operate START explicitly.

To create a model variant, apply an existing item, change its parameters in Configure and save the selection as a new library item. Manufacturer details and terminal lists can also be updated on a saved item. Libraries are private to each account; workspace exports retain configured devices and layout, while optional vendor references stay in the account's library.
