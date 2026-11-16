# Local team meetings

uSOPp.ai owns invitations, conversation membership, project/task links, RSVP,
calendar export and recording files. A separate self-hosted Jitsi server owns
live calls. It is not Microsoft Teams and does not implement every Teams feature.
All conversation participants may access its scheduled meetings and recordings.

The application issues authenticated, room-specific 15-minute JWT join links.
There is no anonymous/guest join option in the prepared service configuration.
Team chat permissions are checked before issuing a link. An issued link remains
usable until it expires; removing a member does not eject an ongoing Jitsi call.
The organizer must remove an attendee within the meeting if required. Join-link
requests are recorded; these are not proof of actual meeting attendance.

## Prepare on Windows Docker Desktop or Ubuntu Docker Engine

Docker is not available on the current development machine. The prepared service
has not been started or tested for live multi-party calls here. Use a dedicated
LAN host with Docker Compose, a stable LAN address, and trusted HTTPS/DNS.
Do not use a public hosted Jitsi URL for confidential meetings.

From the application checkout (example addresses; replace with the real host):

```text
python scripts/prepare_local_meetings.py --url https://meet.factory.lan:8443 --lan-ip 192.168.1.50
```

This downloads only the pinned upstream deployment archive, verifies SHA256 and
prepares `deploy/meetings/runtime`. It generates private random credentials and
does not start services, install Docker, change the firewall or configure DNS.
Existing output is never overwritten. Upstream release: `stable-11248-3`, commit
`fca3e3a578a1bdd527c20b9d86a31cfc362d5426`. Review its LICENSE and deployment files.

1. Configure trusted certificates using the upstream custom-certificate procedure
   and make `meet.factory.lan` resolve to the meeting host for all participants.
   Browser audio/video needs trusted HTTPS; a self-signed certificate warning
   alone is not sufficient for a reliable production deployment.
2. Review `.env`: correct URL, LAN address, local DNS, credential files and ports.
   Restrict access to the intended LAN. Jitsi normally uses HTTPS 8443, HTTP 8800
   for its web front end and UDP 10000 for media. Check the pinned compose file
   against your network and upstream guide before opening ports.
3. In the generated directory run `docker compose config --quiet`,
   `docker compose pull`, then `docker compose up -d`.
4. Once the service is reachable over trusted HTTPS, copy the generated private
   `usopp-meetings.json` to `<uSOPp application data>/.usopp_meetings.json`.
   The default data directory for a source installation is the application root;
   a container uses `/data`, and a packaged Windows installation uses its
   configured application-data folder. Never commit or share the secret file.
   Meetings configuration is read on demand; refresh the inbox after copying it.
5. Alternatively set `USOPP_MEETING_URL`, `USOPP_MEETING_JWT_APP_ID` and
   `USOPP_MEETING_JWT_SECRET` on the uSOPp server process. They override the file.
   The app ID/secret must match the Jitsi deployment. Restart for environment
   changes. Do not expose the app secret through the browser or client settings.

## Features and recording

Jitsi supplies its meeting window, microphone/camera controls, screen sharing,
participant controls, chat, hand raising/reactions, polls and local recording
where supported by the chosen browser/deployment. Open it with **Join local
meeting**. Each participant uses their own authorized uSOPp account to join.

Use the meeting's recording controls, tell participants before recording, and
save the recording. The organizer can upload a WebM/MP4 up to 200 MB to its
uSOPp meeting record. Longer recordings must be split. Recordings download only
for current conversation members. Video files are not converted or executed.
Cloud recording, automatic server recording, transcription, whiteboards,
breakout-room policy, PSTN and enterprise compliance features are not certified
by this integration. Jibri server recording, Jigasi transcription and the
whiteboard service require their additional upstream services/configuration;
they are not started by the four-service base deployment.

## Acceptance before team use

Test with two authorized accounts on separate LAN machines: join the same
meeting, camera/audio both ways, screen sharing and audio selection, mute/leave,
record and play back the saved recording, upload and participant-only download.
Verify that an uninvited account cannot obtain a token and that direct anonymous
Jitsi room URLs are denied. Validate TLS, LAN media/firewall rules and recording
retention/backups. Run these against the actual host before calling meetings ready.

References: [official Docker deployment and JWT configuration](https://jitsi.github.io/handbook/docs/devops-guide/devops-guide-docker/),
[Jitsi recording FAQ](https://jitsi.github.io/handbook/docs/faq/),
[browser screen/audio capture constraints](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia).
