# Local-server security review — 2 November 2026

## Result and scope

**Application protections were improved; the installation is not fully secured
for sharing until the remaining actions below are completed.** This is a targeted
source/runtime review using [OWASP ASVS 5.0](https://asvs.owasp.org/) as a checklist,
not an exhaustive ASVS assessment, penetration-test report or certification.

The user requested practical protection for a local server. This review covered
the current Windows checkout, its running HTTP service and local model listener,
account/access behavior, selected browser controls and dependency advisories.
It did not inspect another deployed server, the company's router, VPN, switching,
network segmentation, backups, endpoint controls or every optional external
service. Those cannot be certified from this application workspace.

## Current network observations

- The application listens on **127.0.0.1:8200**.
- The local model listens on **127.0.0.1:8202** when running.
- No HTTP/HTTPS reverse-proxy listener was found on the checked common web ports.
- Windows Domain, Private and Public firewall profiles are enabled. Effective
  application-specific inbound rules and upstream network controls were not
  comprehensively assessed.
- This instance uses HTTP on loopback. HTTPS/certificate configuration for a
  shared LAN hostname was not demonstrated. A different local-server deployment
  can have different bindings and must be checked separately.

Loopback binding prevents direct LAN connections to these listeners. It does not
prove that the machine, other services or network are free from vulnerabilities.

## Changes implemented

| Control | Current evidence and limit |
|---|---|
| Browser response headers | Added nosniff, SAMEORIGIN framing, referrer policy, permissions policy, and a baseline CSP limiting base URI, framing and form targets. This is not a complete script-source CSP. PDF viewers, recording and configured Office integrations remain usable. |
| HTTPS session handling | Secure + HttpOnly + SameSite cookies and HSTS verified on HTTPS requests. HSTS is not emitted for HTTP. This does not create a TLS listener or certificate. |
| Host validation | Default local hostnames/private IPs are accepted; unexpected DNS names are rejected. `USOPP_ALLOWED_HOSTS` can replace the defaults with an explicit host list. TestClient's synthetic host is accepted only for its in-process client. |
| Cross-site mutations | Existing Origin checks extended with Fetch Metadata and Referer checks. Non-browser authenticated local tools/MCP can omit browser-only headers. Existing signed Office callbacks retain their separate token verification path. |
| Internal error disclosure | Generic public 500 responses replace exception/path details. Request-validation responses no longer echo raw input. Internal diagnostics remain in administrator-accessible server logs. |
| Health metadata | Removed application-root and log-file paths from public health output. A hashed installation identity preserves launcher ownership checks. UI/API build-health checks remain available. |
| API documentation | Schema and interactive documentation now require an authenticated administrator. |
| Server files | Non-admin users can use owned uploads or explicitly approved `USOPP_PROJECT_ROOTS`. Arbitrary host-file browsing is restricted. Admin retains existing local-project selection. |
| Password handling | Existing salted PBKDF2-HMAC-SHA256, constant-time checks, hashed revocable sessions, session expiry and failed-login throttling retained. New/reset passwords require at least 12 characters; existing chosen passwords are not silently changed. |
| Initial administrator password | Added an authenticated reminder linking to profile/password settings. The actual administrator still needs to choose a replacement; no private password was generated or printed. |
| Frontend packages | Updated Vite/source-map-js and DataInspect transitive packages. Replaced SheetJS 0.18.5 with the official integrity-locked 0.20.3 tarball. Root and DataInspect npm audits returned zero known findings after updates. |
| Python package fixes | Raised project requirements and prepared/tested patched libraries separately. The running Python environment was not upgraded because automatic approval review blocked the combined stop/install/start action. |

The header changes follow the [OWASP HTTP header guidance](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html).
Security headers supplement authorization and input handling; they do not make
every page safe from XSS. Build indicators are not security/compliance badges.

## Required actions before sharing the server

1. **Change the initial Admin password now**, through Account menu → My profile &
   password. Choose a unique private password. Do not send it in chat or commit it
   to source. The reminder clears after the changed account is refreshed.
2. **Apply the verified Python updates during approved maintenance.** The active
   environment has advisory findings in certifi, Pillow, pypdf, pip and setuptools.
   Selected versions are certifi 2026.10.23, Pillow 13.0.0, pypdf 6.21.4, pip 26.2
   and setuptools 84.1.0. Wheels, SHA-256 manifest and the pre-change version list
   are prepared under `.build/landing-security-20261102/`. The isolated patched
   version audit found no known vulnerabilities and compatibility regressions
   passed. This is not a clean audit of the still-unmodified active environment.
3. **Use HTTPS for LAN/VPN users** through a controlled reverse proxy and a
   company-trusted certificate. Keep the application/model bound to loopback;
   do not expose the model port or a Vite development server to the LAN/internet.
4. **Set allowed hostnames and approved project folders** in the service's own
   environment. For example, `USOPP_ALLOWED_HOSTS=127.0.0.1,localhost,usopp.company.local`.
   `USOPP_PROJECT_ROOTS` uses the OS path separator (`;` on Windows, `:` on Linux).
   Approve project/metadata directories, not entire system drives or account homes.
5. Have the server administrator restrict inbound proxy access to the intended
   company subnet/VPN, use a limited OS service account, secure backups/secrets,
   and maintain Windows, browser and optional-service patches. Review demo access before sharing: the fixed demo login remains enabled in this
   installation, and removing it requires a separate deployment change.

No firewall rules, router configuration, existing account passwords or project
permissions were silently replaced. Demo session isolation remains in place;
this review did not turn the demo service into an unrestricted production user.

### Prepared Python maintenance steps (not executed)

After confirming no jobs or tests are active, the server owner can use the normal
launcher to stop the service, update the selected local environment from the
prepared wheels, and start it again. Back up the application data first. The
following commands show the exact pending change in this checkout:

```powershell
.\start_usopp.ps1 -Action Stop -Port 8200 -NoBrowser
.\.venv\Scripts\python.exe -m pip install --no-index `
  --find-links .build/landing-security-20261102/wheels --upgrade `
  'Pillow==13.0.0' 'pypdf==6.21.4' 'certifi==2026.10.23' `
  'pip==26.2' 'setuptools==84.1.0'
.\start_usopp.ps1 -Action Start -Port 8200 -NoBrowser
```

These prepared wheels are for this installation's Python/Windows architecture.
Other servers must install matching wheels from the updated requirements and
repeat their own checks. If installation fails, retain the install log and recover
the recorded prior versions before resuming service. Do not label the runtime
patched until its installed versions and dependency audit have been verified.

### Example local reverse proxy

An illustrative Caddy configuration is supplied in
[`deploy/local-server/Caddyfile.example`](../deploy/local-server/Caddyfile.example).
Replace the hostname and use your company's certificate/trust process. Its
`tls internal` option requires clients to trust that Caddy instance's local CA;
it is not a publicly trusted certificate. This configuration was prepared, not
installed or tested as an active network service in this review.

## Standards and assurance gaps

| Area | Assessment |
|---|---|
| Authentication/session/access controls | Selected behaviors tested; not every ASVS requirement verified. The unchanged default Admin password remains an immediate open finding. |
| Dependency management | JavaScript findings fixed. Python patches verified in isolation, active runtime application pending. |
| Transport/network security | Loopback bindings and enabled firewall profiles observed. Shared-server HTTPS, certificate trust, router/VPN/firewall policy and segmentation not verified. |
| XSS/content security | React escaping and selected upload validation exist; baseline CSP is partial. A complete rendering/upload/HTML review and strict CSP rollout are outstanding. |
| Operational security | Backup/restore exercises, monitoring, disk encryption, OS account privileges, secret rotation and incident response were not audited. |
| MFA/enterprise identity | No completed enterprise SSO/MFA assurance assessment. Local password/session controls do not establish that requirement. |
| Accessibility | Keyboard behavior and responsive layouts tested for the changed screens. No full WCAG 2.2 assessment or conformance claim. |
| ISO / industrial certification | WorkHub traceability and approvals can supply evidence. No ISO 27001/9001 or IEC 62443 certification is established by this work. |

## Verification artifacts

`.build/landing-security-20261102/` retains the before/after browser and header
records, npm audits, active Python audit, isolated patched audit, wheel hashes,
test/build logs and screenshots. The separate patched regression run passed
166 tests and 18 subtests. Ten focused web-security tests passed and exercise framing/headers,
host and origin rejection, HTTPS cookies, schema authorization, error redaction,
approved-root checks, password reminders and persistent login throttling.

Automatic approval review rejected the combined server-stop/runtime-upgrade
command with the reason **“blocked by policy”**; no more detailed reason was
provided. Application-code changes were restarted and browser-tested normally. The launcher
was also checked for both restart and reuse using the opaque installation ID.
