"""Termux compatibility adjustment for Odin's static ARM64 Linux compiler."""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from ship.config import IS_TERMUX
from ship.patchers.api import (
    EM_AARCH64,
    ArgumentEquals,
    BinaryQuery,
    InstallPatch,
    PackagePatch,
    PatchContext,
    RuntimeCommand,
    RuntimePatch,
    find_binaries,
    raise_tls_alignment,
)

ODIN_TLS_ALIGNMENT = 64
RUN_UNSUPPORTED_FLAGS = frozenset(
    {"build-mode", "print-linker-flags", "subtarget", "windows-sdk-root"}
)


def patch_odin_tls(context: PatchContext) -> None:
    """Fix Odin's static ARM64 TLS metadata when installing on Termux."""
    if not IS_TERMUX:
        return

    for binary in find_binaries(
        context.install_dir,
        BinaryQuery(
            names=("odin",),
            elf_machines=(EM_AARCH64,),
            locations=(Path("bin"),),
        ),
    ):
        if raise_tls_alignment(
            binary, alignment=ODIN_TLS_ALIGNMENT, machine=EM_AARCH64
        ):
            context.record(binary, "adjusted PT_TLS alignment", "64 bytes")


def run_odin(real_binary: str, args: list[str]) -> int:
    """Run Odin's build pipeline while fixing TLS before starting the program."""
    if not args or args[0] != "run":
        return subprocess.run([real_binary, *args], check=False).returncode

    compiler_args = args[1:]
    try:
        separator = compiler_args.index("--")
        program_args = compiler_args[separator + 1 :]
        compiler_args = compiler_args[:separator]
    except ValueError:
        program_args = []

    # Odin handles help before command parsing and reports usage itself when a
    # run command has no source. Keep those cases on Odin's native path.
    if (
        not compiler_args
        or all(arg.startswith("-") for arg in compiler_args)
        or any(arg in ("-help", "--help") for arg in compiler_args)
        or any(
            arg.split(":", 1)[0].lstrip("-") in RUN_UNSUPPORTED_FLAGS
            for arg in compiler_args
        )
        or sum(arg in ("-file", "--file") for arg in compiler_args) > 1
    ):
        return subprocess.run([real_binary, *args], check=False).returncode

    # Odin accepts flags before the source by moving the final non-flag token
    # into source position. Apply that same ordering before appending our -out
    # flag, so the compiler sees the same source and every original flag.
    if (
        len(compiler_args) > 1
        and compiler_args[0].startswith("-")
        and not compiler_args[-1].startswith("-")
    ):
        compiler_args = [compiler_args[-1], *compiler_args[:-1]]

    requested_output = None
    for arg in compiler_args:
        if arg.startswith(("-out:", "--out:")):
            requested_output = Path(arg.partition(":")[2])

    keep_executable = any(
        arg in ("-keep-executable", "--keep-executable") for arg in compiler_args
    )

    def build_and_run(output: Path) -> int:
        build_args = [real_binary, "build", *compiler_args]
        if requested_output is None:
            build_args.append(f"-out:{output}")
        build = subprocess.run(
            build_args,
            check=False,
        )
        if build.returncode:
            if build.returncode < 0:
                signum = -build.returncode
                signal.signal(signum, signal.SIG_DFL)
                os.kill(os.getpid(), signum)
            return build.returncode
        if not output.is_file():
            return 1
        raise_tls_alignment(
            output,
            alignment=ODIN_TLS_ALIGNMENT,
            machine=EM_AARCH64,
        )
        result = subprocess.run([str(output), *program_args], check=False)
        if result.returncode < 0:
            signum = -result.returncode
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)
        if result.returncode == 0 and not keep_executable:
            output.unlink(missing_ok=True)
        return result.returncode

    if requested_output is not None:
        if not requested_output.is_absolute():
            requested_output = Path.cwd() / requested_output
        return build_and_run(requested_output)

    temp_dir = Path(tempfile.mkdtemp(prefix="ship-odin-run-"))
    output = temp_dir / "main"
    result = build_and_run(output)
    if keep_executable or (result != 0 and output.is_file()):
        if output.is_file():
            print(f"Keeping executable at {output}", file=sys.stderr)
    else:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return result


def odin_command(
    binary_name: str, real_binary: Path, target_key: str
) -> RuntimeCommand | None:
    """Wrap Odin's run subcommand so generated executables get patched too."""
    if binary_name != "odin" or not IS_TERMUX:
        return None

    import shutil

    python = shutil.which("python3")
    if not python:
        return None
    ship_lib = Path(__file__).resolve().parents[2]
    code = (
        f"import sys; sys.path.insert(0, {str(ship_lib)!r}); "
        "from ship.patches.odin import run_odin; "
        "raise SystemExit(run_odin(sys.argv[1], sys.argv[2:]))"
    )
    return RuntimeCommand(
        argv=(python, "-c", code, real_binary),
        condition=ArgumentEquals(1, "run"),
        otherwise=RuntimeCommand(argv=(real_binary,)),
    )


PATCH = PackagePatch(
    post_extract=(InstallPatch(patch_odin_tls, targets=("aarch64-*",)),),
    runtime=(
        RuntimePatch(
            binaries=("odin",),
            targets=("aarch64-*",),
            command=odin_command,
        ),
    ),
)
