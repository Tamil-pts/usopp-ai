# LogicScan and ByteMap: evidence review and recommendations

Implemented and checked on 18 November 2026 in the current checkout.

Both result pages now provide a **Review & next actions** panel. It defaults to
results requiring attention, with status counts, search, filters, expected/actual
values, reported source locations and a CSV export of the filtered findings.
Failures appear first. Skipped checks and unclassified results remain separate
from passed checks. Expand a finding to read its evidence and suggested action.

ByteMap's panel lists the engine's reported issues; it is not a replacement for
the engine's complete check totals or the per-group/per-field tables. LogicScan's
panel lists rule results. An empty issue list does not independently establish a
successful validation. Existing Excel, HTML and PDF reports remain available.

## Corrected result interpretation

- Missing/unrecognized field statuses no longer default to Pass.
- Mismatch, Mismatching and Not Matching cannot be interpreted as Matching.
- A field's reported failure/warning is retained even when its parent label says
  Pass. Group presentation respects the explicit overall result and child findings.
- A missing expected offset is no longer copied from the actual offset. Missing
  field sizes and source lines are not filled with invented zeroes or line 1.
- ByteMap field details identify the engine's PLC sequence as a sequence, rather
  than calling a generated table-row number a protocol TAG_CODE.
- Zero/false values and structured expected/actual evidence remain readable.
- Rule property warnings are labeled Warning rather than Failed. Structured rule
  results now retain their top-level engine recommendations.
- A finding for another source file cannot borrow the packet field's line number.
  The review panel offers line navigation only for a reported positive integer.
  Rules with several source locations retain their detailed evidence instead of
  assigning an arbitrary first source to the whole rule.

## Recommendations and scope

Engine-supplied recommendations take priority. When absent, the interface supplies
a labeled next review action appropriate to the finding type. For example, an
offset issue asks the engineer to inspect addresses, sizes and any cursor used;
it does not mandate editing `nw_i` for a fixed-address write. Alarm copy checks,
packet lengths, response controls, datatypes and Sheet2 references receive
different guidance.

These are review actions, not generated replacement PLC code or approvals.
After a correction, rerun the affected checks against the same project, target
and packet branch. Distinct packet alternatives and HMI targets stay separate.
The packet engine, validation rules, project records and approval permissions
were not changed by this update. No model call is needed for this review panel.

## Verification

- 18 frontend evidence/status/rendering regressions passed, together with the
  existing readable-findings rendering check.
- Packet branch, response-control and metadata-quality suites: **26 passed,
  14 subtests passed**.
- Browser checks used actual packet-engine JSON and checked the supplied fix,
  exact source navigation, filtered CSV expected/actual/status values, rule
  filters and preserved structured recommendations.
- Nine screenshots cover ByteMap at 1440, 760 and 390 pixels in light/dark themes,
  and LogicScan at the same three widths. No page errors or horizontal overflow
  occurred in the review panels.
- TypeScript and the main Vite production build passed.
- The local server restarted successfully. `/api/health` reports UI/API 4.99.3,
  matching frontend build metadata and valid bundle integrity; the frontend
  returned HTTP 200. This is a health/build check, not a claim that every API
  endpoint or project configuration was exercised.

Artifacts: `.build/result-evidence-review/` contains the isolated engine project,
JSON/Excel result, filtered CSV, screenshots, browser result and build logs.

Reproduce frontend checks with
`node scripts/check_result_evidence.mjs --browser-fixture`, followed by
`.venv/Scripts/python.exe tests/result_evidence_review_browser.py`.
Run the engine regressions with
`.venv/Scripts/python.exe -m pytest tests/test_packet_branch_variants.py tests/test_packet_response_controls.py tests/test_metadata_quality.py -q`.

The browser fixture verifies actual shared result components and engine evidence.
It does not establish that every configured project rule or every installed PLC
target has been validated.
