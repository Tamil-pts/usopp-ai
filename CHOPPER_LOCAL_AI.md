# Chopper local tools and optional AI

Chopper is the assistant within uSOPp.ai. Log decoding, ByteMap, MetaWorks,
LogicScan and project search run locally without an LLM. Optional models provide
conversation, explanations and suggested code changes; deterministic tools keep
their own results.

## Small CPU setup without Ollama (4.65.9)

In **Settings → Chopper · AI connection**, choose **Set up small CPU model**.
The app downloads Qwen2.5-Coder 1.5B Instruct Q4_K_M from its pinned official
revision, checks size/SHA256, and loads it through the included llama.cpp runtime.
Windows and the Docker image provide their respective CPU runtime. Model weights,
configuration and approved knowledge remain in the persistent data root on updates.
CPU answers are bounded and serialized independently of validation workers.

See [PERSISTENT_STORAGE_AND_CPU_AI.md](PERSISTENT_STORAGE_AND_CPU_AI.md) for
storage details and [the LAN/VPN server guide](distribution/LAN_SERVER.md) for
installation and backup/restore. No Ollama installation is required. The older
external-provider options below remain available for existing configurations.

## Source answers and model response settings (4.65.9)

For **Machine functions**, Chopper selects active cyclic PLC logic and enabled
ladder networks before HMI settings or initialization files. The local fallback
explains extracted IF assignments and ladder contact/coil behaviour with source
locations. It labels shared task ownership, commented networks, complex branches
and incomplete operating-sequence coverage. It does not treat settings-page
matches as a machine-function explanation.

The default model response window is **30 minutes**, including CPU queue waiting
and generation. Admin can set 0.5-30 minutes in Settings. Project indexing and
retrieval happen before that window and depend on project size. Reading,
retrieval, queue and generation stages and elapsed time remain visible in chat.
The answer token limit is separate: increasing it permits longer CPU answers.
On expiry, Chopper retains local source findings and reports the selected limit.
Existing settings without a timeout field use the new 30-minute default.

**Ready** means the runtime has loaded the model. **Save & check** asks for a
short reply with a separate 30-second check and reports its response time; it
does not establish the speed of a large project answer. Existing runtime logs
on the development laptop show project prompt reading plus generation exceeding
the former 60-second limit. Request metrics record timing and token counts,
without recording questions, source excerpts, answers or credentials.

For feature-presence questions, matching active executable source is selected
before HMI files. The local answer shows literal calls, declaration locations,
task ownership and related HMI bindings. Source presence and live operation
remain distinct. No PLC ping is sent by this source analysis.

The AI citation check accepts supplied [S1] identifiers or a supported file:line
location. Unknown paths, identifiers and out-of-excerpt line numbers are rejected.
If a reply fails, chat identifies the citation problem and keeps the local source
answer. A citation warning does not mean the requested feature is missing.
Source citations alone do not verify all of an AI reply's engineering claims.

Restart the backend after installing an update; refresh alone cannot replace
loaded Python code. Check that both UI/API version badges show **4.65.9**.
Self-registration, own-password changes and Admin-created accounts remain
supported. See [ACCOUNT_COMPATIBILITY.md](ACCOUNT_COMPATIBILITY.md) for the
standing account and update requirements.

## Chopper local model inside uSOPp (4.61.0)

The complete Windows package includes the official llama.cpp CPU runtime.
It runs as an app-owned hidden process; installing Ollama is optional.
This is an inference runtime for an existing model, not a newly trained model.

1. Obtain a compatible **GGUF** model whose license permits your use.
2. Sign in as Admin. Open **Settings > Chopper AI connection**.
3. Choose **Chopper local model**, browse to the GGUF on the backend computer,
   and keep the default local port **8202** (allowed: 8200-8500).
4. Save, then select **Start local model**. Wait for **Ready**, then chat.
5. Use **Stop** to release memory. Closing uSOPp also stops its own model process.

Model weights are deliberately separate from the EXE and remain at the selected
local path. The full EXE folder contains `local_ai/runtime`; distribute the whole
folder. The runtime uses loopback only. Browser clients use the uSOPp backend.
Existing Ollama/API settings remain available. A settings change stops the old
app-owned model so the next answer cannot use stale model settings.

The development check loaded the already installed Qwen 1.5B GGUF and completed
an inference request using the bundled runtime without the Ollama service.
Model speed and supported architecture depend on the selected weights and PC.

For MCP engineering tools and client setup, see [MCP_LOCAL_TOOLS.md](MCP_LOCAL_TOOLS.md).

## External Ollama (optional)

1. Start Ollama on the computer running the uSOPp backend.
2. Sign in as administrator and open **Settings → Chopper · AI connection**.
3. Choose **Local Ollama model**.
4. Base URL: `http://127.0.0.1:11434`.
5. Model: `qwen2.5-coder:7b` (installed on this development laptop). The smaller
   `qwen2.5-coder:1.5b` is also installed.
6. Click **Save & check connection**. Installed model names are listed.
7. Open **AI Assistant → Chat** and send a message.

