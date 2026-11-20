# Research: native resource-pack selection and reconnect caching

- Query: Can Paper select a native resource pack for the selected startup save; why does reconnect appear to download it again; what controls cache reuse?
- Scope: mixed; current repository code, actual Paper 26.2 build 135 bytecode, installed vanilla Java 26.2/26.3 client bytecode, existing client logs, official Paper configuration documentation.
- Date: 2026-11-20

## Findings

### Conclusions

1. A pack offer, an HTTP transfer, and a resource reload are three distinct events. The native protocol offer contains UUID, URL, SHA-1, required flag, and optional prompt. There is no force-redownload flag in this packet. The client decides whether a valid cached file avoids HTTP.
2. In both inspected Java 26.2 and 26.3 clients, a valid expected SHA-1 permits an immediate disk-cache hit **before opening the URL**. Empty or invalid SHA-1 becomes null, skips that lookup, downloads the bytes, and only then deduplicates by the computed hash. Therefore the branch's blank native `resource-pack-sha1` is a concrete configuration defect for avoiding repeated transfers.
3. A cache hit does not eliminate resource activation/reloading or the Mojang reload screen. Existing local Craftilo logs explicitly show a cache hit followed immediately by a resource reload.
4. Paper's built-in pack setting is process-wide. For the chosen one-process/one-primary-save model, resolving a pack at startup is sufficient. No world plugin or live world-change listener is necessary.
5. Paper 26.2 exposes `--config FILE` and `--world NAME`, but no `--resource-pack`, hash, or generic property override option. A generated properties file is a supported native input. **Paper rewrites the selected properties file, including the `--world` override.** A generated `--config` path confines those writes away from canonical `server/server.properties`.

### Files found

Paths without an absolute prefix are relative to the `single-world-start` worktree.

| File | Role |
| --- | --- |
| `config/server.properties:58` | Native required flag, URL placeholder, blank UUID/prompt/SHA-1 at lines 58–62. |
| `config.lock.json:165` | Manifest entry for the properties template and declared `PACK_URL`. |
| `settings/minecraft-server.example.json:4` | Existing host-coordinate `PACK_URL`, explicitly empty by default. |
| `scripts/apply_config.py:166` | Strict schema-version-1 host settings parser; only `schema_version` and `values` top-level keys. |
| `scripts/apply_config.py:244` | CLI/settings/environment/default resolution; full bundle rendering remains deployment-time work. |
| `scripts/start.sh:24` | Parses selected save, checks its marker, forwards native `--world` at line 82. |
| `scripts/start.cmd:21` | Windows equivalent; Java invocation at line 81. |
| `.tmp/native-cli/cli-options.txt:27` | Previously captured actual `org.bukkit.craftbukkit.Main$1` bytecode; `config` and world aliases, no resource-pack option. |
| `D:/Repositories/minecraft-asp-server/.tmp/world-lifecycle-manual/runtime/versions/26.2/paper-26.2.jar` | Actual Paper server classes inspected read-only with Java 25 `javap -p -c`. |
| `D:/Applications/Portable/PrismLauncherCracked/libraries/com/mojang/minecraft/26.2/minecraft-26.2-client.jar` | Actual vanilla 26.2 client classes. |
| `D:/Applications/Portable/PrismLauncherCracked/libraries/com/mojang/minecraft/26.3/minecraft-26.3-client.jar` | Actual vanilla 26.3 client classes. |
| `D:/Applications/Portable/PrismLauncherCracked/instances/26.2.Cartilo/minecraft/logs/latest.log:563` | Existing successful cache-hit log immediately preceding resource reload. |
| `D:/Applications/Portable/PrismLauncherCracked/instances/26.2.Cartilo/minecraft/downloads/log.json:10` | Historical local pack requests with supplied hash and cached file path; entries also include cache hits. |

### Artifact identity and reproducibility

