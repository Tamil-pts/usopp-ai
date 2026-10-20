# Virtual PLC 0.5.0 library implementation

The supplied reference corpus is `knowledge/br_help/AS12/Help-en/Data`. These are explicit Python implementations of documented interfaces. The runtime does not load a vendor DLL or execute documentation examples. Unsupported calls remain execution blockers. The authenticated support inventory is available at `/api/virtual-plc/library-support`.

## Memory and string calls

Implemented: ADR, SIZEOF, strcpy, strcat, strlen, strcmp, itoa, ftoa, atoi, atof, memcpy, memmove, memset, memcmp and their supported AsBrStr aliases. Preserve the documented AsString/AsBrStr return-address differences, including C strcpy/memcpy behavior. TON_10ms has UDINT preset/elapsed values in 10 ms increments.

- Addresses are bounded numeric handles into virtual PLC memory. They never reference host memory. Literal strings are read only; constant declarations and user forces retain precedence.
- Fixed arrays, declared scalar types and bounded Latin-1 STRINGs have explicit byte layouts. Array addresses can select a literal or evaluated integral element. Copies cannot cross the containing allocation. Overlapping memcpy fails; memmove permits overlap.
- The virtual byte representation is little endian. Unspecified structure packing, enumeration storage, callable-local addresses, LTIME byte layout and arbitrary pointer dereferencing remain unsupported. Do not infer a target ABI from a source label.
- FTOA rounds to IEEE 32-bit REAL and emits seven significant decimal digits. Exact formatting equivalence to every Automation Runtime version is not asserted.
- IEC string escapes and the bounded repeated-literal initializer form `[2 ('')]` are handled without evaluating source text.

Reference topics:

- `libraries/asstring/fbks/strcpy.html`, `strcat.html`, `itoa.html`, `ftoa.html`, `memcpy.html`, `memmove.html`, `memset.html`
- `libraries/asbrstr/fbks/brsstrcpy.html`, `brsstrcat.html`, `brsmemcpy.html`, `brsmemmove.html`, `brsmemset.html`
- `libraries/standard/fbks/ton_10ms.html`

## Virtual FileIO

Implemented instance types: FileOpen, FileCreate, FileWrite, FileRead, FileClose and FileDelete, plus FileIoGetSysError. Named input/output bindings and the usual preassigned-instance `FWrite()` call are supported. Actual instance names are resolved through their declarations; the names FWrite and FClose are not hard-coded.

- File devices are case-sensitive in-memory namespaces. File names are case-insensitive. No host directory, USB storage or network is accessed.
- Each operation reports busy for at least one completed scan before returning its result. This is a deterministic handshake model, not an emulation of hardware storage timing.
- Preserve documented disabled/busy/success status values, access modes and modeled file/path/handle/data errors. FileOpen does not create a missing file; FileCreate does not overwrite an existing file.
- Limits: 64 open handles, 128 files, 4 MiB per file, 16 MiB total file contents. Paths reject absolute paths, traversal and drive prefixes. Invalid pointers report a modeled error or a bounded memory fault.
- Files remain in memory during the runtime session and a warm reset. Open handles are cleared by reset. Warm reset retains the typed address map so retained pointers cannot select another variable. Cold reset or reopening the workspace clears the simulated files and addresses. Snapshot summaries contain names and sizes, not live file contents.

Reference topics: `libraries/fileio/fbks/fileopen.html`, `filecreate.html`, `filewrite.html`, `fileread.html`, `fileclose.html`, `filedelete.html`, `fileiogetsyserror.html` and `libraries/fileio/datatypes/constants_fileio.html`.

## HMI and Ladder

HMI key actions are decoded from VirtualKeys.vcvk and connected through exact .dso program-folder mappings and scoped PLC declarations. Numeric/string entry has an explicit keypad and confirmation. Set, toggle and momentary actions retain their separate behavior. Bitmaps use the existing resource resolver. Alarm groups follow their own AlarmImage, ImageOffset and indexed captions; the view shows current bits. VC4 control/layer hide and input-lock bits and source-defined login comparisons are implemented. Masked password entry compares against configured local text sources, including unformatted or bounded STRING snippets; unresolved credentials and unsupported formatting do not authenticate. Historical/latched alarm behavior, vendor acknowledgement, unresolved dynamic bitmap variants and status focus/touchpad feedback are not represented as implemented.

References: `visualization/viscompvc4/keys/keys_keyactions_setdatapoint.html`, `keys_keyactions_toggledatapoint.html`, `keys_keyactions_momentarydatapoint.html` and `visualization/viscompvc4/alarmsystem/ref-alarmgroup_alarmimage.html`, `ref-alarmgroup_imageoffset.html`.

The Ladder view uses the same source renderer as MatchView, including block grouping, pins, OR branches and source exclusions. Empty cells do not become conducting wires. Supported RETURN coils terminate the current program section when powered. Unsupported function networks, multi-block scheduling and vendor calls still block active execution. Source rendering and execution compatibility are separate results.

## Virtual CPU services

Supported functions: RTC_gettime, RTC_settime and SYS_battery. Supported blocks: DTGetTime, DTSetTime, BatteryInfo, SysInfo, RTInfo, CfgGetIPAddr/CfgSetIPAddr, CfgGetSubnetMask/CfgSetSubnetMask and CfgGetDefaultGateway/CfgSetDefaultGateway. DATE_AND_TIME/DT are unsigned epoch-second values. CPU block instance declarations and named inputs/outputs are type checked.

The exact sys_lib RTCtime_typ field sequence has a known 12-byte virtual layout, including member addresses. Other structure packing remains unsupported. The virtual RTC starts from a configured UTC seed and advances only with scan time. Ethernet calls use a bounded interface registry and a one-scan busy handshake. Option 1 records a virtual nonvolatile value during the session; reset/reopen restores saved configuration, so persistence across controller reboot is not emulated. The battery bitmask returned by SYS_battery differs from the BatteryInfo.state enum. Module serial numbers require an explicit virtual value plus a matching source I/O map channel.

References: `libraries/sys_lib/fbks/rtc_gettime.html`, `rtc_settime.html`, `sys_battery.html`; `libraries/astime/fbks/dtgettime.html`, `dtsettime.html`; `libraries/brsystem/fbks/batteryinfo.html`, `sysinfo.html`, `rtinfo.html`; `libraries/asarcfg/fbks/cfggetipaddr.html`, `cfgsetipaddr.html` and the corresponding subnet-mask/default-gateway topics.

Supported HMI snippets now include integral numeric text, MinIntegerDigits and bounded STRING formatting. Fractional formatting remains explicit. Password-derived role flags require their actual PLC source programs to execute; an HMI preview is clearly separate from complete machine execution. The runtime layer inspector lists original switch commands. No trigger is invented for an editor active layer.
