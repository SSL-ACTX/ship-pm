"""Public patch authoring API.

Package and runtime authors should import from ``ship.api`` only. Internal
modules under ``ship.api.toolkit`` and ``ship.runtime`` are not a stable surface.
"""

from __future__ import annotations

from ship.api.code import SourcePatcher
from ship.api.recipes import BuildContext, Mixin, PackageRecipe
from ship.api.toolkit import (
    EM_AARCH64,
    PT_INTERP,
    PT_TLS,
    ArgumentCondition,
    ArgumentEquals,
    ArgumentOneOf,
    BinaryQuery,
    ElfByteOrder,
    ElfClass,
    ElfInfo,
    ElfProgramHeader,
    ElfType,
    ExportPolicy,
    InstallHandler,
    InstallPatch,
    InstallStage,
    PackagePatch,
    PatchChange,
    PatchContext,
    PatchRecipe,
    PatchReport,
    ReapplyHandler,
    RuntimeCommand,
    RuntimePatch,
    RuntimeValue,
    create_symlink,
    find_binaries,
    inspect_elf,
    make_executable,
    move_file,
    raise_tls_alignment,
    read_elf_rpath,
    replace_elf_needed,
    set_elf_interpreter,
    set_elf_rpath,
    set_permissions,
    shell_exec,
    shell_export,
    write_text,
)

# Domain-oriented re-export modules for scalable imports:
#   from ship.api.recipes import PackagePatch
#   from ship.api.elf import inspect_elf
#   from ship.api.fs import write_text
#   from ship.api.context import PatchContext

__all__ = [
    "EM_AARCH64",
    "PT_INTERP",
    "PT_TLS",
    "ArgumentCondition",
    "ArgumentEquals",
    "ArgumentOneOf",
    "BinaryQuery",
    "BuildContext",
    "ElfByteOrder",
    "ElfClass",
    "ElfInfo",
    "ElfProgramHeader",
    "ElfType",
    "ExportPolicy",
    "InstallHandler",
    "InstallPatch",
    "InstallStage",
    "Mixin",
    "PackagePatch",
    "PackageRecipe",
    "PatchChange",
    "PatchContext",
    "PatchRecipe",
    "PatchReport",
    "ReapplyHandler",
    "RuntimeCommand",
    "RuntimePatch",
    "RuntimeValue",
    "SourcePatcher",
    "create_symlink",
    "find_binaries",
    "inspect_elf",
    "make_executable",
    "move_file",
    "raise_tls_alignment",
    "read_elf_rpath",
    "replace_elf_needed",
    "set_elf_interpreter",
    "set_elf_rpath",
    "set_permissions",
    "shell_exec",
    "shell_export",
    "write_text",
]