The application stays on port 8200. The existing Ollama service has its own
11434 port. Browsers on other laptops use the same backend model connection;
Ollama does not need to be installed on every client laptop.

Ollama and model weights are separate from the optional Windows EXE. Model
settings for an EXE are stored in `%LOCALAPPDATA%\uSOPp.ai`, or the folder named by
`USOPP_DATA_ROOT`; development settings are in the app folder. Configure each
installation once. Model settings contain no bundled weights.

## Own model / API key

Use **API / own compatible model**, its API base (typically ending in `/v1`),
model ID and optional API key. Chopper sends `/chat/completions` requests. A
self-hosted model exposing that interface can be used without changing the app.
The backend sends selected conversation/project evidence to the configured
service when the engineer asks Chopper. Log decoding itself stays in the browser.
**Explain this capture** sends the selected readings and findings from chat.
Readable document previews attached to a question are also sent to the selected
model service. No model is needed for the log tables or feature shortcuts.

Keys are never returned to the browser. Windows encrypts stored keys for the
server's Windows account; on other systems the settings file uses owner-only
permissions. Do not distribute private settings. The default mode is local tools
when no settings/environment connection exists. Existing `USOPP_LLM_BASE_URL`,
`USOPP_LLM_MODEL`, `USOPP_LLM_PROVIDER` and `USOPP_LLM_API_KEY` are supported;
saved Settings take precedence.

## Decode collected PLC logs

Open **AI Assistant → Chat**. Click the paperclip and select the collected log
and its metadata XLSX/CSV, or paste the log in the message box. Click **Send** or
the **Log decoder** shortcut. There is no separate decoder form and no selected
project is required. Chopper asks for missing files; if several workbooks are
attached, choose the matching one. **Check requests only** works without metadata.

The reply appears inside chat. Filter by asset and group, then choose
a captured timestamp. **Table** shows tags, parameter/screen names, payload
offsets, datatypes, raw decimal bytes and decoded values. **Simple text** and
**Copy result** provide a readable text table for the selected capture.
REAL values default to four decimal places; select **Full REAL precision** to
see their unrounded decoded values. Offsets come from the uploaded metadata;
payload offset 0 starts after the five-byte response header.
Values are historical readings from that log. Rejected or
corrupt response frames are not decoded as valid PLC values. An unanswered final
request is unconfirmed unless the excerpt contains evidence of a timeout.

## One chat for all features

Use the sidebar shortcuts for ByteMap, MetaWorks, DataInspect, MatchView,
LogicScan and KnowHub guidance and links. Project context is optional and
collapsed. Rule configuration and KnowHub remain available as workspace tabs.

The paperclip accepts up to ten attachments, each at most 20 MB. Text/B&R source,
spreadsheets, PDF text and DOCX documents can supply chat evidence. Unreadable
binary files and scanned PDFs show a message asking for a text export. General
document previews are limited; Chopper reports when a preview is incomplete.
No attached code is executed. **New chat** clears attachments and conversation
from this chat and cancels a pending answer. Files remain available for follow-up
questions until removed or a new chat is started.

Copy replies or decoded tables directly. Without a model, Chopper supplies
feature guides, document excerpts and deterministic log results. Ollama/API
adds conversational interpretation. If connection settings cannot be loaded,
the label shows the error instead of `undefined`; restart the updated app before
refreshing the connection.

## B&R code editing and tools

Chopper's source evidence offers **Open source / edit** when a ByteMap/LogicScan
session exists. The engineer reviews and saves changes; the existing editor
backs up the source and checks that its version has not changed. Run validation
again after saving. Wrapped AS 2.7 source containers remain read-only.

`GET /api/assist/tools` lists the local engineering tools and API routes. These
are authenticated application tools. Authenticated MCP tools are available at `/api/mcp/` as described in
MCP_LOCAL_TOOLS.md. Source edits still require engineer review in the application.


## Project understanding and MatchView explanations (4.62)

Select/upload a project in ByteMap or LogicScan and run it once. Chopper indexes
source files, declarations, ladder networks, active Cpu.sw tasks, HMI, alarms and
hardware/I/O. The selected physical configuration and HMI remain separate from
inactive targets. Shared sources with unconfirmed task ownership are labelled.
The index is rebuilt when the source manifest changes; chunks and facts are
cached under `.usopp_workspaces/chopper_knowledge`. Files above 5 MB and projects
above the 80 MB reading budget show explicit coverage notices.

Use **Understand this project** or the suggested questions. The local tools
return source inventories and evidence without a model. The configured embedded
GGUF, Ollama or API model explains the retrieved facts conversationally. This is
project retrieval, not training new model weights. Machine purpose inferred from
names must be confirmed by the engineer; inaccessible library internals and
runtime behaviour remain unresolved.

Run MatchView on both projects, then use **Explain MatchView changes**. Chopper
reads the stored comparison result and categorises variables, logic, ladder,
HMI layout, HMI behaviour and hardware/configuration. Counts describe extracted
changes; they are not defect counts. Model examples are bounded and follow-up
questions can request additional detail.

