"""Typed building blocks for package-specific patches and runtime adapters."""

from __future__ import annotations

import fnmatch
import mmap
import os
import re
import shlex
import shutil
import stat
import struct
import subprocess
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from pathlib import Path
from typing import Literal, Protocol

PT_TLS = 7
PT_INTERP = 3
EM_AARCH64 = 183
InstallStage = Literal["post_extract", "pre_link"]


class InstallHandler(Protocol):
    """One reusable operation in an install patch recipe."""

    def __call__(self, context: PatchContext) -> bool | None: ...


class ReapplyHandler(Protocol):
    """Callable that reapplies package-owned changes and records each change."""

    def __call__(self, report: PatchReport) -> None: ...


class ElfClass(IntEnum):
    """ELF object word size as encoded in ``e_ident[EI_CLASS]``."""

    ELF32 = 1
    ELF64 = 2


class ElfByteOrder(Enum):
    """ELF object byte order as encoded in ``e_ident[EI_DATA]``."""

    LITTLE = "little"
    BIG = "big"

    @property
    def struct_prefix(self) -> str:
        return "<" if self is ElfByteOrder.LITTLE else ">"


class ElfType(IntEnum):
    """Standard ELF object types encoded in ``e_type``."""

    NONE = 0
    REL = 1
    EXEC = 2
    DYN = 3
    CORE = 4


@dataclass(frozen=True)
class ElfProgramHeader:
    """Selected fields from one ELF program header."""

    segment_type: int
    file_offset: int
    virtual_address: int
    file_size: int
    alignment: int
    header_offset: int


@dataclass(frozen=True)
class ElfInfo:
    """Typed summary of an ELF object and its program headers."""

    elf_class: ElfClass
    byte_order: ElfByteOrder
    file_type: int
    machine: int
    os_abi: int
    abi_version: int
    flags: int
    program_headers: tuple[ElfProgramHeader, ...]
    interpreter: str | None

    @property
    def type_name(self) -> str:
        """ELF object type name, preserving unknown values explicitly."""
        try:
            return ElfType(self.file_type).name.lower()
        except ValueError:
            return f"type-{self.file_type}"

    @property
    def architecture(self) -> str:
        """Common architecture name for ``e_machine`` (or ``machine-N``)."""
        if self.machine == 243:
            return "riscv64" if self.elf_class is ElfClass.ELF64 else "riscv32"
        return {
            3: "i386",
            8: "mips",
            20: "powerpc",
            21: "powerpc64",
            22: "s390x",
            40: "arm",
            62: "x86_64",
            183: "aarch64",
        }.get(self.machine, f"machine-{self.machine}")

    @property
    def os_abi_name(self) -> str:
        return {
            0: "sysv",
            1: "hpux",
            2: "netbsd",
            3: "linux",
            6: "solaris",
            7: "aix",
            8: "irix",
            9: "freebsd",
            12: "openbsd",
            97: "arm",
            255: "standalone",
        }.get(self.os_abi, f"osabi-{self.os_abi}")

    @property
    def arm_abi(self) -> str | None:
        """Decode ARM EABI and floating-point ABI flags when present."""
        if self.machine == 40:
            eabi = (self.flags & 0xFF000000) >> 24
            float_abi = self.flags & 0x600
            if eabi:
                if float_abi == 0x400:
                    float_name = "hardfloat"
                elif float_abi == 0x200:
                    float_name = "softfloat"
                else:
                    float_name = "float-unspecified"
                return f"eabi{eabi}-{float_name}"
        return None

    @property
    def abi(self) -> str:
        """Best-effort runtime ABI inferred from interpreter and OS ABI."""
        interpreter = (self.interpreter or "").lower()
        if "musl" in interpreter:
            return "musl"
        if "android" in interpreter or Path(interpreter).name.startswith("linker"):
            return "android-bionic"
        if "ld-linux" in interpreter or "ld64.so" in interpreter:
            return "glibc"
        if self.os_abi != 0:
            return self.os_abi_name
        return "static-or-unspecified"


