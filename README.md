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

## Per-CVE table

| CVE | Severity | Library | Fix method | Evidence |
|---|---|---|---|---|
| CVE-2026-31789 | Critical | openssl / libssl3 | Version bump: `3.0.11-1~deb12u2` → `3.0.20-1~deb12u2` | `triage/baseline-trivy.txt`, `triage/rescan-diff.txt` (gone from both scanners post-fix) |
| CVE-2026-42533 | Critical | nginx (core script/complex-value engine) | Backport: upstream commits [`28219209`](https://github.com/nginx/nginx/commit/28219209e0b4f9e155fd8bd91ab81b8ac30628f2) + [`b7675404`](https://github.com/nginx/nginx/commit/b767540492e8c79a58bc26034d3bab2f708b7bd1) applied onto 1.25.5 | `triage/baseline-grype-critical.txt`, [vex/CVE-2026-42533.openvex.json](vex/CVE-2026-42533.openvex.json) |

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
- Using Claude Code, wrote the compatibility test (`test/compat_test.py`) and its config (`test/config/default.conf`), wired it into `make test`, and validated both ways: a real passing run (8/8) and two deliberate mismatch runs (fabricated results, and a real second container booted with a different config) to confirm it actually fails when things differ, not just when they happen to match.


## Build instructions

```bash
make build-deb   # build/Dockerfile: clean debian:bookworm-slim -> dist/*.deb
make image       # Containerfile: install the .deb -> echo-nginx:1.25-bookworm-patched
make test        # boots both images, diffs their HTTP behavior (see below)
```

## Compatibility test

`test/compat_test.py` (stdlib only — no `pip install` needed) boots
`nginx:1.25-bookworm` and `echo-nginx:1.25-bookworm-patched` as separate
containers, both with the **same** config file
(`test/config/default.conf`) built over `/etc/nginx/conf.d/default.conf`, so any mismatch can only come from the
images themselves, not from different configs.

**"Working correctly" means**: for the same request, both images return the
same status code, the same response headers (except `Date`, which
legitimately differs per boot), and the same response body, byte for byte.

**Scenarios**:

| Scenario | Request | Proves |
|---|---|---|
| root | `GET /` | stock docroot + index file identical |
| 404 | `GET /nope` | stock error path identical |
| custom config location | `GET /custom-status` | a location only this config defines resolves the same on both |
| custom config header | `GET /custom-header` | `add_header` behaves the same on both |
| HEAD | `HEAD /` | headers-only responses match |
| large body, accepted | `POST /upload`, 500 KiB | a body under a custom `client_max_body_size` (2m, not the 1m default) is accepted the same way |
| large body, rejected | `POST /upload`, 3 MiB | a body over that same custom limit is rejected (413) the same way |
| malformed request | raw garbage request line over a socket | both reject it the same way (400) |

**What it doesn't cover**: TLS, the mail/stream modules, WebSocket upgrades.

```bash
make test
# or directly:
python3 test/compat_test.py
```

## Rescan and VEX

```bash
trivy image echo-nginx:1.25-bookworm-patched > triage/patched-trivy.txt
grype echo-nginx:1.25-bookworm-patched > triage/patched-grype.txt
```

## Residual risk assessment

- **CVE-2026-42533 isn't fully closed.** Upstream's real fix is 5 commits; I backported the 2 that close the actual heap overflow (`28219209` + `b7675404`) and left out 3 that harden more specific issues.
- **Every other CVE in the baseline scan is still present** — only the 2 selected CVEs were fixed end-to-end, per the assignment's requirements. See `triage/baseline-trivy.txt` / `triage/baseline-grype.txt` for the rest.
- **Scanners still flag CVE-2026-42533 without the VEX applied** — Trivy/Grype match by package name + version string, and the package is still `1.25.5-1~bookworm`, so a scan run without `--vex vex/CVE-2026-42533.openvex.json` will show it as unfixed even though the code is patched. Anyone consuming this image needs to know to apply the VEX file.
- **Compatibility test scope**: `test/compat_test.py` covers static content, and error paths. It does not cover TLS, the mail/stream modules, WebSocket upgrades, or anything needing a real upstream backend (`proxy_pass`, `fastcgi_pass`) — those would need a second container/service in the test module.
