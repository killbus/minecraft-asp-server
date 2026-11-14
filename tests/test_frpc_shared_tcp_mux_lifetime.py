"""The mux outlives the tmux session, so it needs a lifetime of its own.

HAProxy's master ignores the SIGHUP that tearing a session down sends it:
its reload signal is SIGUSR2 and its stop signal is SIGTERM. A scene that
left the mux to tmux would strand it on the listen port, with no window left
to show it and a pidfile the next caller could not trust. So `down` stops it
by that pidfile, `up` refuses to start a second master over a live one or an
occupied listen port, and `status` reads the same pidfile, which is what
makes the process that outlived its session visible instead of orphaned.

Signalling is replaced with a recorder that writes down its arguments, and
the tmux side with a stand-in that reports no session: what is under test is
which process the scene decides to stop, and what it says about it. Deciding
that needs a process table (`/proc`, or a `ps` that takes `-o comm=`), which
the scene's own platform has and a Windows development box does not: the
tests that identify a running process are skipped there, and the ones that
only read a pidfile run everywhere.
"""

import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / "scripts" / "scenes" / "frpc-shared-tcp.sh"
SH = shutil.which("sh")
SLEEP = shutil.which("sleep")
LINUX = sys.platform.startswith("linux")
# Above every pid_max a Linux kernel offers, so nothing can own it.
NO_SUCH_PID = "2147483647"


def listening_socket_tool():
    """Is the tool the scene reads a listen port with available and working?"""
    for tool in (["ss", "-ltn"], ["netstat", "-ltn"]):
        if shutil.which(tool[0]) is None:
            continue
        try:
            if subprocess.run(tool, capture_output=True).returncode == 0:
                return True
        except OSError:
            continue
    return False


HAVE_LISTEN_TOOL = listening_socket_tool()


