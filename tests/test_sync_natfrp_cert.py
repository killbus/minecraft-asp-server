"""The provider-certificate sync, against a stand-in API instead of NATFRP.

What the script talks to is a live account, a live node and a real issued
certificate, which no fixture can stand in for; the operator runs it. What
is checked here is everything that decides whether the file on disk ends up
right: which name the token owns, when a renewal is asked for, when a
download is skipped, what happens when the pair does not match or covers
another name, and when the reload command runs.

Certificates are made with openssl, so the pair checks run for real; the
tests that need one are skipped on a machine without openssl.
"""

from contextlib import redirect_stderr, redirect_stdout
import http.server
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.parse


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync_natfrp_cert.py"
SPEC = importlib.util.spec_from_file_location("sync_natfrp_cert", SCRIPT)
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)

SH = shutil.which("sh")


def openssl_works():
    command = sync.openssl()
    if not command:
        return False
    probe = subprocess.run(command + ["version"], capture_output=True, text=True, check=False)
    return probe.returncode == 0


OPENSSL = openssl_works()
_PAIRS = {}


def pair_for(name):
    """A throwaway self-signed pair for one name, made once per test run."""
    if name in _PAIRS:
        return _PAIRS[name]
    directory = tempfile.mkdtemp(prefix="asp-cert-fixture-")
    work = Path(directory)
    certificate = work / "cert.pem"
    key = work / "key.pem"
    config = work / "openssl.cnf"
    config.write_text(
        "[req]\n"
        "distinguished_name = dn\n"
        "prompt = no\n"
        "x509_extensions = v3\n"
        "[dn]\n"
        f"CN = {name}\n"
        "[v3]\n"
        f"subjectAltName = DNS:{name}\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        sync.openssl() + [
            "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
            "-config", str(config), "-keyout", str(key), "-out", str(certificate),
        ],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"openssl could not make a test pair: {result.stderr.strip()}")
    _PAIRS[name] = (certificate.read_text(encoding="utf-8"), key.read_text(encoding="utf-8"))
    return _PAIRS[name]


class StubApi:
    """A stand-in for api.natfrp.com/v4 that records what it was asked for."""

    def __init__(self, **state):
        self.account = state.get("account", "r00000000.nyat.app")
        self.records = state.get("records", [("1-mc", 29789033), ("2-mc", 29789034)])
        self.created = state.get("created", 1764000000)
        self.expires = state.get("expires", 1770000000)
        self.issued = state.get("issued", True)
        self.token = state.get("token", "secret")
        self.certificate = state.get("certificate", "")
        self.key = state.get("key", "")
        self.error_page = state.get("error_page", "")
        self.reissue_after_polls = state.get("reissue_after_polls", 0)
        self.calls = []
        self.agents = []
        self.downloads = 0
        self.renewals = 0
        self._polls = 0
        self._lock = threading.Lock()
        stub = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *arguments):
                pass

            def answer(self, code, payload):
                body = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def answer_text(self, code, text, content_type):
                body = text.encode()
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def authorized(self):
                if self.headers.get("Authorization") == f"Bearer {stub.token}":
                    return True
                if stub.error_page:
                    self.answer_text(403, stub.error_page, "text/html")
                else:
                    # The one error shape the API documents: a 500 whose body
                    # carries the real code (`components/responses/ErrorResponse`
                    # in api.natfrp.com/docs/openapi.yaml).
                    self.answer(500, {"code": 403, "msg": "无权访问"})
                return False

            def do_GET(self):
                path, _, query = self.path.partition("?")
                stub.calls.append(("GET", path, query))
                stub.agents.append(self.headers.get("User-Agent"))
                if not self.authorized():
                    return
                if path.endswith("/domain/get"):
                    self.answer(200, stub.domain_document())
                elif path.endswith("/domain/cert"):
                    if "created" not in urllib.parse.parse_qs(query):
                        self.answer(500, {"code": 400, "msg": "created is required"})
                        return
                    stub.downloads += 1
                    self.answer(200, {"key": stub.key, "cert": stub.certificate})
                else:
                    self.answer(500, {"code": 404, "msg": "no such endpoint"})

            def do_POST(self):
                path, _, _query = self.path.partition("?")
                length = int(self.headers.get("Content-Length") or 0)
                stub.calls.append(("POST", path, self.rfile.read(length).decode()))
                if not self.authorized():
                    return
                if path.endswith("/domain/cert"):
                    stub.renewals += 1
                    stub.arm_reissue()
                    self.answer(200, "续签请求已提交")
                else:
                    self.answer(500, {"code": 404, "msg": "no such endpoint"})

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base(self):
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}/v4"

    def domain_document(self):
        with self._lock:
            self._polls += 1
            if self.reissue_after_polls and self._polls >= self.reissue_after_polls:
                self.created += 3600
                self.reissue_after_polls = 0
        document = {
            "domain": self.account,
            "records": [{"rr": rr, "type": "CNAME", "tunnel": tunnel} for rr, tunnel in self.records],
        }
        if self.issued:
            document["ssl"] = {"created": self.created, "expires": self.expires}
        return document

    def arm_reissue(self):
        """A renewal that has to be requested before a new certificate exists."""
        with self._lock:
            self.reissue_after_polls = max(1, self.reissue_after_polls)

    def renew_immediately(self):
        with self._lock:
            self.created += 3600

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def endpoints(self):
        return [(method, path) for method, path, _ in self.calls]


class SyncNatfrpCertTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.out = self.base / "tls" / "1-mc.r00000000.nyat.app.pem"
        self.marker = self.base / "reloaded.txt"
        self.api = StubApi()
        self.addCleanup(self.api.stop)

    def run_sync(self, *arguments, token="secret"):
        output, errors = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"NATFRP_TOKEN": token} if token else {"NATFRP_TOKEN": ""}):
            with redirect_stdout(output), redirect_stderr(errors):
                try:
                    code = sync.main(list(arguments))
                except SystemExit as exit_request:  # argparse reports usage this way
                    code = exit_request.code
        return code, output.getvalue(), errors.getvalue()

    def arguments(self, *extra):
        return [
            "--domain", "1-mc.r00000000.nyat.app",
            "--out", str(self.out),
            "--api", self.api.base,
            "--timeout", "5",
            "--poll-interval", "0.05",
            "--issue-timeout", "5",
            *extra,
        ]

    def with_pair(self, name="1-mc.r00000000.nyat.app"):
        certificate, key = pair_for(name)
        self.api.certificate = certificate
        self.api.key = key
        return certificate, key

    def sidecar(self):
        return Path(str(self.out) + ".created")

    def reload_command(self):
        return f'echo reloaded >> "{self.marker}"'

    # Everything below needs no certificate.

    def test_a_name_the_account_does_not_own_is_refused(self):
        self.api.records = [("2-mc", 29789034)]
        code, output, _ = self.run_sync(*self.arguments())
        self.assertEqual(1, code, output)
        self.assertIn("is not a record of the account", output)
        self.assertIn("2-mc.r00000000.nyat.app", output, "the account's names are listed")
        self.assertNotIn("download", output)

    def test_an_account_without_a_certificate_says_how_to_get_one(self):
        self.api.issued = False
        code, output, _ = self.run_sync(*self.arguments())
        self.assertEqual(1, code, output)
        self.assertIn("no certificate yet", output)
        self.assertIn("auto_https", output)
        self.assertEqual([], self.api.endpoints()[1:], "no call after the first one")

    def test_a_wrong_api_key_is_reported_without_a_traceback(self):
        code, output, _ = self.run_sync(*self.arguments(), token="wrong")
        self.assertEqual(1, code, output)
        self.assertIn("API code 403", output)
        self.assertIn("无权访问", output, "the provider's own message is shown, not a guess")
        self.assertNotIn("Traceback", output)

    def test_a_403_that_is_a_page_is_quoted_rather_than_lost(self):
        """A gateway in front of the API answers with HTML, not with `msg`."""
        self.api.error_page = (
            "<html><head><title>403 Forbidden</title></head>"
            "<body>request denied by the front proxy</body></html>"
        )

        code, output, _ = self.run_sync(*self.arguments(), token="wrong")

        self.assertEqual(1, code, output)
        self.assertIn("HTTP 403", output)
        self.assertIn("403 Forbidden", output)
        self.assertNotIn("Traceback", output)

    def test_a_missing_api_key_is_a_usage_error(self):
        code, output, _ = self.run_sync(*self.arguments(), token="")
        self.assertEqual(1, code, output)
        self.assertIn("no API key", output)
        self.assertIn(sync.TOKEN_ENV, output)
        self.assertEqual([], self.api.calls)

    def test_every_call_says_which_client_it_is(self):
        """The provider's edge answers 403 'error code: 1010' to some
        signatures before the API sees the request, so the default one is not
        good enough."""
        self.api.records = [("2-mc", 29789034)]

        code, output, _ = self.run_sync(*self.arguments())

        self.assertEqual(1, code, output)
        self.assertTrue(self.api.agents, "the test did make a call")
        self.assertEqual({sync.USER_AGENT}, set(self.api.agents))
        self.assertNotIn("urllib", sync.USER_AGENT.lower())

    def test_usage_errors_do_not_start_a_session(self):
        code, output, errors = self.run_sync("--out", str(self.out))
        self.assertEqual(2, code, output + errors)
        self.assertIn("usage", (output + errors).lower())

    def test_the_pure_helpers(self):
        self.assertTrue(sync.covers("1-mc.r00000000.nyat.app", "*.r00000000.nyat.app"))
        self.assertTrue(sync.covers("r00000000.nyat.app", "r00000000.nyat.app"))
        self.assertFalse(sync.covers("a.b.r00000000.nyat.app", "*.r00000000.nyat.app"))
        self.assertFalse(sync.covers("1-mc.r00000000.nyat.app", "*.r00000001.nyat.app"))
        now = 1000 * sync.DAY
        self.assertTrue(sync.needs_renewal(int(now + 2 * sync.DAY), now, 7))
        self.assertFalse(sync.needs_renewal(int(now + 30 * sync.DAY), now, 7))
        self.assertFalse(sync.needs_renewal(0, now, 7), "a certificate still being issued is not renewed")
        self.assertIn("expired", sync.describe_expiry(int(now - 2 * sync.DAY), now))
        self.assertIn("in 30 days", sync.describe_expiry(int(now + 30 * sync.DAY), now))

    def test_a_written_private_key_never_becomes_world_readable(self):
        """The PEM holds a private key, so the umask must not decide its mode."""
        previous = os.umask(0o000)
        try:
            sync.replace_file(str(self.out), "-----BEGIN PRIVATE KEY-----\nsecret\n")
        finally:
            os.umask(previous)

        self.assertEqual("-----BEGIN PRIVATE KEY-----\nsecret\n", self.out.read_text(encoding="utf-8"))
        self.assertEqual(
            [], list(self.out.parent.glob(f"{self.out.name}.tmp.*")),
            "the temporary file is renamed, not left behind",
        )
        if os.name == "posix":
            self.assertEqual(0o600, os.stat(self.out).st_mode & 0o777)

    @unittest.skipUnless(OPENSSL, "openssl is not available")
    def test_a_file_name_that_does_not_name_the_domain_is_noted(self):
        """A bare subdomain in a shared directory does not identify a file."""
        self.with_pair()
        self.api.expires = int(time.time() + 60 * sync.DAY)
        self.out = self.base / "tls" / "1-mc.pem"

        code, output, errors = self.run_sync(*self.arguments())

        self.assertEqual(0, code, output + errors)
        self.assertIn("does not name 1-mc.r00000000.nyat.app", errors)
        self.assertIn("1-mc.r00000000.nyat.app.pem", errors, "the note says what to call it")
        self.assertTrue(self.out.is_file(), "a note is not a refusal")

    @unittest.skipUnless(OPENSSL, "openssl is not available")
    def test_a_file_name_that_names_the_domain_is_not_noted(self):
        self.with_pair()
        self.api.expires = int(time.time() + 60 * sync.DAY)

        code, output, errors = self.run_sync(*self.arguments())

        self.assertEqual(0, code, output + errors)
        self.assertEqual("", errors.strip(), errors)

    # Everything below writes a certificate and needs openssl.

    @unittest.skipUnless(OPENSSL, "openssl is not available")
    def test_the_pair_is_written_and_the_reload_runs(self):
        certificate, key = self.with_pair()
        self.api.expires = int(time.time() + 60 * sync.DAY)

        code, output, _ = self.run_sync(*self.arguments("--reload-command", self.reload_command()))

        self.assertEqual(0, code, output)
        self.assertEqual(certificate.strip() + "\n" + key.strip() + "\n", self.out.read_text(encoding="utf-8"))
        self.assertEqual(str(self.api.created), self.sidecar().read_text(encoding="utf-8").strip())
        self.assertTrue(self.marker.is_file(), "the reload command ran")
        self.assertEqual(1, self.api.downloads)
        self.assertIn("pair     the certificate and the private key match", output)
        self.assertIn("1-mc.r00000000.nyat.app", output)

    @unittest.skipUnless(OPENSSL, "openssl is not available")
    def test_an_unchanged_certificate_is_not_downloaded_again(self):
        certificate, key = self.with_pair()
        self.api.expires = int(time.time() + 60 * sync.DAY)
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.out.write_text(certificate + "\n" + key + "\n", encoding="utf-8")
        self.sidecar().write_text(str(self.api.created), encoding="utf-8")

        code, output, _ = self.run_sync(*self.arguments("--reload-command", self.reload_command()))

        self.assertEqual(0, code, output)
        self.assertEqual(0, self.api.downloads, "the API asks callers not to download repeatedly")
        self.assertFalse(self.marker.exists(), "an unchanged file is not reloaded")
        self.assertIn("action   none", output)

    @unittest.skipUnless(OPENSSL, "openssl is not available")
    def test_a_certificate_inside_the_window_is_renewed_first(self):
        self.with_pair()
        self.api.expires = int(time.time() + 2 * sync.DAY)
        self.api.reissue_after_polls = 2

        code, output, _ = self.run_sync(*self.arguments())

        self.assertEqual(0, code, output)
        self.assertEqual(1, self.api.renewals, "one renewal request")
        self.assertIn("renew    reissued", output)
        self.assertEqual(1, self.api.downloads)
        self.assertEqual(str(self.api.created), self.sidecar().read_text(encoding="utf-8").strip())

    @unittest.skipUnless(OPENSSL, "openssl is not available")
    def test_a_forced_download_happens_when_the_file_is_missing(self):
        self.with_pair()
        self.api.expires = int(time.time() + 60 * sync.DAY)

        code, output, _ = self.run_sync(*self.arguments())

        self.assertEqual(0, code, output)
        self.assertTrue(self.out.is_file(), "the directory was created for the file")
        self.assertIn("reload   not requested", output)

    @unittest.skipUnless(OPENSSL, "openssl is not available")
    def test_a_key_that_does_not_match_is_refused(self):
        certificate, _ = self.with_pair()
        _, other_key = pair_for("other.r00000000.nyat.app")
        self.api.key = other_key
        self.api.expires = int(time.time() + 60 * sync.DAY)
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.out.write_text("the file that was there before\n", encoding="utf-8")

        code, output, _ = self.run_sync(*self.arguments("--reload-command", self.reload_command()))

        self.assertEqual(1, code, output)
        self.assertIn("do not belong together", output)
        self.assertEqual("the file that was there before\n", self.out.read_text(encoding="utf-8"))
        self.assertFalse(self.marker.exists(), "a refused pair is not reloaded into anything")
        self.assertEqual(certificate, self.api.certificate, "the API answered with the certificate it was given")

    @unittest.skipUnless(OPENSSL, "openssl is not available")
    def test_a_certificate_for_another_name_is_refused(self):
        self.with_pair("someone-else.nyat.app")
        self.api.expires = int(time.time() + 60 * sync.DAY)

        code, output, _ = self.run_sync(*self.arguments())

        self.assertEqual(1, code, output)
        self.assertIn("covers someone-else.nyat.app and not 1-mc.r00000000.nyat.app", output)
        self.assertFalse(self.out.exists())

    @unittest.skipUnless(OPENSSL, "openssl is not available")
    def test_a_dry_run_writes_nothing(self):
        self.with_pair()
        self.api.expires = int(time.time() + 60 * sync.DAY)

        code, output, _ = self.run_sync(*self.arguments("--dry-run", "--reload-command", self.reload_command()))

        self.assertEqual(0, code, output)
        self.assertIn("would    write", output)
        self.assertFalse(self.out.exists())
        self.assertFalse(self.marker.exists())
        self.assertEqual(1, self.api.downloads, "a dry run still proves the download works")


if __name__ == "__main__":
    unittest.main()
