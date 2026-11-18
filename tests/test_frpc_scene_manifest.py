"""The --scene manifest: parsing, path resolution and the server-less lifecycle.

A scene names one frpc process per section and two top-level keys, `session`
and `server`. It exists because `--config` can only run one binary and always
owns a server window, while this deployment needs a provider fork for the TCP
entries and the official client for a UDP tunnel that has to forward PROXY v2.

`--dry-run` prints the commands without tmux or frpc. The start path runs
against a stub tmux that records its arguments, so no session is ever created.
The scene parser only reads its input - nothing in a manifest is sourced or
evaluated - and every rejection has to happen before tmux is touched.
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
EXAMPLES = ROOT / "examples" / "scenes"
SH = shutil.which("sh")

SEPARATOR = "\037"
SIDECAR = re.compile(r"^cd '(?P<dir>.*)' && exec '(?P<binary>[^']*)' -c '(?P<config>.*)'$")
DRY_RUN_SIDECAR = re.compile(r"respawn-window -k -t <window-id> (cd .*)$", re.MULTILINE)
WINDOW = re.compile(r"-n (frpc-\S+)")

# Records every call as one line of US-separated arguments. It answers the
# three calls whose output the scene reads: has-session, a window id for a new
# session or window, and a live pane for the sidecar health check. The two
# switches let a test assert the teardown of a session that has no server
# window.
STUB_TMUX = """\
#!/bin/sh
{ printf '%s\\037' "$@"; printf '\\n'; } >> "$TMUX_STUB_LOG"
case "$1" in
    has-session)
        if [ "${TMUX_STUB_HAS_SESSION:-0}" = 1 ]; then exit 0; fi
        exit 1
        ;;
    list-panes)
        if [ -n "${TMUX_STUB_DEAD_WINDOW:-}" ]; then
            case "$*" in
                *"$TMUX_STUB_DEAD_WINDOW"*) printf '1\\n'; exit 0 ;;
            esac
        fi
        case "$*" in
            *":server"*)
                if [ "${TMUX_STUB_NO_SERVER:-0}" = 1 ]; then exit 1; fi
                ;;
        esac
        printf '0\\n'
        ;;
    new-session | new-window) printf 'w%d\\n' "$(wc -l < "$TMUX_STUB_LOG")" ;;
