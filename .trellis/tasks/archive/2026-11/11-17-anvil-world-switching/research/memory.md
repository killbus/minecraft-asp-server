# Memory measurements (2026-11-17)

## Paper / Anvil result

Server: Paper 26.2-135, Java 25, `-Xms2G -Xmx4G -XX:+UseG1GC`.
World: `minecraft:trials`, 43,886 chunks across 47 trimmed regions.

| State | Live heap after `GC.run` | Notes |
| --- | ---: | --- |
| Hub only, `trials` unloaded | 446,137 KB (~436 MB) | no adventure chunks resident |
| `trials` loaded | 494,863 KB (~483 MB) | 355 persistent chunks, load completed in ~2.1s |
| After `/mv unload trials` | 446,428 KB (~436 MB) | returns to hub baseline |

Loaded heap delta: about 48 MB. The full 43,886-chunk map was not resident.
No datafixer or chunk-load exception appeared while loading the trimmed map.

## Previous ASP result

Server: AdvancedSlimePaper 26.2, Java 25, `-Xms4G -Xmx8G -XX:+UseG1GC`.
World: `test_world`, 42,818 chunks, 197 MB `.slime`.

## Results

| State | Live heap after `GC.run` | Notes |
| --- | ---: | --- |
| `test_world` unloaded | 781,753 KB (~782 MB) | hub + plugins only |
| `test_world` loaded | 3,493,336 KB (~3.49 GB) | `World test_world read in 14833ms`, loaded in 2305ms |
| Resident delta | ~2.7 GB | loaded Slime world |

`GC.heap_info` also reported `committed 5,763,072 KB` after loading, with an 8 GB reserved heap.

## Import evidence

- 4 GB heap attempt failed with `java.lang.OutOfMemoryError: Java heap space` during `SlimeSerializer.serializeChunks`.
- 8 GB heap import succeeded in about 99.8 seconds.
- The import peak is therefore higher than the steady-state loaded world, but the loaded world remains resident because `SlimeInMemoryWorld` stores every `SlimeChunk`.

## Commands used

```powershell
& 'D:\Applications\Scoop\apps\temurin25-jdk\current\bin\jcmd.exe' <pid> GC.run
& 'D:\Applications\Scoop\apps\temurin25-jdk\current\bin\jcmd.exe' <pid> GC.heap_info
```

## Implication

For the large persistent map, use Paper/Anvil chunk loading instead of Slime. Multiverse may keep the `World` object registered, but chunks should follow players/tickets and unload when idle.
