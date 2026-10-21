"""Host platform profiles: path defaults, target preference, runtime adapters."""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

ProfileId = Literal[
    "termux", "linux", "darwin", "freebsd", "openbsd", "netbsd", "windows", "generic"
]

TERMUX_PREFIX_DEFAULT = Path("/data/data/com.termux/files/usr")
TERMUX_ROOT_MARKER = Path("/data/data/com.termux")


@dataclass(frozen=True)
class ProfilePaths:
    """Platform-owned path bundle. Package patches must use these, not hardcode hosts."""

    prefix: Path
    glibc_prefix: Path
    glibc_lib: Path
    bash: Path
    cert_candidates: tuple[Path, ...] = ()
    resolv_conf: Path | None = None


@dataclass(frozen=True)
class Profile:
    """Resolved runtime profile for the current host."""

    id: ProfileId
    home: Path
    data_root: Path
    bin_dir: Path
    internal_bin: Path
    cache_dir: Path
    store_dir: Path
    backup_dir: Path
    state_file: Path
    registry_dir: Path
    paths: ProfilePaths
    target_priority: tuple[str, ...]
    runtime_adapters: tuple[str, ...] = ()
    forbid_bin_dirs: tuple[Path, ...] = ()
    allows_system_prefix_bin: bool = False

    @property
    def is_termux(self) -> bool:
        return self.id == "termux"


def detect_profile_id() -> ProfileId:
    explicit = os.environ.get("SHIP_PROFILE", "").strip().casefold()
    if explicit in {
        "termux",
        "linux",
        "darwin",
        "freebsd",
        "openbsd",
        "netbsd",
        "windows",
        "generic",
    }:
        return explicit  # type: ignore[return-value]

    if "TERMUX_VERSION" in os.environ or TERMUX_ROOT_MARKER.exists():
        return "termux"

    system = platform.system().lower()
    if system == "darwin":
        return "darwin"
    if system == "windows":
        return "windows"
    if system == "freebsd":
        return "freebsd"
    if system == "openbsd":
        return "openbsd"
    if system == "netbsd":
        return "netbsd"
    if system == "linux":
        return "linux"
    return "generic"


def _normalize_arch(raw_arch: str) -> str:
    arch = raw_arch.lower()
    if arch in ("x86_64", "amd64", "x64"):
        return "x86_64"
    if arch in ("aarch64", "arm64"):
        return "aarch64"
    if arch.startswith("armv7") or arch in ("armhf", "arm"):
        return "armv7"
    if arch.startswith("armv6") or arch == "armel":
        return "armv6"
    if arch == "riscv64":
        return "riscv64"
    if arch in ("ppc64le", "powerpc64le"):
        return "powerpc64le"
    if arch == "s390x":
        return "s390x"
    if arch.startswith("i") and arch.endswith("86") or arch == "x86":
        return "i686"
    return arch


def probe_libc_flavor() -> str:
    """Accurately determine whether host / runtime environment defaults to gnu (glibc) or musl.

    Returns:
        'gnu', 'musl', or 'bionic'
    """
    import ctypes

    # Direct runtime check via libc symbol export
    try:
        libc = ctypes.CDLL(None)
        if hasattr(libc, "gnu_get_libc_version"):
            return "gnu"
    except Exception:
        pass

    # Inspect running executable interpreter (/proc/self/exe or sys.executable)
    for exe in (Path("/proc/self/exe"), Path(sys.executable)):
        try:
            if exe.is_file():
                with open(exe, "rb") as f:
                    chunk = f.read(4096)
                    if b"ld-musl" in chunk:
                        return "musl"
                    if b"ld-linux" in chunk or b"ld64.so" in chunk:
                        return "gnu"
        except (OSError, PermissionError):
            pass

    # Alpine release marker
    if Path("/etc/alpine-release").exists():
        return "musl"

    # Check for standard musl dynamic loaders
    for path in (
        "/lib/ld-musl-x86_64.so.1",
        "/lib/ld-musl-aarch64.so.1",
        "/usr/lib/ld-musl-x86_64.so.1",
        "/usr/lib/ld-musl-aarch64.so.1",
    ):
        if Path(path).exists():
            return "musl"

    # Check for standard glibc dynamic loaders or ld.so configuration
    if Path("/etc/ld.so.conf").exists() or Path("/etc/ld.so.cache").exists():
        return "gnu"
    for path in (
        "/lib64/ld-linux-x86-64.so.2",
        "/lib/ld-linux-aarch64.so.1",
        "/lib/ld-linux.so.2",
        "/lib/ld-linux-armhf.so.3",
    ):
        if Path(path).exists():
            return "gnu"

    return "gnu"


