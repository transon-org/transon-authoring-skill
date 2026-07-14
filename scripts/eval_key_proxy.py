"""OQ-027f(ii) — key-withholding reverse proxy for the real-host eval gate.

The Claude Agent SDK runs the model's tools (**including Bash**) and the model-API
call in the same subprocess, so a provider key placed in that process's
environment is readable by the model's Bash. To keep the key out of the
tool-execution environment (SPEC §11.8 / AD-024 / OQ-027f(ii)), the dispatch
workflow runs this tiny proxy: it holds the **real** ``ANTHROPIC_API_KEY`` in
**its own** environment and forwards to ``api.anthropic.com``. The eval process
(and therefore the model's Bash) is given only ``ANTHROPIC_BASE_URL`` pointing
here plus a **placeholder** key — never the secret. The proxy rewrites the auth
header to the real key on the way out.

Egress is pinned to the single upstream host; the proxy never connects anywhere
else, and it never logs request paths/headers/bodies (they can carry text).

**Scope / honest limits.** This removes the key from the eval process's
environment and from the AuthoringResult/transcript. It does **not** by itself
defend against an adversarial model that reads the proxy's own
``/proc/<pid>/environ`` or searches the shared filesystem — those require the
OQ-027f(iii) egress-deny (so a read key can't be exfiltrated) and/or running the
model's tools in a **separate container/namespace** from this proxy. This is the
process-level layer of the contract, not the whole of it. Dispatch-only;
unverified until the first real run.
"""

from __future__ import annotations

import argparse
import http.client
import http.server
import os
import socketserver
import ssl
import sys

#: The single upstream the proxy will ever connect to. Hardcoded so a
#: model-crafted request through the proxy can only ever reach Anthropic.
UPSTREAM_HOST = "api.anthropic.com"
UPSTREAM_PORT = 443

#: Hop-by-hop headers (RFC 7230 §6.1) plus ones we always re-derive. Stripped
#: from both the request we forward and the response we return.
_STRIP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
    }
)


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _forward(self) -> None:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            self.send_error(500, "proxy has no upstream key")
            return

        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None

        # Rebuild request headers: drop hop-by-hop + the caller's (placeholder)
        # credentials, then inject the REAL key. The caller never supplies auth
        # that reaches Anthropic — only this proxy does.
        out_headers: dict[str, str] = {}
        for name, value in self.headers.items():
            lname = name.lower()
            if lname in _STRIP or lname in ("x-api-key", "authorization"):
                continue
            out_headers[name] = value
        out_headers["Host"] = UPSTREAM_HOST
        out_headers["x-api-key"] = key
        if body is not None:
            out_headers["Content-Length"] = str(len(body))

        try:
            conn = http.client.HTTPSConnection(
                UPSTREAM_HOST,
                UPSTREAM_PORT,
                timeout=900,
                context=ssl.create_default_context(),
            )
            conn.request(self.command, self.path, body=body, headers=out_headers)
            resp = conn.getresponse()
        except Exception as exc:  # upstream/TLS fault → 502, never leak details
            self.send_error(502, f"proxy upstream error: {type(exc).__name__}")
            return

        # Stream the response back with chunked transfer so SSE (the SDK streams)
        # is delivered incrementally rather than buffered whole.
        try:
            self.send_response(resp.status, resp.reason)
            for name, value in resp.getheaders():
                if name.lower() in _STRIP:
                    continue
                self.send_header(name, value)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                self.wfile.write(b"%X\r\n" % len(chunk) + chunk + b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        finally:
            conn.close()

    do_GET = _forward
    do_POST = _forward
    do_PUT = _forward
    do_DELETE = _forward
    do_PATCH = _forward

    def do_HEAD(self) -> None:  # readiness probe (curl -o /dev/null)
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args: object) -> None:
        # Never log — request lines/headers can carry sensitive text.
        return


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval_key_proxy")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "eval_key_proxy: ANTHROPIC_API_KEY is not set in the proxy's own "
            "environment — nothing to forward with (OQ-027f(ii))",
            file=sys.stderr,
        )
        return 2

    server = _Server((args.host, args.port), _Handler)
    print(
        f"eval_key_proxy: listening on http://{args.host}:{args.port} -> "
        f"https://{UPSTREAM_HOST} (key withheld from tool sandbox, OQ-027f(ii))",
        file=sys.stderr,
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
