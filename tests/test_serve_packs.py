"""The pack server has to answer under /packs/, not at the root."""

import http.client
import functools
import subprocess
import sys
import threading
import unittest
from pathlib import Path

from scripts import serve_packs
from tests import scratch


ROOT = Path(__file__).resolve().parents[1]


class PrefixedServerTests(unittest.TestCase):
    def setUp(self):
        self.root = self.enterContext(scratch.directory("serve-packs-")) / "packs"
        self.root.mkdir()
        (self.root / "pack-a.zip").write_bytes(b"PK\x03\x04payload")
        (self.root.parent / "secret.txt").write_text("no", encoding="utf-8")

        handler = type("Handler", (serve_packs.PrefixedHandler,), {"prefix": "/packs/"})
        self.server = serve_packs.ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(handler, directory=str(self.root)),
        )
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, path):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(connection.close)
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.read()

    def test_the_prefix_is_stripped_before_the_file_lookup(self):
        status, body = self.request("/packs/pack-a.zip")
        self.assertEqual(200, status)
        self.assertEqual(b"PK\x03\x04payload", body)

    def test_the_root_is_not_served(self):
        status, _ = self.request("/pack-a.zip")
        self.assertEqual(404, status)

    def test_the_prefix_itself_lists_the_pack_directory(self):
        status, body = self.request("/packs/")
        self.assertEqual(200, status)
        self.assertIn(b"pack-a.zip", body)

    def test_parent_segments_cannot_leave_the_pack_directory(self):
        status, body = self.request("/packs/../secret.txt")
        self.assertEqual(404, status)
        self.assertNotEqual(b"no", body)

    def test_head_uses_the_same_rule(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(connection.close)
        connection.request("HEAD", "/packs/pack-a.zip")
        response = connection.getresponse()
        self.assertEqual(200, response.status)
        response.read()

    def test_a_malformed_prefix_is_refused_at_startup(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "serve_packs.py"),
             "--prefix", "packs/", "--port", "0"],
            capture_output=True, text=True,
        )

        self.assertEqual(2, result.returncode)
        self.assertIn("must start and end with '/'", result.stderr)


if __name__ == "__main__":
    unittest.main()