def _is_musl_host() -> bool:
    return probe_libc_flavor() == "musl"


def _has_termux_glibc(arch: str | None = None) -> bool:
    """Check if Termux has an active glibc environment with loader installed."""
    prefix_str = os.environ.get("GLIBC_PREFIX")
    if prefix_str:
        prefix = Path(prefix_str)
    else:
        prefix = (
            Path(os.environ.get("PREFIX", "/data/data/com.termux/files/usr")) / "glibc"
        )

    if not prefix.is_dir():
        return False

    lib_dir = prefix / "lib"
    if not lib_dir.is_dir():
        return False

    # Check for any ld-linux loader in the glibc lib dir
    for loader in lib_dir.glob("ld-linux*"):
        if loader.is_file():
            return True
    return bool((lib_dir / "ld.so").exists())


def default_target_priority(
    profile_id: ProfileId, arch: str | None = None
) -> tuple[str, ...]:
    host_arch = arch or _normalize_arch(platform.machine())
    if profile_id == "darwin":
        if host_arch == "aarch64":
            return ("aarch64-apple-darwin", "x86_64-apple-darwin")
        return ("x86_64-apple-darwin",)
    if profile_id == "freebsd":
        return (f"{host_arch}-freebsd",)
    if profile_id == "openbsd":
        return (f"{host_arch}-openbsd",)
    if profile_id == "netbsd":
        return (f"{host_arch}-netbsd",)
    if profile_id == "windows":
        return (f"{host_arch}-pc-windows-msvc", f"{host_arch}-pc-windows-gnu")
    if profile_id == "termux":
        # If Termux has glibc installed, prioritize gnu prebuilts over musl.
        if _has_termux_glibc(host_arch):
            return (
                f"{host_arch}-linux-gnu",
                f"{host_arch}-termux",
                f"{host_arch}-android",
                f"{host_arch}-linux-android",
                f"{host_arch}-linux-musl",
            )
        return (
            f"{host_arch}-linux-musl",
            f"{host_arch}-termux",
            f"{host_arch}-android",
            f"{host_arch}-linux-android",
            f"{host_arch}-linux-gnu",
        )
    if _is_musl_host():
        return (f"{host_arch}-linux-musl", f"{host_arch}-linux-gnu")
    return (f"{host_arch}-linux-gnu", f"{host_arch}-linux-musl")


def _termux_paths(prefix: Path) -> ProfilePaths:
    glibc_prefix = Path(os.environ.get("GLIBC_PREFIX", str(prefix / "glibc")))
    bash = prefix / "bin" / "bash"
    return ProfilePaths(
        prefix=prefix,
        glibc_prefix=glibc_prefix,
        glibc_lib=glibc_prefix / "lib",
        bash=bash if bash.is_file() else Path("/bin/sh"),
        cert_candidates=(
            prefix / "etc" / "tls" / "cert.pem",
            prefix / "etc" / "ssl" / "certs" / "ca-certificates.crt",
            glibc_prefix / "etc" / "ssl" / "certs" / "ca-certificates.crt",
        ),
        resolv_conf=prefix / "etc" / "resolv.conf",
    )


