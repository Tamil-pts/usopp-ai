# WorkHub projects - 4.79.0

## Automatic projects and engineering iterations

Run ByteMap (including metadata generation), DataInspect, MatchView or LogicScan in the normal workspace. New runs by enabled personal accounts automatically create or find a WorkHub project in **Development**. Each distinct saved history ID receives one project-wide iteration number. The update includes the tool, tester, test ID, recorded status, numerical summary and available evidence.

- Re-running the same project creates **Iteration 1**, **Iteration 2**, and subsequent iterations in the same project.
- Starting DataInspect live polling captures its first read as an iteration; subsequent automatic polling cycles do not create a new WorkHub card/iteration every two seconds. Explicit checks and restarts capture new runs.
- Browser decoding, connection-result enrichment and later report exports for the same history ID update that iteration. They do not create duplicate projects or iterations.
- Native B&R project filenames provide the stable identity across temporary uploads. Distinct machine/program names containing a program number can match the same known project across users. Generic names and metadata/target identities are scoped to the uploader; ambiguous aliases do not merge projects.
- DataInspect uses the metadata source, packet layout and PLC target. A uniquely matching known source name can associate it with an existing project. A uniquely known metadata source can belong to one program across several target readings; every run retains its actual PLC target. Ambiguous source names are not merged automatically.
- MatchView attaches its comparison to the developed project; baseline and developed names remain in the recorded comparison.
- Original run JSON, generated reports and archived source snapshots are shared through the project evidence references. WorkHub does not make another permanent copy of the history snapshot or reports. Source ZIP downloads stream from the archived snapshot.
- New runs keep work in Development. Fresh development work on completed or released projects returns the project to Development, clears its active submission and preserves previous decisions in history. A check run by the currently assigned quality/release reviewer stays at that review stage and is recorded as additional evidence; it does not approve the work. Review/release decisions wait for active engineering checks to finish. A recorded blocker stays blocked until explicitly resumed.
- Older private history and demo runs are not backfilled into shared projects. Newly captured engineering evidence is visible to approved personal WorkHub users. Pending synchronization retries while the server is running; original tool results remain retained if capture fails.

## Create and plan a project

1. Choose **New project**. Enter its name and select a Work type, or type a custom value. Saved custom work types appear as suggestions on later projects.
2. Choose **Waterfall**, **Agile**, **Sprint** or **Custom**. Waterfall creates Development, Quality checks and Release delivery tasks. Agile creates multiple planned sprints; Sprint creates one. Custom keeps the phase periods without generating work tasks.
3. Choose the development assignee, quality reviewer, release approver and release owner. These can be any enabled personal users.
   Changing a project phase assignee also reassigns its unstarted steps that still use the previous phase assignee. Individually assigned and completed steps keep their owners.
4. Choose the project start. Agile/Sprint also lets you choose the initial sprint length and number of sprints. These initial dates are calendar dates, not a working-day calendar.
5. In the creation Gantt chart, drag a bar to move its start and finish. Drag its left or right end to resize the period. The pencil opens date entry. Dates can overlap when the project requires parallel planning. Changing a row changes that row only; dates on other rows are not shifted automatically.
6. Select **Create and assign project** to save the project, phases, sprints and generated tasks in one transaction.

## Active project timeline

Active projects open on **Workflow & timeline**. Development, Quality and Release have separate rows, dates, assignees and progress. Development tasks and sprint work appear with the development phase; quality and release work appear in their phases.

- Use **Add workflow step** to add your own names, choose its delivery phase and assignee, and optionally choose a sprint, dates, milestone, notes and dependencies.
- Drag or resize scheduled bars to save dates. Use **Alt + Left/Right** to move one day; add **Shift** to resize the finish. **Escape** cancels a current drag. The pencil and date fields remain available.
- The owner/creator/Admin can plan project work; phase assignees can change their phase period, and sprint owners can manage their sprint. Completed work and closed sprints are locked; planned phase dates can be updated without altering evidence or approval decisions.
- A conflicting change asks for a refresh. Dates, the original due markers and update events remain separate. Changing plan dates does not complete a step or approve a project.
- Quality tasks can start when the project is in Quality check. Release delivery tasks can start after release approval. Development tasks assigned to a sprint can start when that sprint is Active.
- **My work** shows assigned projects and tasks on the same timeline.

