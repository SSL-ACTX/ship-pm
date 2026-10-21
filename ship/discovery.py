"""Discovery and classification of CLI executables within package trees."""

import os
import re
from pathlib import Path

NON_EXEC_EXTENSIONS = (
    ".so",
    ".dylib",
    ".dll",
    ".a",
    ".lib",
    ".rlib",
    ".o",
    ".obj",
    ".export",
    ".h",
    ".hpp",
    ".c",
    ".cpp",
    ".rs",
    ".py",
    ".pyc",
    ".pyo",
    ".lean",
    ".olean",
    ".ilean",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
    ".txt",
    ".md",
    ".lock",
    ".log",
)

NON_EXEC_NAMES = (
    "install.sh",
    "install-sh",
    "uninstall.sh",
    "setup.sh",
    "configure",
    "makefile",
    "cmakelists.txt",
)


def is_cli_executable(file_path: Path) -> bool:
    """Return whether a path is a functional CLI executable, not a script/installer."""
    name = file_path.name.lower()

    if name in NON_EXEC_NAMES or name.startswith("install-"):
        return False

    if any(name.endswith(ext) or f"{ext}." in name for ext in NON_EXEC_EXTENSIONS):
        return False

    if name.startswith("lib") and (".so" in name or ".dylib" in name):
        return False

    try:
        with open(file_path, "rb") as f:
            magic = f.read(18)
            if not magic:
                return False

            if magic.startswith(b"#!"):
                return True

            if magic.startswith(b"MZ"):
                return True

            if magic[:4] in (
                b"\xfe\xed\xfa\xce",
                b"\xfe\xed\xfa\xcf",
                b"\xce\xfa\xed\xfe",
                b"\xcf\xfa\xed\xfe",
                b"\xca\xfe\xba\xbe",
            ):
                return True

            if magic.startswith(b"\x7fELF"):
                if len(magic) >= 18:
                    e_type = magic[16] | (magic[17] << 8)
                    if e_type == 1:  # ET_REL
                        return False
                return True

    except OSError:
        return False

    return False


def is_compiled_executable(file_path: Path) -> bool:
    """Return whether a path is a compiled native binary (ELF / Mach-O / PE)."""
    try:
        with open(file_path, "rb") as f:
            magic = f.read(4)
    except OSError:
        return False

    return magic.startswith((b"\x7fELF", b"MZ")) or magic in (
        b"\xfe\xed\xfa\xce",
        b"\xfe\xed\xfa\xcf",
        b"\xce\xfa\xed\xfe",
        b"\xcf\xfa\xed\xfe",
        b"\xca\xfe\xba\xbe",
    )


def scan_executables(install_dir: Path) -> list[Path]:
    """Find all valid non-symlink CLI executables inside an install tree."""
    results = []
    for root, dirs, files in os.walk(install_dir, followlinks=False):
        dirs[:] = sorted(
            d for d in dirs if d not in ("lib", "lib64", "share", "include", "build")
        )
        for name in files:
            path = Path(root) / name
            if not path.is_symlink() and is_cli_executable(path):
                results.append(path)
    return results


def resolve_command_binaries(
    install_dir: Path,
    pkg_name: str,
    declared_binaries: dict[str, str] | None = None,
    target_key: str = "",
) -> dict[str, Path]:
    """
    Resolve logical command names (e.g. 'kissat', 'yices') to real file paths.
    Prioritizes declared manifest mappings, then compiled ELFs, then base-name matches.
    """
    resolved: dict[str, Path] = {}
    declared = declared_binaries or {}

    # 1. Exact declared path matching
    for cmd_name, rel_path in declared.items():
        candidate = install_dir / rel_path
        if not candidate.is_file():
            candidate = install_dir / "bin" / cmd_name
        if not candidate.is_file():
            search_names = [cmd_name]
            if "windows" in target_key and not cmd_name.lower().endswith(".exe"):
                search_names.append(f"{cmd_name}.exe")
            for root, _, files in os.walk(install_dir):
                match = next((name for name in search_names if name in files), None)
                if match:
                    p = Path(root) / match
                    if is_cli_executable(p):
                        candidate = p
                        break
        if candidate.is_file() and is_cli_executable(candidate):
            resolved[cmd_name] = candidate

    # 2. Gather candidates, prioritizing compiled ELFs
    all_exes = [
        p for p in scan_executables(install_dir) if not p.name.endswith("-real")
    ]
    compiled = [p for p in all_exes if is_compiled_executable(p)]
    pool = compiled if compiled else all_exes

    # 3. Handle single-binary manifests with mismatched filenames (e.g. kissat)
    if not resolved:
        if len(declared) == 1 and len(pool) == 1:
            cmd_name = next(iter(declared))
            resolved[cmd_name] = pool[0]
        else:
            for cand in pool:
                resolved[cand.name] = cand

    # 4. Resolve package name alias (e.g. yices2 -> yices)
    if pkg_name not in resolved and pool:
        base_name = re.sub(r"\d+$", "", pkg_name)
        matched = next((p for p in pool if p.name == base_name), None)
        if not matched:
            matched = resolved.get(next(iter(resolved))) if resolved else pool[0]
        resolved[pkg_name] = matched

    return resolved
