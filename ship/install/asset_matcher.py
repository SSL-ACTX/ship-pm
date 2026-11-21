# ship/install/asset_matcher.py
"""Shared asset-matching logic for GitHub release assets.

This module is the single source of truth for:
  - Extension/pattern filter sets (SIG_EXTENSIONS, SKIP_EXTENSIONS, …)
  - ``parse_asset_target()``  — classify a filename into a target triple
  - ``filter_asset()``        — quick boolean skip-check

Both ``ship/install/github_source.py`` (runtime install) and
``.github/scripts/resolve_release.py`` (CI registry indexer) import from here.
"""

from __future__ import annotations

__all__ = [
    "ARCHIVE_EXTENSIONS",
    "BUILD_ARTIFACT_PATTERNS",
    "SIG_EXTENSIONS",
    "SKIP_EXTENSIONS",
    "filter_asset",
    "parse_asset_target",
]

# ---------------------------------------------------------------------------
# Extension / pattern sets
# ---------------------------------------------------------------------------

SIG_EXTENSIONS: tuple[str, ...] = (
    ".sig",
    ".asc",
    ".minisig",
    ".pem",
    ".cert",
    ".crt",
    ".sbom",
)

ARCHIVE_EXTENSIONS: tuple[str, ...] = (
    ".tar.gz",
    ".tgz",
    ".tar.xz",
    ".txz",
    ".tar.bz2",
    ".tbz2",
    ".tar.zst",
    ".zip",
    ".7z",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
)

# Assets whose format makes them unsuitable for ship's binary-extraction
# pipeline.  .deb is intentionally NOT here — ship/install/deb_source.py
# handles Debian archives natively.
SKIP_EXTENSIONS: tuple[str, ...] = (
    ".whl",
    ".nupkg",
    ".snupkg",
    ".gem",
    ".jar",
    ".egg",
    ".rpm",
    ".apk",
    ".msi",
    ".dmg",
    ".pkg",
    ".appimage",
    ".txt",
    ".md",
    ".rst",
    ".pdf",
    ".html",
    ".htm",
)

BUILD_ARTIFACT_PATTERNS: tuple[str, ...] = (
    "lean-build-",
    "-debug.",
    "-dbg.",
    "-symbols.",
    "-sdk.",
    "-source.",
    "-src.",
    "-sources.",
    "installer",
    "setup",
    "-relink-kit",
    "relink-kit",
)

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def filter_asset(name: str) -> str | None:
    """Return a skip reason string if *name* should be excluded, else ``None``.

    ``name`` should already be lowercased by the caller.

    Return values (when not ``None``):
      ``"sig"``       — cryptographic signature / certificate
      ``"skip"``      — unsupported package format
      ``"build"``     — debug / SDK / source build artefact
      ``"doc"``       — documentation archive
      ``"checksum"``  — checksum manifest
    """
    if any(name.endswith(ext) for ext in SIG_EXTENSIONS):
        return "sig"
    if any(name.endswith(ext) for ext in SKIP_EXTENSIONS):
        return "skip"
    if any(k in name for k in BUILD_ARTIFACT_PATTERNS):
        return "build"
    if any(k in name for k in ("doc.zip", "docs.zip", "-doc.", "-docs.")):
        return "doc"
    if any(k in name for k in ("sha256", "checksum", "hashes", "sha256sum")):
        return "checksum"
    return None