- Paper runtime baseline: 26.2 build 135. Its already-recorded actual patched server JAR SHA-256 is `7c391444fd5f5fb77d193414924e7a16dbfd1cac87a2a6c858a8ea8dd041f44e`; this is different from the downloaded Paperclip outer JAR hash. See root `.trellis/tasks/11-20-world-statistics-display/research/craftilo-resource-reload.md` for the previous runtime measurement.
- Client 26.2 SHA-256, freshly measured: `40896ee9f1e2bec3c934daac7e93d41e9e3d9c2f8ae0ca366d52ffbfd1afa290`.
- Client 26.3 SHA-256, freshly measured: `4508d006323f24fa02876310c192d739af56516eb259000ac50f0909a68c9a2d`.
- Java tool: `D:/Applications/Scoop/apps/temurin25-jdk/current/bin/javap.exe -p -c -classpath <jar> <class>`.
- Compared the complete disassembly outputs for `net.minecraft.util.HttpUtil`, `net.minecraft.server.packs.DownloadQueue`, and `net.minecraft.client.resources.server.DownloadedPackSource` across the two client versions: all three were identical, with zero differing lines.

### Exact client cache path

`net.minecraft.client.resources.server.DownloadedPackSource.tryParseSha1Hash(String)`:

- Offsets 0–14 check a non-null string against the SHA-1 pattern.
- Offsets 17–27 lowercase and parse it using `HashCode.fromString`.
- Offsets 28–29 return null on a missing/nonmatching value.
- `pushPack(UUID, URL, String)` invokes this parser and gives the result to `ServerPackManager.pushPack`.

`net.minecraft.server.packs.DownloadQueue.lambda$runDownload$0`:

- Offsets 0–13 resolve the pack UUID string under the client cache directory.
- Offsets 18–50 call `HttpUtil.downloadFile`, passing the requested SHA-1 and this UUID-specific directory.
- Its constructor calls `DownloadCacheCleaner.vacuumCacheDir(cacheDir, 20)` at offsets 47–50. Cache retention is finite; a previously cached pack may legitimately be evicted.

`net.minecraft.util.HttpUtil.downloadFile(Path, URL, Map, HashFunction, HashCode, int, Proxy, DownloadProgressListener)`:

- Offsets 13–15: if expected hash is null, skip directly to the network branch.
- Offsets 18–34: expected hash exists; derive cache filename from that hash and hash-check the existing file.
- Offsets 37–62: log `Returning cached file since actual hash matches requested`, notify success, touch mtime, return. **No URL connection has been opened.**
- Offsets 136–176: call `URL.openConnection`, configure redirects/headers, obtain the HTTP body.
- Offsets 260–331: with an expected hash, write/hash the download and reject a mismatch.
- Offsets 332–430: without an expected hash, download into a temporary file, calculate its hash, find/check the resulting cache file, retain/move/deduplicate, and return. Reusing the stored final file at this point did not save network transfer.

The effective disk-cache identity is therefore **UUID plus SHA-1**. Changing UUID while retaining the same bytes and hash selects a different directory and can cause another download. Different launcher instances also have different game/cache directories.

`DownloadedPackSource.cleanupAfterDisconnect()` calls `manager.popAll()` and resets prompt state. It does not clear the disk download directory. `ServerPackManager.popAll()` marks packs for removal; `triggerReloadIfNeeded()` schedules reload at offset 277. Rejoining pushes a pack again; even a cache hit still feeds activation and reload.

### Existing local evidence distinguishes reload from transfer

Craftilo's retained client log contains:

```text
[12:51:26] [Download-1/INFO]: Returning cached file since actual hash matches requested
[12:51:26] [Render thread/INFO]: Reloading ResourceManager: ... server/00000001/d34104d8-533c-3a6e-89af-ca6e43d4fec0
```

This was the earlier local PackManagerPro session, not a fresh measurement of production's new native properties. It proves a real observed reload can occur without another HTTP transfer, but does not establish that the user's latest production symptom is only a reload.

The corresponding local cache log names `http://127.0.0.1:18000/packs/pack-a.zip`, SHA-1 `9bc16f3e826d38857de42bec6fc8a25d61746f67`, and size 28,745,280. It has entries at both 04:50:01Z and 04:51:26Z. **A repeated `downloads/log.json` entry is not proof of a repeated network download**, because `DownloadQueue` records the result after `HttpUtil` returns, including the cache-hit branch. The local served test pack is not assumed byte-identical to the original external ZIP or production's file.

