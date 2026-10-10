# uSOPp Ubuntu server deployment guide

Version: **4.64.8**. Updated: **2026-10-09**.

Use these steps to deploy a fresh demo on another Ubuntu server. The server
provides the web interface and API; users open the application in their browsers.

The user confirmed that SpinConnect started successfully on **192.168.19.10:8201**
and reported **Health: ready**. Docker already publishes port 8200 there.
This guide uses **8201** consistently. Use the new server's own IP address and
check that the chosen port is free.

## Contents

1. [Before starting](#1-before-starting)
2. [Transfer the deployment ZIP](#2-transfer-the-deployment-zip)
3. [Install Ubuntu prerequisites](#3-install-ubuntu-prerequisites)
4. [Install Node and configure PATH](#4-install-node-and-configure-path)
5. [Extract the application](#5-extract-the-application)
6. [Install Python 3.12](#6-install-python-312)
7. [Install and build uSOPp](#7-install-and-build-usopp)
8. [Choose a port and start](#8-choose-a-port-and-start)
9. [Firewall and browser access](#9-firewall-and-browser-access)
10. [First sign-in and project uploads](#10-first-sign-in-and-project-uploads)
11. [Daily commands and reboot](#11-daily-commands-and-reboot)
12. [Troubleshooting](#12-troubleshooting)
13. [Backup and update](#13-backup-and-update)
14. [Deployment record and verification](#14-deployment-record-and-verification)

## 1. Before starting

You need:

- An Ubuntu server and a normal login account with sudo access for apt/firewall commands.
- SSH access from your laptop, or a terminal opened directly on the server.
- Internet access to download Node, Python and application dependencies.
- The corrected `uSOPp_AI_4.64.8_Ubuntu_Demo_Source.zip` supplied with this guide.

The application requires Python 3.11 or later and Node 20 or later. These steps
use a separate **Python 3.12** environment and **Node 24**. Run all application
commands as the same normal server account, without sudo. Only apt and firewall
commands below use sudo.

Run each step in order. If a command fails, resolve it before continuing.
The Windows EXE is a separate release; use the Ubuntu source ZIP here. Source
code is visible in this demo. Linux source-free packaging is deferred.

## 2. Transfer the deployment ZIP

### From a Windows laptop

Save the supplied ZIP in your Windows **Downloads** folder. Open **PowerShell**.
Replace `SERVER_USER` and `SERVER_IP` with the new server's login and IP address.
For example, the existing server uses `lmw` and `192.168.19.10`.

```powershell
$usoppZip = Join-Path $env:USERPROFILE 'Downloads\uSOPp_AI_4.64.8_Ubuntu_Demo_Source.zip'
scp $usoppZip SERVER_USER@SERVER_IP:~/
ssh SERVER_USER@SERVER_IP
```

If the ZIP is elsewhere, change `$usoppZip` to its actual path. PowerShell
commands end here. Run the remaining installation commands in the **Ubuntu
terminal**, not in Windows PowerShell.

### From another Linux computer

From the folder containing the deployment ZIP:

```bash
scp uSOPp_AI_4.64.8_Ubuntu_Demo_Source.zip SERVER_USER@SERVER_IP:~/
ssh SERVER_USER@SERVER_IP
```

For a fresh deployment, transfer the supplied ZIP and recreate dependencies on
the destination. Do not copy Python environments or node_modules from the old
machine. The fresh bundle excludes your accounts, credentials, uploaded projects,
reports and model weights. It creates an independent installation.

## 3. Install Ubuntu prerequisites

Record the operating system and architecture:

```bash
cat /etc/os-release
uname -m
```

These are separate commands. Do not type the word `and` between them.

Install the operating system packages:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip python3-dev build-essential pkg-config libcairo2-dev curl ca-certificates unzip rsync
```

The compiler, pkg-config and Cairo development files support pycairo installation
for report dependencies. See the [Pycairo Ubuntu prerequisites](https://pycairo.readthedocs.io/en/latest/getting_started.html).

## 4. Install Node and configure PATH

Install Node under the server account with nvm, following the
[official nvm instructions](https://github.com/nvm-sh/nvm#installing-and-updating):

```bash
export NVM_DIR="$HOME/.nvm"
touch "$HOME/.bashrc"

curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.8/install.sh \
  -o "$HOME/usopp-nvm-install.sh"

PROFILE="$HOME/.bashrc" bash "$HOME/usopp-nvm-install.sh"

. "$NVM_DIR/nvm.sh"
nvm install 24
nvm alias default 24
nvm use 24
```

Check the versions and the commands found on PATH:

```bash
node --version
npm --version
command -v node
command -v npm
```

nvm configures the Node PATH. An example is:

```text
/home/lmw/.nvm/versions/node/v24.21.0/bin/node
```

The username and patch version may differ on the new server. Use the actual
path reported by `command -v node`; do not hardcode this example in system PATH.

## 5. Extract the application

On a fresh server:

```bash
mkdir -p "$HOME/usopp-demo"

unzip "$HOME/uSOPp_AI_4.64.8_Ubuntu_Demo_Source.zip" \
  -d "$HOME/usopp-demo"

cd "$HOME/usopp-demo/usopp_ai_2.0"
ls package.json usopp.sh backend_requirements.txt
```

The ZIP already contains the `usopp_ai_2.0` directory. For user `lmw`, the
application path is `/home/lmw/usopp-demo/usopp_ai_2.0`.
For an existing installation, use the update procedure in section 13.

## 6. Install Python 3.12

Use uv to install Python for this account. See the official
[uv installer](https://docs.astral.sh/uv/getting-started/installation/) and
[Python installation guide](https://docs.astral.sh/uv/guides/install-python/).

```bash
cd "$HOME/usopp-demo/usopp_ai_2.0"

curl -fsSL https://astral.sh/uv/install.sh \
  -o "$HOME/usopp-uv-install.sh"

UV_INSTALL_DIR="$HOME/.local/bin" sh "$HOME/usopp-uv-install.sh"

"$HOME/.local/bin/uv" python install 3.12
"$HOME/.local/bin/uv" venv --python 3.12 --seed .venv-ubuntu

source .venv-ubuntu/bin/activate
python3 --version
command -v python3
```

Expected: Python **3.12.x** and a path inside the application environment:

```text
/home/lmw/usopp-demo/usopp_ai_2.0/.venv-ubuntu/bin/python3
```

The prompt may show `(.venv-ubuntu)`. Activation changes Python for this shell
without replacing Ubuntu's system Python. Activate the environment again in each
new terminal before using the npm application commands.

## 7. Install and build uSOPp

From the application folder, with the Python environment active:

```bash
npm run server:install
```

The installer installs backend packages, root frontend packages and Nami
packages, then builds both interfaces. The corrected bundle installs Nami before
the main TypeScript build because Chopper imports its metadata parser. It
includes esbuild install-script approvals for the versions in the lockfiles.

**Wait for `Installation complete` before starting the server.** Installation
speed depends on downloads and server resources. Repeating after an error can
reuse downloaded files. For the original ZIP's missing `xlsx` or esbuild script
warning, use the recovery commands in section 12.

## 8. Choose a port and start

Check whether port 8201 is already occupied:

```bash
sudo ss -ltnp 'sport = :8201'
```

A LISTEN entry means it is occupied. Choose a free port between **8200 and 8500**
and use it in start/restart commands, firewall rules and browser addresses.
This guide uses **8201**:

```bash
npm start -- --port 8201
npm run status
```

Successful output should resemble:

```text
uSOPp 4.64.8 started (PID ...).
On this server: http://127.0.0.1:8201

Running: PID ..., port 8201, version 4.64.8.
Health: ready
```

The server runs in the background. The launcher records its own process in
`.usopp_server/server.json`; status and stop use that record.
`npm start` without a port selects **8200**. `npm restart` without a port also
selects 8200, even if the last run used 8201. Keep `-- --port 8201` in both commands.

## 9. Firewall and browser access

Check Ubuntu's firewall:

```bash
sudo ufw status
```

If UFW is active, allow the port:

```bash
sudo ufw allow 8201/tcp
```

If UFW is inactive, adding a rule does not activate it. A separate network/cloud
firewall, if present, also needs to allow the chosen port.

Find the server's addresses:

```bash
hostname -I
```

Use the server address reachable from your laptop. Docker can add several
addresses to this list. SpinConnect's working LAN address is `192.168.19.10`;
use the new server's address on another installation.

Open from your laptop:

```text
http://SERVER_IP:8201
```

Existing SpinConnect example: `http://192.168.19.10:8201`.
On the Ubuntu server itself, use `http://127.0.0.1:8201`.
The default binding is `0.0.0.0`, allowing network access. For local access only
or a reverse proxy, bind to loopback explicitly:

```bash
npm start -- --host 127.0.0.1 --port 8201
```

## 10. First sign-in and project uploads

A fresh account database creates this initial administrator:

| Field | Initial value |
| --- | --- |
| Username | `Admin` |
| Password | `usopp.2026` |

After signing in, change the administrator password in **Settings**.
Existing installations retain their current password; restarting does not reset
it. Admin can create/manage accounts in **WorkHub → User management**.
Users can change their own passwords in Settings.

For PLC projects on your laptop, use the browser upload/attachment controls.
A local path entered in the application must exist on the Ubuntu server;
a Windows `C:\...` path on the laptop is not an Ubuntu server path.

PLC log decoding, validation and comparison work without a language model.
Admin can configure an optional local model, Ollama or API provider in Settings.
`localhost` in a model connection refers to the Ubuntu server. Ollama on your
laptop is a separate service and is not automatically installed on the server.
Model weights and API keys are not included in the deployment ZIP.

## 11. Daily commands and reboot

In a new SSH terminal, load Node and activate Python:

```bash
export NVM_DIR="$HOME/.nvm"
. "$NVM_DIR/nvm.sh"
nvm use 24

cd "$HOME/usopp-demo/usopp_ai_2.0"
source .venv-ubuntu/bin/activate
```

Then use:

| Action | Command |
| --- | --- |
| Start on port 8201 | `npm start -- --port 8201` |
| Check tracked server | `npm run status` |
| Stop tracked server | `npm stop` |
| Restart on port 8201 | `npm restart -- --port 8201` |
| Last 80 launcher-log lines | `npm run logs` |
| Live launcher log | `tail -f logs/ubuntu-demo.log` |
| List backend log files | `ls logs/usopp_backend_*.log` |

Ctrl+C exits a live tail view. The launcher starts a background process, so
closing SSH does not require starting another instance.

**This demo does not install an automatic startup service.** After reboot, open
SSH, run the environment commands above, start on 8201 and check status.
Automatic startup/systemd can be configured separately later.

Equivalent commands without npm shortcuts:

```bash
bash usopp.sh install
bash usopp.sh start --port 8201
bash usopp.sh status
bash usopp.sh logs
bash usopp.sh stop
bash usopp.sh restart --port 8201
```

## 12. Troubleshooting

### Python version too old

For `Use Python 3.11 or later`, complete section 6. Activate `.venv-ubuntu` in
new terminals. Check `python3 --version` and `command -v python3`.

### pycairo / Cairo / pkg-config failure

Errors include `metadata-generation-failed`, `Dependency lookup for cairo`,
or `Pkg-config ... not found`:

```bash
sudo apt update
sudo apt install -y build-essential pkg-config libcairo2-dev python3-dev

cd "$HOME/usopp-demo/usopp_ai_2.0"
source .venv-ubuntu/bin/activate
npm run server:install
```

The CMake message in the reported error was a discovery check. Installing
pkg-config and Cairo development files resolves that specific dependency lookup.

### Missing xlsx or esbuild warning in the original ZIP

The earlier ZIP compiled the main application before installing Nami's `xlsx`.
`TS2307: Cannot find module 'xlsx'` and the related `TS7006` can appear together.
Recover that existing copy with:

```bash
cd "$HOME/usopp-demo/usopp_ai_2.0"
source .venv-ubuntu/bin/activate

npm install-scripts approve esbuild
npm rebuild esbuild

cd nami
npm ci --no-audit --no-fund
npm install-scripts approve esbuild
npm rebuild esbuild

cd ..
npm run server:install
```

Newer npm stores approvals in each project's package.json, so they persist
through later installs. The commands approve esbuild specifically. See
[npm install-script approvals](https://docs.npmjs.com/cli/v11/commands/npm-install-scripts/).
If `install-scripts` is unknown, that npm version lacks the approval command;
use the Node setup in section 4.

### Port occupied while status says stopped

Status reports only the process tracked by this launcher. Docker or a server
started by another command can occupy a port independently:

```bash
sudo ss -ltnp 'sport = :8200'
sudo ss -ltnp 'sport = :8201'
```

SpinConnect showed docker-proxy on 8200 and uSOPp worked on 8201. Choose a free
port. If 8201 is also occupied:

```bash
npm start -- --port 8202
```

Use `http://SERVER_IP:8202` and allow 8202 in the firewall for that run.

### Install the demo first

The application environment or built interface is missing. Complete
`npm run server:install` successfully before starting.

### Server exited or did not become ready

```bash
npm run logs
tail -n 100 logs/ubuntu-demo.log
```

Read the final log error before starting again.

### npm/node command not found

Load the nvm environment using the first three commands in section 11, then
check `command -v node` and `command -v npm`.

### Browser cannot connect although health is ready

On the server:

```bash
curl -fsS http://127.0.0.1:8201/api/health
sudo ss -ltnp 'sport = :8201'
sudo ufw status
hostname -I
```

For direct LAN access, the server must listen on `0.0.0.0:8201` and the browser
must use the reachable server IP and port. Check network/cloud firewall rules
if local health responds but the remote browser cannot connect.

## 13. Backup and update

### Data locations

Source-demo data stays inside the application folder:

| Location | Contents |
| --- | --- |
| `accounts.sqlite3` | Accounts and sessions |
| `.usopp_workspaces/` | Uploads, operation sessions and reports |
| `.usopp_exports/` | Generated metadata and workbook copies |
| `knowledge/` | Mappings, project knowledge, data models and settings |
| `rules/` | Rule configuration |
| `logs/` | Runtime and backend logs |

A fresh deployment on another server creates independent accounts/data.
To migrate existing data, retain a backup and transfer the required data
separately from the fresh deployment ZIP. Server-local project paths may need
to be selected again on the destination.

### Backup before an update

Finish active comparisons/exports. Stop the application, then back up:

```bash
cd "$HOME/usopp-demo/usopp_ai_2.0"
source .venv-ubuntu/bin/activate
npm stop

usopp_backup_stamp=$(TZ=Asia/Kolkata date +%Y%m%d_%H%M%S)

tar -czf "$HOME/usopp-demo-backup-${usopp_backup_stamp}.tar.gz" \
  --exclude='usopp_ai_2.0/.venv-ubuntu' \
  --exclude='usopp_ai_2.0/.venv' \
  --exclude='usopp_ai_2.0/node_modules' \
  --exclude='usopp_ai_2.0/nami/node_modules' \
  --exclude='usopp_ai_2.0/dist' \
  --exclude='usopp_ai_2.0/nami/dist' \
  --exclude='usopp_ai_2.0/.usopp_server' \
  -C "$HOME/usopp-demo" usopp_ai_2.0

ls -lh "$HOME/usopp-demo-backup-${usopp_backup_stamp}.tar.gz"
```

This includes source and persistent data; dependencies/builds can be recreated.
Keep the archive private because it contains application data and settings.

### Apply an updated source ZIP

Copy the new ZIP to the server's home directory. Extract into a separate staging
folder and copy source while preserving current data:

```bash
usopp_update_dir=$(mktemp -d "$HOME/usopp-update.XXXXXX")

unzip "$HOME/uSOPp_AI_4.64.8_Ubuntu_Demo_Source.zip" \
  -d "$usopp_update_dir"

rsync -av \
  --exclude='/accounts.sqlite3*' \
  --exclude='/.usopp_*' \
  --exclude='/.venv*' \
  --exclude='/node_modules/' \
  --exclude='/nami/node_modules/' \
  --exclude='/dist/' \
  --exclude='/nami/dist/' \
  --exclude='/logs/' \
  --exclude='/knowledge/' \
  --exclude='/rules/' \
  --exclude='/.env*' \
  "$usopp_update_dir/usopp_ai_2.0/" "$HOME/usopp-demo/usopp_ai_2.0/"

cd "$HOME/usopp-demo/usopp_ai_2.0"
source .venv-ubuntu/bin/activate
npm run server:install
```

Replace the ZIP filename for a later release. This preserves existing knowledge
and rules; review changes to bundled defaults separately when a release adds new
ones. It does not delete old source files. Follow release-specific migration
instructions when supplied.

### 4.65.3 fixed data model references

For this release, also copy the bundled `knowledge/data_models` folder from the
updated source. The general update command above excludes `knowledge`, so it
will otherwise keep the earlier versioned references. Use these commands while
the staging folder from the update step is still available:

```bash
usopp_model_backup_stamp=$(date +%Y%m%d_%H%M%S)
cp -a "$HOME/usopp-demo/usopp_ai_2.0/knowledge/data_models" \
  "$HOME/usopp-data-models-backup-${usopp_model_backup_stamp}"
rsync -av \
  "$usopp_update_dir/usopp_ai_2.0/knowledge/data_models/" \
  "$HOME/usopp-demo/usopp_ai_2.0/knowledge/data_models/"
```

Use the complete 4.65.3 source, rebuild with `npm run server:install`, and restart
the backend. The UI and API badges should show **4.65.3**. References now appear
under PMS, QMS and CMS, with a department JSON in each service. Finisher and
Breaker remain separate; parameter names ignore letter case. See
[fixed data model documentation](knowledge/data_models/README.md) for source
selection, the mislabeled QMS Breaker source and future reference rebuilds.
Private user imports, account databases and saved tests are preserved.

After installation completes:

```bash
npm start -- --port 8201
npm run status
```

## 14. Multiple users and test history (4.65.2)

The updated application defaults to five enabled regular users plus Admin
(six accounts total). If the startup environment has `USOPP_MAX_USERS=5`,
change it to `USOPP_MAX_USERS=6` before restarting.
WorkHub now retains DataInspect, ByteMap and LogicScan results with a separate
test ID, owner and timestamp. Admin sees every user's tests; regular users see
their own. Existing accounts and stored results are retained.

Follow [MULTI_USER.md](MULTI_USER.md) for the update commands, capacity settings,
history operation and data locations. Its changes apply after copying updated
source, rebuilding and restarting the backend. The earlier 4.64.8 demo ZIP and
the confirmed running server do not acquire this update automatically.

## 15. Deployment record and verification

Record these details for each server:

| Item | SpinConnect deployment / new-server entry |
| --- | --- |
| Deployment date | 2026-10-09 / fill in new date |
| Server name | SpinConnect / new server name |
| Server user | lmw / new login account |
| LAN IP | 192.168.19.10 / new reachable IP |
| Application version | 4.64.8 |
| Application folder | /home/lmw/usopp-demo/usopp_ai_2.0 / new user's path |
| HTTP port | 8201 / chosen free port |
| Python version | Record `python3 --version` after activation |
| Node / npm | Record `node --version` and `npm --version` |
| OS version | Record `cat /etc/os-release` output |
| Startup result | Running; Health: ready / new result |

The user confirmed installation, startup and browser operation on SpinConnect
after the Python, Cairo, Nami and port fixes. This confirms that deployment,
not every application feature on Ubuntu. The corrected bundle includes the
source build-order fix and this guide. A fresh installation of that bundle on
the second server is still to be confirmed.