@unittest.skipIf(SH is None, "POSIX sh is not available")
class MuxLifetimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        # A relative pidfile: the scene resolves it against the caller's
        # directory, which is this repository root.
        self.pidfile = Path(".tmp") / f"lifetime-test-{os.getpid()}" / "haproxy.pid"
        self.absolute_pidfile = ROOT / self.pidfile
        self.addCleanup(shutil.rmtree, self.absolute_pidfile.parent, True)
        self.signals = self.directory / "signals.txt"
        self.recorder = self.record_signal()
        self.stubs = self.stub_tmux()
        self.configs = self.directory / "configs"
        self.configs.mkdir()
        (self.configs / "frpc.toml").write_text(
            "serverAddr = 'example.org'\n", encoding="utf-8"
        )
        self.haproxy_config = self.directory / "haproxy.cfg"
        self.processes = []
        self.addCleanup(self.stop_processes)

    def record_signal(self):
        """A stand-in for the signal command that writes down its arguments."""
        path = self.directory / "record-signal.sh"
        path.write_text(
            "#!/bin/sh\n"
            f'printf "%s\\n" "$*" >> "{self.signals.as_posix()}"\n',
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    def stub_tmux(self):
        """A tmux with no session, which is all the sidecar teardown asks."""
        directory = self.directory / "stubs"
        directory.mkdir()
        path = directory / "tmux"
        path.write_text(
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            "    has-session) exit 1 ;;\n"
            "esac\n"
            "exit 0\n",
            encoding="utf-8",
        )
        path.chmod(0o755)
        return directory

    def stop_processes(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()

    def start(self, name):
        """A stand-in master: a real process whose executable is `name`."""
        if SLEEP is None:
            self.skipTest("sleep is not available")
        binary = self.directory / name
        shutil.copy(SLEEP, binary)
        binary.chmod(0o755)
        process = subprocess.Popen([str(binary), "60"])
        self.processes.append(process)
        return process

    def write_pidfile(self, text):
        self.absolute_pidfile.parent.mkdir(parents=True, exist_ok=True)
        self.absolute_pidfile.write_text(text, encoding="utf-8")

    def run_verb(self, verb, *arguments, **environment):
        environ = dict(os.environ)
        environ["MUX_PIDFILE"] = self.pidfile.as_posix()
        environ["MUX_SIGNAL"] = self.recorder.as_posix()
        # Never the repository's own generated configuration.
        environ["MUX_HAPROXY_CONFIG"] = self.haproxy_config.as_posix()
        # The stand-in comes first, so a real tmux on the host is not used.
        environ["PATH"] = f"{self.stubs}{os.pathsep}{environ['PATH']}"
        environ.update(environment)
        return subprocess.run(
            [SH, SCENE.as_posix(), verb, *arguments],
            cwd=ROOT, capture_output=True, text=True, env=environ,
        )

    def recorded(self):
        if not self.signals.is_file():
            return []
        return self.signals.read_text(encoding="utf-8").split()

    def down(self, *arguments, **environment):
        return self.run_verb("down", *arguments, **environment)

    def status(self, *arguments, **environment):
        return self.run_verb("status", *arguments, **environment)

    def up(self, *arguments, **environment):
        return self.run_verb("up", *arguments, **environment)

    def test_down_stops_the_master_the_pidfile_names(self):
        if not LINUX:
            self.skipTest("reading a process name needs a Linux process table")
        master = self.start("haproxy")
        self.write_pidfile(f"{master.pid}\n")

        result = self.down(MUX_STOP_TIMEOUT="0")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        # SIGTERM first, and SIGKILL only after the wait gives up: the
        # stand-in never reacts to a recorded signal, which is the case the
        # escalation exists for.
        self.assertEqual(
            ["-TERM", str(master.pid), "-KILL", str(master.pid)],
            self.recorded(),
        )
        self.assertIn("sending SIGKILL", result.stderr)
        self.assertFalse(self.absolute_pidfile.exists(), "the pidfile goes with the master")

    def test_down_stops_a_master_that_has_already_exited(self):
        if not LINUX:
            self.skipTest("reading a process name needs a Linux process table")
        master = self.start("haproxy")
        pid = master.pid
        master.terminate()
        master.wait(timeout=5)
        self.write_pidfile(f"{pid}\n")

        result = self.down()

        # The kernel may hand the recycled pid to something else in the
        # meantime, in which case it is the name check that refuses it. Either
        # way nothing is signalled, and the pidfile still goes with the stop.
        self.assertEqual([], self.recorded())
        self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
        self.assertFalse(self.absolute_pidfile.exists())

    def test_down_removes_a_stale_pidfile(self):
        self.write_pidfile(f"{NO_SUCH_PID}\n")

        result = self.down()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual([], self.recorded())
        self.assertIn("is gone; nothing to stop", result.stdout)
        self.assertFalse(self.absolute_pidfile.exists())

    def test_down_without_a_pidfile_has_nothing_to_stop(self):
        result = self.down()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual([], self.recorded())

    def test_down_refuses_to_stop_something_that_is_not_the_master(self):
        if not LINUX:
            self.skipTest("reading a process name needs a Linux process table")
        stranger = self.start("sleeper")
        self.write_pidfile(f"{stranger.pid}\n")

        result = self.down(MUX_STOP_TIMEOUT="0")

        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("refusing to signal it", result.stderr)
        self.assertEqual([], self.recorded())
        # The pidfile is not the stranger's to keep: dropping it is what lets
        # the next 'up' proceed.
        self.assertFalse(self.absolute_pidfile.exists())

    def test_down_rejects_a_stop_timeout_that_is_not_a_number(self):
        result = self.down(MUX_STOP_TIMEOUT="soon")

        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("MUX_STOP_TIMEOUT", result.stderr)

    def test_down_rejects_arguments_it_does_not_know(self):
        result = self.down("--now")

        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("Usage:", result.stderr)

    def test_status_reports_a_stale_pidfile(self):
        self.write_pidfile(f"{NO_SUCH_PID}\n")

        result = self.status()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("stale", result.stdout)

    def test_status_reports_a_master_that_outlived_its_session(self):
        if not LINUX:
            self.skipTest("reading a process name needs a Linux process table")
        master = self.start("haproxy")
        self.write_pidfile(f"{master.pid}\n")

        result = self.status()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("is up", result.stdout)
        self.assertIn(str(master.pid), result.stdout)
        # The stand-in tmux has no session, so this is a master with no window
        # left to appear in: exactly what status has to make visible.
        self.assertIn("no session", result.stdout)

    def test_status_reports_the_certificates_the_configuration_binds(self):
        self.haproxy_config.write_text(
            "global\n"
            "    maxconn 4096\n"
            "\n"
            "frontend mc_shared\n"
            "    bind 127.0.0.1:25566\n"
            "\n"
            "frontend geyser_tls_termination\n"
            "    bind 127.0.0.1:25567 ssl crt /outside/asp-frpcs/tls/one.pem"
            " crt /outside/asp-frpcs/tls/two.pem strict-sni\n"
            "    default_backend geyser_signaling\n",
            encoding="utf-8",
        )

        result = self.status()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        # The bind line as written, because that is what tells an operator
        # whether the file they just synced is the one being served.
        self.assertIn("bind 127.0.0.1:25567 ssl", result.stdout)
        self.assertIn("/outside/asp-frpcs/tls/one.pem", result.stdout)
        self.assertIn("/outside/asp-frpcs/tls/two.pem", result.stdout)
        self.assertIn("strict-sni", result.stdout)

    def test_status_reports_a_configuration_that_binds_no_certificate(self):
        self.haproxy_config.write_text(
            "frontend mc_shared\n"
            "    bind 127.0.0.1:25566\n",
            encoding="utf-8",
        )

        result = self.status()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("binds no certificate", result.stdout)

    def test_status_reports_a_configuration_that_is_not_there(self):
        result = self.status()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("no configuration at", result.stdout)

    def test_up_refuses_a_master_that_is_already_running(self):
        if not LINUX:
            self.skipTest("reading a process name needs a Linux process table")
        master = self.start("haproxy")
        self.write_pidfile(f"{master.pid}\n")

        result = self.up("--config", self.configs.as_posix())

        self.assertEqual(3, result.returncode, result.stdout + result.stderr)
        self.assertIn("already running", result.stderr)
        self.assertEqual([], self.recorded(), "up signals nothing itself")

    def test_up_refuses_a_pidfile_that_names_something_else(self):
        if not LINUX:
            self.skipTest("reading a process name needs a Linux process table")
        stranger = self.start("sleeper")
        self.write_pidfile(f"{stranger.pid}\n")

        result = self.up("--config", self.configs.as_posix())

        self.assertEqual(3, result.returncode, result.stdout + result.stderr)
        self.assertIn("run down to clear it", result.stderr)

    @unittest.skipUnless(
        HAVE_LISTEN_TOOL, "no listening-socket tool for the scene to read"
    )
    def test_up_refuses_an_occupied_listen_port(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            port = listener.getsockname()[1]

            result = self.up(
                "--config", self.configs.as_posix(),
                "--listen", f"127.0.0.1:{port}",
            )

        self.assertEqual(3, result.returncode, result.stdout + result.stderr)
        self.assertIn("already listens", result.stderr)


if __name__ == "__main__":
    unittest.main()