def _posix_paths(prefix: Path) -> ProfilePaths:
    bash = Path("/bin/bash") if Path("/bin/bash").is_file() else Path("/bin/sh")
    return ProfilePaths(
        prefix=prefix,
        glibc_prefix=prefix,
        glibc_lib=prefix / "lib",
        bash=bash,
        cert_candidates=(
            Path("/etc/ssl/certs/ca-certificates.crt"),
            Path("/etc/pki/tls/certs/ca-bundle.crt"),
            Path("/etc/ssl/cert.pem"),
        ),
        resolv_conf=Path("/etc/resolv.conf"),
    )


def _layout_for(
    profile_id: ProfileId,
    *,
    home: Path,
    prefix: Path,
) -> tuple[Path, Path, ProfilePaths, tuple[str, ...], tuple[Path, ...]]:
    """Return data_root, bin_dir, paths, adapters, forbidden bins."""
    if profile_id == "termux":
        data_root = prefix / "share" / "ship"
        bin_dir = home / ".local" / "bin"
        paths = _termux_paths(prefix)
        adapters = ("qemu", "termux-glibc")
        forbidden = (
            Path("/bin"),
            Path("/sbin"),
            Path("/usr/bin"),
            Path("/usr/sbin"),
            prefix / "bin",
        )
        return data_root, bin_dir, paths, adapters, forbidden

    data_root = home / ".local" / "share" / "ship"
    bin_dir = home / ".local" / "bin"
    paths = _posix_paths(prefix if profile_id != "darwin" else Path("/usr/local"))
    adapters = ("qemu",) if profile_id in {"linux", "generic"} else ()
    forbidden = (
        Path("/bin"),
        Path("/sbin"),
        Path("/usr/bin"),
        Path("/usr/sbin"),
        prefix / "bin",
    )
    return data_root, bin_dir, paths, adapters, forbidden


def build_profile(
    profile_id: ProfileId | None = None,
    *,
    home: Path | None = None,
    environ: dict[str, str] | None = None,
) -> Profile:
    """Construct a Profile from detection + environment overrides."""
    env = environ if environ is not None else os.environ
    home_path = home or Path.home()
    resolved_id = profile_id or detect_profile_id()

    if "PREFIX" in env:
        prefix = Path(env["PREFIX"])
    elif resolved_id == "termux":
        prefix = TERMUX_PREFIX_DEFAULT
    elif resolved_id == "darwin":
        prefix = Path("/usr/local")
    else:
        prefix = Path("/usr")

    data_root, bin_dir, paths, adapters, forbidden = _layout_for(
        resolved_id, home=home_path, prefix=prefix
    )

    if "SHIP_ROOT" in env:
        data_root = Path(env["SHIP_ROOT"])
    if "SHIP_BIN_DIR" in env:
        bin_dir = Path(env["SHIP_BIN_DIR"]).resolve()
    else:
        bin_dir = bin_dir.resolve()

    if "GLIBC_PREFIX" in env:
        glibc_prefix = Path(env["GLIBC_PREFIX"])
        paths = replace(
            paths,
            glibc_prefix=glibc_prefix,
            glibc_lib=glibc_prefix / "lib",
        )

    return Profile(
        id=resolved_id,
        home=home_path,
        data_root=data_root,
        bin_dir=bin_dir,
        internal_bin=data_root / "bin",
        cache_dir=data_root / "cache",
        store_dir=data_root / "store",
        backup_dir=data_root / "backups",
        state_file=data_root / "state.json",
        registry_dir=data_root / "registry",
        paths=paths,
        target_priority=default_target_priority(resolved_id),
        runtime_adapters=adapters,
        forbid_bin_dirs=forbidden,
    )


# Process-wide active profile. Tests may call ``set_active_profile``.
_ACTIVE: Profile | None = None


def get_active_profile() -> Profile:
    global _ACTIVE
    if _ACTIVE is None:
        _ACTIVE = build_profile()
    return _ACTIVE


def set_active_profile(profile: Profile | None) -> None:
    """Replace or clear the process-wide profile (primarily for tests)."""
    global _ACTIVE
    _ACTIVE = profile


def reset_active_profile() -> Profile:
    set_active_profile(None)
    return get_active_profile()
