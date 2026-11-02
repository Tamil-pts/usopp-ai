# Default Validation and FAT reports

Validation and FAT use structured nine-section forms by default. Document Studio
remains in Settings for designing reusable layouts. The report forms provide:

1. Document number, controlled revision, report date and document type.
2. Project name/number, customer and customer reference.
3. Editable objective and scope.
4. References with document numbers, exact revisions and dates.
5. Requirement-linked cases, expected/actual results, status, remarks and evidence.
6. Issues, corrections, retest observations and status.
7. Computed total, passed, failed and pending counts; not-applicable counts separately.
8. Validation conclusion or the recorded FAT acceptance decision.
9. Actual prepared/reviewed/approved identities and dates, including the recorded
   customer or authorized representative for FAT.

Numbers and revision labels use the company settings already configured under
Engineering Quality / document controls. A report never substitutes a hard-coded
example number. Existing issued identities and approved snapshots are preserved.

New reports seed cases from the project's approved FRD when available. **Import
from FRD** adds missing cases without duplicating existing requirement coverage.
**Import validation result** links a completed project tool run; engineers confirm
the report scope before imported outcomes count toward its summary. Manual
executions use the existing authenticated evidence/actual-result controls. Retests
append history instead of replacing the original record. Changing a case's test
specification invalidates its earlier result until it is executed again.

Closing a report issue does not change a failed test into a pass. FAT acceptance is
recorded through the existing actual customer acceptance dialog and requires its
supporting record. Empty reports start untested, with pending sign-off. Existing
confirmation, independent review and approval rules remain in effect.

PDF export renders the same sections, configured number/revision, current valid
results and recorded acceptance/sign-off. Approved source/layout/PDF snapshots
remain immutable.

Regression coverage: `tests/test_workhub_report_templates.py` plus the existing
workspace, workflow, Studio and FRD suites. Isolated browser/PDF evidence is under
`.build/workhub-project-reference/` (`reports.cjs`, `validation-report.pdf`).
