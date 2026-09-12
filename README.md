# Echo Assignment

This repo includes the files, steps, and code for the Echo home assignment.
Steps taken and explanations are also included here, and were updated with the commits.

---

## Chosen CVEs

- Version Bump (CVE-2026-31789):
    - Found in openssl/libssl3
    - Found in a core system library, and has an official fix at 3.0.19-1~deb12u2
    
- Backport (CVE-2026-42533):
    - Found in nginx
    - Backporting a system library like curl or perl would require system compilation to patch.
    - Since I'm going to compile nginx from source anyways, it would serve as a good target.

## Steps

- First, generated both trivy and grype baselines without any filtering
- Then, generated baselines with only critical CVEs and formatted grype as table using jq.
- Using AI, created a diff between both of them, and added annotations for each of the tables with the fix strategy.
- Using Claude Code, cloned and applied the 5 commits that fixed the nginx core vulnerability.
- Using Claude Code, generated a patch with a header explaining the CVE and verified it.
- For the version bump fix, using Claude Code, generated a dockerfile and containerfile which both run apt-get for the fixed libssl3 version.
- Generated makefile using Claude Code and verified the patch.
- Added .gitignore for the dist directory
- Rescanned the built image with trivy and grype, diffed against the baseline (`triage/rescan-diff.txt`).
- Using Claude Code, generated an OpenVEX document for CVE-2026-42533 (`vex/CVE-2026-42533.openvex.json`), re-ran grype with `--vex` to confirm the CVE actually drops out of the report.


## Build instructions

```bash
make build-deb   # build/Dockerfile: clean debian:bookworm-slim -> dist/*.deb
make image       # Containerfile: install the .deb -> echo-nginx:1.25-bookworm-patched
```

## Rescan and VEX

```bash
trivy image echo-nginx:1.25-bookworm-patched > triage/patched-trivy.txt
grype echo-nginx:1.25-bookworm-patched > triage/patched-grype.txt
```
