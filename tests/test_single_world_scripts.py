"""Execute launchers and backups in disposable server trees without Minecraft."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
SCRATCH = REPOSITORY / ".tmp"
GIT_BASH = Path("D:/Applications/Scoop/apps/git/current/bin/bash.exe")
BASH = str(GIT_BASH) if os.name == "nt" and GIT_BASH.is_file() else shutil.which("bash")

WINDOWS_STUB = r'''
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;

public class ScriptFixture {
    public static int Main(string[] args) {
        string tool = Path.GetFileNameWithoutExtension(Assembly.GetExecutingAssembly().Location);
        if (tool == "powershell") {
            foreach (string argument in args) {
                if (argument.Contains("Win32_Process")) {
                    File.WriteAllLines(Environment.GetEnvironmentVariable("PROCESS_LOG"), args);
                    return int.Parse(Environment.GetEnvironmentVariable("PROCESS_RESULT") ?? "0");
                }
            }
            string command = Environment.CommandLine;
            int offset = command[0] == '"' ? command.IndexOf('"', 1) + 1 : command.IndexOf(' ');
            ProcessStartInfo start = new ProcessStartInfo(
                Environment.GetEnvironmentVariable("REAL_POWERSHELL"), command.Substring(offset).TrimStart());
            start.UseShellExecute = false;
            using (Process child = Process.Start(start)) {
                child.WaitForExit();
                return child.ExitCode;
            }
        }
        File.AppendAllText(Environment.GetEnvironmentVariable("JAVA_CALLS"), "call\n");
        if (args.Length == 1 && args[0] == "-version") {
            Console.Error.WriteLine("openjdk version \"25.0.1\"");
            return 0;
        }
        File.WriteAllLines(Environment.GetEnvironmentVariable("JAVA_ARGS"), args);
        File.WriteAllText(Environment.GetEnvironmentVariable("JAVA_CWD"), Environment.CurrentDirectory);
        return int.Parse(Environment.GetEnvironmentVariable("JAVA_RESULT") ?? "0");
    }
}
'''


class SingleWorldScriptsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SCRATCH.mkdir(exist_ok=True)
        cls.shared = tempfile.TemporaryDirectory(prefix="script-tools-", dir=SCRATCH)
        cls.addClassCleanup(cls.shared.cleanup)
        cls.tools = Path(cls.shared.name)
        cls.powershell = shutil.which("powershell.exe")
        if os.name == "nt":
            if not cls.powershell:
                raise unittest.SkipTest("Windows PowerShell is required for CMD script tests")
            source = cls.tools / "ScriptFixture.cs"
            source.write_text(WINDOWS_STUB, encoding="utf-8")
            compiler_env = dict(os.environ, FIXTURE_SOURCE=str(source),
                                FIXTURE_EXE=str(cls.tools / "java.exe"),
                                TMP=str(cls.tools), TEMP=str(cls.tools))
            compile_result = subprocess.run(
                [cls.powershell, "-NoProfile", "-Command",
                 "Add-Type -Path $env:FIXTURE_SOURCE -OutputAssembly $env:FIXTURE_EXE -OutputType ConsoleApplication"],
                env=compiler_env, capture_output=True, text=True, timeout=60, check=False,
            )
            if compile_result.returncode:
                raise RuntimeError(compile_result.stdout + compile_result.stderr)
            shutil.copyfile(cls.tools / "java.exe", cls.tools / "powershell.exe")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="single-world-", dir=SCRATCH)
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.scripts = self.directory / "scripts"
        self.scripts.mkdir()
        for name in ("start.sh", "start.cmd", "backup.sh", "backup.cmd", "backup-debug.cmd",
                     "select_resource_pack.py", "host_settings.py", "verify_runtime.py",
                     "backup_settings.py", "backup_cleanup.ps1"):
            target = self.scripts / name
            target.write_text((REPOSITORY / "scripts" / name).read_text(encoding="utf-8"),
                              encoding="utf-8", newline="\r\n" if name.endswith(".cmd") else "\n")
            target.chmod(0o755)
        self.server = self.directory / "server"
        self.server.mkdir()
        self.write("paper-server.jar", b"fixture jar")
        self.write("server.properties", b"level-name=Adventure_A\nenable-command-block=true\n")
        for name in ("Adventure_A", "Puzzle-2"):
            for relative in ("level.dat", "data/minecraft/scoreboard.dat", "players/player.dat",
                             "dimensions/minecraft/overworld/region/r.0.0.mca"):
                self.write(f"{name}/{relative}", f"{name}:{relative}".encode())
        self.backups = self.directory / "backups"
        self.bin = self.directory / "bin"
        self.bin.mkdir()
        self.elsewhere = self.directory / "elsewhere/nested"
        self.elsewhere.mkdir(parents=True)
        self.environment = dict(os.environ)
        for name in ("BACKUP_TARGETS", "BACKUP_ROOT", "SETTINGS_DIR", "ASP_SKIP_BACKUP", "ALLOW_ONLINE", "WORLD_NAME",
                     "PAUSE_ON_EXIT", "JAVA", "BACKUP_DEBUG"):
            self.environment.pop(name, None)
        self.environment.update(
            JAVA_ARGS=str(self.directory / "java-args.txt"),
            JAVA_CWD=str(self.directory / "java-cwd.txt"),
            JAVA_CALLS=str(self.directory / "java-calls.txt"),
            PROCESS_LOG=str(self.directory / "process.txt"), PROCESS_RESULT="0",
            BACKUP_MARKER=str(self.backups) + ".called", BACKUP_MIN_INTERVAL="0", KEEP="5",
            BACKUP_REQUIRE_ALL="1", REAL_POWERSHELL=self.powershell or "",
        )

    def write(self, relative, content=b"fixture"):
        target = self.server / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def prepare(self, shell, stub_backup=False):
        if shell == "sh":
            if not BASH:
                self.skipTest("Bash is unavailable")
            java = self.bin / "java"
            java.write_text(
                '#!/bin/sh\nprintf "call\\n" >> "$JAVA_CALLS"\n'
                'if [ "$1" = -version ]; then echo \'openjdk version "25.0.1"\' >&2; exit 0; fi\n'
                'printf "%s\\n" "$@" > "$JAVA_ARGS"\npwd > "$JAVA_CWD"\n'
                'exit "${JAVA_RESULT:-0}"\n', encoding="utf-8", newline="\n")
            java.chmod(0o755)
            process = self.bin / "pgrep"
            process.write_text(
                '#!/bin/sh\nprintf "%s\\n" "$@" > "$PROCESS_LOG"\n'
                'if [ "$PROCESS_RESULT" = 2 ]; then exit 0; else exit 1; fi\n',
                encoding="utf-8", newline="\n")
            process.chmod(0o755)
            self.environment["JAVA"] = java.as_posix()
            self.environment["PATH"] = str(self.bin) + os.pathsep + self.environment["PATH"]
            if stub_backup:
                (self.scripts / "backup.sh").write_text(
                    '#!/bin/sh\nprintf "backup\\n" > "$BACKUP_MARKER"\n',
                    encoding="utf-8", newline="\n")
        else:
            if os.name != "nt":
                self.skipTest("CMD is available only on Windows")
            self.environment["JAVA"] = str(self.tools / "java.exe")
            self.environment["PATH"] = str(self.tools) + os.pathsep + self.environment["PATH"]
            if stub_backup:
                (self.scripts / "backup.cmd").write_text(
                    '@echo off\n> "%BACKUP_MARKER%" echo backup\nexit /b 0\n',
                    encoding="utf-8", newline="\r\n")

    def run_script(self, name, *arguments):
        script = self.scripts / name
        if name.endswith(".sh"):
            command = [BASH, script.as_posix(), *arguments]
        else:
            invocation = " ".join(f'"{argument}"' for argument in (str(script), *arguments))
            command = f'"{os.environ.get("COMSPEC", "cmd.exe")}" /d /s /c "{invocation}"'
        return subprocess.run(command, cwd=self.elsewhere, env=self.environment,
                              input="\n", capture_output=True, text=True, timeout=40, check=False)

    def assert_launch(self, shell, *arguments):
        before = {path.relative_to(self.server): path.read_bytes()
                  for path in self.server.rglob("*") if path.is_file()}
        result = self.run_script(f"start.{shell}", *arguments)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        recorded = Path(self.environment["JAVA_ARGS"]).read_text().splitlines()
        self.assertEqual(["-Xms2G", "-Xmx4G", "-XX:+UseG1GC",
                          "-Dpaper.disableStartupVersionCheck=true", "-jar", "paper-server.jar"], recorded[:6])
        after = {path.relative_to(self.server): path.read_bytes()
                 for path in self.server.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertTrue(Path(str(self.backups) + ".called").is_file())
        working_directory = Path(self.environment["JAVA_CWD"]).read_text().strip()
        if shell == "sh" and os.name == "nt":
            working_directory = working_directory[1] + ":" + working_directory[2:]
        self.assertEqual(self.server.resolve(), Path(working_directory).resolve())
        return recorded[6:]

    def check_launches(self, shell):
        self.prepare(shell, stub_backup=True)
        self.assertEqual([], self.assert_launch(shell))
        for name in ("Adventure_A", "Puzzle-2", "--help", "--world", "-pause"):
            with self.subTest(world=name):
                self.write(f"{name}/level.dat")
                self.assertEqual(["--world", name], self.assert_launch(shell, "--world", name))
        if shell == "cmd":
            self.assertEqual(["--world", "Puzzle-2"],
                             self.assert_launch(shell, "-pause", "--world", "Puzzle-2"))
            self.assertEqual(["--world", "Puzzle-2"],
                             self.assert_launch(shell, "--world", "Puzzle-2", "-pause"))

    def test_shell_default_and_selection(self):
        self.check_launches("sh")

    def test_cmd_default_selection_and_pause(self):
        self.check_launches("cmd")

    def check_pack_policy(self, shell):
        self.prepare(shell, stub_backup=True)
        settings = self.directory / "settings"
        settings.mkdir()
        policy = settings / "minecraft-server.json"
        policy.write_text(json.dumps({
            "schema_version": 1,
            "values": {"MANAGEMENT_SERVER_SECRET": "env:UNSET_CREDENTIAL"},
            "resource_packs": {
                "default": {"url": "https://assets.example.com/global.zip", "sha1": "a" * 40},
                "worlds": {"Puzzle-2": None, "--help": None},
            },
        }), encoding="utf-8")
        expected_config = "../.tmp/startup/server.properties" if shell == "sh" else "..\\.tmp\\startup\\server.properties"
        for world, expected_pack in ((None, True), ("Puzzle-2", False), ("Adventure_A", True), ("--help", False)):
            with self.subTest(world=world):
                if world:
                    self.write(f"{world}/level.dat")
                world_args = ["--world", world] if world else []
                self.assertEqual([*world_args, "--config", expected_config],
                                 self.assert_launch(shell, *world_args))
                output = self.directory / ".tmp/startup/server.properties"
                rendered = output.read_text(encoding="ascii")
                self.assertIn("resource-pack-id=\n", rendered)
                self.assertEqual(expected_pack, "global.zip" in rendered)
                self.assertEqual(expected_pack, "a" * 40 in rendered)
                output.write_text("level-name=stale\nresource-pack=stale\n", encoding="ascii")
        policy.write_text(json.dumps({"schema_version": 1, "values": {
            "MANAGEMENT_SERVER_SECRET": "env:UNSET_CREDENTIAL",
        }}), encoding="utf-8")
        self.assertEqual([], self.assert_launch(shell))
        self.assertEqual(["--world", "Puzzle-2"], self.assert_launch(shell, "--world", "Puzzle-2"))
        policy.unlink()
        self.assertEqual([], self.assert_launch(shell))

    def test_shell_pack_policy_selection_and_removal(self):
        self.check_pack_policy("sh")

    def test_cmd_pack_policy_selection_and_removal(self):
        self.check_pack_policy("cmd")

    def check_legacy_native_properties(self, shell):
        self.prepare(shell, stub_backup=True)
        settings = self.directory / "settings"
        settings.mkdir()
        (settings / "minecraft-server.json").write_text(
            '{"schema_version":1,"values":{"MANAGEMENT_SERVER_SECRET":"env:UNSET_CREDENTIAL"}}',
            encoding="utf-8")
        properties = self.server / "server.properties"
        properties.write_bytes(b"level-name=Native save name\n")
        self.assertEqual([], self.assert_launch(shell))
        properties.unlink()
        self.assertEqual([], self.assert_launch(shell))
        self.assertFalse((self.directory / ".tmp/startup/server.properties").exists())

    def test_shell_legacy_settings_preserve_native_startup(self):
        self.check_legacy_native_properties("sh")

    def test_cmd_legacy_settings_preserve_native_startup(self):
        self.check_legacy_native_properties("cmd")

    def check_invalid_policy(self, shell):
        self.prepare(shell, stub_backup=True)
        settings = self.directory / "settings"
        settings.mkdir()
        (settings / "minecraft-server.json").write_text('{"schema_version":1}', encoding="utf-8")
        result = self.run_script(f"start.{shell}")
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("ERROR:", result.stderr)
        self.assertFalse(Path(self.environment["JAVA_CALLS"]).exists())
        self.assertFalse(Path(str(self.backups) + ".called").exists())
        self.assertFalse((self.directory / ".tmp/startup/server.properties").exists())

    def test_shell_invalid_policy_stops_before_java_and_backup(self):
        self.check_invalid_policy("sh")

    def test_cmd_invalid_policy_stops_before_java_and_backup(self):
        self.check_invalid_policy("cmd")

    def check_standalone_migration(self, shell):
        self.prepare(shell, stub_backup=True)
        settings = self.directory / "settings"
        settings.mkdir()
        legacy = settings / "resource-packs.json"
        legacy.write_text('{"schema_version":1,"default":null,"worlds":{}}', encoding="utf-8")
        for unified_present in (False, True):
            with self.subTest(unified_present=unified_present):
                if unified_present:
                    (settings / "minecraft-server.json").write_text(
                        '{"schema_version":1,"values":{},"resource_packs":{"default":null,"worlds":{}}}',
                        encoding="utf-8")
                result = self.run_script(f"start.{shell}")
                self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                self.assertIn("move its default and worlds", result.stderr)
                self.assertTrue(legacy.is_file())
                self.assertFalse(Path(self.environment["JAVA_CALLS"]).exists())
                self.assertFalse(Path(str(self.backups) + ".called").exists())
                self.assertFalse((self.directory / ".tmp/startup/server.properties").exists())

    def test_shell_standalone_policy_requires_migration(self):
        self.check_standalone_migration("sh")

    def test_cmd_standalone_policy_requires_migration(self):
        self.check_standalone_migration("cmd")

    def check_linked_pack_policy(self, shell):
        self.prepare(shell, stub_backup=True)
        settings = self.directory / "settings"
        settings.mkdir()
        policy = settings / "minecraft-server.json"
        try:
            policy.symlink_to(self.directory / "missing.json")
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlinks unavailable: {error}")
        result = self.run_script(f"start.{shell}")
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("links and junctions", result.stderr)
        self.assertFalse(Path(self.environment["JAVA_CALLS"]).exists())
        self.assertFalse(Path(str(self.backups) + ".called").exists())

    def test_shell_dangling_pack_policy_does_not_fall_back(self):
        self.check_linked_pack_policy("sh")

    def test_cmd_dangling_pack_policy_does_not_fall_back(self):
        self.check_linked_pack_policy("cmd")

    def check_linked_settings_without_policy(self, shell):
        self.prepare(shell, stub_backup=True)
        outside = self.directory / "outside-settings"
        outside.mkdir()
        settings = self.directory / "settings"
        try:
            settings.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlinks unavailable: {error}")
        result = self.run_script(f"start.{shell}")
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("links and junctions", result.stderr)
        self.assertFalse(Path(self.environment["JAVA_CALLS"]).exists())
        self.assertFalse(Path(str(self.backups) + ".called").exists())

    def test_shell_linked_settings_without_policy_does_not_fall_back(self):
        self.check_linked_settings_without_policy("sh")

    def test_cmd_linked_settings_without_policy_does_not_fall_back(self):
        self.check_linked_settings_without_policy("cmd")

    def check_settings_file(self, shell):
        self.prepare(shell, stub_backup=True)
        settings = self.directory / "settings"
        settings.write_text("invalid settings directory", encoding="utf-8")
        settings.chmod(0o755)
        result = self.run_script(f"start.{shell}")
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertFalse(Path(self.environment["JAVA_CALLS"]).exists())
        self.assertFalse(Path(str(self.backups) + ".called").exists())

    def test_shell_settings_file_does_not_fall_back(self):
        self.check_settings_file("sh")

    def test_cmd_settings_file_does_not_fall_back(self):
        self.check_settings_file("cmd")

    def check_invalid(self, shell):
        self.prepare(shell, stub_backup=True)
        invalid = [("--world",), ("--world", ""), ("",), ("--unknown",),
                   ("bad&echo REVIEW_INJECTION",),
                   ("--world", "Adventure_A", "bad&echo REVIEW_INJECTION"),
                   ("--world", "../outside"), ("--world", "..\\outside"),
                   ("--world", "/absolute"), ("--world", "C:\\absolute"),
                   ("--world", "name space"), ("--world", "missing"),
                   ("--world", "world.name"), ("--world", "world!name"),
                   ("--world", "world&name"), ("--world", "地图"),
                   ("--world", "Adventure_A", "--world", "Puzzle-2"),
                   ("--world", "Adventure_A", "--unknown")]
        self.write("dimension-only/region/r.0.0.mca")
        (self.server / "not-a-file" / "level.dat").mkdir(parents=True)
        invalid.extend([("--world", "dimension-only"), ("--world", "not-a-file")])
        for arguments in invalid:
            with self.subTest(arguments=arguments):
                result = self.run_script(f"start.{shell}", *arguments)
                self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                self.assertIn("[start] ERROR:", result.stderr)
                self.assertNotIn("REVIEW_INJECTION", result.stdout)
                self.assertFalse(Path(self.environment["JAVA_CALLS"]).exists())
                self.assertFalse(Path(str(self.backups) + ".called").exists())
        self.assertFalse((self.server / "missing").exists())

    def test_shell_invalid_input_has_no_side_effects(self):
        self.check_invalid("sh")

    def test_cmd_invalid_input_has_no_side_effects(self):
        self.check_invalid("cmd")

    def check_link_refusal(self, shell):
        self.prepare(shell, stub_backup=True)
        linked_world = self.server / "linked-world"
        linked_level = self.server / "linked-level" / "level.dat"
        linked_level.parent.mkdir()
        outside = self.directory / "outside-save"
        outside.mkdir()
        (outside / "level.dat").write_bytes(b"outside save")
        try:
            linked_world.symlink_to(outside, target_is_directory=True)
            linked_level.symlink_to(outside / "level.dat")
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlinks unavailable: {error}")
        for name in ("linked-world", "linked-level"):
            with self.subTest(world=name):
                result = self.run_script(f"start.{shell}", "--world", name)
                self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                self.assertIn("no links", result.stderr)
                self.assertFalse(Path(self.environment["JAVA_CALLS"]).exists())
                self.assertFalse(Path(str(self.backups) + ".called").exists())

    def test_shell_refuses_linked_save_and_marker(self):
        self.check_link_refusal("sh")

    def test_cmd_refuses_linked_save_and_marker(self):
        self.check_link_refusal("cmd")

    def check_exit_status(self, shell):
        self.prepare(shell, stub_backup=True)
        self.environment.update(JAVA_RESULT="7", ASP_SKIP_BACKUP="1")
        result = self.run_script(f"start.{shell}", "--world", "Adventure_A")
        self.assertEqual(7, result.returncode, result.stdout + result.stderr)
        self.assertFalse(Path(str(self.backups) + ".called").exists())

    def test_shell_preserves_exit_and_backup_override(self):
        self.check_exit_status("sh")

    def test_cmd_preserves_exit_and_backup_override(self):
        self.check_exit_status("cmd")

    def check_backup(self, entrypoint):
        self.prepare("sh" if entrypoint.endswith(".sh") else "cmd")
        included = ["Adventure_A/level.dat", "Puzzle-2/level.dat",
                    "Adventure_A/data/minecraft/scoreboard.dat", "Puzzle-2/players/player.dat",
                    "Adventure_A/dimensions/minecraft/overworld/region/r.0.0.mca",
                    "Puzzle-2/datapacks/example.zip", "Sibling_nether/level.dat",
                    "Sibling_nether/dimensions/minecraft/the_nether/region/r.0.0.mca",
                    "config/paper-global.yml", "plugins/Example/cache/important.db",
                    "plugins/Example/config.yml", "plugins/Geyser-Spigot/config.yml",
                    "whitelist.json", "server.properties", "permissions.yml"]
        excluded = ["Adventure_A/session.lock", "Puzzle-2/level.dat_old",
                    "Puzzle-2/dimensions/minecraft/overworld/session.lock",
                    "plugins/Example/helper.jar", "plugins/extra.jar", "paper-server.jar",
                    "plugins/Geyser-Spigot/cache/generated", "plugins/SkinsRestorer/cache/generated",
                    "libraries/dependency.jar", "logs/latest.log", "unrelated/notes.txt",
                    "packs/pack-a.zip"]
        for relative in included + excluded:
            self.write(relative, relative.encode())
        settings = self.directory / "settings"
        settings.mkdir()
        (settings / "host.json").write_bytes(b'{"schema_version":1,"values":{"PACK_URL":""}}')
        (settings / "host.example.json").write_bytes(b"example")
        (settings / "minecraft-server.json").write_text(json.dumps({
            "schema_version": 1, "values": {"MANAGEMENT_SERVER_SECRET": "env:UNSET_BACKUP_SECRET"},
            "backup": {"targets": ["backups"]},
        }), encoding="utf-8")
        self.environment["SETTINGS_DIR"] = settings.as_posix()
        result = self.run_script(entrypoint, self.server.as_posix())
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        completed = list(self.backups.glob("*/COMPLETE"))
        self.assertEqual(1, len(completed), result.stdout + result.stderr)
        backup = completed[0].parent
        for relative in included:
            self.assertEqual((self.server / relative).read_bytes(), (backup / relative).read_bytes())
        for relative in excluded:
            self.assertFalse((backup / relative).exists(), relative)
        self.assertFalse((backup / "world").exists())
        self.assertEqual((settings / "host.json").read_bytes(), (backup / "settings/host.json").read_bytes())
        self.assertFalse((backup / "settings/host.example.json").exists())
        manifest = (backup / "MANIFEST.txt").read_text()
        for path in backup.rglob("*"):
            if path.is_file() and path.name not in ("MANIFEST.txt", "COMPLETE"):
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertIn(f"{digest}  ./{path.relative_to(backup).as_posix()}", manifest)
        process_query = Path(self.environment["PROCESS_LOG"]).read_text()
        self.assertIn("paper-server", process_query)
        self.assertNotIn("asp-server", process_query)

    def test_shell_backup_covers_inactive_native_saves(self):
        self.check_backup("backup.sh")

    def test_cmd_backup_covers_inactive_native_saves(self):
        self.check_backup("backup.cmd")

    def test_debug_backup_uses_same_scope(self):
        self.check_backup("backup-debug.cmd")

    def test_backup_refuses_native_save_and_snapshot_directory_collision(self):
        for entrypoint in ("backup.sh", "backup.cmd", "backup-debug.cmd"):
            with self.subTest(entrypoint=entrypoint):
                self.prepare("sh" if entrypoint.endswith(".sh") else "cmd")
                self.write("settings/level.dat", b"native save")
                result = self.run_script(entrypoint, self.server.as_posix())
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                self.assertIn("collides with snapshot directory", result.stdout + result.stderr)
                self.assertFalse(self.backups.exists())

    def check_online_refusal(self, shell):
        self.prepare(shell)
        self.write_backup_settings(["backups"])
        self.environment["PROCESS_RESULT"] = "2"
        result = self.run_script(f"backup.{shell}", str(self.server))
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("Paper server is running", result.stdout + result.stderr)
        self.assertFalse(self.backups.exists())

    def test_shell_backup_refuses_running_paper(self):
        self.check_online_refusal("sh")

    def test_cmd_backup_refuses_running_paper(self):
        self.check_online_refusal("cmd")

    def write_backup_settings(self, targets):
        settings = self.directory / "settings"
        settings.mkdir(exist_ok=True)
        path = settings / "minecraft-server.json"
        path.write_text(json.dumps({"schema_version": 1,
                                   "values": {"SECRET": "env:UNSET_BACKUP_SECRET"},
                                   "backup": {"targets": targets}}), encoding="utf-8")
        return path

    def check_backup_destinations(self, shell):
        self.prepare(shell)
        primary = self.directory / "primary backups"
        mirror = self.directory / "other disk/mirror backups"
        self.write_backup_settings(["primary backups", str(mirror)])
        for target in (primary, mirror):
            for stamp in ("20000101-000001", "20000101-000002", "20000101-000003"):
                directory = target / stamp
                directory.mkdir(parents=True)
                (directory / "old.txt").write_text("old snapshot")
                if stamp != "20000101-000003":
                    (directory / "COMPLETE").write_text("")
            (target / "unrelated").mkdir()
            (target / "unrelated/keep.txt").write_text("keep")
        self.environment["KEEP"] = "2"
        result = self.run_script(f"backup.{shell}")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        for target in (primary, mirror):
            complete = list(target.glob("*/COMPLETE"))
            self.assertEqual(2, len(complete))
            self.assertFalse((target / "20000101-000001").exists())
            self.assertFalse((target / "20000101-000003").exists())
            self.assertEqual("keep", (target / "unrelated/keep.txt").read_text())
            current = next(marker.parent for marker in complete if marker.parent.name != "20000101-000002")
            self.assertEqual((self.server / "Adventure_A/level.dat").read_bytes(),
                             (current / "Adventure_A/level.dat").read_bytes())
            self.assertIn("./settings/minecraft-server.json", (current / "MANIFEST.txt").read_text())
        before = {str(path): path.read_bytes() for target in (primary, mirror)
                  for path in target.rglob("*") if path.is_file()}
        self.environment["BACKUP_MIN_INTERVAL"] = "60"
        result = self.run_script(f"backup.{shell}")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("SKIP", result.stdout)
        self.assertEqual(before, {str(path): path.read_bytes() for target in (primary, mirror)
                                  for path in target.rglob("*") if path.is_file()})

    def test_shell_configured_destinations_mirror_retention_and_interval(self):
        self.check_backup_destinations("sh")

    def test_cmd_configured_destinations_mirror_retention_and_interval(self):
        self.check_backup_destinations("cmd")

    def check_backup_missing_and_legacy_settings(self, shell):
        self.prepare(shell)
        result = self.run_script(f"backup.{shell}")
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("settings", result.stdout + result.stderr)
        self.assertFalse(self.backups.exists())
        path = self.write_backup_settings(["backups"])
        for name in ("BACKUP_ROOT", "BACKUP_TARGETS"):
            self.environment[name] = str(self.backups)
            result = self.run_script(f"backup.{shell}")
            self.assertEqual(1, result.returncode, result.stdout + result.stderr)
            self.assertIn("move destinations into backup.targets", result.stdout + result.stderr)
            self.assertFalse(self.backups.exists())
            del self.environment[name]
        path.write_text('{"schema_version":1,"values":{}}', encoding="utf-8")
        result = self.run_script(f"backup.{shell}")
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("configure backup.targets", result.stdout + result.stderr)
        self.assertFalse(self.backups.exists())

    def test_shell_backup_requires_configured_destinations(self):
        self.check_backup_missing_and_legacy_settings("sh")

    def test_cmd_backup_requires_configured_destinations(self):
        self.check_backup_missing_and_legacy_settings("cmd")

    def check_backup_unsafe_destinations(self, shell):
        self.prepare(shell)
        (self.directory / "target-file").write_text("keep")
        for targets in (["backups", "backups/nested"], ["backups", "./backups"],
                        ["backups", "server/snapshot"], ["backups", "settings/snapshot"],
                        ["backups", "target-file"]):
            self.write_backup_settings(targets)
            result = self.run_script(f"backup.{shell}")
            self.assertEqual(1, result.returncode, result.stdout + result.stderr)
            self.assertFalse(self.backups.exists())
            self.assertEqual("keep", (self.directory / "target-file").read_text())

    def test_shell_validates_all_destinations_before_first_copy(self):
        self.check_backup_unsafe_destinations("sh")

    def test_cmd_validates_all_destinations_before_first_copy(self):
        self.check_backup_unsafe_destinations("cmd")

    def test_cmd_refuses_destination_metacharacters_before_copy(self):
        self.prepare("cmd")
        for character in "!%&^|<>()\"":
            with self.subTest(character=character):
                self.write_backup_settings(["backups", "unsafe" + character + "target"])
                result = self.run_script("backup.cmd")
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                self.assertIn("CMD backup paths cannot contain", result.stdout + result.stderr)
                self.assertFalse(self.backups.exists())

    def test_shell_destination_metacharacters_remain_literal_data(self):
        self.prepare("sh")
        name = "literal !%&;$(touch injected) ' path"
        self.write_backup_settings([name])
        result = self.run_script("backup.sh")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        complete = list((self.directory / name).glob("*/COMPLETE"))
        self.assertEqual(1, len(complete))
        self.assertFalse((self.elsewhere / "injected").exists())
        self.assertFalse((self.scripts / "injected").exists())

    def check_backup_preserves_complete_snapshot_when_prune_refuses_link(self, shell):
        self.prepare(shell)
        self.write_backup_settings(["backups"])
        old = self.backups / "20000101-000000"
        old.mkdir(parents=True)
        outside = self.directory / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("keep")
        try:
            (old / "unsafe-link").symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        result = self.run_script(f"backup.{shell}")
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertEqual("keep", (outside / "keep.txt").read_text())
        self.assertTrue((old / "unsafe-link").is_symlink())
        complete = list(self.backups.glob("*/COMPLETE"))
        self.assertEqual(1, len(complete))
        self.assertEqual((self.server / "Adventure_A/level.dat").read_bytes(),
                         (complete[0].parent / "Adventure_A/level.dat").read_bytes())

    def test_shell_cleanup_preserves_external_and_complete_data(self):
        self.check_backup_preserves_complete_snapshot_when_prune_refuses_link("sh")

    def test_cmd_cleanup_preserves_external_and_complete_data(self):
        self.check_backup_preserves_complete_snapshot_when_prune_refuses_link("cmd")

    def test_windows_cleanup_refuses_destination_outside_target(self):
        if os.name != "nt":
            self.skipTest("Windows PowerShell cleanup is available only on Windows")
        self.backups.mkdir()
        outside = self.directory / "20000101-000000"
        outside.mkdir()
        (outside / "keep.txt").write_text("keep")
        result = subprocess.run(
            [self.powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             str(self.scripts / "backup_cleanup.ps1"), "-Action", "remove"],
            env=dict(self.environment, TDIR=str(self.backups), DEST=str(outside)),
            capture_output=True, text=True, timeout=20, check=False)
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("escaped its target", result.stderr)
        self.assertEqual("keep", (outside / "keep.txt").read_text())

    def check_native_invalid_backup_destination(self, shell):
        if os.name != "nt":
            self.skipTest("Windows native path rules")
        self.prepare(shell)
        for target in ("COM1", "bad:stream", "trailing."):
            with self.subTest(target=target):
                self.write_backup_settings(["backups", target])
                result = self.run_script(f"backup.{shell}")
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                self.assertIn("invalid Windows path component", result.stdout + result.stderr)
                self.assertFalse(self.backups.exists())

    def test_cmd_refuses_native_invalid_destination_before_first_copy(self):
        self.check_native_invalid_backup_destination("cmd")

    def test_windows_bash_refuses_native_invalid_destination_before_first_copy(self):
        self.check_native_invalid_backup_destination("sh")


if __name__ == "__main__":
    unittest.main()
