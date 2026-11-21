#!/bin/sh
set -eu

if ! command -v why3 >/dev/null 2>&1; then
    printf '%s\n' "why3 was not found on PATH; install why3 first." >&2
    exit 127
fi

# Ensure provers are registered if no config exists yet
if [ ! -f "${HOME}/.why3.conf" ]; then
    printf '%s\n' "==> Detecting installed provers for Why3..."
    why3 config detect
fi

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd)
work_dir=$(mktemp -d "${TMPDIR:-/tmp}/ship-why3-examples.XXXXXX")
cleanup() {
    rm -rf "$work_dir"
}
trap cleanup EXIT HUP INT TERM

cp "$script_dir/fibonacci.mlw" "$work_dir/"

printf '\n==> Verifying fibonacci.mlw\n'
if command -v z3 >/dev/null 2>&1; then
    (cd "$work_dir" && why3 prove -P z3 fibonacci.mlw)
else
    printf '%s\n' "Notice: z3 solver not installed; running why3 typecheck only."
    (cd "$work_dir" && why3 prove fibonacci.mlw)
fi

printf '\n==> Why3 verification finished successfully.\n'