**Development completed is an active project state.** Its development phase can show 100% while quality and release remain unfinished. Only **Released / Closed** projects show the completed view with **Summary**, **Updates & evidence**, **Issues** and **Approval history**.

Attach project files, screenshots or documents using **Updates & evidence > Add update**. Existing deliverables and submitted revision downloads remain under evidence and history. There is no separate Original project and revisions screen.

## Agile backlog and sprint delivery

Agile and Sprint projects include **Backlog & sprints**. Existing sprints remain visible even if a project's planning method is changed later.

1. Create or edit a sprint's name, goal, owner, start and finish. A sprint is at most 91 calendar days; initial template lengths are 3 to 60 days.
2. Add tasks to the backlog or a selected sprint. Use **Assign to** on a task, or its step dialog, to move unfinished work between open sprints and the backlog.
3. The project manager or named sprint owner chooses **Start sprint**. Its assigned tasks can then start.
4. Record work, evidence and task completion normally. Sprint progress uses completed development work, weighted by estimates where available.
5. Choose **Close sprint** after its tasks are complete. Move unfinished work to the backlog first. Closing a sprint does not approve or release the project.
6. **Reopen sprint** allows further planning. Historical events remain available. An empty sprint cannot be closed as completed work.

## Completion percentage

Project completion uses three equally weighted delivery phases: **Development**, **Quality**, and **Release**. Development completion uses its completed leaf tasks or the explicit development-completed action. Quality includes its planned work and the quality-pass decision; Release includes its planned work, release approval and release closure. Task estimates weight work within each phase; missing estimates count as one unit, as do approval checkpoints.

A project without work tasks normally shows 33% when development is completed, 67% after quality passes, 83% after release approval, and 100% only after release closes. Projects with planned quality/release tasks also include those tasks. Dates alone do not imply completion. The portfolio, summary and timeline show development progress separately from overall project progress.

All approved personal users can view shared projects and evidence. Demo accounts cannot access company project data. Actual workflow decisions remain restricted to the named person responsible for the current stage. Scheduling and sprint actions never approve a release.

## Record daily work with minimal entry

1. Open a project or task and select **Add update / evidence**.
2. Enter a short note, or attach screenshots, PDFs, spreadsheets or other documents.
3. Review the extracted text and its source references. You can edit the wording or enter details manually. **Write with Chopper** optionally rewrites the supplied evidence into a draft when the configured assistant is available.
4. Optionally mention a colleague using `@username`, record minutes/date, or explicitly share one of your saved engineering results.
5. Select **Confirm and save update**. Saving a note does not complete or approve a task.

Image extraction uses installed Tesseract or the Windows OCR service. Scanned PDFs require a text/OCR copy or a manual note. Document reading is limited to 25 MiB per file, 12 selected files and bounded pages/sheets/text. Native Siemens, B&R, CAD and other binary archives are stored intact for download; uploading them does not imply technical parsing or validation.

Time entries are optional and go separately to the quality reviewer. Returned entries appear under **Approvals > My time entries needing correction**. The author can correct and resubmit them; the previous values and comments remain in history.

## Quality and release workflow

```text
Create and assign -> Development -> Development completed -> Quality check -> Release approval -> Ready for release -> Released / Closed
              ^              |                |                    |
              +--------------+----------------+--------------------+
                              Request changes
```

1. The development assignee chooses **Start development**.
2. After recording work and reviewing its engineering evidence, choose **Mark development completed**. It can stay there without entering approval. When needed, choose **Send for quality check**, select the reviewer and release approver, then review the submitted revision or engineering iteration shown in the confirmation.
3. The named quality reviewer opens **Approvals**, downloads the submitted revision and either passes quality or requests changes with a reason.
4. The named release approver reviews that revision and either approves release or requests changes.
5. The release owner chooses **Mark released / Close**. Release is a separate action following approval.

