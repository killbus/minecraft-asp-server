"""The installer has to follow the lock, never the network's opinion of it."""

import contextlib
import hashlib
import http.server
import io
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

from scripts import install_runtime


PAYLOAD = b"runtime-bytes"


class FixtureHandler(http.server.BaseHTTPRequestHandler):
    files = {}
    requests = []
    user_agents = []

    def do_GET(self):
        type(self).requests.append(self.path)
        type(self).user_agents.append(self.headers.get("User-Agent"))
        body = type(self).files.get(self.path)
        if body is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *arguments):
        pass


class InstallRuntimeTests(unittest.TestCase):
    def setUp(self):
        FixtureHandler.files = {}
        FixtureHandler.requests = []
        FixtureHandler.user_agents = []
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.server_dir = self.directory / "server"
        self.server_dir.mkdir()
        self.lock = self.directory / "runtime.lock.json"

    def url(self, name="paper.jar"):
        return f"http://127.0.0.1:{self.port}/{name}"

    def write_lock(self, artifacts):
        self.lock.write_text(
            json.dumps({
                "schema_version": 1,
                "datapack_directories": [],
                "artifacts": artifacts,
            }),
            encoding="utf-8",
        )

    def artifact(self, path="paper-server.jar", kind="server", body=PAYLOAD,
                 name="paper.jar", url=True):
        entry = {
            "id": Path(path).stem,
            "kind": kind,
            "path": path,
            "version": "test",
            "source": "https://example.invalid/project",
            "sha256": hashlib.sha256(body).hexdigest(),
        }
        if url:
            entry["download_url"] = self.url(name)
        return entry

    def run_installer(self, *arguments, server_dir=None):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = install_runtime.main([
                "--lock", str(self.lock),
                "--server-dir", str(server_dir or self.server_dir),
                *arguments,
            ])
        return code, output.getvalue()

    def test_a_missing_artifact_is_downloaded_and_verified(self):
        FixtureHandler.files["/paper.jar"] = PAYLOAD
        self.write_lock([self.artifact()])

        code, output = self.run_installer()

        self.assertEqual(0, code, output)
        self.assertEqual(PAYLOAD, (self.server_dir / "paper-server.jar").read_bytes())
        self.assertEqual(["/paper.jar"], FixtureHandler.requests)
        self.assertEqual([install_runtime.USER_AGENT], FixtureHandler.user_agents)
        self.assertIn(
            "github.com/killbus/minecraft-asp-server", install_runtime.USER_AGENT,
        )

    def test_a_matching_file_is_skipped_without_a_request(self):
        (self.server_dir / "paper-server.jar").write_bytes(PAYLOAD)
        self.write_lock([self.artifact()])

        code, output = self.run_installer()

        self.assertEqual(0, code, output)
        self.assertEqual([], FixtureHandler.requests)
        self.assertIn("OK", output)

    def test_drift_is_refused_and_the_file_is_kept(self):
        destination = self.server_dir / "paper-server.jar"
        destination.write_bytes(b"old")
        self.write_lock([self.artifact()])

        code, output = self.run_installer()

        self.assertEqual(1, code, output)
        self.assertEqual(b"old", destination.read_bytes())
        self.assertEqual([], FixtureHandler.requests)
        self.assertIn("DRIFT", output)

    def test_replace_installs_over_drift(self):
        destination = self.server_dir / "paper-server.jar"
        destination.write_bytes(b"old")
        FixtureHandler.files["/paper.jar"] = PAYLOAD
        self.write_lock([self.artifact()])

        code, output = self.run_installer("--replace")

        self.assertEqual(0, code, output)
        self.assertEqual(PAYLOAD, destination.read_bytes())

    def test_bytes_that_do_not_match_the_lock_are_discarded(self):
        FixtureHandler.files["/paper.jar"] = b"tampered"
        self.write_lock([self.artifact()])

        code, output = self.run_installer()

        self.assertEqual(1, code, output)
        self.assertFalse((self.server_dir / "paper-server.jar").exists())
        self.assertEqual(
            [], [path for path in self.server_dir.iterdir() if ".part" in path.name],
        )
        self.assertIn("FAIL", output)

    def test_an_artifact_without_a_url_is_manual(self):
        (self.server_dir / "paper-server.jar").write_bytes(PAYLOAD)
        self.write_lock([
            self.artifact(),
            self.artifact(path="plugins/Thing.jar", kind="plugin", url=False),
        ])

        code, output = self.run_installer()

        self.assertEqual(1, code, output)
        self.assertIn("MANUAL", output)
        self.assertIn("https://example.invalid/project", output)

    def test_dry_run_plans_without_requests_or_writes(self):
        FixtureHandler.files["/paper.jar"] = PAYLOAD
        self.write_lock([self.artifact()])

        code, output = self.run_installer("--dry-run")

        self.assertEqual(1, code, output)
        self.assertIn("INSTALL", output)
        self.assertEqual([], FixtureHandler.requests)
        self.assertFalse((self.server_dir / "paper-server.jar").exists())

    def test_an_unsafe_lock_path_exits_2(self):
        artifact = self.artifact()
        artifact["path"] = "../paper-server.jar"
        self.write_lock([artifact])

        code, output = self.run_installer()

        self.assertEqual(2, code, output)

    def test_a_relative_server_dir_is_resolved_before_the_path_check(self):
        FixtureHandler.files["/paper.jar"] = PAYLOAD
        self.write_lock([self.artifact()])
        previous = os.getcwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(self.directory)

        code, output = self.run_installer(server_dir="server")

        self.assertEqual(0, code, output)
        self.assertEqual(PAYLOAD, (self.server_dir / "paper-server.jar").read_bytes())

    def test_only_restricts_the_selection(self):
        FixtureHandler.files["/paper.jar"] = PAYLOAD
        other = self.artifact(path="plugins/Other.jar", kind="plugin",
                              body=b"other", name="other.jar")
        self.write_lock([self.artifact(), other])

        code, output = self.run_installer("--only", "paper-server")

        self.assertEqual(0, code, output)
        self.assertEqual(["/paper.jar"], FixtureHandler.requests)
        self.assertFalse((self.server_dir / "plugins" / "Other.jar").exists())

    def test_an_unknown_only_id_is_refused(self):
        self.write_lock([self.artifact()])

        code, output = self.run_installer("--only", "nope")

        self.assertEqual(2, code, output)


if __name__ == "__main__":
    unittest.main()
