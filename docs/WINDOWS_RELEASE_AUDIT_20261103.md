# Windows release audit fix — 3 November 2026

The reported GitHub Actions Windows build completed `uSOPp_AI.exe`, then failed
the raw-source audit in `build_windows_exe.ps1`. PyInstaller's `--collect-all`
collects Python source files as package data. In this environment, PDFium's two
packages contributed 24 `.py` files this way.
The full local build also exposed four Playwright `.d.ts` development declarations.
Local hooks keep its Node driver/runtime assets and omit typings and source maps.

The build now collects Python modules into the frozen archive, PDFium binaries
separately, and non-code resources with `--collect-data`. The source audit stays
enabled and prints the first 25 offending relative paths if it fails. The bundle
also includes WorkHub's HTML report template and Studio print assets. An already
installed matching PyInstaller version is reused.

The release workflow now stops immediately when Python environment creation or
dependency installation fails. Both jobs check an isolated running application's
UI assets and authenticated APIs before packaging. The Linux image receives its
source commit build argument. Windows portable packages and the Linux container remain separate jobs;
Docker Desktop on Windows uses the Linux image.

A local frozen PDFium probe opened, rendered and extracted text from a generated
PDF. The complete application then built successfully and passed the raw-source
audit. The running EXE passed UI asset/checksum, authentication, version agreement
and selected API checks (484 API paths registered). The download packager produced
a 142.1 MiB Windows ZIP containing 1,545 files and zero forbidden source/map files.
WorkHub report templates and the Playwright Node driver are retained.

The targeted regression run passed 57 tests, including actual Playwright asset
collection, delivery gates, MIS permissions/date grouping and container packaging.
Verification artifacts are under `.build/release-audit-20261103/`, including
`windows-build-fixed.log`, `windows-runtime-smoke.log`, `regression.log` and
`final-checks.json`.

A GitHub Actions rerun is still required to verify the hosted runner. Docker is
unavailable on this workstation, so the Linux image was not built/run locally.
No remote run, commit, push or release publication was performed.