def parse_asset_target(filename: str) -> tuple[str, bool] | None:
    """Classify *filename* into ``(target_triple, is_archive)`` or ``None``.

    Returns ``None`` when the asset should be skipped (signature, unsupported
    format, build artefact, documentation, or unrecognised platform).

    ``is_archive`` is ``True`` when the asset is a compressed archive rather
    than a bare executable.
    """
    fn = filename.lower()

    if filter_asset(fn) is not None:
        return None

    clean_name = fn
    is_archive = False
    for ext in ARCHIVE_EXTENSIONS:
        if clean_name.endswith(ext):
            clean_name = clean_name[: -len(ext)]
            is_archive = True
            break

    # .deb counts as an archive — binaries are extracted from the data tarball.
    if clean_name.endswith(".deb"):
        clean_name = clean_name[: -len(".deb")]
        is_archive = True

    clean_name = clean_name.removesuffix(".exe")

    # ------------------------------------------------------------------
    # 1. Operating system
    # ------------------------------------------------------------------
    if any(
        k in clean_name
        for k in ("linux", "glibc", "manylinux", "musl", "alpine", "ubuntu", "debian")
    ):
        os_name = "linux"
    elif any(
        k in clean_name for k in ("apple", "darwin", "macos", "osx", "mac-", "-mac")
    ):
        os_name = "darwin"
    elif (
        any(
            k in clean_name
            for k in (
                "windows",
                "pc-windows",
                "win64",
                "win32",
                "-win-",
                "-win.",
                "_win_",
                "_win.",
            )
        )
        or clean_name.endswith(("-win", "_win", "windows"))
        or fn.endswith(".exe")
    ):
        os_name = "windows"
    elif "openbsd" in clean_name:
        os_name = "openbsd"
    elif "freebsd" in clean_name:
        os_name = "freebsd"
    elif "netbsd" in clean_name:
        os_name = "netbsd"
    elif "android" in clean_name or "termux" in clean_name:
        os_name = "android"
    else:
        return None

    # ------------------------------------------------------------------
    # 2. Architecture
    # ------------------------------------------------------------------
    if any(k in clean_name for k in ("x86_64", "amd64", "x64")):
        arch = "x86_64"
    elif any(
        k in clean_name
        for k in ("aarch64", "arm64", "mac-arm", "-mac-arm", "macos-arm")
    ) or (os_name == "darwin" and any(k in clean_name for k in ("-arm", "_arm"))):
        arch = "aarch64"
    elif any(
        k in clean_name
        for k in (
            "armv7",
            "armhf",
            "arm32",
            "arm-unknown",
            "linux-arm",
            "-linux-arm",
            "-arm-linux",
            "_arm_linux",
            "-arm.",
        )
    ) or clean_name.endswith(("-arm", "_arm")):
        # Distinguish 64-bit ARM vs 32-bit ARM:
        # Modern Linux distros (e.g. ubuntu-*-arm) and generic desktop distributions
        # label 64-bit aarch64 archives simply as 'arm' or 'linux-arm'.
        arch = "aarch64" if os_name in ("linux", "darwin") else "armv7"
    elif any(k in clean_name for k in ("armv6", "armel")):
        arch = "armv6"
    elif "riscv64" in clean_name:
        arch = "riscv64"
    elif "ppc64le" in clean_name:
        arch = "powerpc64le"
    elif "s390x" in clean_name:
        arch = "s390x"
    elif any(
        k in clean_name for k in ("i686", "i386", "386", "-x86-", "-x86.", "-x86")
    ):
        arch = "i686"
    else:
        # Universal / source assets have no meaningful machine arch.
        if any(k in clean_name for k in ("universal", "source", "src", "-all", "_all")):
            return None
        arch = "x86_64"

    # ------------------------------------------------------------------
    # 3. ABI / libc
    # ------------------------------------------------------------------
    if "musl" in clean_name or "alpine" in clean_name:
        abi = "musl"
    elif "msvc" in clean_name:
        abi = "msvc"
    else:
        abi = "gnu"  # covers explicit "gnu"/"glibc" and untagged linux/android

    # ------------------------------------------------------------------
    # 4. Target triple
    # ------------------------------------------------------------------
    if os_name == "linux":
        target_triple = f"{arch}-linux-{abi}"
    elif os_name == "darwin":
        target_triple = f"{arch}-apple-darwin"
    elif os_name == "windows":
        target_triple = f"{arch}-pc-windows-{abi if abi in ('msvc', 'gnu') else 'msvc'}"
    elif os_name == "android":
        target_triple = f"{arch}-android"
    else:
        target_triple = f"{arch}-{os_name}"

    return target_triple, is_archive
