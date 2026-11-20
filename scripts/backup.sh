#!/bin/sh
# ============================================================
#  Paper server backup (POSIX sh, for Linux deployments)
#
#  Usage:  scripts/backup.sh [SERVER_DIR]
#  Default SERVER_DIR: ../server (relative to this script)
#
#  Scope (see docs/SINGLE-WORLD-SOP.md):
#    native saves + whitelist/ban/usercache/ops json + server config
#    + config/ (Paper) + per-plugin config dirs (jars excluded)
#    + settings/*.json (per-host coordinates; *.example.json excluded)
#    Known-regenerable plugin caches are excluded (see below).
#  Output: <target>/<UTC timestamp>/ with MANIFEST.txt
#
#  Every configured target gets its own full copy and its own manifest,
#  so the copies are independent: one bad disk cannot corrupt the other.
#
#  A backup counts as complete only when COMPLETE exists. Prune keeps
#  the newest $KEEP complete backups per target and deletes partial
#  leftovers, so a failed run can never push a good backup out of the
#  window. Run while the server is stopped for a consistent snapshot.
#
#  Env overrides:
#    KEEP                  complete backups kept per target (default 5)
#    BACKUP_MIN_INTERVAL   skip when every target already has a complete
#                          backup younger than this many minutes
#                          (default 0 = never skip)
#    SETTINGS_DIR          per-host settings source (default ../settings)
#    BACKUP_REQUIRE_ALL=1  a failed mirror fails the run (default 0)
#    ALLOW_ONLINE=1        proceed even though the server is running
# ============================================================
set -eu
cd "$(dirname "$0")"
SCRIPT_DIR="$(pwd)"

KEEP="${KEEP:-5}"
if [ $# -ge 1 ]; then SERVER_DIR="$1"; else SERVER_DIR="$SCRIPT_DIR/../server"; fi
MIN_INTERVAL="${BACKUP_MIN_INTERVAL:-0}"
REQUIRE_ALL="${BACKUP_REQUIRE_ALL:-0}"
SETTINGS_DIR="${SETTINGS_DIR:-$SCRIPT_DIR/../settings}"
TS="$(date -u +%Y%m%d-%H%M%S)"
CURRENT_DEST=""
CURRENT_TARGET=""

remove_snapshot() {
    python3 -B "$SCRIPT_DIR/backup_settings.py" --snapshot "$1" "$2" || return 1
    rm -rf -- "$1/$2"
}

# Only directories named like our own timestamps are ever pruned, so a
# target may point at a shared folder without us deleting its contents.
is_our_dir() {
    case "$1" in
        */[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9]/) return 0 ;;
        *) return 1 ;;
    esac
}