Chat shows reading/indexing/retrieval/model stages, elapsed seconds and an
approximate remaining time for file processing when enough files have completed.
Model generation has no reliable completion estimate. Replies include the total
elapsed time. Starting a new chat stops displaying a pending answer; its server
analysis may finish in the background.

Help includes prompt examples, placeholders and follow-up questions. MCP adds
`understand_project` and `compare_explanation` to the existing authenticated tools.


## Project attachments, comparison summary and accounts (4.63)

Click the chat paperclip and choose **Project folder** to upload the complete
Automation Studio directory, or **Files / project ZIP** to attach a complete
project ZIP (up to 200 MB compressed and 600 MB extracted). An .apj/.pgp descriptor
alone does not contain the logic. Chopper selects the newly attached project;
**Optional project context > Project for this chat** lets you choose another
attachment or the ByteMap/LogicScan project. Uploaded code is read, never run.

In MatchView, complete the comparison and click **Chopper summary**. The popup
explains the current compared projects, categorises changes and offers **Copy
summary**. Closing the popup allows its current request to finish; reopening the
same comparison reuses the answer. A new comparison resets that summary.

Only Admin sees model connection details, Refresh connection and model/MCP
settings. Ordinary users can chat with the configured model without seeing or
changing its setup. WorkHub offers Admin **User management** to create and edit
user accounts, reset passwords and enable/disable access. Disabling an account
or resetting its password revokes existing sessions. The Admin account uses
its own Settings password change flow.

If an older running server does not support chat jobs, chat uses its existing
synchronous endpoint. If project attachments or both chat routes are missing,
stop the old launcher and restart the updated application. A browser refresh
alone does not reload backend code.
# Metadata and RTC in 4.64.2

Metadata reads the active HMI's alarm groups and the project's `Logical/VCShared/AlarmGroups/*.algrp`, including when the active AlarmGroups folder is empty. Multiple shared groups are retained; SystemAlarms.algrp and .alcfg files are excluded. GC 30 remains BYTE through Excel normalization. Generated metadata shows alarm source findings when the PLC packing/copy or AlarmImage binding can explain missing Sheet2 captions.

DataInspect RTC uses a 30-byte SpinConnect frame with `YYYY-MM-DD HH:MM:SS` at indices 9..27 by default. The timestamp is attached to a Function 1 / GC 10 read; the old ASCII-at-byte-5 layout remains optional. The result shows the actual sent request and GC 11 closure separately. An acknowledgement does not prove the PLC applied the clock. Read GC 150 using the loaded metadata and verify PLC update conditions. See RTC_PROTOCOL.md for byte positions and the supplied PLC code's conversion-call ordering.

# MatchView reports in 4.64.1

Use **Project details** beside Chopper summary before comparing. Enter the project name, description, validated by, date, validation details and approved by; leave approval blank until approved. Choose formats (HTML and PDF by default), then save. After comparison, preparation continues in the background. **Reports / download** shows elapsed time and each format as queued, preparing, ready or failed. Close the window freely; prepared downloads remain available while other formats finish.

Editing the details after comparison prepares a separate report version. The previous report keeps its original cover. HTML and PDF have cover pages; Word and JSON keep their existing report structures. Identical options reuse the prepared report, and HMI preview images are cached across formats and cover edits. Large first-time reports can still take more than 60 seconds; there is no fixed promise about rendering time.

In Screen view, **Skip layout properties in screen differences** filters Width, Top, Left, AlignmentVertical and AlignmentHorizontal from differences and exported property rows. It does not change the source project or actual screen geometry. File counts still describe the raw comparison.

Restart the backend after updating source or the EXE, then refresh the browser. Version 4.64.1 separates background report routes from older export routes to avoid the missing projectName/date error. A comparison must remain available to prepare a new version; downloaded reports do not require a connected PLC.

# Graphical ladder comparison in 4.64.3

Run MatchView again after installing this update. Select a .ld file under Logic,
then select its network. The main view is a ladder drawing with contacts, coils,
branches, functions and function blocks; source text and element lists are
collapsed below it. Both sides share zoom and scrolling. Use Fit width, or zoom
in and scroll for complex networks. Click a symbol for its variable, type,
instance, source, declaration and other uses in the ladder file.

Green indicates added logic, red removed logic, and amber modified logic. Network
numbers remain those of each source project; inserted networks do not renumber
the source. Network comments and commented-out state are retained. Declarations
provide datatype labels when available; missing types are not invented. XML
elements outside the supported symbol set produce visible warnings.

SVG and PNG download the selected diagram. Reports / download prepares HTML,
PDF, Word or JSON with the same graphical comparison. Large PDF/Word networks
continue across labelled tiles without becoming new networks. HTML and SVG
retain full drawing detail for zooming. Existing saved diagram models are
upgraded when rendered, but old network pairing requires a fresh comparison.
See LADDER_REFERENCE_REVIEW.md for the verified reference cases.