@dataclass(frozen=True)
class BinaryQuery:
    """Filters for selecting package executables from an install tree."""

    names: tuple[str, ...] = ()
    locations: tuple[Path, ...] = ()
    excluded_locations: tuple[Path, ...] = ()
    excluded_directory_names: tuple[str, ...] = ()
    architectures: tuple[str, ...] = ()
    elf_machines: tuple[int, ...] = ()
    elf_classes: tuple[ElfClass, ...] = ()
    elf_types: tuple[int, ...] = ()
    os_abis: tuple[int, ...] = ()
    abis: tuple[str, ...] = ()
    interpreters: tuple[str, ...] = ()
    executable_only: bool = True


@dataclass(frozen=True)
class PatchChange:
    """One file-level change made by a package patch handler."""

    path: Path
    action: str
    detail: str = ""


@dataclass
class PatchReport:
    """Accumulated changes from package install and runtime patch handlers."""

    package_name: str
    changes: list[PatchChange] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.changes)

    def add(self, path: Path, action: str, detail: str = "") -> PatchChange:
        change = PatchChange(path=path, action=action, detail=detail)
        self.changes.append(change)
        return change

    def extend(self, changes: Iterable[PatchChange]) -> None:
        self.changes.extend(changes)

    @staticmethod
    def describe(change: PatchChange) -> str:
        """Format a concise user-facing description of one file change."""
        path = change.path.name if change.path.is_absolute() else str(change.path)
        if change.action == "install runtime launcher":
            family = "QEMU" if "QEMU" in change.detail else "Termux"
            return f"{family} runtime launcher configured for {path}"
        if change.action == "configure glibc runtime":
            return f"glibc runtime configured for {path}"
        detail = f" ({change.detail})" if change.detail else ""
        return f"{change.action}: {path}{detail}"

    def summary(self) -> str:
        if not self.changes:
            return f"{self.package_name}: no patch files changed"
        return "\n".join(self.describe(change) for change in self.changes)


@dataclass
class PatchContext:
    """Typed context passed to a declarative install-stage patch handler."""

    package_name: str
    stage: InstallStage
    install_dir: Path
    target_key: str
    report: PatchReport

    def resolve(self, relative_path: Path | str) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"patch path must stay inside install_dir: {relative}")
        root = self.install_dir.resolve()
        candidate = root / relative
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"patch path escapes install_dir: {relative}") from exc
        return candidate

    def record(self, path: Path, action: str, detail: str = "") -> PatchChange:
        root = self.install_dir.resolve()
        candidate = path if path.is_absolute() else root / path
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            relative = candidate.resolve(strict=False).relative_to(root)
        return self.report.add(relative, action, detail)


@dataclass(frozen=True)
class InstallPatch:
    """An install handler with optional target triple glob filters."""

    handler: InstallHandler
    targets: tuple[str, ...] = ()

    def matches(self, target_key: str) -> bool:
        return not self.targets or any(
            fnmatch.fnmatchcase(target_key, pattern) for pattern in self.targets
        )


@dataclass(frozen=True)
class PatchRecipe:
    """Ordered reusable install operations that need no custom wrapper handler."""

    steps: tuple[InstallHandler, ...]

    def __call__(self, context: PatchContext) -> None:
        for step in self.steps:
            step(context)


@dataclass(frozen=True)
class ArgumentEquals:
    """A shell condition that matches one positional argument exactly."""

    index: int
    value: str

    def __post_init__(self) -> None:
        if self.index < 1:
            raise ValueError("shell positional argument indexes start at 1")


@dataclass(frozen=True)
class ArgumentOneOf:
    """A shell condition matching one positional argument against choices."""

    index: int
    values: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.index < 1:
            raise ValueError("shell positional argument indexes start at 1")
        if not self.values:
            raise ValueError("ArgumentOneOf requires at least one value")


ArgumentCondition = ArgumentEquals | ArgumentOneOf


