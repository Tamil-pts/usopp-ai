# Team inbox and system alerts - 13 November 2026

A chat icon beside the notification bell opens a private inbox popup. Approved
personal accounts can start direct conversations, send text and emojis, attach
up to three files (20 MB total), preview validated raster images and download
shared files. Conversation history, unread cursors and read receipts persist on
the local application server. The popup supports expansion, keyboard dismissal,
focus trapping, Enter/Shift+Enter composing and mobile conversation navigation.
Drafts are retained while switching conversations or closing the popup during the
current page session; they are not promised to survive a browser refresh.

Messages are plain text, not executable HTML. Downloads require membership in the
conversation even for administrators; no public attachment URL is exposed.
Recipients must be active, approved personal accounts. Disabled/deleted users
cannot receive new messages. Participants are bound to account creation identity
as well as numeric ID, so a deleted and recreated account cannot inherit chat
history when SQLite reuses a numeric ID. Demo accounts cannot access team chat.
Retries use a per-sender message key to avoid duplicate posts. A 60-message/minute
limit and explicit upload size/type limits apply. SVG/HTML and executable uploads
are rejected. Images are verified with Pillow before inline preview; Office,
PDF, CSV and text downloads are served as attachments with nosniff headers.

Storage is .usopp_chat/messages.sqlite3 plus .usopp_chat/files under the existing
application data root. Back up both together. This is local-server messaging,
not an end-to-end encrypted external messenger or a malware-scanning service.
Existing projects, approvals and account records are not replaced by this feature.

## Notifications

The unread inbox badge remains available without OS permission. Enable system
alerts explicitly from the inbox or the existing notification panel. The inbox
also provides Send test alert. New workflow items and messages can request native
browser/OS alerts. Old history is not replayed as notifications on first load.
Chat previews in OS alerts use generic text instead of message content.

Browser system notifications require a supported browser, site permission and a
secure context (HTTPS or localhost). An HTTP LAN IP address is not a secure
context. Keep uSOPp.ai open; background polling is subject to browser throttling.
Browser-closed push delivery, email/SMS and a Windows background notification
service are not implemented. OS Do Not Disturb and browser policies may suppress
visible alerts even when a notification is requested.

## Verification

Backend tests cover participant isolation, attachment protection, database reopen,
unread/read receipts, pagination, duplicate retry handling, deleted-ID reuse,
invalid uploads and size limits. Account and web-security regressions also pass.
A two-account browser test covers messages, emojis, CSV/image sharing, image
preview, history reload, unread badges, mobile popup and the native-alert adapter.
The adapter verifies notification calls without claiming that a real OS toast was
delivered. Artifacts: .build/team-chat-20261113/inbox.png.

Final checks: 11 chat API tests and 18 account/web-security regression tests passed. TypeScript and the production build passed. The final two-account browser test passed against the combined application with no page errors. Local server restarted on port 8200; health returned status ok, UI/API 4.99.3, teamInbox=true and browserSystemAlertRequests=true. Test messages were created only in isolated test data, not sent to real users. The new chat storage is excluded from Git and the Docker build context.
