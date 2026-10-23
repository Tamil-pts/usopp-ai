# Copy and install the private Ubuntu build

Current handover: **uSOPp 4.74.2 / Virtual PLC 0.9.0**.

`uSOPp_4.74.2_server_build.tar.gz` contains Docker build inputs and the existing
container installer. Build the image on the server using `docker build`.
The server needs internet access for base images, npm, pip and llama.cpp.
No Docker build or installation on the destination server has been performed
from the development laptop.

Run one section at a time and stop if a command fails.

## 1. Copy from Windows

Open **Windows PowerShell**, separate from the Ubuntu SSH terminal:

```powershell
scp -o "User=tamilselvan.p@petrus.local" "C:\Users\PTPL0241\Projects\AI_QC\uaopp.ai\usopp_ai_2.0\release\container-build\uSOPp_4.74.2_server_build.tar.gz" "pt-ws-0013.dx.petrus.local:/tmp/"
```

Use your SSH password when prompted. The destination is `/tmp` so it does not
depend on the domain account's home-directory spelling.

## 2. Check Ubuntu and Docker

In your **Ubuntu root terminal**:

```bash
cat /etc/os-release
uname -m
docker version
docker compose version
```

If Docker and Compose already work, skip the installation block below. For a
fresh Ubuntu host, these commands follow
[Docker's official Ubuntu repository instructions](https://docs.docker.com/engine/install/ubuntu/):

```bash
apt-get update
apt-get install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker version
docker compose version
```

Do not replace a working Docker installation. If the package manager reports
conflicting container packages, resolve that existing installation before
continuing; this guide does not remove it.

### Docker works but `docker compose` is unknown

Keep the installed Docker Engine and the image already built. The installer
requires the Compose CLI plugin, which is separate from Docker Engine. Docker
documents installing it manually for all users in
[`/usr/local/lib/docker/cli-plugins`](https://docs.docker.com/compose/install/linux/).
For this x86_64 server, run as root:

```bash
apt-get update
apt-get install -y ca-certificates curl
curl --fail --location --retry 3 https://github.com/docker/compose/releases/download/v5.6.0/docker-compose-linux-x86_64 -o /tmp/usopp-docker-compose-v5.6.0
echo '40343e21ca777173e69cff5dbafeb37c6f81f3b0d57d9e597f036e95eb63e76a  /tmp/usopp-docker-compose-v5.6.0' | sha256sum -c -
```

Only after the checksum reports `OK`:

```bash
install -d -m 0755 /usr/local/lib/docker/cli-plugins
install -m 0755 /tmp/usopp-docker-compose-v5.6.0 /usr/local/lib/docker/cli-plugins/docker-compose
docker compose version
docker compose ls
```

Continue only after both Compose commands succeed. The checksum is from the
[official v5.6.0 release](https://github.com/docker/compose/releases/tag/v5.6.0).
A manually installed plugin must be updated separately in future.

On `pt-ws-0013`, the reported LAN IPv4 is `10.20.31.137`. For a fresh install,
the complete command avoids an interactive address prompt:

```bash
cd /opt/usopp/build-4.74.2
USOPP_PORT=8200 USOPP_BIND_ADDRESS=10.20.31.137 bash distribution/usopp-container.sh install usopp-ai:4.74.2
```

Choose the Admin password when asked, then open
`http://10.20.31.137:8200`. Use the existing-install update section instead if
uSOPp is already installed under another account/configuration.

## 3. Extract and build

Compare `sha256sum /tmp/uSOPp_4.74.2_server_build.tar.gz` against the checksum
supplied with the handover, then:

```bash
mkdir -p /opt/usopp/build-4.74.2
tar -xzf /tmp/uSOPp_4.74.2_server_build.tar.gz -C /opt/usopp/build-4.74.2
cd /opt/usopp/build-4.74.2
docker build --build-arg APP_VERSION=4.74.2 -t usopp-ai:4.74.2 .
```

Continue only after the image build succeeds. Leave the terminal open while it
builds. This compiles the frontend, Virtual PLC frontend, Python runtime and CPU
llama-server. AI model weights are installed separately through the app.

### Earlier archive: `--chmod option requires BuildKit`

The updated Dockerfile uses plain `COPY` followed by `RUN chmod`, which also
works with the legacy Linux builder. If you already extracted the earlier
archive and reached this error at the entrypoint copy, run in Ubuntu:

```bash
cd /opt/usopp/build-4.74.2
sed -i 's/\r$//' Dockerfile
sed -i 's|^COPY --chmod=755 deploy/container/entrypoint.sh /usr/local/bin/usopp-start$|COPY deploy/container/entrypoint.sh /usr/local/bin/usopp-start\nRUN chmod 755 /usr/local/bin/usopp-start|' Dockerfile
docker build --build-arg APP_VERSION=4.74.2 -t usopp-ai:4.74.2 .
```

This keeps the completed build stages available in Docker's cache. It does not
require another archive transfer. The `debconf` frontend fallback messages in
the package installation output do not cause this build failure.

## 4A. Fresh installation

Check for an existing app or an occupied port:

```bash
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'
ss -ltnp '( sport = :8200 )'
hostname -I
```

Use this section only if uSOPp has not already been installed on this server.
Choose the LAN IPv4 address reached by your browser, then run:

```bash
read -r -p 'Server LAN IPv4 address: ' usopp_lan_ip
USOPP_PORT=8200 USOPP_BIND_ADDRESS="$usopp_lan_ip" \
  bash /opt/usopp/build-4.74.2/distribution/usopp-container.sh install usopp-ai:4.74.2
```

Choose an initial Admin password of 12 to 128 characters when prompted.
The installer creates persistent volume `usopp-container_data`. It stores its
configuration under the installation account's `~/.config/usopp-container`.
For a root installation this is `/root/.config/usopp-container`.
Use port 8201 instead if 8200 is occupied, and use 8201 in the browser URL.

## 4B. Update an existing container installation

Finish active user jobs first. Use the same Linux account and installer
configuration as the original installation. Logging in as root does not
automatically select another user's configuration.

In that original installation account's shell:

```bash
test -f "$HOME/.config/usopp-container/image"
cat "$HOME/.config/usopp-container/image"
cat "$HOME/.config/usopp-container/port"
bash /opt/usopp/build-4.74.2/distribution/usopp-container.sh update usopp-ai:4.74.2
```

The updater stops the app, creates a full backup and starts the new image on
the existing volume. It keeps the saved port/address, accounts and data.
If the installer configuration is missing, locate the original account/config
before continuing. A native Python/npm installation needs its own migration;
do not initialize a fresh container expecting it to contain the old data.

## 5. Check startup and open the app

Use the same installation account as step 4:

```bash
bash /opt/usopp/build-4.74.2/distribution/usopp-container.sh status
bash /opt/usopp/build-4.74.2/distribution/usopp-container.sh logs
```

Open `http://pt-ws-0013.dx.petrus.local:8200/api/health` from the browser. Expected
application version: `4.74.2`. Then open
`http://pt-ws-0013.dx.petrus.local:8200` and sign in as `Admin` with the chosen
password. Use the saved address/port for an existing installation.

If name resolution fails, use the chosen server LAN IPv4 address. Allow the
application port for the intended LAN/VPN users using your network's Docker
firewall configuration. Docker-published ports require Docker-aware firewall
rules; see the firewall section of the official installation guide above.

The build archive excludes laptop accounts, project uploads, saved workspaces
and AI model weights. Upload Project 2 through the browser for a new server,
then open Virtual PLC and enable its Simulation jig. To transfer existing saved
workspaces, use a supported backup/export separately from this application
build. Existing server data stays on its retained volume during an update.

For Chopper on a new server, install/select the local CPU model through Settings
after signing in. The first model download needs internet access.
Production, quality, stoppage, breakage, air and power report calculations work
without a language model. After updating, refresh the browser and reattach the
report workbooks in Chopper. See `REPORT_ANALYSIS.md` for question examples and
calculation rules.
