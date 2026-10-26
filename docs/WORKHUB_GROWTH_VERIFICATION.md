# WorkHub growth requirements and verification - 4.83.1

## Corrections after the first release

The first release's successful build did not establish completion of the requested workflows. The follow-up audit found that the performance collector read only shared WorkHub runs, leaving existing personal engineering archives out of the dashboard. This workspace contained 637 archived engineering runs and no shared WorkHub run records when inspected.

Release 4.83.1 reads attributed existing archives into each recorded author's own performance history. It preserves original summaries and scores, including `complianceScore`. It does not infer a WorkHub project from a filename or project label, publish private archives to the company, or give verified capability credit merely because a run exists. Demo, unowned and unknown-account archives are excluded.

An engineer can submit a native result as manual evidence, explicitly select the relevant project/task and choose an independent reviewer. That named reviewer can inspect the submitted original result. Verified evidence retains the exact source event and approved revision. New unsubmitted revisions remain private to the author.

Additional corrections include native iteration ordering for latest results, paginated activity/issue history, selected-period trend coverage and explicit API/UI versions and feature flags in health.

## Requirement coverage

| Requirement | Implementation | Verification |
|---|---|---|
| Engineer performance profile and manager team overview | WorkHub / Performance & Capability, project/period filters, team profiles | API scope checks and browser navigation |
| Assignments, completed work and shared project progress | Existing WorkHub item records and recorded completion events | Isolated project/task API fixtures and browser profile |
| Native validation, scores, comparisons and iterations | Shared runs plus author-attributed existing archive projection | API checks for scores, latest iteration and task links |
| Issue resolution history | Existing issue events, paginated history | Create/resolve issue API flow and pagination/scope checks |
| Trends, strengths, improvement areas and evidence | Transparent evidence counts, dated trend bins and recorded feedback | Profile API and rendered light/dark dashboards |
| Non-PLC work and independent manual verification | Activity type, project/task, work description/result, attachments and named reviewer | Manual submission/verification and retained approved revision checks |
| No penalties for iterations or bug discovery | No negative iteration/issue weights, composite rating or ranking | API methodology and neutral-iteration regression |
| Five guided knowledge categories | Category-specific questions, one at a time, optional choices/text/files | All categories via API; troubleshooting guide via browser |
| Structured editable article | Deterministic article from actual answers and editable preview | Browser answer/save/submit workflow |
| Draft/submitted/approved/rejected/published states | Exact revision review and separate authorized publication | API transitions, rejection exclusion and browser review/publication |
| Search, categories, author/project filters and article details | Published-revision search index and knowledge library | API publication/search isolation and browser search |
| Contribution Passport | Engineer's published reviewed articles | Library/author data and browser navigation |
| Answers based on reviewed knowledge with citations | Internal published-source retrieval and exact revision links | Source-citation API/browser checks |
| Verified knowledge supports performance | Published contributions support knowledge sharing; other capabilities are reviewer confirmed | API capability-credit assertion and browser linked-project profile |
| Attachment and revision access | Author/reviewer/manager/revision checks, central deduplicated files | Public-vs-draft attachment checks and manual draft privacy regression |
| Existing accounts, notifications and approvals | Existing personal accounts and project reviewer roles, new queues linked from the notification bell | Non-admin author/reviewer browser flow and API authorization checks |
| Current theme, dark/light and responsive layout | Existing theme variables and responsive WorkHub components | Edge browser screenshots at desktop and 390px width; no document overflow |
| Preserve engineering engines and project workflow | Additive projection and new WorkHub APIs/UI | No validator or PLC engine edits for these corrections; full app builds |
| Internal persistent storage and no external AI | Existing server database/data root; deterministic guide and source excerpts work without AI | Isolated local workflow checks; browser external requests blocked |

## Checks and their limits

`tests/test_workhub_growth.py` uses disposable accounts, databases and attachment storage. It checks authorization, article states/publication/search, capabilities, private attachments, manual verification/revisions, existing archive inclusion, exact source sharing, neutral iteration counts, latest results, history pagination and matching health versions. It does not execute or validate PLC logic.

The local browser audit exercises the built interface against a disposable server: engineer submission with an attachment, independent non-admin reviewer approval, publication, search, cited library answer, team profile and contribution credit. It records JavaScript errors and growth API failures, and checks desktop light/dark plus mobile layout. Screenshots and results are in `.build/growth-ui-audit/`. Test articles and users are never added to company storage.

The full production build covers the main application, Nami and Virtual PLC. Existing bundle-size warnings remain. These checks do not establish production load behavior or all possible account/data combinations.

Final local evidence on 24 October 2026: 11 API regression checks passed; the browser workflow completed with no page errors or growth API failures and no document overflow at 390px. The displayed test UI badge was `UI 4.83.1 | API 4.83.1`. After the normal local restart, `/api/health` returned `status: ok`, explicit API/UI versions `4.83.1`, and matching compiled build integrity. The real collector projected 635 attributable archived runs and 11 existing WorkHub events. Existing company storage still contained two item records, no shared engineering-run records and no knowledge/manual-evidence test records. An online SQLite backup was taken before restart.

Linux deployment and local model/service activation remain skipped at the user's request. Optional model explanations and polishing therefore remain unverified here. Guided entry, article generation, review, publication, search and source-excerpt answers do not require a model. No external AI fallback is added.
