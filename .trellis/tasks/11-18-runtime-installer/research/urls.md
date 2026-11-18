# Research: pinned download URLs

- Query: pin a concrete, build-specific `download_url` for the seven
  `runtime.lock.json` artifacts that have none, and prove the bytes hash to the
  recorded SHA-256.
- Scope: mixed (external vendor endpoints + internal lock/verifier contracts)
- Date: 2026-11-18

## Findings

All seven artifacts resolved to a build-specific URL whose bytes match the lock
exactly. No conflicts, no artifact left without a URL.

| id | version / build | candidate URL | HTTP | bytes | sha256 | matches lock |
| --- | --- | --- | --- | --- | --- | --- |
| coreprotect | 24.1 (Modrinth `3sehX6Sg`) | `https://cdn.modrinth.com/data/Lu3KuzdV/versions/3sehX6Sg/CoreProtect-CE-24.1.jar` | 200 | 1113283 | `a2acef7c06ef201355cef07d591a6055dfed358ad768faaaaaf4e276865ecc97` | yes |
| floodgate | 2.2.5 build 141 (`81b65cc`) | `https://download.geysermc.org/v2/projects/floodgate/versions/2.2.5/builds/141/downloads/spigot` | 200 | 11561096 | `21570aff9ce17d6983928e8552777760e1ede5050026b04c686b0ae112e6fd7e` | yes |
| geyser-spigot | 2.12.1 build 1302 (`cbd42b8`) | `https://download.geysermc.org/v2/projects/geyser/versions/2.12.1/builds/1302/downloads/spigot` | 200 | 52216329 | `e13592d8ef907657eb9bae6f778dcb6ccb7f4a5b4641baeeb298ff5d13ccc92f` | yes |
| grimac | 2.3.75-1299a2a (Modrinth `QNc4r5Qj`) | `https://cdn.modrinth.com/data/LJNGWSvH/versions/QNc4r5Qj/grimac-bukkit-2.3.75-1299a2a.jar` | 200 | 13193483 | `080e01c5545695b7e755f705d73da49c5eae9b86d67f1425f88f2c7b414f8da9` | yes |
| skinsrestorer | 15.12.6 (GitHub release) | `https://github.com/SkinsRestorer/SkinsRestorer/releases/download/15.12.6/SkinsRestorer.jar` | 200 | 8016648 | `a85b4a370f988741c9a38f4d0498262edacbf3220314790ac1c127461996359c` | yes |
| viaversion | 5.12.2-SNAPSHOT, Jenkins `#1478` (`08776de`) | `https://ci.viaversion.com/job/ViaVersion/1478/artifact/build/libs/ViaVersion-5.12.2-SNAPSHOT.jar` | 200 | 6506260 | `5b76329e2c832746dac7cae47a8b688bcba8d31254b6872134e98ae7d5c561d4` | yes |
| viabackwards | 5.12.2-SNAPSHOT, Jenkins `#806` (`2aec244`) | `https://ci.viaversion.com/job/ViaBackwards/806/artifact/build/libs/ViaBackwards-5.12.2-SNAPSHOT.jar` | 200 | 1438466 | `a88617fa001469c3be0c8ba7f24a5bb2593294d176c1f81041d6bf4482c5d726` | yes |

### Provenance detail

- **coreprotect** - Modrinth project `Lu3KuzdV` (title "CoreProtect", filename
  `CoreProtect-CE-24.1.jar`). The published SHA-1
  `3e6ef12c6d4bd2c72f8dc32a35491fd414dc4d80` and SHA-512
  `76aad727...e58de0c95` equal the installed JAR. The GitHub release tag
  `v24.1` in `PlayPro/CoreProtect` confirms the version but publishes no binary
  assets. `https://coreprotect.net/download/` answered 403 to scripted
  requests.
- **floodgate** - GeyserMC download API. Build 141, commit
  `81b65ccb766bf8024858ebf3eefa6974056aecc5`, built `2026-09-17T14:53:03Z`.
  The API's own `downloads.spigot.sha256` equals the lock.
- **geyser-spigot** - GeyserMC download API. Build 1302, commit
  `cbd42b8a0c47cef046b408411508c67f82cd8e3c`, built `2026-11-12T13:14:37Z`,
  matching the `git.properties` inside the installed JAR. The API's
  `downloads.spigot.sha256` equals the lock.
- **grimac** - Modrinth project `LJNGWSvH`, version `2.3.75-1299a2a`
  (channel `alpha`). File size and SHA-1/SHA-512 equal the installed JAR.
  The GitHub release tag `2.3.75` does not exist and GitHub releases publish no
  assets, so Modrinth is the only build-specific binary source.
- **skinsrestorer** - GitHub release `15.12.6`, asset `SkinsRestorer.jar`;
  the release also ships loader-specific mods that are not this artifact.
