#!/usr/bin/env python3
"""Compatibility test for echo-nginx:1.25-bookworm-patched vs. nginx:1.25-bookworm.

"Working correctly" means: given the *same* nginx config file and the *same*
HTTP request, both images produce the same response status, the same
response headers (excluding ones that inherently vary per boot/request and
carry no compatibility signal, e.g. Date), and the same response body, byte
for byte.

Both images are booted as separate containers with the same config file
(test/config/default.conf) bind-mounted over /etc/nginx/conf.d/default.conf,
so a mismatch can only come from the images themselves (binary, patch,
library versions), not from different configs.

Scenarios covered (see SCENARIOS below) -- chosen to be representative, not
exhaustive:
  - root                    GET /                     (stock docroot + index)
  - 404 not found           GET /nope                 (stock error path)
  - custom config location  GET /custom-status         (location only this
                                                         config defines)
  - custom config header    GET /custom-header         (add_header directive)
  - HEAD request            HEAD /                     (headers only, no body)
  - large body, accepted    POST /upload, 500 KiB      (under client_max_body_size)
  - large body, rejected    POST /upload, 3 MiB        (over client_max_body_size -> 413)
  - malformed request       raw garbage request line   (-> 400 Bad Request)

Not covered (see README.md "Residual risk"): TLS, the mail/stream modules,
WebSocket upgrades, or anything needing an upstream backend (proxy_pass,
fastcgi, etc.) -- the assignment's target is nginx serving static content
and enforcing its own directives, which is what these scenarios exercise.

No third-party dependencies: stdlib only (http.client, socket, subprocess),
plus the `docker` CLI. Run directly (`python3 test/compat_test.py`) or via
`make test`. Exits 0 if every scenario matches, 1 if any differ, 2 on a
setup problem (e.g. an image isn't built).
"""

import http.client
import os
import socket
import subprocess
import sys
import time
import uuid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF_PATH = os.path.join(REPO_ROOT, "test", "config", "default.conf")

BASELINE_IMAGE = os.environ.get("BASELINE_IMAGE", "nginx:1.25-bookworm")
PATCHED_IMAGE = os.environ.get("PATCHED_IMAGE", "echo-nginx:1.25-bookworm-patched")

STARTUP_TIMEOUT_S = 10

# Headers that legitimately differ between two independent boots and carry
# no compatibility signal.
IGNORED_HEADERS = {"date"}

LARGE_BODY_OK = b"x" * (500 * 1024)            # under the 2m limit in the config
LARGE_BODY_TOO_BIG = b"x" * (3 * 1024 * 1024)  # over the 2m limit in the config


