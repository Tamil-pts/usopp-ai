# Automation Studio 2.7 project layout

Use this layout when the uploaded project is an Automation Studio 2.7 project. The sample in `Project in AS2.7/LD_22120.pgp` has these locations. Project, controller and configuration names can differ in another project.

| Purpose | Location in the supplied layout | How uSOPp uses it |
| --- | --- | --- |
| HMI screens | `Logical/HMI/Pages/*.page` | Read screen controls and their properties from the selected visualization. |
| PLC subroutines | `pgm/TRIAL_01/CPU/*.src` | Include the resolved legacy CPU source folder in MatchView and Chopper project knowledge. |
| I/O mapping | `pgm/TRIAL_01/CPU/IOMap.iom` | Look up legacy mappings in the same CPU scope for serial mapping rules. |
| Active physical configuration | `Physical/Config1` | Select the only user configuration when the legacy project has no `LastUser.set`. |
| HMI panel type | `Physical/Config1/PCC1/HMI/hw.cfg` | Read the `MasterPanel` / `Type` property and show it as **HMI type**. |
| Shared alarm definitions | `Logical/VCShared/AlarmGroups/*.algrp` | Read shared alarm definitions, including when the HMI alarm folder is absent or empty. |
| Shared HMI resources | `Logical/VCShared` | Resolve shared text groups, data sources and other referenced HMI resources. |
| Project descriptor | Project-root `*.GDM` | Detect the legacy project format/version. |
| Exported declarations | Project-root `CPU.txt`, when supplied | Retain the declaration source for the existing validation readers. Chopper still applies its file reading limits. |

## Configuration selection

1. If `LastUser.set` is supplied, use its recorded active configuration. Invalid or conflicting settings remain unresolved.
2. For a detected AS 2.x legacy project without that file, select a configuration only when exactly one user folder exists under `Physical`. `System`, `VisualComponents` and `Temp` are support folders and do not count as configurations.
3. Select `pgm/<project>/CPU` only when exactly one such CPU folder and one matching selected physical configuration exist. `Config1` and `TRIAL_01` are examples, not hardcoded names.
4. If selection is ambiguous, report the unresolved scope and exclude the legacy CPU sources. Do not combine multiple CPU/configuration folders.

The same identity reader is used by local project details, MatchView, Chopper and validation HMI discovery. The uploaded-folder summary uses the equivalent selection rules. MatchView continues to skip `.pkg` and `.prg` files.

## Hardware evidence

In the supplied sample, `Physical/Config1/PCC1/HMI/hw.cfg` contains:

```xml
<MasterPanel Name="4PP065.0571-K37">
  <Property Name="Type" Value="4PP065.0571-K37" />
</MasterPanel>
```

This identifies the HMI panel. Keep this evidence separate from the PLC CPU type. The XML processing instruction in this file says `AutomationStudio Version="2.5"`; it describes that resource format and is not used to override the project-level version.

## Alarm evidence

The supplied project has `Logical/VCShared/AlarmGroups/LD2_Alarm.algrp`. The existing alarm reader searches the selected HMI and `VCShared`, so an empty local alarm folder does not hide the shared definitions. Existing exclusions, including system alarms and the configured Ringframe prefixes, still apply.

## Upload and deployment

Upload or copy the complete project folder, retaining `Logical`, `pgm`, `Physical`, the `.GDM` descriptor and any exported declarations. Selecting only the HMI folder does not provide the PLC logic or physical configuration.

These discovery changes are source changes. Existing Windows executables and Ubuntu source bundles need a new build/package before they include them. No build or automated tests were run for this update.
