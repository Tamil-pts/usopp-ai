# Account requirements for future updates

Keep all three account flows available in every uSOPp release:

- Anyone can choose **New user? Create account** on the sign-in page. Registration creates a regular user, never an administrator.
- Every signed-in user, including Admin, can change their own password through **Settings > My account**, by supplying the current password.
- Admin can create and manage regular accounts through **WorkHub > User management**. Creating a user must keep the Admin's current session.

There is no fixed account-count limit. Support 200 or more accounts while
keeping account count separate from concurrent project-engine jobs. Disabled
accounts retain history. Keep registration, Admin creation and re-enabling
transactional without a capacity gate. See [MULTI_USER.md](MULTI_USER.md) for
concurrent jobs and per-test history.

Admin sees every user's history; regular users see their own results. Keep
ownership checks on result, download, workspace, source and project-reuse
routes. Retain distinct test IDs and DataInspect/packet/rule-validation records
through cache clearing and updates.

Account management and shared model settings remain Admin-only. Regular users
can use Chopper without seeing or editing the shared model connection.

Preserve the `/api/auth/register`, `/api/auth/password`, and Admin-only
`/api/auth/users` routes and their frontend controls. Keep existing usernames,
password hashes, profiles and account roles during database migrations.
Never reseed an existing Admin password or include a real account database
in a distributable EXE package. Existing account checks are in
`tests/test_accounts.py`.

Accounts are stored under the application's data root. Source launches use the
app folder; EXE launches normally use `%LOCALAPPDATA%\uSOPp.ai`. Setting
`USOPP_DATA_ROOT` selects another persistent data root. Updating the EXE folder
does not reset accounts when the same data root is retained. Moving from a
source launch to the EXE with a different data root creates a separate account
store; it does not automatically transfer the source installation's accounts.

After updating code, finish current jobs and restart the backend. A running
Python process keeps its loaded code until restarted. The UI and API version
badges should show the same updated version.
