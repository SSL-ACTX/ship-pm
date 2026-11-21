#!/bin/sh
set -eu

if ! command -v verus >/dev/null 2>&1; then
    printf '%s\n' "verus was not found on PATH; install Verus first." >&2
    exit 127
fi

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd)
work_dir=$(mktemp -d "${TMPDIR:-/tmp}/ship-verus-examples.XXXXXX")
cleanup() {
    rm -rf "$work_dir"
}
trap cleanup EXIT HUP INT TERM

cp "$script_dir/lower_bound.rs" "$work_dir/"

printf '\n==> Verifying lower_bound.rs\n'
(cd "$work_dir" && verus lower_bound.rs)
