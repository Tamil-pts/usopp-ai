# Private GitHub repositories and local installation

## Package layout

| Repository / package | Contains | Access |
| --- | --- | --- |
| Private `usopp-ai` | Application source, approved default rules/data models, build scripts | Maintainers |
| Private `usopp-distribution` | Installation README and compiled release downloads | Authorized users |
| Windows ZIP | Portable EXE, dependencies, frontend and defaults | Windows users |
| Container image archive + launchers ZIP | Compiled Linux application, dependencies, defaults and Compose commands | Windows Docker / Ubuntu users |

Users who can read the source repository can download its source. Keep end users in the downloads repository only. Both repositories are private. GitHub's automatic **Source code** release archive in the downloads repository contains only its installation README, not application code.

The container's final stage copies compiled application code from a builder. Original `.py`, `.ts`, `.tsx` and frontend source maps are excluded. Third-party Python dependencies retain their own files and licenses. Bytecode and JavaScript are reversible; containers provide packaging, not encryption. See [Docker multi-stage builds](https://docs.docker.com/get-started/docker-concepts/building-images/multi-stage-builds/).

## 1. Publish the reviewed source

The Git root must be **`usopp_ai_2.0`**, never the parent containing customer PLC projects. Ignored data includes accounts, uploads, results, logs, private model settings, model weights, dependencies, build outputs, project knowledge caches and the local B&R help archive. Approved department data models and default knowledge are included.

### GitHub Desktop (installed on this laptop)

Both local repositories are committed and ready for Desktop. Publish the source first:

1. Open GitHub Desktop and sign in to your GitHub account if needed.
2. Choose **File -> Add local repository**, select the following folder, and click **Add repository**:

```text
C:\Users\PTPL0241\Projects\AI_QC\uaopp.ai\usopp_ai_2.0
```

3. Click **Publish repository**. Change its GitHub name to **`usopp-ai`**.
4. Leave **Keep this code private** checked. Select your personal account or intended organization, then click **Publish repository**.

Repeat **File -> Add local repository** for the prepared downloads folder:

```text
C:\Users\PTPL0241\Projects\AI_QC\uaopp.ai\usopp-distribution
```

Publish it as **`usopp-distribution`**, keeping **Keep this code private** checked. This repository initially contains only installation instructions and ignore rules. Download packages go in **Releases**, not Git commits. Give end users access to this repository only.

These steps follow GitHub's [add a local repository](https://docs.github.com/en/desktop/adding-and-cloning-repositories/adding-a-repository-from-your-local-computer-to-github-desktop) and [publish an existing project](https://docs.github.com/en/desktop/adding-and-cloning-repositories/adding-an-existing-project-to-github-using-github-desktop) instructions. After publishing both repositories, continue with section 2 to configure release access.

### Optional GitHub CLI

If GitHub is connected to this workspace, use that connection to create the repositories. For command-line publishing, install Git and GitHub CLI on the maintainer PC:

```powershell
winget install --id Git.Git --exact
winget install --id GitHub.cli --exact
```

Close and reopen PowerShell for PATH changes. Sign in using your browser; never paste credentials into chat:

```powershell
Set-Location "C:\Users\PTPL0241\Projects\AI_QC\uaopp.ai\usopp_ai_2.0"
gh auth login
git status --short
git log -1 --oneline
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\publish_private_github.ps1
```

Select **GitHub.com → HTTPS → browser login**. The publisher creates private `usopp-ai` and `usopp-distribution` in the authenticated personal account, pushes the reviewed main branch, and puts only the README in the downloads repository. It does not force-push or change existing public repositories. For an organization you administer, add `-Owner <organization>`. Use `-SourceName` and `-DownloadsName` if those names are occupied by unrelated projects.

