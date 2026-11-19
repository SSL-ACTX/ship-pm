"""Termux compatibility adjustment for Odin's static ARM64 Linux compiler."""

from __future__ import annotations

from ship.api import (
    PackageRecipe,
    on_termux,
    raise_tls_alignment,
)

ODIN_TLS_ALIGNMENT = 64
RUN_UNSUPPORTED_FLAGS = frozenset(
    {"build-mode", "print-linker-flags", "subtarget", "windows-sdk-root"}
)

_RECIPE = (
    PackageRecipe("odin")
    .raise_tls_alignment(
        ("bin/odin", "odin"),
        alignment=ODIN_TLS_ALIGNMENT,
        stage="post_extract",
        condition=on_termux(arch="aarch64"),
    )
    .intercept_compiler_run(
        binary="odin",
        subcommand="run",
        build_subcommand="build",
        output_flag="-out:{output}",
        unsupported_flags=RUN_UNSUPPORTED_FLAGS,
        fixup=lambda out: raise_tls_alignment(out, alignment=ODIN_TLS_ALIGNMENT),
        condition=on_termux(arch="aarch64"),
    )
)

# Export run_odin for ship call / CLI entrypoint dispatch
run_odin = _RECIPE.intercept_func

PATCH = _RECIPE.to_patch()
