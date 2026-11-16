"""Classifiers of the public-entry probe, tested against local fakes.

The probe itself measures a live node, but its judgement does not have to
be taken on faith: everything here runs against loopback servers in an
isolated temporary space. TLS judgement is left to the Linux smoke test,
because a self-signed certificate needs an issuer (`openssl`) that the
development machine is not required to have.
"""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import socket
import socketserver
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "probe_public_entry.py"
SPEC = importlib.util.spec_from_file_location("probe_public_entry", SCRIPT)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)

# Shape of the datacenter page: HTML, "Server: Apache", and the markers the
# checker keys on. Kept ASCII here; the real page is a Chinese 404.
EDGE_PAGE = (
    b"<!DOCTYPE html><html><head><title>sorry</title></head>"
    b"<body><h1>whitelist required</h1>"
    b"<img src='http://www.example.com/sorry.png'>0632idc.com</body></html>"
)
JAVA_REPLY = b"\xff" + "1.20.4".encode("utf-16-be") + b"\x00\x00"
PLAIN_HTTP = b"HTTP/1.1 200 OK\r\nServer: Geyser\r\nContent-Length: 2\r\n\r\nok"
# What the header has to be for the family the probe sends, spelled out so
# the test does not just echo the implementation's own constants.
PROXY_SIGNATURE = b"\r\n\r\n\x00\r\nQUIT\n"


class FakeJava(socketserver.BaseRequestHandler):
    def handle(self):
        # A Minecraft server answers a legacy ping with 0xFF plus a UTF-16
        # string. Anything else here is a client that is not asking.
        self.request.recv(64)
        self.request.sendall(JAVA_REPLY)


def read_proxy_v2(connection):
    """Read one PROXY v2 header and return the payload address block."""
    header = b""
    while len(header) < 16:
        chunk = connection.recv(16 - len(header))
        if not chunk:
            raise ConnectionError("the connection closed inside the PROXY header")
        header += chunk
    length = int.from_bytes(header[14:16], "big")
    addresses = b""
    while len(addresses) < length:
        chunk = connection.recv(length - len(addresses))
        if not chunk:
            raise ConnectionError("the connection closed inside the PROXY header")
        addresses += chunk
    return addresses


class FakeProxiedJava(socketserver.BaseRequestHandler):
    """A Java backend behind a mux that sends PROXY v2 (the real chain)."""

    def handle(self):
        read_proxy_v2(self.request)
        self.request.recv(64)
        self.request.sendall(JAVA_REPLY)


class FakeEdgePage(BaseHTTPRequestHandler):
    server_version = "Apache"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.send_response(404)
        self.send_header("Content-Type", "text/html;charset=UTF-8")
        self.send_header("Content-Length", str(len(EDGE_PAGE)))
        self.end_headers()
        self.wfile.write(EDGE_PAGE)

    def log_message(self, *args):
        pass


class FakeGeyser(BaseHTTPRequestHandler):
    server_version = "Geyser"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


class FakeServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class ProbePublicEntryTests(unittest.TestCase):
    def serve(self, handler):
        server = FakeServer(("127.0.0.1", 0), handler)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server.server_address[1]

    def closed_port(self):
        server = socketserver.TCPServer(("127.0.0.1", 0), None)
        port = server.server_address[1]
        server.server_close()
        return port

    def run_probe(self, *arguments):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = probe.main(["--host", "127.0.0.1", "--timeout", "3", *arguments])
        return code, output.getvalue(), errors.getvalue()

    def test_a_minecraft_answer_passes(self):
        port = self.serve(FakeJava)
        code, output, errors = self.run_probe("--port", str(port))
        self.assertEqual(0, code, output)
        self.assertIn("java     JAVA", output)
        self.assertIn("reached a Minecraft server", output)
        self.assertEqual("", errors)

    def test_the_datacenter_page_fails_and_is_named(self):
        port = self.serve(FakeEdgePage)
        code, output, errors = self.run_probe("--port", str(port))
        self.assertEqual(1, code, output)
        self.assertIn("http     EDGE", output)
        self.assertIn("HTTP over this port:  intercepted at the edge", output)
        self.assertIn("with or without a certificate", output)
        self.assertEqual("", errors)

    def test_a_signalling_answer_is_not_mistaken_for_the_edge(self):
        port = self.serve(FakeGeyser)
        code, output, errors = self.run_probe("--port", str(port))
        self.assertEqual(1, code, output)
        self.assertIn("http     HTTP", output)
        self.assertIn("HTTP/1.1 200 OK", output)
        self.assertNotIn("EDGE", output)
        self.assertEqual("", errors)

    def test_the_local_control_block_separates_the_two_halves(self):
        public = self.serve(FakeEdgePage)
        mux = self.serve(FakeJava)
        code, output, errors = self.run_probe(
            "--port", str(public), "--local-mux", f"127.0.0.1:{mux}",
        )
        self.assertEqual(1, code, output)
        self.assertIn("local mux 127.0.0.1:", output)
        self.assertEqual(1, output.split("local mux")[1].count("JAVA"), output)
        self.assertNotIn("PROXY", output)
        self.assertEqual("", errors)

    def test_proxy_protocol_prefixes_the_local_mux_connections(self):
        public = self.serve(FakeEdgePage)
        mux = self.serve(FakeProxiedJava)

        code, output, errors = self.run_probe(
            "--port", str(public), "--local-mux", f"127.0.0.1:{mux}",
            "--proxy-protocol",
        )

        self.assertEqual(1, code, output)
        self.assertIn(f"local mux 127.0.0.1:{mux} (PROXY protocol v2)", output)
        self.assertEqual(1, output.split("local mux")[1].count("JAVA"), output)
        self.assertEqual("", errors)

    def test_the_header_is_a_well_formed_proxy_v2_header(self):
        self.assertEqual(
            PROXY_SIGNATURE
            + b"\x21"  # version 2, PROXY command
            + b"\x11"  # AF_INET, STREAM
            + b"\x00\x0c"  # 12 bytes of addresses
            + b"\xcb\x00\x71\x07"  # 203.0.113.7 - the source the probe names
            + b"\x7f\x00\x00\x01"  # 127.0.0.1 - the target it is going to
            + b"\x9f\x49"  # 40777 - the source port
            + b"\x63\xdd",  # 25565 - the destination port
            probe.proxy_v2_header(("203.0.113.7", 40777), ("127.0.0.1", 25565)),
        )

    def test_a_closed_port_reports_the_failure_without_a_traceback(self):
        code, output, errors = self.run_probe("--port", str(self.closed_port()))
        self.assertEqual(1, code, output)
        self.assertIn("connect  FAILED", output)
        self.assertNotIn("Traceback", output + errors)

    def test_exit_two_on_bad_usage(self):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--port", "1"],
            capture_output=True, text=True,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("usage", result.stderr.lower())

    def test_edge_page_markers_are_required(self):
        self.assertTrue(probe.looks_like_edge_page(EDGE_PAGE))
        self.assertTrue(probe.looks_like_edge_page(b"0632idc.com"))
        self.assertFalse(probe.looks_like_edge_page(b"<html><title>hi</title></html>"))
        self.assertFalse(probe.looks_like_edge_page(PLAIN_HTTP))

    def test_fake_ip_range_is_reported(self):
        self.assertTrue(probe.fake_ip(["198.18.92.16"]))
        self.assertTrue(probe.fake_ip(["198.19.0.1", "203.0.113.7"]))
        self.assertFalse(probe.fake_ip(["203.0.113.7"]))
        self.assertFalse(probe.fake_ip(["unresolved: nothing"]))

    def test_describe_java(self):
        self.assertEqual("JAVA", probe.describe_java(JAVA_REPLY)[0])
        self.assertEqual("EDGE", probe.describe_java(b"<html>nope</html>")[0])
        self.assertEqual("NO DATA", probe.describe_java(b"")[0])
        self.assertEqual("OTHER", probe.describe_java(b"\x02\x03")[0])

    def test_request_over_reads_a_whole_answer(self):
        # The TLS path reuses this helper, so its reading loop is covered
        # here rather than behind a certificate the test machine may lack.
        port = self.serve(FakeJava)
        with socket.create_connection(("127.0.0.1", port), 3) as connection:
            connection.settimeout(3)
            self.assertEqual(JAVA_REPLY, probe.request_over(connection, probe.JAVA_PING))

    def test_describe_http(self):
        self.assertEqual("EDGE", probe.describe_http(EDGE_PAGE)[0])
        self.assertEqual("HTTP", probe.describe_http(PLAIN_HTTP)[0])
        self.assertEqual("NO DATA", probe.describe_http(b"")[0])
        self.assertEqual("OTHER", probe.describe_http(b"\x01\x02")[0])


if __name__ == "__main__":
    unittest.main()