Pending edits must be reviewed and committed before publishing. See GitHub CLI [repository creation](https://cli.github.com/manual/gh_repo_create) and [authentication](https://cli.github.com/manual/gh_auth_login).

## 2. Configure release access

1. In the private source repository, open **Settings → Secrets and variables → Actions → Variables**. Set `DISTRIBUTION_REPO` to `<owner>/usopp-distribution`; the publisher sets this automatically.
2. Create a **fine-grained personal access token** restricted to the downloads repository, with **Contents: read and write** and an appropriate expiry. Store it only as the source repository's Actions secret **`DISTRIBUTION_TOKEN`**.
3. Give approved users read access to the **downloads repository**. Keep source access for maintainers.

The normal workflow token has only `contents: read`. The distribution token is used only in the draft-release step. No token goes into packages or images. See [GitHub token permissions](https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens).

## 3. Build downloads on GitHub

1. Open **Actions → Build private download packages → Run workflow** on `main`.
2. Leave **Create a draft release** unchecked for private Actions artifacts only. Check it after configuring the distribution variable and token to also prepare a draft release.
3. The Windows job builds the frontend and portable EXE; the Linux job builds a Linux amd64 image with compiled application bytecode. Neither job starts the application or runs runtime tests.
4. Download the run's artifacts or open the draft in the downloads repository. Review packages and installation behavior before publishing the draft to users. Publication is a separate manual action.

Assets for 4.65.11:

```text
uSOPp_AI_4.65.11_Windows_x64.zip
uSOPp_AI_4.65.11_Container_Launchers.zip
uSOPp_AI_4.65.11_Container_linux_amd64.tar.gz
```

Each has a `.sha256` companion. The image is exported with `docker image save` and loaded with `docker image load`, so users need no registry account. Earlier Ubuntu/Azure source ZIPs are **not end-user assets** and are ignored by Git.

The workflow runs only on manual request. Private repositories may consume Actions minutes/storage depending on the account plan. Failed builds stop before a draft is created. EXEs are currently unsigned; ARM servers need a separate image build.

## 4. Build locally

On a Windows build PC with the project `.venv`, Node and dependencies:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build_windows_exe.ps1 -RebuildFrontend
.\.venv\Scripts\python.exe scripts/package_downloads.py --latest-windows
```

Docker Desktop / Engine is required to build the image:

```powershell
docker build --platform linux/amd64 --build-arg APP_VERSION=4.65.11 -t usopp-ai:4.65.11 .
docker image save --output uSOPp_AI_4.65.11_Container_linux_amd64.tar usopp-ai:4.65.11
```

The Windows launcher also accepts an uncompressed `.tar`. On Ubuntu, produce the compressed release asset:

```bash
docker build --platform linux/amd64 --build-arg APP_VERSION=4.65.11 -t usopp-ai:4.65.11 .
docker image save usopp-ai:4.65.11 | gzip -1 > uSOPp_AI_4.65.11_Container_linux_amd64.tar.gz
sha256sum uSOPp_AI_4.65.11_Container_linux_amd64.tar.gz > uSOPp_AI_4.65.11_Container_linux_amd64.tar.gz.sha256
```

See [distribution/README.md](distribution/README.md) for installation, start/stop, passwords, ports, data and updates. See [BUILD_WINDOWS_EXE.md](BUILD_WINDOWS_EXE.md) for EXE details. The GitHub workflow builds both packages without Docker on the maintainer PC.

## 5. Update users

1. Edit the private source; bump `package.json` and root versions in `package-lock.json`, update CHANGELOG, review, commit and push `main`.
2. Manually build the version and publish the reviewed draft in the downloads repository.
3. Users download compiled assets from **Releases**, finish jobs, and replace their EXE package or image.
4. Native Windows users retain `%LOCALAPPDATA%\uSOPp.ai`. Container users retain the named data volume and installer settings. These installations use separate stores. Container updates make a full backup first; see the server guide for restore to another server.

Keep container project name `usopp-container`. Do not run `docker compose down --volumes` when updating: it deletes saved data. New defaults seed missing knowledge/rules without overwriting edited entries.

## 6. Windows Docker and website hosting

Windows users can run the same Linux amd64 image through Docker Desktop with its WSL 2 backend and Linux containers mode. The prepared `usopp-container.ps1` launcher installs the app from a downloaded image archive, then provides start, stop, status, logs and update commands. Install Docker Desktop separately first; the actual uSOPp image must be built before installation. See [Docker's Windows installation guide](https://docs.docker.com/desktop/setup/install/windows-install/) and [the user commands](distribution/README.md#windows-container).

| Location | What it provides for uSOPp |
| --- | --- |
| Private GitHub source repository | Versioned application source and build workflow |
| Private GitHub Releases | Windows ZIPs, container archives, launchers and checksums |
| GitHub Pages | A static information, documentation or download-links website |
| Docker on Windows or Ubuntu | The running application, Python APIs, login, validation, comparison, reports and persistent history |

[GitHub Pages is static hosting](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages). It cannot run this app's FastAPI backend, validation subprocesses or writable account/report storage. Publishing the frontend there alone would not provide a working uSOPp application. For the complete app, run the backend/container on a PC or server and provide the browser URL from that host.

Keep application source private when creating an information website. GitHub Pages availability for private repositories depends on the GitHub plan; see the linked Pages documentation. A separate download/information site can be prepared after choosing its audience and visibility. The current container browser binding is localhost; LAN or internet access requires an intentional host/proxy configuration.

## Preparation status

The agreed deployment is one shared server over the existing LAN/VPN. Follow [LAN_SERVER.md](distribution/LAN_SERVER.md) for install, retained-volume updates, automatic backups, new-volume restore and small CPU model setup. GitHub distributes application packages; private server data stays in the persistent volume.

Compilation and package audits are recorded in CHANGELOG. Remote creation/push needs a signed-in GitHub connection. Windows runtime, Docker build/run, Actions and destination installation are not verified merely by preparing these files.
