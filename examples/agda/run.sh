#!/bin/sh
set -eu

if ! command -v agda >/dev/null 2>&1; then
    printf '%s\n' "agda was not found on PATH; install Agda first ('ship i agda --deb')." >&2
    exit 127
fi

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd)
work_dir=$(mktemp -d "${TMPDIR:-/data/data/com.termux/files/usr/tmp}/ship-agda-examples.XXXXXX")
cleanup() {
    rm -rf "$work_dir"
}
trap cleanup EXIT HUP INT TERM

cp "$script_dir/StandaloneFib.agda" "$work_dir/"

printf '\n==> Type-checking and verifying StandaloneFib.agda\n'
(cd "$work_dir" && agda --no-default-libraries --local-interfaces StandaloneFib.agda)

printf '\n==> Agda verification finished successfully.\n'