esac
exit 0
"""


def write_scene(path, text):
    """Write a manifest with LF endings, whatever the host default is."""
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


@unittest.skipIf(SH is None, "POSIX sh is not available")
class SceneManifestTests(unittest.TestCase):
    def setUp(self):
        self.base = self.enterContext(scratch.directory("frpc-manifest-"))
        self.scenes = self.base / "scenes"
        self.scenes.mkdir()
        self.stubs = self.base / "stubs"
        self.stubs.mkdir()
        for name in ("frpc", "sakura-frpc"):
            (self.stubs / name).write_bytes(b"#!/bin/sh\nexit 0\n")
        (self.stubs / "tmux").write_bytes(STUB_TMUX.encode())
        self.log = self.base / "tmux.log"
        self.log.write_text("", encoding="utf-8")
        # Present by default so a case that is meant to fail on grammar does
        # not fail on the config lookup first.
        self.config("udp.toml")

    # -- fixtures ---------------------------------------------------------

    def config(self, name):
        path = self.scenes / name
        path.write_text("# frpc\n", encoding="utf-8")
        return path

    def scene_binary(self, name):
        path = self.scenes / name
        path.write_bytes(b"#!/bin/sh\nexit 0\n")
        return path

    def scene(self, text, name="the.scene"):
        return write_scene(self.scenes / name, text)

    def environment(self, env=None):
        environment = dict(os.environ)
        environment.pop("FRPC_SESSION", None)
        environment.update({
            "PATH": os.pathsep.join([self.stubs.as_posix(), environment["PATH"]]),
            "TMUX_STUB_LOG": self.log.as_posix(),
            "FRPC_READY_TIMEOUT": "0",
        })
        environment.update(env or {})
        return environment

    def run_scene(self, scene, *arguments, cwd=ROOT, env=None):
        self.log.write_text("", encoding="utf-8")
        return subprocess.run(
            [SH, SCENE.as_posix(), "up", "--scene", scene.as_posix(), *arguments],
            cwd=cwd, capture_output=True, text=True, env=self.environment(env),
        )

    def run_verb(self, verb, *arguments, env=None):
        self.log.write_text("", encoding="utf-8")
        return subprocess.run(
            [SH, SCENE.as_posix(), verb, *arguments],
            cwd=ROOT, capture_output=True, text=True, env=self.environment(env),
        )

    def dry_run(self, scene, *arguments, cwd=ROOT, env=None):
        return self.run_scene(scene, "--dry-run", *arguments, cwd=cwd, env=env)

    # -- reading what the scene did --------------------------------------

    def calls(self):
        calls = []
        for line in self.log.read_text(encoding="utf-8").split("\n"):
            arguments = line.split(SEPARATOR)
            if arguments and arguments[-1] == "":
                arguments.pop()
            if arguments:
                calls.append(arguments)
        return calls

    def respawned(self):
        return [call[-1] for call in self.calls() if call[:1] == ["respawn-window"]]

    def first_call(self, verb):
        for call in self.calls():
            if call[:1] == [verb]:
                return call
        self.fail(f"no {verb} call: {self.calls()}")

    @staticmethod
    def flag(arguments, name):
        return arguments[arguments.index(name) + 1]

    def sidecars(self, output):
        return [SIDECAR.match(command) for command in DRY_RUN_SIDECAR.findall(output)]

    def assert_rejected(self, text, message):
        scene = self.scene(text)
        # Dry run parses the same way, so a rejection does not need tmux.
        result = self.dry_run(scene)
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn(message, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        return result

    # -- per-section processes -------------------------------------------

    def test_each_section_names_its_own_binary_and_config(self):
        for name in ("entry-a.toml", "entry-b.toml", "udp.toml"):
            self.config(name)
        scene = self.scene(
            "session = asp-frpc\n"
            "server = true\n"
            "\n"
            "[entry_a]\n"
            "binary = sakura-frpc\n"
            "config = entry-a.toml\n"
            "\n"
            "[entry_b]\n"
            "binary = sakura-frpc\n"
            "config = entry-b.toml\n"
            "\n"
            "[udp]\n"
            "binary = frpc\n"
            "config = udp.toml\n"
        )

        result = self.dry_run(scene)

        self.assertEqual(0, result.returncode, result.stderr)
        matches = self.sidecars(result.stdout)
        self.assertEqual(3, len(matches), result.stdout)
        self.assertEqual(["sakura-frpc", "sakura-frpc", "frpc"],
                         [match.group("binary") for match in matches])
        self.assertEqual(["entry-a.toml", "entry-b.toml", "udp.toml"],
                         [Path(match.group("config")).name for match in matches])
        self.assertEqual(["frpc-entry_a", "frpc-entry_b", "frpc-udp"],
                         WINDOW.findall(result.stdout))

    def test_relative_paths_resolve_against_the_scene_directory(self):
        self.config("udp.toml")
        self.scene_binary("official-frpc")
        scene = self.scene(
            "session = asp-frpc\n"
            "server = false\n"
            "[udp]\n"
            "binary = ./official-frpc\n"
            "config = ./udp.toml\n"
        )

        here = self.dry_run(scene, cwd=ROOT)
        elsewhere = self.dry_run(scene, cwd=self.base)

        self.assertEqual(0, here.returncode, here.stderr)
        self.assertEqual(0, elsewhere.returncode, elsewhere.stderr)
        # The caller's directory cannot move the paths: same scene, same text.
        self.assertEqual(DRY_RUN_SIDECAR.findall(here.stdout),
                         DRY_RUN_SIDECAR.findall(elsewhere.stdout))
        match = self.sidecars(here.stdout)[0]
        self.assertTrue(match.group("config").startswith("/"), match.group("config"))
        self.assertTrue(match.group("binary").startswith("/"), match.group("binary"))
        self.assertEqual("udp.toml", Path(match.group("config")).name)
        self.assertEqual("official-frpc", Path(match.group("binary")).name)

    def test_a_bare_binary_stays_a_command_name(self):
        self.config("udp.toml")
        scene = self.scene(
            "session = asp-frpc\nserver = false\n[udp]\nbinary = frpc\nconfig = udp.toml\n"
        )

        result = self.dry_run(scene)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("frpc", self.sidecars(result.stdout)[0].group("binary"))

    def test_a_config_path_with_spaces_and_a_quote_stays_one_argument(self):
        self.config("entry one's.toml")
        scene = self.scene(
            "session = asp-frpc\nserver = false\n"
            "[udp]\nbinary = frpc\nconfig = entry one's.toml\n"
        )

        result = self.run_scene(scene, "--no-attach")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        commands = [command for command in self.respawned() if command.startswith("cd '")]
        self.assertEqual(1, len(commands), commands)
        syntax = subprocess.run(
            [SH, "-n", "-c", commands[0]], capture_output=True, text=True,
        )
        self.assertEqual(0, syntax.returncode, commands[0] + syntax.stderr)

    def test_a_missing_binary_is_rejected_before_tmux(self):
        self.config("udp.toml")
        scene = self.scene(
            "session = asp-frpc\nserver = false\n"
            "[udp]\nbinary = ./absent-frpc\nconfig = udp.toml\n"
        )

        result = self.run_scene(scene, "--no-attach")

        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("no such frpc binary", result.stderr)
        self.assertEqual([], self.calls())

    # -- the server key ---------------------------------------------------

    def test_server_false_creates_no_server_window(self):
        self.config("udp.toml")
        scene = self.scene(
            "session = asp-frpc\nserver = false\n[udp]\nbinary = frpc\nconfig = udp.toml\n"
        )

        result = self.dry_run(scene)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("-n server", result.stdout)
        self.assertNotIn("@asp-server-deferred", result.stdout)
        # The first sidecar is the session, not a window added to a server.
        self.assertIn("new-session -d -P -F '#{window_id}' -s asp-frpc -n frpc-udp", result.stdout)
        self.assertIn("# server not started: the scene says server = false", result.stdout)

    def test_defer_server_still_reserves_the_placeholder(self):
        self.config("udp.toml")
        scene = self.scene(
            "session = asp-frpc\nserver = false\n[udp]\nbinary = frpc\nconfig = udp.toml\n"
        )

        result = self.dry_run(scene, "--defer-server")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("-n server", result.stdout)
        self.assertIn("@asp-server-deferred 1", result.stdout)
        self.assertIn("# server deferred", result.stdout)

    def test_server_true_starts_the_server_last(self):
        self.config("one.toml")
        self.config("two.toml")
        scene = self.scene(
            "session = asp-frpc\n"
            "server = true\n"
            "[a]\nbinary = frpc\nconfig = one.toml\n"
            "[b]\nbinary = frpc\nconfig = two.toml\n"
        )

        result = self.run_scene(scene, "--no-attach")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        commands = self.respawned()
        self.assertEqual(2, len([c for c in commands if c.startswith("cd '")]), commands)
        self.assertEqual("bash scripts/start.sh", commands[-1])

    def test_a_dead_sidecar_prevents_the_server_from_starting(self):
        self.config("one.toml")
        self.config("two.toml")
        scene = self.scene(
            "session = asp-frpc\n"
            "server = true\n"
            "[a]\nbinary = frpc\nconfig = one.toml\n"
            "[b]\nbinary = frpc\nconfig = two.toml\n"
        )

        result = self.run_scene(
            scene, "--no-attach", env={"TMUX_STUB_DEAD_WINDOW": "frpc-b"},
        )

        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("sidecar frpc-b is not running", result.stderr)
        self.assertNotIn("bash scripts/start.sh", self.respawned())
        self.assertFalse(any(call[:1] == ["kill-session"] for call in self.calls()))

    def test_server_false_never_starts_the_server(self):
        self.config("udp.toml")
        scene = self.scene(
            "session = asp-frpc\nserver = false\n[udp]\nbinary = frpc\nconfig = udp.toml\n"
        )

        result = self.run_scene(scene, "--no-attach")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertNotIn("bash scripts/start.sh", self.respawned())
        self.assertEqual("frpc-udp", self.flag(self.first_call("new-session"), "-n"))

    def test_each_section_runs_its_own_binary_at_start(self):
        self.config("udp.toml")
        self.scene_binary("official-frpc")
        scene = self.scene(
            "session = asp-frpc\n"
            "server = false\n"
            "[entry]\nbinary = frpc\nconfig = udp.toml\n"
            "[udp]\nbinary = ./official-frpc\nconfig = udp.toml\n"
        )

        result = self.run_scene(scene, "--no-attach")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        sidecars = [SIDECAR.match(c) for c in self.respawned() if c.startswith("cd '")]
        self.assertEqual(2, len(sidecars), self.respawned())
        # A bare name is resolved through PATH; a relative path joins the
        # scene directory. Both have to reach frpc as absolute paths.
        self.assertTrue(sidecars[0].group("binary").startswith("/"), sidecars[0].group("binary"))
        self.assertEqual("frpc", Path(sidecars[0].group("binary")).name)
        self.assertTrue(sidecars[1].group("binary").startswith("/"), sidecars[1].group("binary"))
        self.assertEqual("official-frpc", Path(sidecars[1].group("binary")).name)

    # -- the session name -------------------------------------------------

    def test_the_scene_names_the_tmux_session(self):
        self.config("udp.toml")
        scene = self.scene(
            "session = asp-frpc-udp\nserver = false\n[udp]\nbinary = frpc\nconfig = udp.toml\n"
        )

        result = self.run_scene(scene, "--no-attach")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("asp-frpc-udp", self.flag(self.first_call("new-session"), "-s"))
        self.assertIn("FRPC_SESSION=asp-frpc-udp", result.stderr)

    def test_frpc_session_overrides_the_scene(self):
        self.config("udp.toml")
        scene = self.scene(
            "session = asp-frpc-udp\nserver = false\n[udp]\nbinary = frpc\nconfig = udp.toml\n"
        )

        result = self.run_scene(scene, "--no-attach", env={"FRPC_SESSION": "asp-frpc-test"})

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("asp-frpc-test", self.flag(self.first_call("new-session"), "-s"))
        self.assertNotIn("FRPC_SESSION=", result.stderr)

    def test_down_kills_a_session_without_a_server_window(self):
        result = self.run_verb(
            "down",
            env={
                "TMUX_STUB_HAS_SESSION": "1",
                "TMUX_STUB_NO_SERVER": "1",
                "FRPC_SESSION": "asp-frpc-udp",
            },
        )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("no server window", result.stdout)
        self.assertTrue(any(call[:1] == ["kill-session"] for call in self.calls()), self.calls())
        # Nothing was sent to a window that does not exist.
        self.assertFalse(any(call[:1] == ["send-keys"] for call in self.calls()), self.calls())

    # -- validation -------------------------------------------------------

    def test_scene_and_config_are_mutually_exclusive(self):
        self.config("udp.toml")
        scene = self.scene(
            "session = asp-frpc\nserver = false\n[udp]\nbinary = frpc\nconfig = udp.toml\n"
        )

        result = self.run_scene(scene, "--dry-run", "--config", self.scenes.as_posix())

        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("mutually exclusive", result.stderr)

    def test_up_needs_a_scene_or_configs(self):
        result = self.run_verb("up", "--dry-run")
        self.assertEqual(2, result.returncode)
        self.assertIn("--config <dir|file> or --scene <file>", result.stderr)

    def test_duplicate_section_is_rejected(self):
        self.assert_rejected(
            "session = s\nserver = false\n"
            "[udp]\nbinary = frpc\nconfig = udp.toml\n"
            "[udp]\nbinary = frpc\nconfig = udp.toml\n",
            "duplicate section [udp]",
        )

    def test_duplicate_section_key_is_rejected(self):
        self.assert_rejected(
            "session = s\nserver = false\n"
            "[udp]\nbinary = frpc\nbinary = frpc\nconfig = udp.toml\n",
            "duplicate key 'binary'",
        )

    def test_duplicate_top_level_key_is_rejected(self):
        self.assert_rejected(
            "session = s\nsession = t\nserver = false\n"
            "[udp]\nbinary = frpc\nconfig = udp.toml\n",
            "duplicate top-level key 'session'",
        )

    def test_unknown_key_is_rejected(self):
        self.config("udp.toml")
        self.assert_rejected(
            "session = s\nserver = false\n[udp]\nbinary = frpc\nconfig = udp.toml\nrole = java\n",
            "unknown key 'role'",
        )

    def test_unknown_top_level_key_is_rejected(self):
        self.assert_rejected(
            "session = s\nserver = false\nuser = nobody\n"
            "[udp]\nbinary = frpc\nconfig = udp.toml\n",
            "unknown top-level key 'user'",
        )

    def test_invalid_server_value_is_rejected(self):
        self.assert_rejected(
            "session = s\nserver = yes\n[udp]\nbinary = frpc\nconfig = udp.toml\n",
            "server must be 'true' or 'false'",
        )

    def test_invalid_section_name_is_rejected(self):
        self.assert_rejected(
            "session = s\nserver = false\n[bad name]\nbinary = frpc\nconfig = udp.toml\n",
            "section names use only letters",
        )

    def test_inline_comments_are_not_interpreted(self):
        self.assert_rejected(
            "session = s # not a comment\nserver = false\n"
            "[udp]\nbinary = frpc\nconfig = udp.toml\n",
            "session uses only letters",
        )

    def test_control_characters_are_rejected(self):
        self.config("udp.toml")
        cases = [
            ("binary", "session = s\nserver = false\n"
                       "[udp]\nbinary = fr\tpc\nconfig = udp.toml\n"),
            ("config", "session = s\nserver = false\n"
                       "[udp]\nbinary = frpc\nconfig = udp\t.toml\n"),
        ]
        for key, text in cases:
            with self.subTest(key=key):
                self.assert_rejected(
                    text,
                    "control characters",
                )

    def test_missing_config_is_rejected(self):
        self.assert_rejected(
            "session = s\nserver = false\n[udp]\nbinary = frpc\nconfig = nope.toml\n",
            "no such config",
        )

    def test_a_section_needs_a_binary(self):
        self.config("udp.toml")
        self.assert_rejected(
            "session = s\nserver = false\n[udp]\nconfig = udp.toml\n",
            "section [udp] needs a binary",
        )

    def test_a_section_needs_a_config(self):
        self.assert_rejected(
            "session = s\nserver = false\n[udp]\nbinary = frpc\n",
            "section [udp] needs a config",
        )

    def test_missing_session_is_rejected(self):
        self.assert_rejected(
            "server = false\n[udp]\nbinary = frpc\nconfig = udp.toml\n",
            "needs a top-level session",
        )

    def test_missing_server_is_rejected(self):
        self.assert_rejected(
            "session = s\n[udp]\nbinary = frpc\nconfig = udp.toml\n",
            "needs a top-level server",
        )

    def test_a_scene_needs_at_least_one_section(self):
        self.assert_rejected("session = s\nserver = false\n", "declares no sections")

    def test_a_broken_scene_never_reaches_tmux(self):
        scene = self.scene("session = s\nserver = false\n[udp]\nconfig = udp.toml\n")

        result = self.run_scene(scene, "--no-attach")

        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertEqual([], self.calls())

    def test_a_missing_scene_file_is_rejected(self):
        result = self.run_scene(self.scenes / "absent.scene", "--dry-run")
        self.assertEqual(2, result.returncode)
        self.assertIn("no such scene file", result.stderr)

    def test_a_crlf_manifest_is_read_as_lf(self):
        self.config("udp.toml")
        scene = self.scene(
            "session = asp-frpc\r\nserver = false\r\n"
            "[udp]\r\nbinary = frpc\r\nconfig = udp.toml\r\n"
        )

        result = self.dry_run(scene)

        self.assertEqual(0, result.returncode, result.stderr)

    # -- legacy mode is untouched -----------------------------------------

    def test_legacy_config_mode_still_uses_frpc_and_a_server_window(self):
        self.config("one.toml")

        legacy = subprocess.run(
            [SH, SCENE.as_posix(), "up", "--config", self.scenes.as_posix(), "--dry-run"],
            cwd=ROOT, capture_output=True, text=True, env=self.environment(),
        )

        self.assertEqual(0, legacy.returncode, legacy.stderr)
        self.assertIn("-n server", legacy.stdout)
        self.assertIn("@asp-server-deferred 0", legacy.stdout)
        self.assertEqual("frpc", self.sidecars(legacy.stdout)[0].group("binary"))
        self.assertEqual(
            ["tmux set-window-option -t <server-window-id> @asp-server-deferred 0",
             "tmux respawn-window -k -t <server-window-id> bash scripts/start.sh"],
            legacy.stdout.splitlines()[-2:],
        )


class SceneExampleTests(unittest.TestCase):
    def test_the_examples_exist(self):
        for name in [
            "README.md",
            "asp-frpc-udp.scene.example",
            "asp-frpc-shared.scene.example",
            "frpc/official-frpc-udp.toml.example",
            "frpc/sakura-frpc-entry.toml.example",
        ]:
            self.assertTrue((EXAMPLES / name).is_file(), name)

    def test_the_examples_carry_no_secret_shaped_values(self):
        markers = ["nyat.app", "wdn.gg", "natfrp.com", "sakurafrp.com"]
        secrets = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}|[A-Fa-f0-9]{32,}")
        for path in sorted(EXAMPLES.rglob("*")):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            for marker in markers:
                self.assertNotIn(marker, text, f"{path} names a real provider endpoint")
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                self.assertIsNone(secrets.search(stripped), f"{path}: {stripped}")


if __name__ == "__main__":
    unittest.main()
