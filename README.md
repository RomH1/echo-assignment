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
