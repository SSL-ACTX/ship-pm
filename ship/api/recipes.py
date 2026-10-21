"""Declarative package patch recipes, mixins, and runtime command builders."""

from __future__ import annotations

import subprocess
from enum import Enum, auto
from pathlib import Path

from ship.api.code import SourcePatcher
from ship.api.toolkit import (
    ArgumentCondition,
    ArgumentEquals,
    ArgumentOneOf,
    ExportPolicy,
    InstallHandler,
    InstallPatch,
    PackagePatch,
    PatchRecipe,
    ReapplyHandler,
    RuntimeCommand,
    RuntimePatch,
    RuntimeValue,
    shell_exec,
    shell_export,
)


class Mixin(Enum):
    """Platform adaptation mixins."""

    PosixShellSanitizer = auto()
    DisableBwrapSandbox = auto()
    BionicCompat = auto()
    AndroidShmem = auto()


class BuildContext:
    """Execution context provided to post_install and lifecycle hooks."""

    def __init__(self, install_dir: Path | str, home: Path | str | None = None) -> None:
        self.install_dir = Path(install_dir)
        self.home = Path(home) if home else Path.home()

    def exec(self, cmd: list[str], cwd: Path | None = None) -> int:
        """Run command synchronously inside the install/build tree."""
        return subprocess.run(cmd, cwd=cwd or self.install_dir, check=False).returncode

    def register_interceptor(
        self,
        tool: str,
        env_trigger: str,
        packages: list[str],
        c_flags: list[str] | None = None,
        ld_flags: list[str] | None = None,
        polyfills: list[str] | None = None,
    ) -> None:
        """Register dynamic toolchain build interceptor."""
        from ship.runtime.intercept import BuildInterceptor

        BuildInterceptor.register_rule(
            tool=tool,
            env_trigger=env_trigger,
            packages=packages,
            c_flags=c_flags,
            ld_flags=ld_flags,
            polyfills=polyfills,
        )


class PackageRecipe:
    """Declarative Ship v2 package recipe specification."""

    name: str = ""
    version: str = ""

    def __init__(
        self,
        name: str = "",
        version: str = "",
        mixins: list[Mixin] | None = None,
        prebuilts: dict[str, str] | None = None,
    ) -> None:
        self.name = name or self.name
        self.version = version or self.version
        self.mixins: list[Mixin] = list(mixins) if mixins is not None else []
        self.prebuilts: dict[str, str] = (
            dict(prebuilts) if prebuilts is not None else {}
        )

    def apply_mixins(self, root_dir: Path) -> None:
        """Apply active mixin shims across the extracted root."""
        from ship.runtime.polyfills import PolyfillEngine

        patcher = SourcePatcher(root_dir)
        for m in self.mixins:
            if m == Mixin.PosixShellSanitizer:
                PolyfillEngine.apply_posix_shell(root_dir, patcher)
            elif m == Mixin.DisableBwrapSandbox:
                PolyfillEngine.ensure_bwrap_shim()
            elif m == Mixin.BionicCompat:
                PolyfillEngine.apply_bionic_compat(root_dir, patcher)
            elif m == Mixin.AndroidShmem:
                PolyfillEngine.apply_android_shmem(root_dir, patcher)

    def post_extract(self, patcher: SourcePatcher, target_key: str) -> None:
        """Runs after initial extraction."""

    def post_install(self, ctx: BuildContext) -> None:
        """Lifecycle hook executed after linking."""


__all__ = [
    "ArgumentCondition",
    "ArgumentEquals",
    "ArgumentOneOf",
    "BuildContext",
    "ExportPolicy",
    "InstallHandler",
    "InstallPatch",
    "Mixin",
    "PackagePatch",
    "PackageRecipe",
    "PatchRecipe",
    "ReapplyHandler",
    "RuntimeCommand",
    "RuntimePatch",
    "RuntimeValue",
    "SourcePatcher",
    "shell_exec",
    "shell_export",
]