class Container:
    """Boots one image with the config mounted; gives back the host
    port it's reachable on. Always removed on exit, pass or fail."""

    def __init__(self, image):
        self.image = image
        self.name = f"compat-test-{uuid.uuid4().hex[:10]}"
        self.port = None

    def __enter__(self):
        subprocess.run(["docker", "rm", "-f", self.name], capture_output=True)
        subprocess.run(
            [
                "docker", "run", "-d",
                "--name", self.name,
                "-p", "127.0.0.1::80",
                "-v", f"{CONF_PATH}:/etc/nginx/conf.d/default.conf:ro",
                self.image,
            ],
            check=True, capture_output=True, text=True,
        )
        port_out = subprocess.run(
            ["docker", "port", self.name, "80/tcp"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        # e.g. "127.0.0.1:32812"
        self.port = int(port_out.rsplit(":", 1)[1])
        self._wait_ready()
        return self

    def _wait_ready(self):
        deadline = time.time() + STARTUP_TIMEOUT_S
        last_err = None
        while time.time() < deadline:
            try:
                conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=1)
                conn.request("GET", "/")
                conn.getresponse().read()
                conn.close()
                return
            except (OSError, http.client.HTTPException) as e:
                last_err = e
                time.sleep(0.2)
        raise RuntimeError(
            f"{self.image} never became ready on 127.0.0.1:{self.port}: {last_err}"
        )

    def __exit__(self, *exc_info):
        subprocess.run(["docker", "rm", "-f", self.name], capture_output=True)


def http_request(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request(method, path, body=body, headers=headers or {})
    except (BrokenPipeError, ConnectionResetError):
        # A server that rejects an oversized body (413) may reply and close
        # the connection before we finish writing it; the response is still
        # there to read.
        pass
    resp = conn.getresponse()
    resp_body = resp.read()
    resp_headers = {
        k.lower(): v for k, v in resp.getheaders() if k.lower() not in IGNORED_HEADERS
    }
    conn.close()
    return {"status": resp.status, "headers": resp_headers, "body": resp_body}


def raw_malformed_request(port):
    """http.client won't let us send an invalid request line, so this one
    goes over a raw socket."""
    with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
        s.sendall(b"NOT A REQUEST\r\n\r\n")
        s.settimeout(5)
        data = b""
        try:
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
        except socket.timeout:
            pass
    status = None
    if data.startswith(b"HTTP/"):
        try:
            status = int(data.split(b"\r\n", 1)[0].split(b" ")[1])
        except (IndexError, ValueError):
            pass
    return {"status": status, "headers": {}, "body": b""}


SCENARIOS = [
    ("root",                     lambda p: http_request(p, "GET", "/")),
    ("404 not found",            lambda p: http_request(p, "GET", "/this-path-does-not-exist")),
    ("custom config location",   lambda p: http_request(p, "GET", "/custom-status")),
    ("custom config add_header", lambda p: http_request(p, "GET", "/custom-header")),
    ("HEAD request",             lambda p: http_request(p, "HEAD", "/")),
    ("large body (accepted)",    lambda p: http_request(
        p, "POST", "/upload", body=LARGE_BODY_OK,
        headers={"Content-Type": "application/octet-stream"})),
    ("large body (rejected)",    lambda p: http_request(
        p, "POST", "/upload", body=LARGE_BODY_TOO_BIG,
        headers={"Content-Type": "application/octet-stream"})),
    ("malformed request line",   lambda p: raw_malformed_request(p)),
]


def diff(baseline, patched):
    problems = []
    if baseline["status"] != patched["status"]:
        problems.append(f"status: baseline={baseline['status']} patched={patched['status']}")
    if baseline["headers"] != patched["headers"]:
        keys = set(baseline["headers"]) | set(patched["headers"])
        for k in sorted(keys):
            bv, pv = baseline["headers"].get(k), patched["headers"].get(k)
            if bv != pv:
                problems.append(f"header {k!r}: baseline={bv!r} patched={pv!r}")
    if baseline["body"] != patched["body"]:
        problems.append(
            f"body differs: baseline {len(baseline['body'])} bytes vs "
            f"patched {len(patched['body'])} bytes"
        )
    return problems


def preflight():
    for img in (BASELINE_IMAGE, PATCHED_IMAGE):
        found = subprocess.run(
            ["docker", "image", "inspect", img], capture_output=True
        ).returncode == 0
        if found:
            continue
        if img == BASELINE_IMAGE:
            print(f"baseline image {img} not found locally, pulling...")
            subprocess.run(["docker", "pull", img], check=True)
        else:
            print(
                f"error: {img} not found locally. Run `make image` first.",
                file=sys.stderr,
            )
            return False
    return True


def main():
    if not preflight():
        return 2

    print(f"baseline: {BASELINE_IMAGE}")
    print(f"patched:  {PATCHED_IMAGE}")
    print(f"config:   {CONF_PATH}\n")

    with Container(BASELINE_IMAGE) as baseline_c, Container(PATCHED_IMAGE) as patched_c:
        failures = {}
        for name, scenario in SCENARIOS:
            baseline_result = scenario(baseline_c.port)
            patched_result = scenario(patched_c.port)
            problems = diff(baseline_result, patched_result)
            print(f"[{'FAIL' if problems else 'PASS'}] {name}")
            for p in problems:
                print(f"       {p}")
            if problems:
                failures[name] = problems

    print()
    if failures:
        print(f"{len(failures)}/{len(SCENARIOS)} scenario(s) FAILED")
        return 1
    print(f"all {len(SCENARIOS)} scenarios PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
