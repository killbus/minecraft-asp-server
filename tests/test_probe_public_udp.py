"""Unit tests for the UDP PROXY-protocol probe.

The live frp tunnel is an operator observation, not a test dependency. These
tests cover the header decoder and a real loopback UDP exchange.
"""

import importlib.util
from pathlib import Path
import socket
import struct
import subprocess
import sys
import threading
import time
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "probe_public_udp.py"
SPEC = importlib.util.spec_from_file_location("probe_public_udp", SCRIPT)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)

PROXY_V2_SIGNATURE = b"\r\n\r\n\x00\r\nQUIT\n"


def ipv4_header(command=0x21, protocol=0x12):
    addresses = (
        socket.inet_aton("203.0.113.7")
        + socket.inet_aton("198.51.100.9")
        + struct.pack("!HH", 40777, 34003)
    )
    return (
        PROXY_V2_SIGNATURE
        + bytes([command, protocol])
        + struct.pack("!H", len(addresses))
        + addresses
    )


class ParseProxyV2Tests(unittest.TestCase):
    def test_a_plain_udp_payload_has_no_header(self):
        parsed = probe.parse_proxy_v2(b"asp-udp-probe")
        self.assertEqual("none", parsed["kind"])
        self.assertEqual(b"asp-udp-probe", parsed["payload"])

    def test_an_ipv4_datagram_header_supplies_the_request_endpoint(self):
        parsed = probe.parse_proxy_v2(ipv4_header() + b"hello")
        self.assertEqual("header", parsed["kind"])
        self.assertEqual("PROXY", parsed["command"])
        self.assertEqual("IPv4", parsed["family"])
        self.assertEqual("DGRAM", parsed["protocol"])
        self.assertEqual("203.0.113.7:40777", parsed["source"])
        self.assertEqual("198.51.100.9:34003", parsed["destination"])
        self.assertEqual(b"hello", parsed["payload"])

    def test_a_truncated_header_is_named_instead_of_crashing(self):
        parsed = probe.parse_proxy_v2(ipv4_header()[:-1])
        self.assertEqual("incomplete", parsed["kind"])
        self.assertIn("only 11 arrived", parsed["detail"])

    def test_local_command_supplies_no_request_endpoint(self):
        parsed = probe.parse_proxy_v2(
            PROXY_V2_SIGNATURE + b"\x20\x00\x00\x00" + b"payload"
        )
        self.assertEqual("header", parsed["kind"])
        self.assertEqual("LOCAL", parsed["command"])
        self.assertIsNone(parsed["source"])
        self.assertEqual(b"payload", parsed["payload"])
        self.assertIn("no request-side endpoint", probe.format_verdict(parsed))

    def test_local_command_ignores_populated_address_fields(self):
        parsed = probe.parse_proxy_v2(ipv4_header(command=0x20) + b"payload")
        self.assertEqual("header", parsed["kind"])
        self.assertEqual("LOCAL", parsed["command"])
        self.assertIsNone(parsed["source"])
        self.assertIsNone(parsed["destination"])
        self.assertIn("no request-side endpoint", probe.format_verdict(parsed))

    def test_verdict_names_when_proxy_is_absent(self):
        parsed = probe.parse_proxy_v2(b"ordinary data")
        self.assertIn("no PROXY v2 header", probe.format_verdict(parsed))

    def test_endpoint_parser_accepts_ipv4_and_bracketed_ipv6(self):
        self.assertEqual(("127.0.0.1", 19132), probe.parse_endpoint("127.0.0.1:19132"))
        self.assertEqual(("::1", 19132), probe.parse_endpoint("[::1]:19132"))
        with self.assertRaises(ValueError):
            probe.parse_endpoint("::1:19132")


class LoopbackUdpTests(unittest.TestCase):
    def test_send_puts_the_payload_on_a_real_udp_socket(self):
        receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(receiver.close)
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(3)
        port = receiver.getsockname()[1]

        result = {}

        def receive():
            result["packet"], result["peer"] = receiver.recvfrom(1024)

        thread = threading.Thread(target=receive, daemon=True)
        thread.start()
        self.assertEqual(0, probe.send("127.0.0.1", port, b"probe", 1))
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(b"probe", result["packet"])
        self.assertEqual("127.0.0.1", result["peer"][0])

    def test_capture_pairs_a_header_only_datagram_with_its_payload(self):
        receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(receiver.close)
        receiver.bind(("127.0.0.1", 0))
        port = receiver.getsockname()[1]
        result = {}

        def capture():
            result["parsed"], result["peer"] = probe.capture_datagram(receiver, 3)

        thread = threading.Thread(target=capture, daemon=True)
        thread.start()
        time.sleep(0.02)
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(sender.close)
        sender.sendto(ipv4_header(), ("127.0.0.1", port))
        sender.sendto(b"following payload", ("127.0.0.1", port))
        thread.join(3)

        self.assertFalse(thread.is_alive())
        self.assertEqual("header", result["parsed"]["kind"])
        self.assertTrue(result["parsed"]["payload_separate"])
        self.assertEqual(b"following payload", result["parsed"]["payload"])

    def test_exit_two_on_bad_usage(self):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "listen", "--count", "0"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("at least 1", result.stderr)


if __name__ == "__main__":
    unittest.main()