# Newest complete backup in a target, or nothing.
newest_complete() {
    ls -1d "$1"/*/ 2>/dev/null | sort -r | while IFS= read -r d; do
        if is_our_dir "$d" && [ -f "$d/COMPLETE" ]; then
            printf '%s\n' "$d"
            break
        fi
    done
}

# A failed run must not leave a half-written directory behind.
cleanup() {
    rc=$?
    if [ -n "$CURRENT_DEST" ] && [ -d "$CURRENT_DEST" ]; then
        echo "[backup] ERROR: aborted; removing $CURRENT_DEST" >&2
        remove_snapshot "$CURRENT_TARGET" "$TS" || echo "[backup] ERROR: unsafe partial snapshot preserved" >&2
    fi
    exit "$rc"
}
trap cleanup EXIT

# --- preflight ---
if [ ! -f "$SERVER_DIR/paper-server.jar" ]; then
    echo "[backup] ERROR: not a server dir: $SERVER_DIR (paper-server.jar missing)" >&2
    exit 1
fi

for reserved in config plugins settings; do
    if [ -e "$SERVER_DIR/$reserved/level.dat" ]; then
        echo "[backup] ERROR: native save collides with snapshot directory: $reserved" >&2
        exit 1
    fi
done

if ! command -v python3 >/dev/null 2>&1; then
    echo "[backup] ERROR: python3 is required for settings/minecraft-server.json" >&2
    exit 1
fi
TARGET_LIST="$(python3 -B "$SCRIPT_DIR/backup_settings.py" --format sh --server-dir "$SERVER_DIR" --settings-dir "$SETTINGS_DIR")" || exit 1

# Refuse a torn snapshot: the Paper server must be stopped while we copy.
# Match the real launch shape (`java ... -jar .../paper-server.jar`) so an
# unrelated process that merely mentions the file name is not a false hit.
# pgrep is absent on some minimal shells (e.g. Git Bash), so fall back to ps.
server_running() {
    if command -v pgrep >/dev/null 2>&1; then
        pgrep -f -- '-jar[[:space:]]+.*paper-server\.jar' >/dev/null 2>&1
    else
        ps -ef 2>/dev/null | grep -E -- '-jar[[:space:]]+.*[p]aper-server\.jar' >/dev/null 2>&1
    fi
}
if server_running; then
    if [ "${ALLOW_ONLINE:-0}" != "1" ]; then
        echo "[backup] ERROR: the Paper server is running; stop it first (or set ALLOW_ONLINE=1)" >&2
        exit 1
    fi
    echo "[backup] WARN: ALLOW_ONLINE=1 - snapshot may be inconsistent" >&2
fi

# --- optional: skip only when EVERY target is already up to date ---
# A target that fell behind (unplugged disk, newly added target) forces a
# run even if the primary is fresh, so the mirror can catch up.
if [ "$MIN_INTERVAL" -gt 0 ] 2>/dev/null; then
    all_recent=1
    while IFS= read -r t; do
        [ -n "$t" ] || continue
        newest="$(newest_complete "$t")"
        if [ -z "$newest" ]; then all_recent=0; break; fi
        age=$(( ( $(date +%s) - $(stat -c %Y "$newest/COMPLETE" 2>/dev/null || stat -f %m "$newest/COMPLETE") ) / 60 ))
        if [ "$age" -ge "$MIN_INTERVAL" ]; then all_recent=0; break; fi
    done <<TARGETS
$TARGET_LIST
TARGETS
    if [ "$all_recent" -eq 1 ]; then
        echo "[backup] SKIP: every target has a complete backup younger than ${MIN_INTERVAL}m"
        exit 0
    fi
fi

# ============================================================
#  One complete backup into one target. Returns 0 on success.
#  NOTE: this runs as the condition of an `if`, which switches errexit
#  off for the whole body - every step therefore checks itself.
# ============================================================
do_target() {
    tdir="$1"
    dest="$tdir/$TS"
    python3 -B "$SCRIPT_DIR/backup_settings.py" --snapshot "$tdir" "$TS" --new || return 1

    if ! mkdir -p "$tdir" || ! mkdir "$dest"; then
        echo "[backup] ERROR: cannot create $dest" >&2
        return 1
    fi
    CURRENT_DEST="$dest"
    CURRENT_TARGET="$tdir"

    for world_dir in "$SERVER_DIR"/*/; do
        [ -f "$world_dir/level.dat" ] || continue
        world_name="$(basename "$world_dir")"
        mkdir -p "$dest/$world_name" || return 1
        tar cf - --exclude=session.lock --exclude=level.dat_old -C "$world_dir" . | tar xf - -C "$dest/$world_name" || return 1
        src_count=$(find "$world_dir" -type f ! -name session.lock ! -name level.dat_old | wc -l)
        dst_count=$(find "$dest/$world_name" -type f | wc -l)
        if [ "$src_count" -ne "$dst_count" ]; then
            echo "[backup] ERROR: world copy incomplete: $world_name ($dst_count of $src_count files): $dest" >&2
            return 1
        fi
    done

    # --- player files + server config ---
    for f in whitelist.json ops.json banned-ips.json banned-players.json usercache.json \
             server.properties eula.txt bukkit.yml spigot.yml commands.yml permissions.yml server-icon.png; do
        if [ -f "$SERVER_DIR/$f" ]; then
            cp "$SERVER_DIR/$f" "$dest/" || return 1
        fi
    done

    # --- Paper config dir ---
    if [ -d "$SERVER_DIR/config" ]; then
        mkdir -p "$dest/config" || return 1
        tar cf - -C "$SERVER_DIR/config" . | tar xf - -C "$dest/config"
        src_count=$(find "$SERVER_DIR/config" -type f | wc -l)
        dst_count=$(find "$dest/config" -type f | wc -l)
        if [ "$src_count" -ne "$dst_count" ]; then
            echo "[backup] ERROR: config copy incomplete ($dst_count of $src_count): $dest" >&2
            return 1
        fi
    fi

    # --- plugin dirs: config + data, jars excluded ---
    # Only caches proven regenerable in docs/SINGLE-WORLD-SOP.md are
    # excluded. Do not widen this to every */cache/: a plugin may keep
    # real state in a directory with that name.
    mkdir -p "$dest/plugins" || return 1
    for d in "$SERVER_DIR"/plugins/*/; do
        [ -d "$d" ] || continue
        name="$(basename "$d")"
        mkdir -p "$dest/plugins/$name" || return 1
        case "$name" in
            Geyser-Spigot|SkinsRestorer)
                tar cf - --exclude='*.jar' --exclude='./cache' --exclude='./cache/*' -C "$d" . | tar xf - -C "$dest/plugins/$name"
                src_count=$(find "$d" -type f ! -name '*.jar' ! -path "${d%/}/cache/*" | wc -l)
                ;;
            *)
                tar cf - --exclude='*.jar' -C "$d" . | tar xf - -C "$dest/plugins/$name"
                src_count=$(find "$d" -type f ! -name '*.jar' | wc -l)
                ;;
        esac
        dst_count=$(find "$dest/plugins/$name" -type f | wc -l)
        if [ "$src_count" -ne "$dst_count" ]; then
            echo "[backup] ERROR: plugin copy incomplete: $name ($dst_count of $src_count): $dest" >&2
            return 1
        fi
    done
    cp "$SERVER_DIR"/plugins/*.yml "$dest/plugins/" 2>/dev/null || true

    # --- per-host settings: untracked, so the snapshot is their only copy ---
    # git tracks settings/*.example.json only. The file that fills the
    # placeholders is host state, not source: it cannot be reconstructed from
    # the repository, and it is what explains the rendered server.properties
    # and plugin yml beside it. See docs/SINGLE-WORLD-SOP.md.
    if [ -d "$SETTINGS_DIR" ]; then
        mkdir -p "$dest/settings" || return 1
        tar cf - --exclude='*.example.json' -C "$SETTINGS_DIR" . | tar xf - -C "$dest/settings"
        src_count=$(find "$SETTINGS_DIR" -type f ! -name '*.example.json' | wc -l)
        dst_count=$(find "$dest/settings" -type f | wc -l)
        if [ "$src_count" -ne "$dst_count" ]; then
            echo "[backup] ERROR: settings copy incomplete ($dst_count of $src_count): $dest" >&2
            return 1
        fi
    fi

    # Resource packs under packs/ are externally sourced and regenerable;
    # they stay out of the snapshot. Preserve their external source and hash.

    # --- manifest: hash every backed-up file (world included) ---
    {
        echo "# Paper backup $TS"
        (cd "$dest" && find . -type f ! -name MANIFEST.txt | LC_ALL=C sort | while IFS= read -r f; do sha256sum --text "$f"; done)
    } > "$dest/MANIFEST.txt" || {
        echo "[backup] ERROR: cannot write manifest: $dest" >&2
        return 1
    }

    # The manifest must cover every file, or the restore check is a lie.
    man_count=$(grep -c '^[0-9a-f]\{64\}  ' "$dest/MANIFEST.txt" || true)
    file_count=$(find "$dest" -type f ! -name MANIFEST.txt | wc -l)
    if [ "$man_count" -ne "$file_count" ]; then
        echo "[backup] ERROR: manifest covers $man_count of $file_count files: $dest" >&2
        return 1
    fi

    # --- completion marker: written last, only for a fully written backup ---
    : > "$dest/COMPLETE" || {
        echo "[backup] ERROR: cannot write COMPLETE marker: $dest" >&2
        return 1
    }
    CURRENT_DEST=""

    # --- prune THIS target: keep its newest $KEEP complete backups ---
    ls -1d "$tdir"/*/ 2>/dev/null | sort -r | {
        n=0
        while IFS= read -r d; do
            is_our_dir "$d" || continue
            if [ -f "$d/COMPLETE" ]; then
                n=$((n + 1))
                if [ "$n" -gt "$KEEP" ]; then remove_snapshot "$tdir" "$(basename "${d%/}")" || exit 1; fi
            else
                remove_snapshot "$tdir" "$(basename "${d%/}")" || exit 1
            fi
        done
    } || return 1

    CURRENT_DEST=""
    return 0
}

