"""The shared-TCP scene swaps the mux configuration under a running server.

`reload` reads one pidfile and sends one signal, so it is testable without
tmux, frpc or HAProxy: a stand-in for the signal command records what it was
asked to send, and a process whose executable is called `haproxy` stands in
for the master. What the scene must never do is signal a pid it cannot
identify as HAProxy, because a stale pidfile plus a recycled pid would aim
that signal at an unrelated process.

Reading a process name needs a process table (`/proc`, or a `ps` that takes
`-o comm=`), which the shared-TCP scene's own platform has and a Windows
development box does not: the tests that identify a running process are
skipped there, and the ones that only read a pidfile run everywhere.
"""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / "scripts" / "scenes" / "frpc-shared-tcp.sh"
SH = shutil.which("sh")
SLEEP = shutil.which("sleep")
LINUX = sys.platform.startswith("linux")


@unittest.skipIf(SH is None, "POSIX sh is not available")
class ReloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        # A relative pidfile: the scene resolves it against the caller's
        # directory, which is this repository root.
        self.pidfile = Path(".tmp") / f"reload-test-{os.getpid()}" / "haproxy.pid"
        self.absolute_pidfile = ROOT / self.pidfile
        self.signals = self.directory / "signals.txt"
        self.addCleanup(shutil.rmtree, self.absolute_pidfile.parent, True)
        self.recorder = self.record_signals()
        self.processes = []
        self.addCleanup(self.stop_processes)

    def record_signals(self):
        """A stand-in for the signal command that writes down its arguments."""
        path = self.directory / "record-signal.sh"
        path.write_text(
            "#!/bin/sh\n"
            f'printf "%s\\n" "$*" >> "{self.signals.as_posix()}"\n',
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

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

    def reload(self, *arguments, **environment):
        environ = dict(os.environ)
        environ["MUX_PIDFILE"] = self.pidfile.as_posix()
        environ["MUX_SIGNAL"] = self.recorder.as_posix()
        environ.update(environment)
        return subprocess.run(
            [SH, SCENE.as_posix(), "reload", *arguments],
            cwd=ROOT, capture_output=True, text=True, env=environ,
        )

    def recorded(self):
        if not self.signals.is_file():
            return []
        return self.signals.read_text(encoding="utf-8").split()

    def test_reload_without_a_pidfile_says_the_mux_is_not_running(self):
        result = self.reload()

        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("the mux is not running", result.stderr)
        self.assertEqual([], self.recorded())

    def test_reload_refuses_a_pidfile_that_holds_no_process_id(self):
        self.write_pidfile("not-a-pid\n")

        result = self.reload()

        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("does not hold a process id", result.stderr)
        self.assertEqual([], self.recorded())

    def test_reload_refuses_a_pid_no_process_has(self):
        # Above every pid_max a Linux kernel offers, so nothing can own it.
        self.write_pidfile("2147483647\n")

        result = self.reload()

        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("pidfile is stale", result.stderr)
        self.assertEqual([], self.recorded())

    def test_reload_refuses_arguments_it_does_not_know(self):
        result = self.reload("--now")

        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("Usage:", result.stderr)

    def test_reload_is_in_the_usage(self):
        result = subprocess.run(
            [SH, SCENE.as_posix(), "help"], cwd=ROOT, capture_output=True, text=True,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("frpc-shared-tcp.sh reload", result.stdout)

    def test_the_up_command_runs_haproxy_as_a_master_with_a_pidfile(self):
        """A reload needs a master that stays alive and a pidfile to address it."""
        configs = self.directory / "configs"
        configs.mkdir()
        (configs / "frpc.toml").write_text("serverAddr = 'example.org'\n", encoding="utf-8")

        result = subprocess.run(
            [SH, SCENE.as_posix(), "up", "--config", configs.as_posix(), "--dry-run"],
            cwd=ROOT, capture_output=True, text=True,
        )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        command = [line for line in result.stdout.splitlines() if "haproxy" in line and "respawn-window" in line]
        self.assertEqual(1, len(command), result.stdout)
        self.assertIn(" -W -db -p ", command[0], "the master stays alive and writes a pidfile")
        pidfile = command[0].split(" -p ", 1)[1].split(" -f ", 1)[0].strip("'\"")
        self.assertTrue(pidfile.endswith("frpc-shared-tcp/haproxy.pid"), pidfile)

    @unittest.skipUnless(LINUX, "reading a process name needs a Linux process table")
    def test_reload_refuses_a_pid_that_has_exited(self):
        gone = self.start("sleeper")
        pid = gone.pid
        gone.terminate()
        gone.wait(timeout=5)
        self.write_pidfile(f"{pid}\n")

        result = self.reload()

        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertEqual([], self.recorded())
        # The kernel may hand the pid to something else in the meantime, in
        # which case it is the name check that refuses it. Either way the
        # process is not signalled, and neither branch trusts the pidfile.
        self.assertTrue(
            "stale" in result.stderr or "refusing to signal it" in result.stderr,
            result.stderr,
        )

    @unittest.skipUnless(LINUX, "reading a process name needs a Linux process table")
    def test_reload_refuses_to_signal_something_that_is_not_haproxy(self):
        stranger = self.start("sleeper")
        self.write_pidfile(f"{stranger.pid}\n")

        result = self.reload()

        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("refusing to signal it", result.stderr)
        self.assertEqual([], self.recorded())

    @unittest.skipUnless(LINUX, "reading a process name needs a Linux process table")
    def test_reload_signals_the_master_named_in_the_pidfile(self):
        master = self.start("haproxy")
        self.write_pidfile(f"{master.pid}\n")

        result = self.reload()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(["-USR2", str(master.pid)], self.recorded())
        self.assertIn("SIGUSR2", result.stdout)


if __name__ == "__main__":
    unittest.main()
