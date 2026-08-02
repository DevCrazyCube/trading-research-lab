#!/usr/bin/env python3
"""B12b preview — serve the read-only operator console on loopback, and nothing else.

Python standard library only. No dependency is added by this file and none may be.

WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT
=============================================

It is a convenience for looking at `ui/operator_console.html` in a browser with a real viewport.
The console works identically opened straight from disk; this exists because `file://` makes some
browser tooling awkward, not because the page needs a server.

It is **not** an API and cannot become one by accident:

- **Loopback only.** It binds `127.0.0.1` and refuses any other address, so nothing outside this
  machine can reach it even if a firewall is open.
- **GET and HEAD only.** Every other method — POST, PUT, PATCH, DELETE — is answered `405` without
  ever reaching a handler. There is no route that writes, mutates, approves, signs or submits, and
  there is no code path here that could grow one without deleting the check that forbids it.
- **One directory, no traversal.** Only files under `ui/` are served; a resolved path outside it is
  `403`, so a crafted URL cannot read the repository, the artifacts or the environment.
- **No logging of request contents** beyond a single line to stderr, and no writing anywhere.
"""
import argparse
import functools
import http.server
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
UI_DIRECTORY = ROOT / "ui"
LOOPBACK = "127.0.0.1"

BANNER = """
  READ-ONLY PREVIEW of the operator console.
  Serving {directory} on http://{host}:{port}/operator_console.html

  GET and HEAD only. No API, no write endpoint, no wallet, no signing, no submission.
  Loopback only: nothing outside this machine can reach it.
  Press Ctrl-C to stop.
"""


class ReadOnlyHandler(http.server.SimpleHTTPRequestHandler):
    """Static files from one directory, by GET or HEAD, and no other verb at all."""

    def do_POST(self):        # noqa: N802 - http.server's naming
        self.send_error(405, "This preview is read-only; there is no write or API endpoint.")

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST
    do_OPTIONS = do_POST

    def translate_path(self, path):
        """Resolve inside the UI directory, or refuse.

        `SimpleHTTPRequestHandler` already normalises away `..`, but it resolves relative to the
        process's working directory. Re-checking against the real directory means a symlink or a
        future change to how the base path is chosen cannot walk out of `ui/`.
        """
        resolved = pathlib.Path(super().translate_path(path)).resolve()
        base = pathlib.Path(self.directory).resolve()
        if resolved != base and base not in resolved.parents:
            return str(base / "__forbidden__")
        return str(resolved)

    def end_headers(self):
        # A page that makes no request of any kind still benefits from a policy that says so: if a
        # future edit ever added one, the browser would block it rather than the reviewer catching
        # it. `default-src 'self'` with inline style/script allowed is exactly what this page is.
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; "
                         "script-src 'unsafe-inline'; img-src data:; form-action 'none'; "
                         "base-uri 'none'; frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format, *args):     # noqa: A002 - signature is http.server's
        sys.stderr.write("preview %s\n" % (format % args))


def build_server(port=0, directory=UI_DIRECTORY):
    directory = pathlib.Path(directory).resolve()
    if not directory.is_dir():
        raise SystemExit(f"REFUSING: {directory} is not a directory")
    handler = functools.partial(ReadOnlyHandler, directory=str(directory))
    return http.server.ThreadingHTTPServer((LOOPBACK, port), handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    server = build_server(args.port)
    host, port = server.server_address[0], server.server_address[1]
    print(BANNER.format(directory=UI_DIRECTORY, host=host, port=port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  preview stopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