# --- run every target; a mirror failure is not fatal by default ---
ok_count=0
fail_count=0
primary_failed=0
idx=0

while IFS= read -r t; do
    [ -n "$t" ] || continue
    idx=$((idx + 1))
    if do_target "$t"; then
        ok_count=$((ok_count + 1))
        echo "[backup] OK: $t/$TS"
    else
        fail_count=$((fail_count + 1))
        if [ "$idx" -eq 1 ]; then primary_failed=1; fi
        if [ -n "$CURRENT_DEST" ] && [ -d "$CURRENT_DEST" ]; then
            remove_snapshot "$CURRENT_TARGET" "$TS" || echo "[backup] ERROR: unsafe partial snapshot preserved" >&2
        fi
        CURRENT_DEST=""
        echo "[backup] ERROR: target failed: $t" >&2
    fi
done <<TARGETS
$TARGET_LIST
TARGETS

if [ "$ok_count" -eq 0 ]; then
    echo "[backup] ERROR: every target failed" >&2
    exit 1
fi
if [ "$primary_failed" -eq 1 ]; then
    echo "[backup] ERROR: the primary target failed" >&2
    exit 1
fi
if [ "$fail_count" -gt 0 ]; then
    if [ "$REQUIRE_ALL" = "1" ]; then
        echo "[backup] ERROR: mirror failed and BACKUP_REQUIRE_ALL=1" >&2
        exit 1
    fi
    echo "[backup] WARN: $fail_count of $((ok_count + fail_count)) targets failed; the rest are complete" >&2
fi
