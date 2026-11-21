#!/bin/sh
set -eu

if ! command -v frama-c >/dev/null 2>&1; then
    printf '%s\n' "frama-c was not found on PATH; install frama-c-base first (e.g. 'ship i frama-c-base --deb')." >&2
    exit 127
fi

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd)
work_dir=$(mktemp -d "${TMPDIR:-/tmp}/ship-frama-c-examples.XXXXXX")
cleanup() {
    rm -rf "$work_dir"
}
trap cleanup EXIT HUP INT TERM

cp "$script_dir/linear_search.c" "$work_dir/"

printf '\n==> Type-checking and analyzing linear_search.c with ACSL contracts\n'
(cd "$work_dir" && frama-c -cpp-extra-args="-Wno-builtin-macro-redefined" linear_search.c)

printf '\n==> Normalizing and pretty-printing validated AST\n'
(cd "$work_dir" && frama-c -cpp-extra-args="-Wno-builtin-macro-redefined" linear_search.c -print)

printf '\n==> Frama-C analysis finished successfully.\n'
