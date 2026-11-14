"""The ASP-free public check, tested as far as it goes without haproxy.

The happy path needs a real `haproxy` and a real tunnel and is what the
operator runs; what is checked here is the part that must not need either:
the generated configuration, the endpoint and bind handling, the marker
judgement, and the two failure modes worth naming before anything starts.
"""

from contextlib import redirect_stderr, redirect_stdout
import argparse
import importlib.util
import io
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "plain_website_check.py"
SPEC = importlib.util.spec_from_file_location("plain_website_check", SCRIPT)
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)

EDGE_PAGE = b"<html><title>sorry</title>0632idc.com/sorry.png</html>"

# Stands in for haproxy so the check can be exercised end to end on a machine
# that does not have it: it validates nothing and relays to the "server
# files" address of the configuration it was handed.
STUB_HAPROXY = '''\
import socket
import sys
import threading


def relay(source, sink):
    try:
        while True:
            data = source.recv(65536)
            if not data:
                break
            sink.sendall(data)
    except OSError:
        pass
    finally:
        for connection in (source, sink):
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()


def address(text):
    host, port = text.rsplit(":", 1)
    return host, int(port)


def main(argv):
    if "-c" in argv:
        return 0
    with open(argv[argv.index("-f") + 1], encoding="utf-8") as handle:
        lines = [line.strip() for line in handle]
    bind = next(line for line in lines if line.startswith("bind ")).split()[1]
    backend = next(line for line in lines if line.startswith("server files ")).split()[2]
    server = socket.create_server(address(bind))
    while True:
        client, _ = server.accept()
        upstream = socket.create_connection(address(backend))
        threading.Thread(target=relay, args=(client, upstream), daemon=True).start()
        threading.Thread(target=relay, args=(upstream, client), daemon=True).start()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''


def relay(source, sink):
    try:
        while True:
            data = source.recv(65536)
            if not data:
                break
            sink.sendall(data)
    except OSError:
        pass
    finally:
        for connection in (source, sink):
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()


class PlainWebsiteCheckTests(unittest.TestCase):
    def run_check(self, *arguments):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = check.main(list(arguments))
        return code, output.getvalue(), errors.getvalue()

    def empty_path(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return patch.dict(os.environ, {"PATH": directory.name})

    def free_port(self):
        return check.free_port()

    def eventually(self, predicate, timeout=8.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.1)
        return predicate()

    @staticmethod
    def connectable(port):
        try:
            with socket.create_connection(("127.0.0.1", port), 0.3):
                return True
        except OSError:
            return False

    def stub_haproxy_on_path(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        stub = Path(directory.name) / "stub.py"
        stub.write_text(STUB_HAPROXY, encoding="utf-8")
        if os.name == "nt":
            launcher = Path(directory.name) / "haproxy.cmd"
            launcher.write_text(f'@"{sys.executable}" -B "{stub}" %*\n', encoding="utf-8")
        else:
            launcher = Path(directory.name) / "haproxy"
            launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" -B "{stub}" "$@"\n', encoding="utf-8")
            launcher.chmod(0o755)
        return patch.dict(os.environ, {"PATH": directory.name})

    def mock_tunnel(self, port):
        """A stand-in for frps and frpc: a plain forwarder to a local port."""
        server = socket.create_server(("127.0.0.1", 0))
        self.addCleanup(server.close)

        def accept_loop():
            while True:
                try:
                    client, _ = server.accept()
                except OSError:
                    return
                try:
                    upstream = socket.create_connection(("127.0.0.1", port), 3)
                except OSError:
                    client.close()
                    continue
                threading.Thread(target=relay, args=(client, upstream), daemon=True).start()
                threading.Thread(target=relay, args=(upstream, client), daemon=True).start()

        threading.Thread(target=accept_loop, daemon=True).start()
        return server.getsockname()[1]

    def test_config_is_an_ordinary_reverse_proxy(self):
        config = check.haproxy_config("127.0.0.1:25566", "127.0.0.1:8080")
        self.assertIn("    mode http", config)
        self.assertIn("    bind 127.0.0.1:25566", config)
        self.assertIn("    server files 127.0.0.1:8080", config)
        self.assertIn("frontend plain_website", config)
        self.assertNotIn("ssl", config)
        self.assertNotIn("25565", config)

    def test_endpoint_parsing(self):
        self.assertEqual(("127.0.0.1", 25566), check.endpoint("127.0.0.1:25566"))
        self.assertEqual(("example.test", 443), check.endpoint("example.test:443"))
        for value in ["25566", "127.0.0.1:", ":25566", "127.0.0.1:0", "127.0.0.1:70000", "a:b"]:
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    check.endpoint(value)

    def test_marker_decides_before_anything_else(self):
        self.assertEqual("OK", check.classify(b"<html>plain-website-ok-abc</html>", "plain-website-ok-abc")[0])
        self.assertEqual("EDGE", check.classify(EDGE_PAGE, "plain-website-ok-abc")[0])
        self.assertEqual("NO DATA", check.classify(b"", "plain-website-ok-abc")[0])

    def test_helper_port_is_free_and_wait_for_port(self):
        port = self.free_port()
        self.assertTrue(check.port_is_free("127.0.0.1", port))
        self.assertFalse(check.wait_for_port("127.0.0.1", port, timeout=0.3))
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", port))
            listener.listen(1)
            self.assertFalse(check.port_is_free("127.0.0.1", port))

    def test_a_busy_listen_port_is_named_before_haproxy_is_considered(self):
        # An empty PATH would be reported as "haproxy is not on PATH", so a
        # busy port answering first pins the order of the two checks.
        port = self.free_port()
        with socket.socket() as listener, self.empty_path():
            listener.bind(("127.0.0.1", port))
            listener.listen(1)
            code, output, errors = self.run_check(
                "--host", "example.test", "--port", "40000", "--listen", f"127.0.0.1:{port}",
            )
        self.assertEqual(1, code, output)
        self.assertIn("is already in use", output)
        self.assertNotIn("haproxy is not on PATH", output)
        self.assertEqual("", errors)

    def test_missing_haproxy_fails_without_a_traceback(self):
        with self.empty_path():
            code, output, errors = self.run_check(
                "--host", "example.test", "--port", "40000",
                "--listen", f"127.0.0.1:{self.free_port()}",
            )
        self.assertEqual(1, code, output)
        self.assertIn("haproxy is not on PATH", output)
        self.assertNotIn("Traceback", output + errors)

    def test_cli_usage_exit_codes(self):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--help"], capture_output=True, text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--listen", result.stdout)
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--host", "example.test"],
            capture_output=True, text=True,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("usage", result.stderr.lower())

    def test_the_website_and_the_proxy_are_not_the_server(self):
        # A guard against the file quietly growing a dependency on the
        # deployment: it may only import the public probe, not the verifier.
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("import probe_public_entry as probe", source)
        self.assertNotIn("verify_runtime", source)
        self.assertNotIn("start.sh", source)

    def test_the_whole_check_runs_against_a_mocked_tunnel(self):
        # Nothing outside this machine: the proxy and the FrP hop are both
        # stand-ins, so the verdict, the exit code and the cleanup are
        # exercised without haproxy, frpc or the server being involved.
        listen = self.free_port()
        tunnel = self.mock_tunnel(listen)
        with self.stub_haproxy_on_path():
            code, output, errors = self.run_check(
                "--host", "127.0.0.1", "--port", str(tunnel),
                "--listen", f"127.0.0.1:{listen}", "--timeout", "3",
            )
        self.assertEqual(0, code, output)
        self.assertIn(f"local    http://127.0.0.1:{listen}/  OK (HTTP 200)", output)
        self.assertIn("marker:   PLAIN-WEBSITE-OK-", output)
        self.assertIn("OK       the page came back", output)
        self.assertIn("the public name serves this page", output)
        self.assertEqual("", errors)
        # Both throwaway servers stop listening, and the throwaway website
        # and configuration go with them. On Windows an emptied directory can
        # linger for a moment because the .cmd launcher this test writes is a
        # parent process of its own; the check reports that instead of hiding
        # it, so a log file is the only thing allowed to survive here.
        lines = output.splitlines()
        work_dir = [line for line in lines if line.startswith("work dir: ")][0].split(": ", 1)[1]
        backend = [line for line in lines if line.startswith("website: ")][0].rsplit(":", 1)[1]
        self.assertTrue(
            self.eventually(lambda: not self.connectable(listen) and not self.connectable(int(backend))),
            output,
        )
        leftovers = sorted(path.name for path in Path(work_dir).glob("*")) if Path(work_dir).exists() else []
        self.assertIn(leftovers, [[], ["haproxy.log"]], output)


if __name__ == "__main__":
    unittest.main()