def shell_export(name: str, value: str | Path) -> str:
    """Render one safely quoted shell environment assignment."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"invalid shell variable name: {name}")
    return f"export {name}={shlex.quote(str(value))}"


@dataclass(frozen=True)
class RuntimeCommand:
    """Typed, composable launcher command with environment and arg conditions."""

    argv: tuple[str | Path, ...]
    environment: tuple[tuple[str, str | Path], ...] = ()
    forward_args: bool = True
    ignore_failure: bool = False
    condition: ArgumentCondition | None = None
    otherwise: RuntimeCommand | None = None

    def __post_init__(self) -> None:
        if not self.argv:
            raise ValueError("runtime command argv cannot be empty")
        for name, _ in self.environment:
            shell_export(name, "")

    def render(self, indent: int = 0) -> str:
        pad = " " * indent
        lines = [shell_export(name, value) for name, value in self.environment]
        command = shell_exec(*self.argv, forward_args=self.forward_args)
        if self.ignore_failure:
            command += " || true"
        lines.append(command)
        if self.condition is None:
            return "\n".join(pad + line for line in lines)

        condition = self.condition
        argument = f'"${{{condition.index}:-}}"'
        if isinstance(condition, ArgumentEquals):
            test = f"[ {argument} = {shlex.quote(condition.value)} ]"
        else:
            tests = [
                f"[ {argument} = {shlex.quote(value)} ]" for value in condition.values
            ]
            test = " || ".join(tests)
        branches = [f"{pad}if {test}; then"]
        branches.append("\n".join(" " * (indent + 2) + line for line in lines))
        if self.otherwise:
            branches.append(f"{pad}else")
            branches.append(self.otherwise.render(indent + 2))
        branches.append(f"{pad}fi")
        return "\n".join(branches)


RuntimeValue = (
    str | RuntimeCommand | Callable[[str, Path, str], str | RuntimeCommand | None]
)


def write_text(context: PatchContext, path: Path | str, content: str) -> bool:
    """Atomically write UTF-8 text inside a package and report actual changes."""
    destination = context.resolve(path)
    if destination == context.install_dir.resolve():
        raise ValueError("write_text requires a file path inside install_dir")
    if destination.is_symlink():
        raise ValueError(f"refusing to write through a package symlink: {path}")
    if destination.exists() and not destination.is_file():
        raise IsADirectoryError(destination)
    encoded = content.encode("utf-8")
    if destination.is_file() and destination.read_bytes() == encoded:
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.parent.resolve() != context.install_dir.resolve():
        try:
            destination.parent.resolve().relative_to(context.install_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"write path escapes install_dir: {path}") from exc
    mode = stat.S_IMODE(destination.stat().st_mode) if destination.exists() else 0o644
    fd, temp_name = tempfile.mkstemp(prefix=".ship-patch-", dir=destination.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
        temp_path.chmod(mode)
        os.replace(temp_path, destination)
    finally:
        temp_path.unlink(missing_ok=True)
    context.record(destination, "write", "updated UTF-8 text")
    return True


def set_permissions(context: PatchContext, path: Path | str, mode: int) -> bool:
    """Set a package file's mode safely; return whether permissions changed."""
    if mode < 0 or mode > 0o7777:
        raise ValueError(f"invalid file mode: {mode:o}")
    target = context.resolve(path)
    if target.is_symlink() or not target.is_file():
        raise FileNotFoundError(f"not a regular package file: {path}")
    current = stat.S_IMODE(target.stat().st_mode)
    if current == mode:
        return False
    target.chmod(mode)
    context.record(target, "chmod", f"{current:o} -> {mode:o}")
    return True


def make_executable(context: PatchContext, path: Path | str) -> bool:
    """Add executable bits for owner, group, and other, preserving other bits."""
    target = context.resolve(path)
    if target.is_symlink() or not target.is_file():
        raise FileNotFoundError(f"not a regular package file: {path}")
    mode = stat.S_IMODE(target.stat().st_mode)
    return set_permissions(context, path, mode | 0o111)


