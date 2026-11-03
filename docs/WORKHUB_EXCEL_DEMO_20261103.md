# Historical Excel demo — 3 November 2026

Status: prepared and verified in an isolated stage; **not installed over the local
data**. Automatic approval review rejected the combined stop/replace command with
“blocked by policy” and no detailed reason. No destructive replacement occurred.
The original application was restored on port 8200. The WorkHub demo preview runs
separately at `http://127.0.0.1:8391` using the copied Admin credentials.

Source: the supplied `Downloads/sample.xlsx`, SHA-256
`0be592fd46dec1f77661a1bd1c2f40876fe3fcf6d0d717986f57d3fefc76b263`.

The stage contains:

- 53 explicitly labelled sample projects: 46 closed, one awaiting validation,
  four on hold and two withdrawn. No upcoming project is invented.
- 318 controlled reports: FRD, correction notes, validation, FAT, quality and
  closure for each project. Advanced samples have independent review records;
  a representative sample includes rejection, correction and revalidation.
- Seven historical sprints and project/task timeline dates.
- Fourteen fictional engineer/reviewer accounts, plus the preserved Admin and
  built-in demo accounts. Old employee accounts are absent from the stage.
- A saved **DEMO MIS | Historical Excel** dashboard with daily/weekly hours cards,
  completed/ongoing/upcoming counts, delivery-state bars and historical hours bars.
- Competency sample-project previews driven by fictional workflow feedback.
  Sample projects remain excluded from real employee indices.

All supplied dates remain historical. Missing/invalid dates are blank and source
conflicts are retained in project custom fields/import notes. The expanded row
contains conflicting In-QC/HOLD statuses; this is recorded, not silently resolved
as engineering truth. Excel duration fractions are interpreted as days × 24 hours,
as in the existing report importer; the workbook has no duration number formats.

The workbook supplies totals rather than daily timesheets. For the demo charts,
available totals were allocated to original dated weekdays, up to eight hours per
engineer/day. These 227 entries total 1,701.5 demo hours and remain **submitted,
not approved billing time**. Missing dates, capacity conflicts and unallocated
totals are reported separately. The latest populated demonstration day is
2025-07-31 (2.5 h); its week beginning 2025-07-28 contains 34.5 h.

Every project/report/evidence entry states that test results, approvals and
handover are fictional demonstration records. No human sign-off stamps were
created. Actual machine behavior, physical FAT and customer acceptance remain
outside this demonstration.

Validation passed for all project date boundaries, database integrity, independent
document approvals and an empty active-job queue. FRD, validation, FAT and closure
PDF exports succeeded. Browser checks passed at widths 1600, 1067, 800 and 390,
including the competency sample warning and profile. Test artifacts, source
warnings, exports and private demo credentials are retained under:
`.build/excel-demo-20261103/full-01/`.

`scripts/prepare_workhub_demo.py` prepares a fresh isolated stage; it never replaces
live data. `scripts/install_workhub_demo.py` is a separate offline installer with
an explicit replacement flag, installation checks, a full WorkHub rollback copy,
account/application database backups and Admin-password preservation. The
installer was not executed after the automatic approval rejection. Review the
stage and this script before any manual installation. The current live databases,
master mappings, engineering history and model settings remain in place.
