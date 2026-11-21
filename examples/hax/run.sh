#!/bin/sh
set -eu

if ! command -v hax >/dev/null 2>&1; then
    printf '%s\n' "hax was not found on PATH." >&2
    exit 127
fi

SKIP_LAKE="${SKIP_LAKE:-1}"

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd)
work_dir=$(mktemp -d "${TMPDIR:-/tmp}/ship-hax-examples.XXXXXX")
cleanup() {
    rm -rf "$work_dir"
}
trap cleanup EXIT HUP INT TERM

cp -R "$script_dir/." "$work_dir/"
rm -f "$work_dir/run.sh"

printf '%s\n' "==> Running Cargo unit tests..."
(cd "$work_dir" && cargo test)

printf '%s\n' "==> Extracting Rust definitions to Lean with hax..."
(cd "$work_dir" && hax into -i '-** +hax_examples::lower_bound +hax_examples::search_or_insert' --output-dir "$work_dir/extraction" lean)

if [ "$SKIP_LAKE" = "1" ] || [ "$SKIP_LAKE" = "true" ]; then
    printf '%s\n' "==> Skipping 'lake build' (set SKIP_LAKE=0 to verify proofs; heavy RAM usage on mobile devices)."
else
    if ! command -v lake >/dev/null 2>&1; then
        printf '%s\n' "lake (Lean 4 build system) was not found on PATH." >&2
        exit 127
    fi
    printf '%s\n' "==> Building extracted Lean 4 proof obligations with lake..."
    (cd "$work_dir/extraction" && lake build)
fi

printf '%s\n' "==> Lean extraction finished successfully in $work_dir."
