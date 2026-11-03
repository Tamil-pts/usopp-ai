# Build the current uSOPp.ai container on Windows or Ubuntu

The root `Dockerfile` has two host profiles: `windows-desktop` and `ubuntu`.
Both produce the same Linux application runtime and persistent data format.
The Windows profile uses Docker Desktop with Linux containers. The Ubuntu
profile uses Docker Engine. The default Dockerfile target remains `ubuntu`.

The helpers read `package.json` for the current release and supply APP_VERSION.
The Dockerfile rejects a mismatch between that version and the compiled UI/API.
The current checkout is 4.99.3. These commands build local images; they do not
publish a release or copy existing production accounts into an image.

## Windows desktop

Install and start [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
with its Linux-container engine. Run from the extracted private build bundle or
current source checkout:

```powershell
.\deploy\container\build-windows.ps1 -Plan
.\deploy\container\build-windows.ps1
$Version = (Get-Content .\package.json -Raw | ConvertFrom-Json).version
.\distribution\usopp-container.ps1 install -Image "usopp-ai:$Version"
.\distribution\usopp-container.ps1 status
```

The installer asks for an initial Admin password and retains server data in a
named Docker volume. If port 8200 is occupied, add `-Port 8201` to installation.
Docker Desktop is intended for supported Windows desktop editions. A Windows
Server deployment can use an Ubuntu VM with the Docker Engine profile.

## Ubuntu

Install [Docker Engine and its Compose plugin](https://docs.docker.com/engine/install/ubuntu/).
Your account must be allowed to use the daemon. Run from the extracted private
build bundle or current checkout:

```bash
bash deploy/container/build-ubuntu.sh plan
bash deploy/container/build-ubuntu.sh build
# Use the image version printed by the builder, for example:
bash distribution/usopp-container.sh install usopp-ai:4.99.3
bash distribution/usopp-container.sh status
```

If port 8200 is occupied, prefix installation with `USOPP_PORT=8201`.
The images target Linux amd64. The host helpers do not need Node or Python;
Docker builds the frontend, Python runtime, llama.cpp CPU server and ngspice.
The image includes model runtime software; model weights are configured separately
and stored in the persistent volume.

## Build and startup verification

Both `-Plan` on Windows and `plan` on Ubuntu print the exact build without invoking
Docker. Build, install and inspect the container's health before using it.
For an isolated test installation, the bundled HTTP checker can verify the UI
assets/checksum, version agreement, authentication and registered APIs:

```bash
python scripts/container_smoke.py --url http://127.0.0.1:8200 --version 4.99.3 --password-file /private/path/admin-password.txt
```

Use a password file belonging to that isolated test installation. The checker
logs out its verification session and does not submit PLC requests. Optional
physical connections, Office services, OCR and model downloads require their
own configured integration checks.

For an existing container installation use the launcher's `update` command.
It retains the chosen bind address, port and data volume and takes a backup.
See [the installation guide](README.md) and [LAN deployment](LAN_SERVER.md).
Do not substitute the source checkout's local databases for a container volume.

The private source build archive includes both host helpers, both runtime
launchers, Compose, this guide and the smoke checker. Runtime images contain
compiled Python and built JavaScript. Database files, secret files, local reports,
model weights, private learning records and frontend source maps are excluded.