Bounded verification on the user's next join/rejoin:

1. Ensure the active generated properties contain the SHA-1 of the **exact ZIP bytes being served**. SHA-256 in a repository artifact manifest is a different purpose and is not the protocol field.
2. Observe the client's `Returning cached file...` line on the second join.
3. Observe the pack HTTP server access log for a second GET of that path. A `200` GET suggests a transfer; measure served bytes/complete response if proving full transfer matters. A reload screen or a cache event alone does not prove it.
4. Keep URL, UUID, hash, and client game directory stable across the comparison. Do not change the ZIP while keeping an old expected hash; that will fail integrity validation.

Native `require-resource-pack=true` means acceptance/application is required to stay connected. It does not mean bypassing the client cache.

### Exact native server semantics

`net.minecraft.server.network.config.ServerResourcePackConfigurationTask.start` constructs `ClientboundResourcePackPushPacket(UUID, String URL, String hash, boolean required, Optional prompt)` at offsets 1–43 and sends it at 46. It carries a pack request, not the ZIP contents and not a cache-control override. Client acceptance policy still applies.

`net.minecraft.server.dedicated.DedicatedServerProperties` constructor reads the native fields at offsets 935–985. Its `getServerPackInfo`:

- Returns empty immediately when URL is empty (offsets 0–10).
- Prefers `resource-pack-sha1`; only falls back to deprecated `resource-pack-hash` when SHA-1 is empty.
- Does not compute the remote file's hash itself.
- For an empty `resource-pack-id`, computes `UUID.nameUUIDFromBytes(url.getBytes(UTF_8))` at offsets 131–138. Thus a stable URL already gives a deterministic stable UUID. An explicit UUID is optional, not mandatory for caching.
- Parses a nonempty configured UUID and rejects invalid UUID with an empty pack result.

There is a stale-sounding server warning when hash is absent: `Pack will be updated on the client only if you change the name of the pack.` Do not use this literal as authoritative evidence of modern client caching; the actual 26.2/26.3 client methods above perform the null-hash download branch.

`org.bukkit.craftbukkit.Main$1` declares `c/config` as a required File option with default `server.properties`; `w/world/level-name` are one required String option. Its full declared option list has no resource-pack argument or general key/value override.

`net.minecraft.server.dedicated.DedicatedServerSettings` constructor reads `options.valueOf("config")` into its source path and loads from there. `forceSave()` stores the resolved properties back to that same path. `net.minecraft.server.Main.main` calls `forceSave` at offset 156, before world creation/loading.

`net.minecraft.server.dedicated.Settings.getOverride` checks `options.has(propertyName)`, then takes `options.valueOf(propertyName)` if present. `get0` writes the resolved result into the backing `Properties` at offsets 31–44. `DedicatedServerProperties` reads `level-name` through this path at offsets 183–187. Because `--world` and `level-name` are aliases, **native startup persists the chosen world into whichever file `--config` selected**. Existing launcher fixture tests using fake Java only establish that the launcher itself does not edit canonical properties; they do not establish that real Paper leaves them unchanged.

### Properties encoding and parsing contract

Actual `Settings.loadFromFile(Path)` first uses a strict UTF-8 decoder (`REPORT` for malformed and unmappable input) and `Properties.load(Reader)`. Only a `CharacterCodingException` triggers its ISO-8859-1 reader fallback. It logs other IO exceptions and returns empty Properties. `Settings.store` writes with a UTF-8 writer.

A startup helper deriving a temporary properties file must preserve Java Properties behavior: escaped key delimiters, whitespace separators, comments, Unicode escapes, continued logical lines, and duplicate-last-wins semantics. Plain `split("=", 1)` or Python INI parsing is insufficient. Read UTF-8 strictly and fall back to Latin-1 on decoding failure. For this tool, refusing unreadable/invalid input is safer than silently treating it as empty and losing essential settings.

### Smallest suitable selection design

The parent's proposed dedicated, optional `settings/resource-packs.json` policy is compatible with the inspected native behavior:

- A default descriptor enables the same pack for every startup save; default null disables it.
- An exact save-name map overrides the default, with null explicitly disabling a pack for that save.
- Descriptor minimum: validated URL plus required lowercase 40-hex SHA-1. Native deterministic URL-derived UUID is sufficient while URLs are stable; no random UUID generation on startup.
- Startup resolves the selected save from explicit `--world`, otherwise the native `level-name` (default `world` if absent), using Java Properties semantics.
- Generate a derived properties file under ignored `.tmp`, retaining existing unrelated settings, overriding only owned resource-pack fields, then invoke native Paper with `--config` and the existing world argument.
- Clear legacy `resource-pack-hash` as well as owned URL/hash/ID fields as appropriate, so an old fallback hash cannot leak into the selected descriptor. With an absent policy file, document the deliberate fallback to existing native properties.
- Keep full config-bundle deployment separate; do not reapply every plugin config on every server launch. The dedicated settings contract must be documented as an explicit exception to the current spec saying no settings file is read implicitly.

No universal per-save registry, engine/profile model, pack download daemon, or world plugin is needed. This policy selects one native resource pack for the whole running process, including that save's native Nether/End. It is not different simultaneous packs for dimensions within a running save.

Tradeoff requiring explicit documentation: Paper writes property changes to the generated file. Changes made through the runtime management API or equivalent property-mutating commands may be ephemeral if the next startup regenerates from canonical `server.properties`. Do not claim that generated config has identical persistence semantics to the canonical file. Avoid deleting the generated file before Paper exits, since it is an active config write target. Do not persist a temporary selected `level-name` back into the canonical source merely to hide this difference.

### External references

- [Paper server.properties reference](https://docs.papermc.io/paper/reference/server-properties/), retrieved 2026-11-20: documents native URL, UUID, prompt, SHA-1 verification, and required-pack behavior. It recommends SHA-1 to ensure the correct pack. The exact caching conclusion here comes from inspected client bytecode, not an overreading of this short documentation.
- [Official 26.2 client artifact](https://piston-data.mojang.com/v1/objects/2dc72797acbc1b63fc16a11c4ac393605f453754/client.jar): the installed client's SHA-1 and launcher metadata association were previously recorded in root `.trellis/tasks/11-20-world-statistics-display/research/craftilo-keepalive-probe.md`; this task freshly verified SHA-256 and inspected the relevant classes locally.
- The guessed Paper `/paper/reference/startup-parameters/` documentation URL returned 404. No claim depends on that URL; the actual pinned option parser is the source of truth for CLI support.

### Related specs

- `.trellis/spec/backend/single-world-start.md`: selected primary save, no hot-switch, native argv forwarding, existing save marker checks. Correct the inference about real Paper properties persistence.
- `.trellis/spec/backend/config-bundle.md`: host settings ownership, URL validation, no settings implicit load under current contract. A dedicated opt-in startup pack policy requires an explicit scoped contract amendment.
- `.trellis/spec/backend/frpc-scenes.md`: HTTP sidecar and HTTPS shared ingress own delivery; native pack selection/hash owns the game protocol offer. Do not conflate enabling a pack with starting its delivery service.

## Caveats / Not Found

- No production SSH, service restart, active cache deletion, client modification, or new GUI session occurred.
- Actual network transfer on the user's latest production reconnect has not been observed. Blank SHA-1 explains a concrete download path, while earlier local logs separately prove some observed reloads were cache hits.
- Installed client artifacts are vanilla base jars; running Fabric mixins can alter methods. This was not a transformed-mod-client audit.
- Method bytecode and existing logs are sufficient for the stated mechanism, but no new controlled HTTP-count harness was executed by this researcher. Parent received the exact method signature, artifact paths, and existing dependency-classpath location for an optional isolated probe.
- A stable URL-derived UUID is sufficient for a stable endpoint. If the URL/domain changes, the UUID and cache directory change too, potentially causing a one-time download despite equal content hash. Supporting an optional explicit stable UUID is a later policy choice, not necessary for the reported steady-state reconnect problem.
- Legacy Paper warning strings and pre-1.20 client resource-pack cache explanations can conflict with this modern implementation. Prefer the inspected 26.2/26.3 behavior.
