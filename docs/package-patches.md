# Package patches

Package-specific behavior lives in `ship/patches/<package_name>.py`; hyphens
in package names become underscores. Platform-wide compatibility belongs in
`ship/patchers/`.

Package modules declare install and runtime behavior through typed `PATCH`
recipes. Each handler receives a `PatchContext`:

```python
from pathlib import Path
from functools import partial

from ship.patches.api import (
    InstallPatch,
    PackagePatch,
    PatchRecipe,
    PatchContext,
    RuntimeCommand,
    RuntimePatch,
    make_executable,
    write_text,
)


prepare = PatchRecipe(
    (
        partial(write_text, path="share/tool/config.ini", content="mode=termux\n"),
        partial(make_executable, path="bin/tool-helper"),
    )
)


def tool_command(
    binary_name: str, real_binary: Path, target_key: str
) -> RuntimeCommand:
    return RuntimeCommand(
        argv=("qemu-aarch64", "-L", "/some/sysroot", real_binary),
        environment=(("TOOL_MODE", "compat"),),
    )


PATCH = PackagePatch(
    post_extract=(InstallPatch(prepare, targets=("aarch64-*",)),),
    runtime=(
        RuntimePatch(
            binaries=("tool",),
            targets=("aarch64-*",),
            command=tool_command,
        ),
    ),
)
```

`PatchRecipe` runs its reusable operations in order; `functools.partial` binds
operation arguments so simple filesystem changes need no custom handler
function. Custom handlers remain available for logic and conditional work.
Install handlers run in declaration order. `InstallPatch` and `RuntimePatch`
target filters use glob patterns against the target triple. A context contains
the package name, stage, install directory, target, and shared `PatchReport`.
Filesystem helpers (`write_text`, `set_permissions`, `make_executable`,
`create_symlink`, and `move_file`) accept paths relative to the install
directory, reject paths that escape it, skip no-op changes, and record changes
in the report. A custom handler can report a change with
`context.record(path, action, detail)`.

`RuntimeCommand` quotes argv, optionally exports environment values, forwards
the launcher's `"$@"` by default, and can suppress command failures.
`ArgumentEquals(index, value)` and
`ArgumentOneOf(index, values)` add positional argument conditions with an
optional `otherwise` command. `shell_exec` and `shell_export` are available
when building a shell snippet is more convenient. Multiple matching runtime
recipes append their before/after hooks; the first command handler that returns
a command takes precedence.

`inspect_elf(path)` returns typed `ElfInfo | None`. It exposes ELF class, byte
order, machine and architecture, numeric file type plus its readable `type_name`,
OS ABI and ABI version, ELF flags, a best effort ABI label, interpreter, and
program headers. `arm_abi` separately decodes ARM EABI and float flags when
available. Inspection memory maps the file instead of reading the full binary
into memory. `BinaryQuery` and `find_binaries(root, query)` select sorted
executable files by name, relative location, architecture or machine, ELF
class/type, ABI, OS ABI, or interpreter. `BinaryQuery` can also exclude
relative locations or prune every directory with a named component, which is
useful for avoiding generated caches while walking a package tree.

ELF mutation helpers return whether they changed the file:

- `set_elf_interpreter(binary, path)` sets the ELF interpreter.
- `set_elf_rpath(binary, rpath)` sets its RPATH or RUNPATH.
- `raise_tls_alignment(binary, alignment=..., machine=...)` updates `PT_TLS`
  only when the file layout satisfies the stronger alignment.

Interpreter and RPATH mutation use `patchelf` and raise if it is unavailable
or fails. Package patches choose when and where those operations apply.

`ship repatch <package>` reapplies package handlers and platform patchers to an
installed package, runs its optional `PackagePatch.reapply` handlers, refreshes
its links, and displays reported package and platform file changes without
downloading the archive again. Reapply handlers receive the shared
`PatchReport`, including when they patch files outside the package directory.

