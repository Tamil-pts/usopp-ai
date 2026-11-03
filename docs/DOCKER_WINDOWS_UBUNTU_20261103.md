# Latest build and Docker host verification - 3 November 2026

The verified application version is **4.99.3**. Existing architecture, accounts,
project workflow and independent approval controls remain in place.

The root Dockerfile now provides `ubuntu` and `windows-desktop` targets, sharing
one Linux runtime. The Windows target is for Docker Desktop in Linux-container
mode; the Ubuntu target is for Docker Engine. This is a host packaging choice.

Build commands, run from the current checkout or extracted private source bundle:

```powershell
.\deploy\container\build-windows.ps1 -Plan
.\deploy\container\build-windows.ps1
```

```bash
bash deploy/container/build-ubuntu.sh plan
bash deploy/container/build-ubuntu.sh build
```

Both helpers read the release version from package.json, pass it to the build,
select the host target and default to `usopp-ai:4.99.3`. They reject invalid
versions and check for a Linux Docker daemon before building. Plan mode works
without Docker. Spaced source paths and source bundles without Git metadata were
checked. They do not start a new installation or alter its data volume.

The private build bundle now includes the Windows launcher as well as the Ubuntu
launcher, both builders, Compose, current instructions and the API smoke checker.
The Docker frontend stage also copies public assets, including the document
studio print script and its license. The existing comparison-report build script
and Linux ngspice dependency remain included.

Verification completed:

- Production builds passed for the main interface, comparison report, DataInspect
  and Virtual PLC.
- 202 regression tests and 35 subtests passed. Packaging tests were rerun after
  correcting the public-asset build context.
- 174 responsive layouts passed: 162 workspace/standalone layouts, four landing
  widths and eight light/dark top-bar layouts. Keyboard account-menu checks
  passed. Zoom checks use CSS widths equivalent to 80-200 percent browser zoom
  on a 1600-pixel display, plus mobile widths; browser zoom is user controlled.
- The staged runtime compiled without raw Python/TypeScript application source.
  Authenticated HTTP checks passed for UI entries/assets, the Studio print asset,
  checksums, UI/API version agreement, authentication, account storage, mappings,
  WorkHub resources/overview and Virtual PLC catalogs. OpenAPI registered 484 API
  paths; registration does not mean every endpoint was executed.
- 893 frontend relative imports passed Linux filename-case inspection.
- Both host build plans passed version, invalid-version and spaced-path checks.
  PowerShell parsing and Bash syntax checks passed.
- Source-bundle and launcher-ZIP checksums, both-host contents, secret exclusion,
  persistent-volume configuration and the live installation's version/integrity
  were verified. The source bundle includes the 1,129-row updated parameter master.

Docker and WSL are unavailable on this workstation. A Linux Docker image build,
container startup and physical PLC/optional-service integrations were not run.
The staged runtime was checked with the available Windows Python environment.
Run the supplied build and startup checks on a Docker-enabled host before
installing that image. Existing container volumes retain their saved data;
replacing master mappings in an existing installation remains an explicit import.

See [installation/build instructions](../distribution/CONTAINER_BUILD.md).
Evidence is retained under `.build/docker-hosts-20261103/`.