- **viaversion** - ViaVersion Jenkins, job `ViaVersion`, build 1478, commit
  `08776de83283112c345ec03b725ec9f7fe58265f`, built
  `2026-10-12T16:42:10Z`. Builds 1474-1485 all produced
  `ViaVersion-5.12.2-SNAPSHOT.jar`; 1478 is the only one whose SHA-256 matches.
- **viabackwards** - ViaBackwards Jenkins, job `ViaBackwards`, build 806,
  commit `2aec24449efe16002e4f8cf6b4988e6c7a1bf4da`, built
  `2026-10-12T17:01:10Z`. Builds 801-813 produced the 5.12.2-SNAPSHOT JAR; 806
  is the only match.

### Verification method

Each candidate was downloaded to `.tmp/runtime-research/`, hashed with SHA-256,
and compared both to `runtime.lock.json` and to the installed JAR in
`server/plugins/`. `python .tmp/runtime-research/compare.py` printed
`lock=ok` for all seven (downloaded == lock == installed). Sizes also equal the
installed files byte for byte.

### Relevant internal contracts

- `scripts/verify_runtime.py:63` - `read_lock` owns lock grammar.
- `scripts/verify_runtime.py:105` - `download_url`, when present, must already
  be an absolute HTTP(S) URL, so the installer needs no new URL validation.
- `scripts/verify_runtime.py:131` - `safe_path` rejects path escapes through
  `..`, symlinks, and junctions.
- `scripts/verify_runtime.py:154` - `fingerprint` streams SHA-256 in 1 MiB
  blocks.
- `.trellis/spec/backend/world-artifacts.md:141` - the project's existing
  atomic-write pattern (`os.replace` from a temporary sibling) is the precedent
  the installer should follow.

### Implementation notes

- Upstream file names differ from the lock paths for floodgate
  (`floodgate-spigot.jar`), geyser (`Geyser-Spigot.jar`), viaversion
  (`ViaVersion-5.12.2-SNAPSHOT.jar`), and viabackwards
  (`ViaBackwards-5.12.2-SNAPSHOT.jar`). The installer must write to the lock
  `path`, never to the URL basename.
- Upstream API version strings omit `-SNAPSHOT` for Geyser (`2.12.1`) and
  Floodgate (`2.2.5`). The lock `version` fields are the JAR-internal versions;
  keep them unchanged and only add `download_url`.
- The new URLs are plain anonymous HTTPS GETs; none require headers, auth, or
  cookies (a normal `User-Agent` is enough for Jenkins).

## Caveats / Not Found

- **Jenkins retention:** `ci.viaversion.com` may discard old builds. If build
  1478 or 806 is pruned, the pinned URL will 404 and no `latest` URL can
  reproduce the recorded hash. The truthful behaviour is a download failure;
  do not silently substitute the newest build or rewrite the lock hash.
- **GrimAC channel:** the exact build is published as `alpha`, not a stable
  channel. It is still immutable and hash-pinned.
- **CoreProtect site:** `coreprotect.net/download/` blocks scripted clients
  (403). Modrinth is the working build-specific mirror and its bytes equal the
  installed JAR.
- The four artifacts that already had `download_url` (paper, multiverse-core,
  packmanagerpro, datapack) were not re-downloaded; they are outside this
  task's seven-artifact scope.
- No conflicts: every lock hash was reproduced by a vendor or vendor-mirrored
  build. No lock hash was rewritten.

## Evidence files

- `D:\Repositories\minecraft-asp-server\.tmp\runtime-research\CoreProtect-CE-24.1.jar`
- `D:\Repositories\minecraft-asp-server\.tmp\runtime-research\Floodgate-Spigot.jar`
- `D:\Repositories\minecraft-asp-server\.tmp\runtime-research\Geyser-Spigot.jar`
- `D:\Repositories\minecraft-asp-server\.tmp\runtime-research\grimac-bukkit.jar`
- `D:\Repositories\minecraft-asp-server\.tmp\runtime-research\SkinsRestorer.jar`
- `D:\Repositories\minecraft-asp-server\.tmp\runtime-research\ViaVersion.jar`
- `D:\Repositories\minecraft-asp-server\.tmp\runtime-research\ViaBackwards.jar`
- `D:\Repositories\minecraft-asp-server\.tmp\runtime-research\geyser-build.json`
- `D:\Repositories\minecraft-asp-server\.tmp\runtime-research\floodgate-build.json`
- `D:\Repositories\minecraft-asp-server\.tmp\runtime-research\via-1478.json`
- `D:\Repositories\minecraft-asp-server\.tmp\runtime-research\viab-806.json`
- `D:\Repositories\minecraft-asp-server\.tmp\runtime-research\compare.py`
