"""What the frpc scene hands to tmux for each sidecar.

`--dry-run` prints the commands without starting anything, but the start
path builds them again in its own loop further down. A change made to one
and not the other is a real bug, so both are exercised here. tmux is a
stub that records its arguments, so no session is ever created.

The working directory matters: frpc resolves the relative paths inside a
configuration (certificates, logs, plugin files) against the directory it
was started in, so every sidecar has to start where its own
configuration file lives.
"""

from pathlib import Path
import os
import re
import shutil
import subprocess
import unittest

from tests import scratch


ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / "scripts" / "scenes" / "frpc.sh"
SHARED_SCENE = ROOT / "scripts" / "scenes" / "frpc-shared-tcp.sh"
SH = shutil.which("sh")

# Records every call as one line of US-separated arguments, then answers
# the two calls whose output the scene reads: a window id for a new window,
# and a live pane for the sidecar health check. The separator is 0x1f, not
# 0x1c: str.splitlines() treats the latter as a line break.
STUB_TMUX = """\
#!/bin/sh
{ printf '%s\\037' "$@"; printf '\\n'; } >> "$TMUX_STUB_LOG"
case "$1" in
    has-session) exit 1 ;;
    list-panes) printf '0\\n' ;;
    new-session | new-window) printf 'w%d\\n' "$(wc -l < "$TMUX_STUB_LOG")" ;;
esac
exit 0
"""

STUB_FRPC = "#!/bin/sh\nexit 0\n"

SEPARATOR = "\037"
SIDECAR = re.compile(r"^cd '(?P<dir>.*)' && exec '(?P<frpc>[^']*)' -c '(?P<path>.*)'$")
DRY_RUN_SIDECAR = re.compile(r"respawn-window -k -t <window-id> (cd .*)$", re.MULTILINE)


@unittest.skipIf(SH is None, "POSIX sh is not available")
class FrpcSceneSpawnTests(unittest.TestCase):
    def setUp(self):
        self.base = self.enterContext(scratch.directory("frpc-spawn-"))
        self.stubs = self.base / "stubs"
        self.stubs.mkdir()
        (self.stubs / "tmux").write_bytes(STUB_TMUX.encode())
        (self.stubs / "frpc").write_bytes(STUB_FRPC.encode())
        self.log = self.base / "tmux.log"
        self.log.write_text("", encoding="utf-8")

    def frpcs(self, name, *files):
        directory = self.base / name
        directory.mkdir(parents=True, exist_ok=True)
        for file in files:
            (directory / file).write_text("# frpc\n", encoding="utf-8")
        return directory

    def up(self, scene, *arguments, env=None):
        self.log.write_text("", encoding="utf-8")
        environment = dict(os.environ)
        environment.update({
            "PATH": os.pathsep.join([self.stubs.as_posix(), environment["PATH"]]),
            "TMUX_STUB_LOG": self.log.as_posix(),
            "FRPC_READY_TIMEOUT": "0",
            "FRPC_SESSION": "asp-frpc-test",
        })
        environment.update(env or {})
        return subprocess.run(
            [SH, scene.as_posix(), "up", *arguments],
            cwd=ROOT, capture_output=True, text=True, env=environment,
        )

    def commands(self):
        text = self.log.read_text(encoding="utf-8")
        calls = []
        for line in text.split("\n"):
            arguments = line.split(SEPARATOR)
            if arguments and arguments[-1] == "":
                arguments.pop()
            calls.append(arguments)
        return [arguments[-1] for arguments in calls if arguments[:1] == ["respawn-window"]]

    def sidecar_commands(self):
        return [command for command in self.commands() if command.startswith("cd '")]

    def assert_command_matches(self, command):
        match = SIDECAR.match(command)
        self.assertIsNotNone(match, f"unexpected sidecar command: {command}")
        directory = match.group("dir")
        path = match.group("path")
        # The directory is the configuration's own directory, verbatim: the
        # two are built from the same resolved path, not by re-deriving one
        # from the other, and the quotes keep both together as one argument.
        self.assertEqual(f"{directory}/{Path(path).name}", path, command)
        return match

    def test_each_sidecar_starts_where_its_configuration_lives(self):
        one = self.frpcs("one", "first.toml")
        two = self.frpcs("two", "second.toml")

        result = self.up(
            SCENE, "--config", one.as_posix(), "--config", two.as_posix(), "--no-attach",
        )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        directories = {}
        for command in self.sidecar_commands():
            match = self.assert_command_matches(command)
            directories[Path(match.group("path")).name] = Path(match.group("dir")).name
        self.assertEqual({"first.toml": "one", "second.toml": "two"}, directories)

    def test_a_configuration_directory_with_spaces_stays_one_argument(self):
        directory = self.frpcs("frp cs", "mc bedrock.toml")

        result = self.up(SCENE, "--config", directory.as_posix(), "--no-attach")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        commands = self.sidecar_commands()
        self.assertEqual(1, len(commands), commands)
        match = self.assert_command_matches(commands[0])
        self.assertIn(" ", match.group("dir"), commands[0])
        self.assertEqual("mc bedrock.toml", Path(match.group("path")).name)

    def test_only_the_server_window_is_left_unmoved(self):
        directory = self.frpcs("frpcs", "one.toml")

        result = self.up(SCENE, "--config", directory.as_posix(), "--no-attach")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(["bash scripts/start.sh"], [
            command for command in self.commands() if not command.startswith("cd '")
        ])

    def test_dry_run_and_the_start_path_agree(self):
        directory = self.frpcs("frpcs", "one.toml", "two.toml")

        dry_run = self.up(SCENE, "--config", directory.as_posix(), "--dry-run")
        self.assertEqual(0, dry_run.returncode, dry_run.stdout + dry_run.stderr)
        printed = DRY_RUN_SIDECAR.findall(dry_run.stdout)

        started = self.up(SCENE, "--config", directory.as_posix(), "--no-attach")
        self.assertEqual(0, started.returncode, started.stdout + started.stderr)
        spawned = self.sidecar_commands()

        # Only the frpc binary itself may differ: --dry-run cannot resolve it.
        binary = re.compile(r"exec '[^']*'")
        self.assertEqual(2, len(printed), dry_run.stdout)
        self.assertEqual(
            sorted(binary.sub("exec <frpc>", command) for command in printed),
            sorted(binary.sub("exec <frpc>", command) for command in spawned),
        )

    def test_the_shared_scene_keeps_the_configuration_directory(self):
        directory = self.frpcs("frpcs", "one.toml")

        result = self.up(SHARED_SCENE, "--config", directory.as_posix(), "--dry-run")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        commands = DRY_RUN_SIDECAR.findall(result.stdout)
        self.assertEqual(1, len(commands), result.stdout)
        self.assert_command_matches(commands[0])


if __name__ == "__main__":
    unittest.main()
