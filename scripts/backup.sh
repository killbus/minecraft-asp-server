#!/bin/sh
# ============================================================
#  ASP server backup (POSIX sh, for Linux deployments)
#
#  Usage:  scripts/backup.sh [SERVER_DIR]
#  Default SERVER_DIR: ../server (relative to this script)
#
#  Same scope as backup.cmd (docs/ASP-SOP.md section 1):
#    world/ + whitelist/ban/usercache/ops json + server config
#    + config/ (Paper) + per-plugin config dirs (jars excluded)
#  Output: ../backups/<UTC timestamp>/ with MANIFEST.txt
#  Retention: newest $KEEP backups, older ones pruned.
#  Run while the server is stopped for a consistent snapshot.
#
#  Env overrides: KEEP (default 10), BACKUP_ROOT
# ============================================================
set -eu
cd "$(dirname "$0")"

KEEP="${KEEP:-5}"
if [ $# -ge 1 ]; then SERVER_DIR="$1"; else SERVER_DIR="$(pwd)/../server"; fi
BACKUP_ROOT="${BACKUP_ROOT:-$(pwd)/../backups}"
TS="$(date -u +%Y%m%d-%H%M%S)"
DEST="$BACKUP_ROOT/$TS"

# --- preflight ---
if [ ! -f "$SERVER_DIR/asp-server.jar" ]; then
    echo "[backup] ERROR: not a server dir: $SERVER_DIR (asp-server.jar missing)" >&2
    exit 1
fi
if pgrep -x java >/dev/null 2>&1; then
    echo "[backup] WARN: a java process is running; stop the server for a consistent backup"
fi

mkdir -p "$DEST"

# --- world: copy, runtime artifacts excluded ---
mkdir -p "$DEST/world"
tar cf - --exclude=./session.lock --exclude=./level.dat_old -C "$SERVER_DIR/world" . | tar xf - -C "$DEST/world"

# --- player files + server config ---
for f in whitelist.json ops.json banned-ips.json banned-players.json usercache.json \
         server.properties eula.txt bukkit.yml spigot.yml commands.yml server-icon.png; do
    [ -f "$SERVER_DIR/$f" ] && cp "$SERVER_DIR/$f" "$DEST/"
done

# --- Paper config dir ---
if [ -d "$SERVER_DIR/config" ]; then
    mkdir -p "$DEST/config"
    tar cf - -C "$SERVER_DIR/config" . | tar xf - -C "$DEST/config"
fi

# --- plugin dirs: config + data, jars excluded ---
mkdir -p "$DEST/plugins"
for d in "$SERVER_DIR"/plugins/*/; do
    [ -d "$d" ] || continue
    name="$(basename "$d")"
    mkdir -p "$DEST/plugins/$name"
    tar cf - --exclude='*.jar' -C "$d" . | tar xf - -C "$DEST/plugins/$name"
done
cp "$SERVER_DIR"/plugins/*.yml "$DEST/plugins/" 2>/dev/null || true

# --- manifest: hash every backed-up file (world included) ---
{
    echo "# ASP backup $TS"
    (cd "$DEST" && find . -type f ! -name MANIFEST.txt | LC_ALL=C sort | while IFS= read -r f; do sha256sum --text "$f"; done)
} > "$DEST/MANIFEST.txt"

# --- prune: keep newest $KEEP (dir names are timestamps) ---
ls -1d "$BACKUP_ROOT"/*/ 2>/dev/null | sed "s|$BACKUP_ROOT/||;s|/$||" | sort -r | tail -n +"$((KEEP + 1))" | while read -r old; do
    rm -rf "$BACKUP_ROOT/$old"
done

echo "[backup] OK: $DEST"