Requested changes return the item to development and create an open issue. Resolve open issues before approval. Parent work cannot enter quality until its children complete development. Project release accepts development-completed or released steps, and waits for any separately requested step reviews and all project/step issues to finish. Blockers, resumes and reopened work are recorded. A project manager can use **Reassign responsibility** at any stage, including when an old assignee is disabled.

Files in a saved revision never change. A review retains its submitted revision even if another task later uploads newer files. A changed project revision while the submission dialog is open requires reopening that action. History preserves decisions and links to their recorded revision.

## Portfolio and activity

- **Portfolio:** project ownership, current stage, overall delivery percentage and separate Development/Quality/Release percentages. Development completion does not mark the project complete.
- **My work:** Gantt view of assigned projects and workflow steps, including work awaiting your review action.
- **Team activity:** To do, In progress and Done cards for projects/tasks, with assignees, latest iteration/tool/status and user/search filters. Done includes completed tasks and Released projects. Development-completed projects remain In progress until release closes. Dragging between development columns opens the permitted confirmation; quality/release decisions use their assigned roles. Recorded updates remain available below the board.
- **Recent work:** saved engineering results with search, tool/status filters, result opening, JSON/report downloads and project reuse. Admin can also filter by user. The history is inside Project Delivery; there is no separate engineering tools dashboard below it.
- **Workflow & timeline:** draggable/resizable project, phase, sprint and work bars, date entry, milestones, dependencies, original due markers and day/week/month scales. Overall delivery and development percentages are separate.
- **Approvals:** quality/release decisions and optional time review.
- **Reports:** PDF, Excel-compatible CSV and JSON exports of portfolio state. The time view/export contains the latest 1,000 time entries; team activity lists the latest 300 updates. Project detail shows the latest 500 updates/events.
- **Sidebar navigation:** existing ByteMap, DataInspect, MatchView, LogicScan, Chopper and Virtual PLC. Earlier personal runs remain private unless explicitly shared; new supported engineering runs are captured automatically into project updates.

## Large files and storage

Default limits are **4 GiB per file**, **100 GiB shared storage** and **50,000 files per revision**. Change `USOPP_WORKHUB_MAX_FILE_BYTES` and `USOPP_WORKHUB_STORAGE_BYTES` in the server environment before startup if needed. Reverse proxies must accept 8 MiB request chunks and allow long streaming downloads.

- Uploads send 8 MiB chunks. Choose **Pause upload**, then resume the remaining files; after a browser restart, reselect the same unchanged files using the same account and browser. Incomplete sessions expire after seven days.
- Attach files to a saved update to record their purpose and source. Existing immutable revision records remain downloadable through evidence and review history; the separate revision upload screen has been removed.
- Identical file bytes share one permanent content blob, including across projects. References and revision history remain separate. Changed ZIP files can require their full new archive size; upload a folder to reuse unchanged individual files.
- A single-file revision downloads its original file. Multiple files download as a ZIP64 stream without saving another permanent archive on the server.
- Long file lists show a bounded preview. Download the complete revision manifest for every relative path, size and SHA-256 hash.
- WorkHub records and files live in `.usopp_workhub` under the application data directory. Back up the whole directory, including `connections.key`, with restricted filesystem access. Encrypted credentials depend on that key. Clearing the existing temporary engineering cache does not clear WorkHub projects.

The production build does not establish actual 2 GiB transfer throughput or OCR/email/Teams operation. Those require checks in the intended browser, server and connected company environment.

## Administration

Admin opens **Settings > Admin settings > Workspace administration > Manage users** to review requests and manage accounts. User management is not shown in WorkHub. Regular users do not see this Settings section. Engineering activity analytics and its previous dashboard heading have been removed from WorkHub; Recent work and Team activity remain.

## Notifications

Assignments, stage changes, mentions, issues and time review create in-app notifications. The top-right bell opens the inbox. Due reminders run while the server is running, using the Asia/Kolkata calendar, for work due tomorrow or earlier. Delivery status is separate for email and Teams; accepted means the provider accepted the request, not confirmed receipt.

### Share in an existing Teams group (default)

