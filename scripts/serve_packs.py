#!/usr/bin/env python3
"""Serve server/packs at /packs/ over plain HTTP.

The shared mux forwards a request path unchanged, so a client asking for
/packs/pack-a.zip reaches this process with that same path.  Serving
server/packs with ``python -m http.server`` would then look for
server/packs/packs/pack-a.zip.  This handler removes the URL prefix before
the standard static handler runs, and answers 404 for every other path.

No secrets live under server/packs; the directory is public, regenerable
content and is excluded from the server snapshots.
"""

from __future__ import annotations

import argparse
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class PrefixedHandler(SimpleHTTPRequestHandler):
    prefix = "/packs/"

    # Stay on HTTP/1.0 so every download is one connection. The mux matches
    # "GET <prefix>" at offset 0 of a fresh connection; a kept-alive second
    # request starts later in the stream and would fall through to Geyser.
    protocol_version = "HTTP/1.0"

    def _strip_prefix(self) -> bool:
        if not self.path.startswith(self.prefix):
            self.send_error(404, "Not Found")
            return False
        self.path = "/" + self.path[len(self.prefix):]
        return True

    def do_GET(self) -> None:
        if self._strip_prefix():
            super().do_GET()

    def do_HEAD(self) -> None:
        if self._strip_prefix():
            super().do_HEAD()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("PACK_PORT", "8000")),
    )
    parser.add_argument("--directory", default="server/packs")
    parser.add_argument("--prefix", default=os.environ.get("MUX_PACKS_PREFIX", "/packs/"))
    arguments = parser.parse_args()
    if not (arguments.prefix.startswith("/") and arguments.prefix.endswith("/")):
        parser.error("--prefix must start and end with '/'")

    handler = partial(
        type("Handler", (PrefixedHandler,), {"prefix": arguments.prefix}),
        directory=arguments.directory,
    )
    with ThreadingHTTPServer((arguments.bind, arguments.port), handler) as server:
        print(
            f"serving {arguments.directory} at "
            f"http://{arguments.bind}:{arguments.port}{arguments.prefix}",
            flush=True,
        )
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