def create_symlink(
    context: PatchContext,
    link: Path | str,
    target: Path | str,
    *,
    replace: bool = False,
) -> bool:
    """Create an in-package relative symlink without allowing path escapes."""
    link_path = context.resolve(link)
    target_path = context.resolve(target)
    if not target_path.exists():
        raise FileNotFoundError(f"symlink target does not exist: {target}")
    link_path.parent.mkdir(parents=True, exist_ok=True)
    context.resolve(link_path.relative_to(context.install_dir.resolve()))
    relative_target = Path(os.path.relpath(target_path, link_path.parent))
    if link_path.is_symlink():
        if link_path.resolve(strict=False) == target_path.resolve():
            return False
        if not replace:
            raise FileExistsError(link_path)
        link_path.unlink()
    elif link_path.exists():
        if not replace:
            raise FileExistsError(link_path)
        if not link_path.is_file():
            raise IsADirectoryError(link_path)
        link_path.unlink()
    link_path.symlink_to(relative_target)
    context.record(
        link_path,
        "symlink",
        f"-> {target_path.relative_to(context.install_dir.resolve())}",
    )
    return True


def move_file(
    context: PatchContext,
    source: Path | str,
    destination: Path | str,
    *,
    replace: bool = False,
) -> bool:
    """Move a regular package file to another in-package path."""
    source_path = context.resolve(source)
    destination_path = context.resolve(destination)
    if source_path.is_symlink() or not source_path.is_file():
        raise FileNotFoundError(f"not a regular package source file: {source}")
    if source_path == destination_path:
        return False
    if (destination_path.exists() or destination_path.is_symlink()) and not replace:
        raise FileExistsError(destination_path)
    if destination_path.is_dir():
        raise IsADirectoryError(destination_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    context.resolve(destination_path.relative_to(context.install_dir.resolve()))
    os.replace(source_path, destination_path)
    context.record(
        destination_path,
        "move",
        f"from {source_path.relative_to(context.install_dir.resolve())}",
    )
    return True


def _inspect_elf_data(data: bytes | mmap.mmap) -> ElfInfo | None:
    if len(data) < 52 or data[:4] != b"\x7fELF":
        return None
    try:
        elf_class = ElfClass(data[4])
        byte_order = {1: ElfByteOrder.LITTLE, 2: ElfByteOrder.BIG}[data[5]]
    except (ValueError, KeyError):
        return None

    prefix = byte_order.struct_prefix
    file_type, machine = struct.unpack_from(prefix + "HH", data, 16)
    os_abi, abi_version = data[7], data[8]
    if elf_class is ElfClass.ELF64:
        if len(data) < 64:
            return None
        phoff = struct.unpack_from(prefix + "Q", data, 32)[0]
        flags = struct.unpack_from(prefix + "I", data, 48)[0]
        phentsize, phnum = struct.unpack_from(prefix + "HH", data, 54)
        min_phentsize = 56
        word_format = "Q"
        field_offsets = (8, 16, 32, 48)
    else:
        phoff = struct.unpack_from(prefix + "I", data, 28)[0]
        flags = struct.unpack_from(prefix + "I", data, 36)[0]
        phentsize, phnum = struct.unpack_from(prefix + "HH", data, 42)
        min_phentsize = 32
        word_format = "I"
        field_offsets = (4, 8, 16, 28)

    if phnum == 0:
        return ElfInfo(
            elf_class,
            byte_order,
            file_type,
            machine,
            os_abi,
            abi_version,
            flags,
            (),
            None,
        )
    if phnum == 0xFFFF or phentsize < min_phentsize:
        return None
    if phoff + phentsize * phnum > len(data):
        return None

    headers: list[ElfProgramHeader] = []
    interpreter: str | None = None
    for index in range(phnum):
        offset = phoff + index * phentsize
        segment_type = struct.unpack_from(prefix + "I", data, offset)[0]
        file_offset, vaddr, file_size, alignment = (
            struct.unpack_from(prefix + word_format, data, offset + field_offset)[0]
            for field_offset in field_offsets
        )
        headers.append(
            ElfProgramHeader(
                segment_type=segment_type,
                file_offset=file_offset,
                virtual_address=vaddr,
                file_size=file_size,
                alignment=alignment,
                header_offset=offset,
            )
        )
        if segment_type == PT_INTERP and file_offset + file_size <= len(data):
            raw_interpreter = data[file_offset : file_offset + file_size]
            interpreter = raw_interpreter.split(b"\0", 1)[0].decode(
                "utf-8", errors="replace"
            )

    return ElfInfo(
        elf_class=elf_class,
        byte_order=byte_order,
        file_type=file_type,
        machine=machine,
        os_abi=os_abi,
        abi_version=abi_version,
        flags=flags,
        program_headers=tuple(headers),
        interpreter=interpreter,
    )


def inspect_elf(binary: Path) -> ElfInfo | None:
    """Inspect ELF metadata without loading the full binary into memory."""
    with binary.open("rb") as stream:
        if os.fstat(stream.fileno()).st_size == 0:
            return None
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
            return _inspect_elf_data(mapped)


def _patchelf_path(patchelf: str | Path | None) -> str:
    executable = str(patchelf) if patchelf is not None else shutil.which("patchelf")
    if not executable:
        raise FileNotFoundError("patchelf is required for this ELF mutation")
    return executable


def set_elf_interpreter(
    binary: Path,
    interpreter: str | Path,
    *,
    patchelf: str | Path | None = None,
) -> bool:
    """Set an ELF interpreter using patchelf; return whether it changed."""
    info = inspect_elf(binary)
    if info is None:
        return False
    value = str(interpreter)
    if not Path(value).is_absolute():
        raise ValueError("ELF interpreter must be an absolute path")
    if info.interpreter == value:
        return False
    subprocess.run(
        [_patchelf_path(patchelf), "--set-interpreter", value, str(binary)],
        check=True,
        capture_output=True,
        text=True,
    )
    return True


def read_elf_rpath(binary: Path, *, patchelf: str | Path | None = None) -> str | None:
    """Read an ELF RPATH/RUNPATH with patchelf, or return None if absent."""
    if inspect_elf(binary) is None:
        return None
    result = subprocess.run(
        [_patchelf_path(patchelf), "--print-rpath", str(binary)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        return None
    value = result.stdout.strip()
    return value or None


def set_elf_rpath(
    binary: Path,
    rpath: str,
    *,
    patchelf: str | Path | None = None,
) -> bool:
    """Set an ELF RPATH/RUNPATH using patchelf; return whether it changed."""
    if inspect_elf(binary) is None:
        return False
    executable = _patchelf_path(patchelf)
    if (read_elf_rpath(binary, patchelf=executable) or "") == rpath:
        return False
    subprocess.run(
        [executable, "--set-rpath", rpath, str(binary)],
        check=True,
        capture_output=True,
        text=True,
    )
    return True


def find_binaries(root: Path, query: BinaryQuery = BinaryQuery()) -> list[Path]:
    """Return sorted, non-symlink files under ``root`` matching ``query``.

    ``locations`` are relative paths naming allowed subtrees or individual
    files. Exclusions prune matching subtrees while walking. ELF-specific
    filters are combined and reject scripts/non-ELF files.
    """
    if not root.is_dir():
        return []
    for location in (*query.locations, *query.excluded_locations):
        if location.is_absolute() or ".." in location.parts:
            raise ValueError(f"binary query location must stay inside root: {location}")
    if any(
        not name or Path(name).name != name for name in query.excluded_directory_names
    ):
        raise ValueError("excluded directory names must be single path components")

    selected: list[Path] = []
    executable_bits = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    needs_elf_info = bool(
        query.elf_machines
        or query.architectures
        or query.elf_classes
        or query.elf_types
        or query.os_abis
        or query.abis
        or query.interpreters
    )
    for current, dirs, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        relative_dir = current_path.relative_to(root)
        dirs[:] = sorted(
            name
            for name in dirs
            if name not in query.excluded_directory_names
            and not any(
                excluded == Path(".")
                or relative_dir == excluded
                or excluded in relative_dir.parents
                or (relative_dir / name) == excluded
                or excluded in (relative_dir / name).parents
                for excluded in query.excluded_locations
            )
        )
        for name in sorted(files):
            path = current_path / name
            if path.is_symlink() or not path.is_file():
                continue
            if query.names and path.name not in query.names:
                continue
            try:
                mode = path.stat().st_mode
            except OSError:
                continue
            if query.executable_only and not mode & executable_bits:
                continue
            relative = path.relative_to(root)
            if any(
                relative == excluded or excluded in relative.parents
                for excluded in query.excluded_locations
            ):
                continue
            if query.locations and not any(
                location == Path(".")
                or relative == location
                or location in relative.parents
                for location in query.locations
            ):
                continue
            if needs_elf_info:
                try:
                    info = inspect_elf(path)
                except OSError:
                    continue
                if info is None:
                    continue
                if query.architectures and info.architecture not in query.architectures:
                    continue
                if query.elf_machines and info.machine not in query.elf_machines:
                    continue
                if query.elf_classes and info.elf_class not in query.elf_classes:
                    continue
                if query.elf_types and info.file_type not in query.elf_types:
                    continue
                if query.os_abis and info.os_abi not in query.os_abis:
                    continue
                if query.abis and info.abi not in query.abis:
                    continue
                if query.interpreters and info.interpreter not in query.interpreters:
                    continue
            selected.append(path)
    return sorted(selected)


def shell_exec(*argv: str | Path, forward_args: bool = True) -> str:
    """Build a safely quoted launcher command, forwarding the caller's arguments."""
    if not argv:
        raise ValueError("shell command argv cannot be empty")
    command = " ".join(shlex.quote(str(part)) for part in argv)
    if forward_args:
        command += ' "$@"'
    return command


def raise_tls_alignment(
    binary: Path,
    *,
    alignment: int,
    machine: int,
) -> bool:
    """Raise ELF PT_TLS alignment when the file layout safely permits it.

    Supports ELF32 and ELF64 in either byte order. Returns True only when a
    PT_TLS program header was changed. The caller owns the policy for which
    binaries and alignment requirements should be applied.
    """
    if alignment < 2 or alignment & (alignment - 1):
        raise ValueError("TLS alignment must be a power of two greater than one")

    data = bytearray(binary.read_bytes())
    info = _inspect_elf_data(data)
    if info is None or info.machine != machine:
        return False
    word_format = "Q" if info.elf_class is ElfClass.ELF64 else "I"
    alignment_offset = 48 if info.elf_class is ElfClass.ELF64 else 28
    if alignment >= 1 << (struct.calcsize(word_format) * 8):
        raise ValueError(f"TLS alignment does not fit {info.elf_class.name}")

    changed = False
    prefix = info.byte_order.struct_prefix
    for header in info.program_headers:
        if header.segment_type != PT_TLS or header.alignment >= alignment:
            continue
        if header.file_offset % alignment != header.virtual_address % alignment:
            continue
        struct.pack_into(
            prefix + word_format,
            data,
            header.header_offset + alignment_offset,
            alignment,
        )
        changed = True

    if changed:
        binary.write_bytes(data)
    return changed


@dataclass(frozen=True)
class PackagePatch:
    """Composable package install and runtime handlers."""

    post_extract: tuple[InstallPatch, ...] = ()
    pre_link: tuple[InstallPatch, ...] = ()
    runtime: tuple[RuntimePatch, ...] = ()
    reapply: tuple[ReapplyHandler, ...] = ()
    excluded_link_names: tuple[str, ...] = ()
    discover_all_bins: bool = False


@dataclass(frozen=True)
class RuntimePatch:
    """Runtime behavior scoped by command name and target triple patterns."""

    binaries: tuple[str, ...]
    targets: tuple[str, ...] = ()
    before: RuntimeValue = ""
    after: RuntimeValue = ""
    command: RuntimeValue = ""

    def matches(self, binary_name: str, target_key: str) -> bool:
        return binary_name in self.binaries and (
            not self.targets
            or any(fnmatch.fnmatchcase(target_key, pattern) for pattern in self.targets)
        )

    def resolve(
        self,
        value: RuntimeValue,
        binary_name: str,
        real_binary: Path,
        target_key: str,
    ) -> str:
        resolved = (
            value(binary_name, real_binary, target_key) if callable(value) else value
        )
        if isinstance(resolved, RuntimeCommand):
            return resolved.render()
        return resolved or ""