All notification connections are in **Settings > Notifications and Teams sharing**. WorkHub no longer has a separate Connections tab.

1. In your Teams group, use a message's **More options > Copy link**. A normal Teams chat or message link is accepted; a webhook URL belongs in the optional workflow settings.
2. Admin pastes the **Shared group chat link** once for everyone. Users can optionally enter their own group link; a blank personal link uses the shared group.
3. Keep **Group chat link - copy and send manually** selected and save notification settings. This method does not require a Microsoft app registration, client secret, mail authorization or Power Automate workflow. Members still need access to the group under their existing Teams accounts.
4. On a project, task or notification, select **Share in Teams**. Review or edit the prepared text, including its status, responsibility and review link.
5. Select **Copy & open Teams**, paste into the group and select **Send**. A separate **Copy message** button and editable text support manual copying if the browser blocks clipboard access.
6. Colleagues follow the review link and record approval decisions in WorkHub. Opening a chat, copying text or sending in Teams does not approve the project or mark a notification as automatically delivered.

Admin can set **WorkHub address for shared review links** to the office server or LAN origin, including HTTP LAN addresses where used by the application. A `127.0.0.1` / `localhost` review link points to each colleague's own computer. The address must be reachable from the recipients' office network or VPN. This setting does not enable LAN listening or configure a reverse proxy.

The inbox labels Teams chat sharing as manual. Ordinary chat URLs are opened in the user's browser; the server does not post to them. Optional automatic connections stay collapsed until the organization permits them. Microsoft describes the supported [chat links and manual composition](https://learn.microsoft.com/en-us/microsoftteams/platform/concepts/build-and-test/deep-link-teams).

### Automatic email from each user (optional, when approved)

No separate sender mailbox is required. This release supports delegated **Microsoft 365 / Outlook** mail. Company setup uses an application registration; each sender then signs in with their own Microsoft account and enables workflow sending.

Admin / IT setup:

1. Register a company Web application in Microsoft Entra. Choose the tenant permitted by your organization.
2. Configure delegated Microsoft Graph `User.Read` and `Mail.Send` permissions and the consent required by your company policy.
3. Register this exact Web redirect URI, replacing the origin with the WorkHub server address:

   `https://usop.company.com/api/workhub/connections/microsoft/callback`

4. In **Settings > Notifications and Teams sharing > Microsoft application setup**, enter tenant ID/domain, application client ID, client secret value and the public application origin. Non-loopback addresses require HTTPS. For local setup, register the exact localhost callback URI used by the application.
5. Each user opens **Settings > Notifications and Teams sharing > Automatic email and Teams connections**, selects **Connect my Microsoft account**, completes sign-in and explicitly enables sending from that account. Save notification preferences. Recipients must also save their contact email; they do not need mail-send authorization merely to receive a message.

Mail is sent using the account of the person whose action created the notification. Tokens/secrets are encrypted on the server. No account password is collected. Disconnecting stops that sender's future delivery. Changing the company application/address clears prior Microsoft connections. Pending notifications may be delivered after their required connections become available; failed delivery can be retried from the inbox.

Microsoft documents the [authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow) and delegated [sendMail operation](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0).

### Automatic Teams delivery (optional, when approved)

1. In Teams / Power Automate create a workflow with **When a Teams webhook request is received**, followed by posting the received Adaptive Card to the intended chat or channel.
2. This version supports the secret-URL trigger configured for **Anyone**. Keep its signed URL private. Tenant-authenticated triggers require an additional authenticated extension and are not implemented here.
3. Choose **Automatic workflow** in Settings, then save the workflow URL under **Automatic email and Teams connections**, enable delivery and save preferences. Appoint a workflow co-owner so it survives the creator's absence.
4. Admin must save the WorkHub application address so messages contain working project links. Office-only addresses require office network or VPN access from the message recipient.

See Microsoft's [Teams workflow webhook guidance](https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/add-incoming-webhook?tabs=dotnet) and [trigger authentication choices](https://learn.microsoft.com/en-us/power-automate/oauth-authentication).

In-app notifications continue independently of external delivery setup. No email or Teams message is sent solely by entering this screen.
