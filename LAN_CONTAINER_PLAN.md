# Shared LAN/VPN container deployment plan

Status: storage, CPU model setup and container install/update/backup/restore are implemented in 4.65.8; destination verification is pending. See PERSISTENT_STORAGE_AND_CPU_AI.md and distribution/LAN_SERVER.md.

## Deployment

- The developer's Windows laptop is used for development and testing.
- One shared server runs the complete uSOPp application in Docker.
- Users reach its internal browser address over the existing LAN/VPN and sign in to uSOPp.
- Five enabled regular users plus Admin are supported.
- Source and distribution repositories remain private. GitHub builds versioned packages; the server administrator installs or updates the selected published release.

## Save all user details and results

All durable records belong in the server's persistent data store, outside the application image.

| Records | Required retained contents |
| --- | --- |
| User accounts | Stable account ID, username, designation, company, role, enabled/disabled state, creation timestamp and password hash |
| Every test | Unique test ID, owner account ID, activity, project/PLC identity, timestamps, running/completed/failed/interrupted status, full findings, expected/actual values and error details |
| ByteMap and MetaWorks | Validation results, generated metadata, input metadata, source snapshots and generated workbooks |
| LogicScan | Rule configuration used, rule outcomes, evidence and generated reports |
| MatchView | Comparison results, source/HMI/ladder details, report cover details and each generated report version |
| DataInspect | PLC target, metadata used, request/response captures, decoded values, checks and transport outcomes |
| Data model checks | Reference model used, metadata, parameter name/type/group findings and summary |
| Manual frames / RTC | Sent frame, received response and outcome |
| Knowledge and configuration | User-added mappings, dropdowns, limits, imported data models, rules and saved user/PLC configuration |

Each result must remain linked to its original stable account ID and test ID after upgrades. Disabling or renaming a user must not remove or reassign their historical results. Admin sees all users' history; regular users see their own records.

Retain the full result and generated exports, rather than just a browser summary. Application updates, restarts and temporary-cache cleanup must not delete saved results, knowledge or account details. An upgrade must not overwrite user-edited mappings with bundled defaults.

## Update and restore

1. Finish active tests and stop application writes.
2. Back up the complete persistent store, including the account database, configuration, knowledge, inputs, snapshots, results and report files.
3. Install the selected application image and reconnect the same data volume.
4. Apply any required versioned data migration without resetting accounts or saved records.
5. Start the application with the existing accounts and data.

Moving to another server requires restoring the persistent data as well as installing the image. Publishing source/packages to GitHub does not back up private server data.

## Current implementation and remaining work

The current backend has server-side account storage, owned run history and writable knowledge/rule paths under `USOPP_DATA_ROOT`. The prepared Compose layout mounts this store at `/data` in a named volume.

DataInspect PLC configurations, custom metadata, saved manual frames and UI/report preferences now use per-user SQLite storage with browser migration and revision checks. Browser migration can transfer only records still available in that user's browser. Full archived results are also indexed/stored in SQLite; compatible file archives remain.

The container launchers now implement complete backups before updates, retained-volume startup and restore to a new empty volume. Rules/Knowledge Hub retain their compatible JSON schemas; model weights remain GGUF files. No Docker destination upgrade or complete preservation check has been run.
