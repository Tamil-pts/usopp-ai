# Team inbox, meetings and WorkHub links — 14 November 2026

Additional inbox apps: [approvals, workflows, updates, praise and native shared components](INBOX_APPS_SHARED_COMPONENTS_20261114.md).

The existing inbox now accepts ZIP files alongside images, documents and
audio/video attachments. Chat messages retain their existing three-file,
20 MB total limit. ZIPs are checked as archives and stored/downloaded without
extraction or execution. This is not antivirus scanning. Prior direct-chat
history, permissions, unread counts and image previews are retained.

## Team groups

Use **New chat → Create group** to name a group and select approved users.
The creator is included. Default WorkHub team groups appear automatically from
active teams and saved membership; they are not generated from sample names.
Membership/name changes synchronize when chat is accessed. A removed member
loses access to messages, files, meetings and recordings. Reused account IDs
cannot inherit old direct/custom-group identities or stale team profiles.
Group history is visible to current members, including newly assigned members.

## Meetings

Select a conversation/team, then **Meetings → Schedule meeting**. Enter title,
start/end and agenda, optionally linking a project/task. Dates use the browser's
local time zone and are stored as absolute UTC timestamps. Invitations are
posted to the conversation. Participants can accept, tentatively accept or
decline, download an ICS calendar invitation with a ten-minute reminder, and
join through the configured local meeting service. The organizer can cancel.

Self-hosted Jitsi integration issues signed, room-specific JWTs only after
conversation access checks. The private server setup is described in
[local meeting deployment](../deploy/meetings/README.md). The preparation script
pins and verifies upstream source, generates private credentials, and enables
JWT authentication with anonymous access disabled. No public meeting service
receives project content through this integration.

**Live calls are not deployed on the development machine:** Docker is absent.
The self-hosted HTTPS host/IP and trusted certificates are still required.
The prepared deployment YAML and authentication configuration were checked;
actual camera/audio, screen sharing and recording playback have not been
validated against a running Jitsi installation. The Join button remains disabled
until configured. This is not complete Microsoft Teams feature parity.

Jitsi owns meeting controls and local recording, subject to its browser/server
support. The organizer can upload saved WebM/MP4 recordings up to 200 MB into the
meeting record. Current conversation members can download them. These upload
and authorization paths were tested, not actual call recording quality. Server
recording/Jibri, transcription/Jigasi, collaborative whiteboards, PSTN and other
optional services require their own deployment and integration checks. Join-link
requests are labelled as requests; they are not reported as verified attendance.

## Notifications

In-app unread records are always active. Opening the inbox requests system-alert
permission once per browser session when permission has not yet been decided.
Already granted system alerts work by default. Browser denial, insecure LAN HTTP,
OS focus mode or a closed application can prevent system delivery; permission
cannot be forced. The existing Enable system alerts and Send test alert actions
remain available. Meeting invitations/reminders use the same local browser
notification adapter while the application stays open. Old alerts are not replayed
on every refresh. Calendar reminders are handled by the user's calendar app.

## Project and task integration

The message composer can link a saved project and task. Each text message offers
**Create task / project**, which creates a WorkHub draft using the selected title
and message body. Existing WorkHub permissions, project status gates and normal
approval flows apply; chat does not approve, release or complete work. File
attachments stay private to the conversation and are not silently copied into
project evidence. Opening a work link still checks WorkHub permissions.

## Verification

- 18 chat/collaboration API tests passed: direct history, ZIP round trip, groups,
  default-team membership/revocation, account identity, invitations, RSVP, ICS,
  JWT signature/scope/expiry, organizer controls, recording download permissions,
  project/task creation and date/time-zone validation.
- Nine speech/chain regression tests and 18 account/web-security tests passed.
- Two-account browser checks passed for existing direct messages, emoji,
  image/CSV previews, unread alerts and persistence; new checks passed for team
  groups, ZIP downloads, custom groups, notification permission request, meeting
  scheduling, calendar export, participant RSVP, message-to-task creation and
  desktop/mobile chat and meeting layout.
- TypeScript and production Vite build passed. Prepared Jitsi source archive
  checksum, Compose YAML, four base services, pinned image version and JWT-only
  settings were checked. Docker Compose execution was unavailable.

Artifacts: `.build/team-collaboration-*.log`,
`.build/team-collaboration-20261114/`, and the isolated prepared deployment under
`.build/meetings-prepared-final-20261114/`. Prepared deployment credentials remain
local and are excluded from Git. Existing application records were not replaced
with test data.
