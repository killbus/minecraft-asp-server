"""Applying the tracked configuration bundle, using isolated fixture directories only."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from tests import scratch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("apply_config", SCRIPTS / "apply_config.py")
apply_config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(apply_config)


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


class ApplyConfigTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(scratch.directory("apply-config-"))
        self.config = self.directory / "config"
        self.config.mkdir()
        self.server = self.directory / "server"
        self.server.mkdir()
        self.lock_path = self.directory / "config.lock.json"
        self.settings_path = self.directory / "settings.json"
        self.files = []
        self.environment = patch.dict(os.environ)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        for name in (
            "PACK_URL",
            "SECRET",
            "PORT",
            "GEYSER_ADVERTISE_ADDRESS",
            "BSTATS_SERVER_UUID",
            "MANAGEMENT_SERVER_SECRET",
            "WORLD_LIFECYCLE_MANAGED_WORLDS",
        ):
            os.environ.pop(name, None)

    def add(self, relative, payload, placeholders=(), classification="source"):
        path = self.config / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        self.files.append(
            {
                "path": relative,
                "class": classification,
                "sha256": digest(payload),
                "placeholders": list(placeholders),
            }
        )
        return path

    def save(self):
        self.lock_path.write_text(
            json.dumps({"schema_version": 1, "files": self.files}), encoding="utf-8"
        )

    def save_settings(self, values, schema_version=1):
        self.settings_path.write_text(
            json.dumps({"schema_version": schema_version, "values": values}),
            encoding="utf-8",
        )

    def run_tool(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = apply_config.main(
                [
                    "--config-dir",
                    str(self.config),
                    "--lock",
                    str(self.lock_path),
                    "--server-dir",
                    str(self.server),
                    *args,
                ]
            )
        return code, output.getvalue(), errors.getvalue()

    def assert_refused(self, contains=None, *args):
        code, output, errors = self.run_tool(*args)
        self.assertEqual(2, code, (output, errors))
        self.assertIn("ERROR:", errors)
        self.assertNotIn("Traceback", errors)
        if contains is not None:
            self.assertIn(contains, errors)
        return errors

    def test_render_writes_the_rendered_bytes(self):
        self.add("server.properties", b"motd=Hi\nurl=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        code, output, errors = self.run_tool("--set", "PACK_URL=https://host/packs/a.zip")
        self.assertEqual(0, code, errors)
        self.assertIn("CREATE", output)
        self.assertEqual(
            b"motd=Hi\nurl=https://host/packs/a.zip\n",
            (self.server / "server.properties").read_bytes(),
        )

    def test_second_run_is_unchanged(self):
        self.add("server.properties", b"port=${PORT}\n", [{"name": "PORT"}])
        self.save()
        self.assertEqual(0, self.run_tool("--set", "PORT=25565")[0])
        code, output, errors = self.run_tool("--set", "PORT=25565")
        self.assertEqual(0, code, errors)
        self.assertIn("UNCHANGED", output)
        self.assertNotIn("CREATE", output)

    def test_update_replaces_an_existing_difference(self):
        self.add("server.properties", b"port=${PORT}\n", [{"name": "PORT"}])
        self.save()
        (self.server / "server.properties").write_bytes(b"port=1\n")
        code, output, errors = self.run_tool("--set", "PORT=25565")
        self.assertEqual(0, code, errors)
        self.assertIn("UPDATE", output)
        self.assertEqual(b"port=25565\n", (self.server / "server.properties").read_bytes())

    def test_value_comes_from_the_environment(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        os.environ["PACK_URL"] = "https://env/packs/a.zip"
        code, _, errors = self.run_tool()
        self.assertEqual(0, code, errors)
        self.assertIn(
            b"https://env/packs/a.zip",
            (self.server / "server.properties").read_bytes(),
        )

    def test_set_wins_over_the_environment(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        os.environ["PACK_URL"] = "https://env/a.zip"
        self.assertEqual(0, self.run_tool("--set", "PACK_URL=https://flag/a.zip")[0])
        self.assertIn(b"https://flag/a.zip", (self.server / "server.properties").read_bytes())

    def test_missing_value_is_refused_before_any_write(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        self.assert_refused("no value for ${PACK_URL}")
        self.assertFalse((self.server / "server.properties").exists())

    def test_malformed_set_is_refused(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        self.assert_refused("NAME=VALUE", "--set", "PACK_URL")

    def test_duplicate_set_is_refused(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        self.assert_refused("twice", "--set", "PACK_URL=a", "--set", "PACK_URL=b")

    def test_unused_set_value_is_not_inspected(self):
        self.add("server.properties", b"port=1\n")
        self.save()
        code, _, errors = self.run_tool("--set", "UNUSED=${X}")
        self.assertEqual(0, code, errors)

    def test_settings_supply_the_values(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        self.save_settings({"PACK_URL": "https://host/a.zip"})
        code, output, errors = self.run_tool("--settings", str(self.settings_path))
        self.assertEqual(0, code, errors)
        self.assertIn("settings   ", output)
        self.assertIn(
            b"url=https://host/a.zip",
            (self.server / "server.properties").read_bytes(),
        )

    def test_set_wins_over_settings(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        self.save_settings({"PACK_URL": "https://host/a.zip"})
        code, _, errors = self.run_tool(
            "--settings",
            str(self.settings_path),
            "--set",
            "PACK_URL=https://flag/b.zip",
        )
        self.assertEqual(0, code, errors)
        self.assertIn(
            b"url=https://flag/b.zip",
            (self.server / "server.properties").read_bytes(),
        )

    def test_settings_win_over_the_environment(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        self.save_settings({"PACK_URL": "https://host/a.zip"})
        os.environ["PACK_URL"] = "https://env/b.zip"
        code, _, errors = self.run_tool("--settings", str(self.settings_path))
        self.assertEqual(0, code, errors)
        self.assertIn(
            b"url=https://host/a.zip",
            (self.server / "server.properties").read_bytes(),
        )

    def test_settings_env_reference_is_resolved(self):
        self.add("server.properties", b"seed=${SECRET}\n", [{"name": "SECRET"}])
        self.save()
        self.save_settings({"SECRET": "env:SOURCE"})
        with patch.dict(os.environ, {"SOURCE": "s3cret"}):
            code, _, errors = self.run_tool("--settings", str(self.settings_path))
        self.assertEqual(0, code, errors)
        self.assertIn(b"seed=s3cret", (self.server / "server.properties").read_bytes())

    def test_settings_env_reference_that_is_unset_is_refused(self):
        self.add("server.properties", b"seed=${SECRET}\n", [{"name": "SECRET"}])
        self.save()
        self.save_settings({"SECRET": "env:ABSENT_VARIABLE"})
        self.assert_refused("ABSENT_VARIABLE", "--settings", str(self.settings_path))
        self.assertFalse((self.server / "server.properties").exists())

    def test_settings_name_no_template_declares_is_refused(self):
        self.add("server.properties", b"port=1\n")
        self.save()
        self.save_settings({"TYPO": "x"})
        self.assert_refused("no template declares", "--settings", str(self.settings_path))

    def test_settings_blank_value_is_refused(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        self.save_settings({"PACK_URL": ""})
        self.assert_refused("nonblank", "--settings", str(self.settings_path))

    def test_settings_value_that_holds_a_placeholder_is_refused(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        self.save_settings({"PACK_URL": "${HOST}/a.zip"})
        self.assert_refused("must not hold", "--settings", str(self.settings_path))

    def test_settings_require_schema_version_one(self):
        self.add("server.properties", b"port=1\n")
        self.save()
        self.save_settings({"PACK_URL": "https://host/a.zip"}, schema_version=2)
        self.assert_refused("schema_version 1", "--settings", str(self.settings_path))

    def test_settings_file_that_is_absent_is_refused(self):
        self.add("server.properties", b"port=1\n")
        self.save()
        self.assert_refused(
            "cannot read settings", "--settings", str(self.directory / "nope.json")
        )

    def test_settings_unknown_top_level_key_is_refused(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        self.settings_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "value": {"PACK_URL": "https://host/a.zip"},
                }
            ),
            encoding="utf-8",
        )
        self.assert_refused("unknown key", "--settings", str(self.settings_path))

    def test_default_renders_when_the_host_supplies_nothing(self):
        self.add(
            "plugins/bStats/config.yml",
            b"serverUuid: ${BSTATS_SERVER_UUID}\n",
            [{"name": "BSTATS_SERVER_UUID", "default": "11111111-2222"}],
        )
        self.save()
        code, _, errors = self.run_tool()
        self.assertEqual(0, code, errors)
        self.assertIn(
            b"serverUuid: 11111111-2222",
            (self.server / "plugins/bStats/config.yml").read_bytes(),
        )

    def test_placeholder_the_manifest_does_not_declare_is_refused(self):
        self.add(
            "server.properties",
            b"url=${PACK_URL}\nport=${PORT}\n",
            [{"name": "PACK_URL"}],
        )
        self.save()
        self.assert_refused("${PORT}", "--set", "PACK_URL=https://a/b.zip")

    def test_value_that_still_holds_a_placeholder_is_refused(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        self.assert_refused(
            "still contains a placeholder", "--set", "PACK_URL=${HOST}/p.zip"
        )

    def test_public_http_pack_url_is_refused(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        errors = self.assert_refused(
            "must be https", "--set", "PACK_URL=http://host/packs/a.zip"
        )
        self.assertFalse((self.server / "server.properties").exists())

    def test_loopback_http_pack_url_is_accepted(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        code, _, errors = self.run_tool(
            "--set", "PACK_URL=http://127.0.0.1:8000/packs/pack-a.zip"
        )
        self.assertEqual(0, code, errors)
        self.assertIn(
            b"url=http://127.0.0.1:8000/packs/pack-a.zip",
            (self.server / "server.properties").read_bytes(),
        )

    def test_instance_class_is_refused(self):
        self.add(
            "plugins/Multiverse-Core/worlds.yml",
            b"world: {}\n",
            classification="instance",
        )
        self.save()
        self.assert_refused("only source may be applied")

    def test_instance_path_is_refused_even_when_the_manifest_says_source(self):
        self.add("plugins/Multiverse-Core/worlds.yml", b"world: {}\n")
        self.save()
        self.assert_refused("instance state")

    def test_mvi_instance_files_cannot_be_smuggled_into_a_bundle(self):
        for relative in (
            "plugins/Multiverse-Inventories/groups.yml",
            "plugins/Multiverse-Inventories/playernames.json",
            "plugins/Multiverse-Inventories/worlds/adventure/player.json",
            "plugins/Multiverse-Inventories/groups/shared/player.json",
            "plugins/Multiverse-Inventories/players/player.json",
        ):
            with self.subTest(relative=relative):
                self.files.clear()
                self.add(relative, b"existing state\n")
                self.save()
                self.assert_refused("instance state")
                self.assertFalse((self.server / relative).exists())

    def test_managed_worlds_require_an_explicit_value_before_any_write(self):
        self.add("server.properties", b"motd=Changed\n")
        self.add(
            "plugins/MultiverseWorldLifecycle/config.yml",
            b"managed-worlds: ${WORLD_LIFECYCLE_MANAGED_WORLDS}\n",
            [{"name": "WORLD_LIFECYCLE_MANAGED_WORLDS"}],
        )
        self.save()
        self.assert_refused("no value for ${WORLD_LIFECYCLE_MANAGED_WORLDS}")
        self.assertEqual([], list(self.server.rglob("*")))

    def test_case_variant_mvi_manifest_paths_preserve_existing_state(self):
        variants = (
            ("groups.yml", "plugins/Multiverse-Inventories/GROUPS.YML"),
            ("groups.yml", "plugins/multiverse-inventories/groups.yml"),
            ("groups.yml", "Plugins/Multiverse-Inventories/groups.yml"),
            ("playernames.json", "PLUGINS/MULTIVERSE-INVENTORIES/PLAYERNAMES.JSON"),
            ("worlds/actor.json", "plugins/Multiverse-Inventories/WORLDS/actor.json"),
            ("groups/shared/actor.json", "Plugins/multiverse-inventories/GROUPS/shared/actor.json"),
            ("players/actor.json", "plugins/MULTIVERSE-INVENTORIES/PLAYERS/actor.json"),
        )
        for canonical, forged in variants:
            with self.subTest(forged=forged):
                existing = self.server / "plugins/Multiverse-Inventories" / canonical
                existing.parent.mkdir(parents=True, exist_ok=True)
                existing.write_bytes(b"preserve existing player state\n")
                before = (existing.read_bytes(), existing.stat().st_mtime_ns)
                self.files.clear()
                self.add("server.properties", b"motd=must not apply\n")
                self.add(forged, b"forged source replacement\n")
                self.save()

                self.assert_refused("instance state")

                self.assertEqual(before, (existing.read_bytes(), existing.stat().st_mtime_ns))
                self.assertFalse((self.server / "server.properties").exists())

    def test_managed_worlds_validate_all_input_channels(self):
        self.add(
            "plugins/MultiverseWorldLifecycle/config.yml",
            b"managed-worlds: ${WORLD_LIFECYCLE_MANAGED_WORLDS}\n",
            [{"name": "WORLD_LIFECYCLE_MANAGED_WORLDS"}],
        )
        self.save()
        name = "WORLD_LIFECYCLE_MANAGED_WORLDS"
        for value in (
            "adventure", "{}", "null", '["adventure", "adventure"]',
            '[""]', '[" adventure"]', '[3]', '[{}]', '["bad\\nname"]', '["bad\\u007fname"]',
        ):
            for channel in ("settings", "environment", "set"):
                with self.subTest(value=value, channel=channel):
                    arguments = []
                    if channel == "settings":
                        self.save_settings({name: value})
                        arguments = ["--settings", str(self.settings_path)]
                    elif channel == "set":
                        arguments = ["--set", f"{name}={value}"]
                    with patch.dict(os.environ, {name: value} if channel == "environment" else {}):
                        self.assert_refused("must be a JSON array", *arguments)
                    self.assertEqual([], list(self.server.rglob("*")))

    def test_managed_worlds_render_as_a_normalized_yaml_flow_list(self):
        relative = "plugins/MultiverseWorldLifecycle/config.yml"
        self.add(
            relative,
            b"managed-worlds: ${WORLD_LIFECYCLE_MANAGED_WORLDS}\n",
            [{"name": "WORLD_LIFECYCLE_MANAGED_WORLDS"}],
        )
        self.save()
        for worlds in ([], ["adventure", "minecraft:arena", 'quoted"world']):
            with self.subTest(worlds=worlds):
                self.save_settings({"WORLD_LIFECYCLE_MANAGED_WORLDS": json.dumps(worlds, indent=2)})
                arguments = ["--settings", str(self.settings_path)]
                code, _, errors = self.run_tool(*arguments)
                self.assertEqual(0, code, errors)
                self.assertEqual(
                    f"managed-worlds: {json.dumps(worlds)}\n".encode(),
                    (self.server / relative).read_bytes(),
                )
                self.assertEqual(0, self.run_tool("--check", *arguments)[0])

    def test_template_hash_drift_is_refused(self):
        self.add("server.properties", b"port=${PORT}\n", [{"name": "PORT"}])
        self.save()
        (self.config / "server.properties").write_bytes(b"port=${PORT}\n# edited\n")
        self.assert_refused("drifted from the manifest", "--set", "PORT=1")
        self.assertFalse((self.server / "server.properties").exists())

    def test_a_refusal_does_not_apply_the_entries_before_it(self):
        self.add("a.yml", b"a=1\n")
        self.add("b.yml", b"b=${B}\n", [{"name": "B"}])
        self.save()
        (self.config / "b.yml").write_bytes(b"b=${B}\n# edited\n")
        self.assert_refused("drifted from the manifest", "--set", "B=2")
        self.assertFalse((self.server / "a.yml").exists())
        self.assertFalse((self.server / "b.yml").exists())

    def test_dry_run_writes_nothing(self):
        self.add("server.properties", b"port=${PORT}\n", [{"name": "PORT"}])
        self.save()
        code, output, errors = self.run_tool("--dry-run", "--set", "PORT=1")
        self.assertEqual(0, code, errors)
        self.assertIn("CREATE", output)
        self.assertFalse((self.server / "server.properties").exists())

    def test_check_exits_one_on_a_difference_without_writing(self):
        self.add("server.properties", b"port=${PORT}\n", [{"name": "PORT"}])
        self.save()
        code, output, errors = self.run_tool("--check", "--set", "PORT=1")
        self.assertEqual(1, code, errors)
        self.assertIn("CREATE", output)
        self.assertFalse((self.server / "server.properties").exists())

    def test_check_exits_zero_when_the_host_matches(self):
        self.add("server.properties", b"port=${PORT}\n", [{"name": "PORT"}])
        self.save()
        self.assertEqual(0, self.run_tool("--set", "PORT=1")[0])
        code, output, errors = self.run_tool("--check", "--set", "PORT=1")
        self.assertEqual(0, code, errors)
        self.assertIn("UNCHANGED", output)

    def test_file_outside_the_manifest_is_refused(self):
        self.add("server.properties", b"port=1\n")
        self.save()
        (self.config / "stray.yml").write_bytes(b"x: 1\n")
        self.assert_refused("not in the manifest")
        self.assertFalse((self.server / "server.properties").exists())

    def test_manifest_entry_without_a_template_is_refused(self):
        self.add("server.properties", b"port=1\n")
        self.save()
        (self.config / "server.properties").unlink()
        self.assert_refused("missing from")

    def test_escaping_path_never_reaches_the_server_dir(self):
        self.files.append(
            {
                "path": "../outside.yml",
                "class": "source",
                "sha256": digest(b"x"),
                "placeholders": [],
            }
        )
        self.save()
        self.assert_refused()
        self.assertFalse((self.directory / "outside.yml").exists())

    def test_plain_crlf_survives_rendering(self):
        self.add(
            "server.properties",
            b"motd=Hi\r\nurl=${PACK_URL}\r\n",
            [{"name": "PACK_URL"}],
        )
        self.save()
        code, _, errors = self.run_tool("--set", "PACK_URL=https://a/b.zip")
        self.assertEqual(0, code, errors)
        payload = (self.server / "server.properties").read_bytes()
        self.assertEqual(b"motd=Hi\r\nurl=https://a/b.zip\r\n", payload)

    def test_duplicate_manifest_key_is_refused(self):
        self.lock_path.write_text('{"files": [], "files": []}', encoding="utf-8")
        self.assert_refused("duplicate JSON key")

    def test_absent_server_tree_is_created(self):
        self.add("plugins/GrimAC/config.yml", b"alerts: true\n")
        self.save()
        self.server.rmdir()
        code, output, errors = self.run_tool()
        self.assertEqual(0, code, errors)
        self.assertIn("CREATE", output)
        self.assertEqual(
            b"alerts: true\n",
            (self.server / "plugins/GrimAC/config.yml").read_bytes(),
        )

    def test_server_path_that_is_a_file_is_refused(self):
        self.add("server.properties", b"port=1\n")
        self.save()
        self.server.rmdir()
        self.server.write_bytes(b"not a directory")
        self.assert_refused("not a directory")

    def test_round_trip_against_a_fixture_server(self):
        expected = self.directory / "fixture"
        (expected / "plugins/GrimAC").mkdir(parents=True)
        self.add(
            "server.properties",
            b"motd=Fixture\r\nurl=${PACK_URL}\r\nsecret=${SECRET}\r\n",
            [{"name": "PACK_URL"}, {"name": "SECRET"}],
        )
        self.add("plugins/GrimAC/config.yml", b"alerts:\n  print-to-console: true\n")
        self.save()
        (expected / "server.properties").write_bytes(
            b"motd=Fixture\r\nurl=https://host/packs/a.zip\r\nsecret=s3cret\r\n"
        )
        (expected / "plugins/GrimAC/config.yml").write_bytes(
            b"alerts:\n  print-to-console: true\n"
        )
        code, output, errors = self.run_tool(
            "--set",
            "PACK_URL=https://host/packs/a.zip",
            "--set",
            "SECRET=s3cret",
        )
        self.assertEqual(0, code, errors)
        for relative in ("server.properties", "plugins/GrimAC/config.yml"):
            self.assertEqual(
                (expected / relative).read_bytes(),
                (self.server / relative).read_bytes(),
                relative,
            )
        self.assertEqual(2, output.count("CREATE"))


class ClassificationTests(unittest.TestCase):
    def test_source_and_instance_boundary(self):
        source = (
            "server.properties",
            "bukkit.yml",
            "config/paper-global.yml",
            "plugins/GrimAC/config.yml",
            "plugins/GrimAC/databases/mysql.yml",
            "plugins/Multiverse-Core/config.yml",
            "plugins/Multiverse-Inventories/config.yml",
            "plugins/MultiverseWorldLifecycle/config.yml",
            "Plugins/multiverse-inventories/CONFIG.YML",
            "plugins/PackManagerPro/config.yml",
        )
        instance = (
            "world/level.dat",
            "logs/latest.log",
            "cache/foo",
            ".paper/x",
            "libraries/a.jar",
            "versions/a.jar",
            "packs/pack-a.zip",
            "plugins/Multiverse-Core/worlds.yml",
            "plugins/Multiverse-Core/anchors.yml",
            "plugins/Multiverse-Inventories/groups.yml",
            "plugins/Multiverse-Inventories/playernames.json",
            "plugins/Multiverse-Inventories/worlds/adventure/player.json",
            "plugins/Multiverse-Inventories/groups/shared/player.json",
            "plugins/Multiverse-Inventories/players/player.json",
            "PLUGINS/MULTIVERSE-INVENTORIES/GROUPS.YML",
            "Plugins/multiverse-inventories/WORLDS/actor.json",
            "World/players/data/actor.dat",
            "Plugins/CoreProtect/DATABASE.DB",
            "plugins/floodgate/key.pem",
            "plugins/CoreProtect/.license",
            "plugins/CoreProtect/database.db",
            "plugins/GrimAC/data/history.v1.db",
            "plugins/Geyser-Spigot/nethernet/identity.pem",
            "plugins/SkinsRestorer/players/a.player",
            "plugins/SkinsRestorer/skins/b.playerskin",
            "plugins/SkinsRestorer/cache/x",
            "ops.json",
            "usercache.json",
            "eula.txt",
            "world.7z",
        )
        for relative in source:
            self.assertEqual("source", apply_config.classify(relative), relative)
        for relative in instance:
            self.assertEqual("instance", apply_config.classify(relative), relative)


class RepositoryConfigTests(unittest.TestCase):
    """The committed bundle must render safely and reproduce an adopted server."""

    @classmethod
    def setUpClass(cls):
        cls.repository = Path(__file__).resolve().parents[1]

    def live_text(self, relative):
        path = self.repository / "server" / relative
        if not path.is_file():
            self.skipTest(f"live server file is absent: {relative}")
        return path.read_text(encoding="utf-8")

    def live_property(self, relative, key):
        """Read `key=value` out of a .properties file."""
        for line in self.live_text(relative).splitlines():
            if line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name == key:
                return value
        self.skipTest(f"{key} is absent from the live {relative}")

    def live_yaml(self, relative, *path):
        """Read a scalar at a YAML key path, honouring indentation."""
        stack = []
        for line in self.live_text(relative).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("- "):
                continue
            if ":" not in stripped:
                continue
            indent = len(line) - len(line.lstrip(" "))
            name, _, value = stripped.partition(":")
            while stack and stack[-1][0] >= indent:
                stack.pop()
            stack.append((indent, name.strip()))
            if tuple(part for _, part in stack) == path and value.strip():
                return value.strip().strip("\"'")
        self.skipTest(f"{'/'.join(path)} is absent from the live {relative}")

    def live_list_first(self, relative, key):
        """Read the first `- item` under a bare `key:` in a YAML file."""
        capture = False
        for line in self.live_text(relative).splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if stripped.startswith(f"{key}:"):
                capture = True
                continue
            if capture and stripped.startswith("- "):
                return stripped[2:].strip().strip("\"'")
        self.skipTest(f"{key} is absent from the live {relative}")

    def test_templates_request_the_proxy_header_the_mux_sends(self):
        # The scene's Java backend always carries send-proxy-v2. Paper and
        # Geyser must accept that header, or every Java connection dies on
        # the first bytes. Both sides move together, so pin them here.
        paper = (self.repository / "config/config/paper-global.yml").read_text(
            encoding="utf-8"
        )
        geyser = (
            self.repository / "config/plugins/Geyser-Spigot/config.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("  proxy-protocol: true", paper)
        self.assertIn("    use-haproxy-protocol: true", geyser)

    def run_tool(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = apply_config.main(list(args))
        return code, output.getvalue(), errors.getvalue()

    def test_committed_bundle_preserves_profiles_and_renders_lifecycle_policy(self):
        with scratch.directory("repository-player-state-") as temporary:
            server = temporary / "server"
            preserved = {}
            for relative in (
                "plugins/Multiverse-Core/worlds.yml",
                "plugins/Multiverse-Inventories/groups.yml",
                "plugins/Multiverse-Inventories/playernames.json",
                "plugins/Multiverse-Inventories/worlds/adventure/player.json",
                "plugins/Multiverse-Inventories/groups/shared/player.json",
                "plugins/Multiverse-Inventories/players/player.json",
                "world/players/data/player.dat",
            ):
                path = server / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"host state: {relative}".encode())
                preserved[path] = (path.read_bytes(), path.stat().st_mtime_ns)
            settings = temporary / "settings.json"
            settings.write_text(json.dumps({
                "schema_version": 1,
                "values": {
                    "PACK_URL": "https://packs.example.test/packs/a.zip",
                    "GEYSER_ADVERTISE_ADDRESS": "relay.example.test:34003",
                    "WORLD_LIFECYCLE_MANAGED_WORLDS": '["adventure", "arena"]',
                    "MANAGEMENT_SERVER_SECRET": "env:MANAGEMENT_SERVER_SECRET",
                },
            }), encoding="utf-8")
            arguments = ["--server-dir", str(server), "--settings", str(settings)]
            with patch.dict(os.environ, {"MANAGEMENT_SERVER_SECRET": "fixture-secret"}):
                code, output, errors = self.run_tool(*arguments)
                self.assertEqual(0, code, errors)
                expected_count = len(apply_config.read_manifest(self.repository / "config.lock.json"))
                self.assertEqual(expected_count, output.count("CREATE"))
                code, output, errors = self.run_tool("--check", *arguments)
                self.assertEqual(0, code, errors)
                self.assertEqual(expected_count, output.count("UNCHANGED"))
            for path, expected in preserved.items():
                self.assertEqual(expected, (path.read_bytes(), path.stat().st_mtime_ns))
            lifecycle = (server / "plugins/MultiverseWorldLifecycle/config.yml").read_text(encoding="utf-8")
            self.assertIn('managed-worlds: ["adventure", "arena"]', lifecycle)
            self.assertIn("login-prepare-timeout-seconds: 30", lifecycle)
            self.assertIn("login-completion-timeout-seconds: 60", lifecycle)
            multiverse = (server / "plugins/Multiverse-Core/config.yml").read_text(encoding="utf-8")
            self.assertIn("enable-join-destination: false", multiverse)
            inventories = (server / "plugins/Multiverse-Inventories/config.yml").read_text(encoding="utf-8")
            for expected in (
                "  - last_location", "  - game_statistics",
                "default-ungrouped-worlds: false", "first-run: false",
                "use-optionals-for-ungrouped-worlds: true",
                "apply-last-location-for-all-teleports: false",
                "apply-playerdata-on-join: false", "always-write-world-profile: true",
            ):
                self.assertIn(expected, inventories)

    @unittest.skipUnless(
        (Path(__file__).resolve().parents[1] / "server").is_dir(), "no live server tree"
    )
    def test_committed_bundle_round_trips_the_live_server(self):
        # The coordinates live only in the gitignored server tree; the
        # credential comes from the environment. This is the documented deploy
        # shape, so the settings path is exercised for real.
        with scratch.directory("repository-") as temporary:
            settings = Path(temporary) / "minecraft-server.json"
            settings.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "values": {
                            "PACK_URL": self.live_yaml(
                                "plugins/PackManagerPro/config.yml",
                                "per-world-application",
                                "trials",
                                "pack-url",
                            ),
                            "GEYSER_ADVERTISE_ADDRESS": self.live_list_first(
                                "plugins/Geyser-Spigot/config.yml",
                                "advertise-addresses",
                            ),
                            "WORLD_LIFECYCLE_MANAGED_WORLDS": self.live_yaml(
                                "plugins/MultiverseWorldLifecycle/config.yml",
                                "managed-worlds",
                            ),
                            "MANAGEMENT_SERVER_SECRET": "env:MANAGEMENT_SERVER_SECRET",
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "MANAGEMENT_SERVER_SECRET": self.live_property(
                        "server.properties", "management-server-secret"
                    )
                },
            ):
                code, output, errors = self.run_tool(
                    "--check", "--settings", str(settings)
                )
        self.assertEqual(0, code, errors)
        self.assertNotIn("CREATE", output)
        self.assertNotIn("UPDATE", output)
        self.assertEqual(
            len(apply_config.read_manifest(self.repository / "config.lock.json")),
            output.count("UNCHANGED"),
        )


if __name__ == "__main__":
    unittest.main()
