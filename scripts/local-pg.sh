#!/usr/bin/env bash
# Runs a project-local Postgres 17 + pgvector without Docker.
# Homebrew's postgresql@17 has no pgvector, so we mirror its install layout under
# .local/pg (postgres resolves share/lib relative to its own binary) and build
# pgvector into that copy. Nothing outside the project folder is modified.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL="$ROOT/.local"
PG_HOME="${PG_HOME:-/opt/homebrew/opt/postgresql@17}"
PGVECTOR_VERSION="0.8.1"
PORT="${POSTGRES_PORT:-5502}"
DATA="$LOCAL/pgdata"

pg_config_val() { "$PG_HOME/bin/pg_config" "--$1"; }

prefix_root() {
  local bindir sharedir
  bindir="$(pg_config_val bindir)"
  sharedir="$(pg_config_val sharedir)"
  local prefix="$bindir"
  while [[ "$sharedir" != "$prefix"* ]]; do prefix="$(dirname "$prefix")"; done
  echo "$prefix"
}

install() {
  local root bindir sharedir pkglibdir
  root="$(prefix_root)"
  bindir="$(pg_config_val bindir)"
  sharedir="$(pg_config_val sharedir)"
  pkglibdir="$(pg_config_val pkglibdir)"
  local mirror="$LOCAL/pg"
  local local_bin="$mirror${bindir#"$root"}"

  if [[ -x "$local_bin/postgres" && -f "$mirror${sharedir#"$root"}/extension/vector.control" ]]; then
    echo "$local_bin"
    return
  fi

  mkdir -p "$local_bin" "$mirror${sharedir#"$root"}" "$mirror${pkglibdir#"$root"}" "$LOCAL/src"
  cp -RL "$bindir/." "$local_bin/"
  cp -RL "$sharedir/." "$mirror${sharedir#"$root"}/"
  cp -RL "$pkglibdir/." "$mirror${pkglibdir#"$root"}/"

  local src="$LOCAL/src/pgvector-$PGVECTOR_VERSION"
  if [[ ! -d "$src" ]]; then
    curl -sSL "https://github.com/pgvector/pgvector/archive/refs/tags/v$PGVECTOR_VERSION.tar.gz" | tar xz -C "$LOCAL/src"
  fi
  local sysroot=""
  command -v xcrun >/dev/null && sysroot="$(xcrun --show-sdk-path)"
  make -C "$src" PG_CONFIG="$PG_HOME/bin/pg_config" PG_SYSROOT="$sysroot" -j8 >/dev/null
  make -C "$src" install PG_CONFIG="$PG_HOME/bin/pg_config" PG_SYSROOT="$sysroot" DESTDIR="$LOCAL/stage" >/dev/null
  cp "$LOCAL/stage$pkglibdir"/vector.* "$mirror${pkglibdir#"$root"}/"
  cp "$LOCAL/stage$sharedir"/extension/vector* "$mirror${sharedir#"$root"}/extension/"
  echo "$local_bin"
}

start() {
  local bin
  bin="$(install | tail -1)"
  if [[ ! -f "$DATA/PG_VERSION" ]]; then
    "$bin/initdb" -D "$DATA" -U postgres --auth=trust -E UTF8 >/dev/null
  fi
  if "$bin/pg_ctl" -D "$DATA" status >/dev/null 2>&1; then
    echo "postgres already running on $PORT"
  else
    "$bin/pg_ctl" -D "$DATA" -l "$LOCAL/postgres.log" -o "-p $PORT -k $LOCAL -c listen_addresses=127.0.0.1" -w start >/dev/null
    echo "postgres started on $PORT"
  fi
  for db in retrieval_lab retrieval_lab_test; do
    "$bin/psql" -h 127.0.0.1 -p "$PORT" -U postgres -tAc "select 1 from pg_database where datname='$db'" | grep -q 1 \
      || "$bin/createdb" -h 127.0.0.1 -p "$PORT" -U postgres "$db"
  done
}

stop() {
  local bin
  bin="$(install | tail -1)"
  "$bin/pg_ctl" -D "$DATA" -m fast stop >/dev/null 2>&1 && echo "postgres stopped" || echo "postgres not running"
}

reset() {
  local bin
  bin="$(install | tail -1)"
  start >/dev/null
  "$bin/dropdb" -h 127.0.0.1 -p "$PORT" -U postgres --if-exists --force retrieval_lab
  "$bin/createdb" -h 127.0.0.1 -p "$PORT" -U postgres retrieval_lab
  echo "retrieval_lab recreated on $PORT"
}

case "${1:-start}" in
  install) install ;;
  start) start ;;
  stop) stop ;;
  reset) reset ;;
  *) echo "usage: $0 {install|start|stop|reset}" >&2; exit 2 ;;
esac
