"""The smoke harness must not report its own probe resets as failures.

`tests/smoke_frpc_shared_tcp_tls.py` needs a real HAProxy, so it only runs on
the host. Its fake signalling backend does not: these cases load the module
straight from its path, start the same `CountingServer` on a free loopback
port, and check that a client which resets mid-read is passed over in silence
while every other exception still reaches socketserver's default traceback.
"""

from contextlib import redirect_stderr
import importlib.util
import io
from pathlib import Path
import socket
import struct
import threading
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tests" / "smoke_frpc_shared_tcp_tls.py"
SPEC = importlib.util.spec_from_file_location("smoke_frpc_shared_tcp_tls", SCRIPT)
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)

# `struct linger` with a zero timeout: close() sends an RST instead of FIN,
# which is what the harness sees when its probes vanish mid-read.
RESET_LINGER = struct.pack("ii", 1, 0)


class ResetProbeHandler(smoke.GeyserHandler):
    """`GeyserHandler` that also says when it has taken the connection."""

    def setup(self):
        super().setup()
        # Once the socket is wrapped a reset is certain to arrive while the
        # handler sits in `readline`, not while the connection still waits in
        # the accept queue - there it would be dropped before any handler ran.
        self.server.live.set()


class ProbeServer(smoke.CountingServer):
    """`CountingServer` with the two moments a test needs to wait for.

    Only `handle_error` is under test, and that is inherited unchanged; the
    hooks exist so the waiting is event-driven, with neither a fixed sleep nor
    the private thread list `ThreadingMixIn` keeps.
    """

    def __init__(self, address, handler):
        super().__init__(address, handler)
        self.live = threading.Event()
        self.finished = threading.Event()

    def shutdown_request(self, request):
        try:
            super().shutdown_request(request)
        finally:
            # socketserver calls handle_error first, then this, so a traceback
            # it decided to print is already in the buffer when this fires.
            self.finished.set()


class HarnessNoiseTests(unittest.TestCase):
    def setUp(self):
        self.server = ProbeServer(("127.0.0.1", 0), ResetProbeHandler)
        self.addCleanup(self.stop)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def assert_event(self, event, description, timeout=5.0):
        if not event.wait(timeout):
            self.fail(f"timed out waiting for {description}")

    def reset_connection(self):
        """Open the port, wait for the handler, then break it with an RST."""
        with socket.create_connection(("127.0.0.1", self.port), 5) as connection:
            self.assert_event(self.server.live, "the handler to start")
            connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, RESET_LINGER)
        self.assert_event(self.server.finished, "the handler to return")

    def test_a_client_reset_is_swallowed(self):
        noise = io.StringIO()
        with redirect_stderr(noise):
            self.reset_connection()
        message = noise.getvalue()
        self.assertNotIn("Traceback", message)
        self.assertNotIn("Exception occurred", message)

    def test_only_connection_errors_are_swallowed(self):
        """A ValueError is the control: it must still print its traceback."""
        noise = io.StringIO()
        with redirect_stderr(noise):
            with socket.socket() as request:
                try:
                    raise ValueError("not a connection reset")
                except ValueError:
                    self.server.handle_error(request, ("127.0.0.1", 0))
        message = noise.getvalue()
        self.assertIn("Exception occurred", message)
        self.assertIn("ValueError: not a connection reset", message)

    def test_a_broken_pipe_is_swallowed_too(self):
        noise = io.StringIO()
        with redirect_stderr(noise):
            with socket.socket() as request:
                try:
                    raise BrokenPipeError("the peer went away")
                except BrokenPipeError:
                    self.server.handle_error(request, ("127.0.0.1", 0))
        self.assertEqual("", noise.getvalue())


if __name__ == "__main__":
    unittest.main()
