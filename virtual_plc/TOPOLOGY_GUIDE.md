# Configure virtual topology

## Inspect project hardware and module manuals

1. Open **Controller layout → Project topology**. The diagram uses the selected physical configuration's Hardware.hw ports and Hardware.hwl positions. Other physical configurations stay separate.
2. Expand the hardware tree to inspect CPU interfaces, local stations and remote X2X branches. ST numbering starts again on a remote branch. Base and terminal modules appear under **Base / terminal parts**.
3. Select a module to inspect its original name, type, station, source and mapped signals. Select a line to inspect its two ports and source link. Orange denotes X2X, blue USB, and cyan another configured connection.
4. Use **Fit**, **+ / -** and drag to pan. **Project tree** toggles the inner hardware tree. The outer source explorer and Properties panel have their own collapse buttons.
5. Double-click a module or choose **Module help**. Search an exact name such as X20AP3131 or X20DI9371, then choose Technical data, Pinout or another topic. Shared family manuals are labeled; check the column for the selected model. Text and figures come from the supplied offline B&R help.

## Connect simulated devices

1. Open a project, then **Controller layout → Virtual wiring**. The **Components** tab opens the same saved configuration.
2. Choose **Add component**. Select DI, DO, AI, AO, motor, servo, VFD or encoder and give it a name.
3. Map the ports marked `*` to declared PLC variables. Inputs read commands; outputs publish simulated feedback. Select the exact scope/ID. A BOOL array element or a structure member may be entered explicitly.
4. Set ranges, ramps and initial values. Apply the draft, enable the device and choose **Save connections**. Pause/reset a pending scan before changing connections. Imported devices start disabled.
5. Drag device handles to arrange the canvas. Save connections to retain positions. Click a port or its settings button to edit its mapping. Devices with the same output/input variable appear connected.
6. Run a supported project or use Single scan. DI contact switches and AI value controls can then supply inputs without resetting the other device models. Save outstanding connection drafts before using these controls. User forces take precedence.

## Example connection chain

Choose existing PLC variables of the stated types, or declare them in your PLC editor and reimport the project. This workspace never adds variables to original source files.

| Connection | Required value type/unit |
| --- | --- |
| DI contact output → VFD Run and motor Enable inputs | Same BOOL identity |
| AI sensor output → VFD target-frequency input | Same REAL, Hz |
| VFD speed output → motor requested-speed input | Same REAL, RPM |
| Motor shaft-speed output → encoder speed input | Same REAL, RPM |
| Encoder pulse-count output → PLC count input | Integer with sufficient range |
| PLC command → DO relay/lamp input | BOOL |

Give each feedback output its own variable. Two device outputs cannot write one variable. Command and feedback on the same component cannot overwrite each other. Set model ranges to fit integer destinations. The same-named local variables in different programs are separate values.

The canvas shows virtual device models and shared memory connections. Generic motor/drive behavior does not implement a vendor fieldbus or physical safety system. All commands are sampled before the completed scan publishes feedback; linked models therefore have a defined scan-boundary delay.

## Display and launch

- **Project topology** shows the CPU, bus ports and local/remote station branches from the source configuration. Actual source configuration is unchanged.
- **HMI simulation** supports 25–900% zoom, Fit, a numeric/string keypad, resolved bitmap images and a live alarm-image view. Use the mouse or keyboard Enter to confirm values. Unsupported controls retain an explanation.
- **PLC logic → Ladder** uses MatchView geometry, five networks per page, Fit/zoom and SVG export. Select a symbol to inspect its scoped value; this is not a claim of rung continuity.
- Double-click **Start_uSOPp.bat** to start the full app with Virtual PLC on the application port (8200 by default).
- Use the same file from CMD: **Start_uSOPp.bat stop** or **Start_uSOPp.bat restart**. Stop/restart refuses unrelated processes.
- If analysis was interrupted by a restart, reopen the workspace and choose **Retry analysis**. Original project sources and the existing incremental index are reused.

Original PLC files remain read only. Configure and inspect a blocked project freely, then resolve its active execution findings before Run.

## Test Project 2's login visibility program

1. Open Project 2 with physical configuration **LDF3S_WO_SUCTION**.
2. Open **How to run** and select **Logical/loginout/loginoutCyclic.ab** under **Program to test**.
3. Choose **Create program test**. Confirm the persistent **Program test only** banner. This copy runs the selected source and its normal lifecycle/dependencies; other machine tasks are excluded.
4. In **Variable monitor**, search **current_password_level**, enter a level such as 3, and choose **Single scan**.
5. Inspect **Login_1_V**, **Login_3_V** and **Login_9_V**. For level 3 the source sets all three to 1. Level 9 sets all three to 0. The interpreter does not infer that 1 always means visible: the HMI uses the actual status bit definitions, including bit 0 for hiding.
6. Inspect **HMI simulation → layers / objects** to see source-backed status and locking bindings. Other machine-dependent values do not update unless their corresponding programs execute.

An empty task Source such as usb_val1 is displayed as an unassigned skipped slot for this configuration. A nonempty unresolved Source remains a blocker. Library interface formals (ANY, REFERENCE TO, etc.) are not standalone PLC instances; a genuinely unsupported instance used by active code remains blocked.

## CPU service configuration (0.5.0)

Open Controller layout, then CPU services. Pause or stop before saving RTC, interface, battery and serial settings. These are virtual values attached to this workspace. Actual SerialNumber input channels determine which PLC variables receive module serial values; a similarly named variable is not enough to establish a connection. EtherNet CfgGet/CfgSet calls operate only on the configured virtual interface names. Reset and reopen restore the saved settings.

HMI runtime layers can be inspected under HMI simulation / Inspect objects. Layer status bindings and their original source keys determine switching. Set Layer As Active is an editor selection; it has no runtime trigger. Layer BackColor is also an editor property and must not create an input cover. Visible controls and hotspots retain their actual drawing order and permissions.
