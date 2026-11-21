"""Canonical package name normalization and resolution utilities."""

from __future__ import annotations

import re


def normalize_package_name(pkg_name: str) -> str:
    """
    Return the bare canonical package name without namespace prefixes or version tags.

    Examples:
      'ubuntu:agda-bin' -> 'agda-bin'
      'u:frama-c-base'  -> 'frama-c-base'
      'adacore/why3'    -> 'why3'
      'agda@2.6.3'      -> 'agda'
    """
    raw = pkg_name.strip()
    if not raw:
        return ""
    # Strip version suffix (e.g. '@2.6.3')
    base = raw.split("@", 1)[0]
    # Strip pool / namespace prefix (e.g. 'ubuntu:', 'u:')
    if ":" in base:
        base = base.split(":", 1)[1]
    # Strip repository / author prefix (e.g. 'owner/repo')
    if "/" in base:
        base = base.split("/")[-1]
    return base.lower().strip()


def package_lookup_candidates(pkg_name: str) -> list[str]:
    """
    Generate ordered lookup variations for patch resolution, aliases, and dependencies.

    Examples for 'ubuntu:agda-bin':
      ['agda_bin', 'agda', 'agda_bin']
    """
    bare = normalize_package_name(pkg_name)
    if not bare:
        return []

    cands: list[str] = []
    # 1. Exact sanitized module name
    base_mod = bare.replace("-", "_")
    cands.append(base_mod)

    # 2. Stripped common packaging suffixes (-bin, -base, -cli, -core, -tools, -stdlib, -data, -doc)
    for suffix in (
        "_bin",
        "_base",
        "_cli",
        "_core",
        "_tools",
        "_tool",
        "_stdlib",
        "_data",
        "_doc",
        "_common",
    ):
        if base_mod.endswith(suffix):
            root = base_mod.removesuffix(suffix)
            if root and root not in cands:
                cands.append(root)

    # 3. Numeric alias variations (e.g. yices2 -> yices)
    stripped_num = re.sub(r"\d+$", "", base_mod)
    if stripped_num and stripped_num not in cands:
        cands.append(stripped_num)

    return cands


def parse_debian_depends(depends_str: str) -> list[str]:
    """
    Parse a Debian 'Depends' header into a list of normalized dependency package names.

    Handles version constraints (e.g. 'libc6 (>= 2.38)'), alternative choices ('a | b'),
    and filters out base system libraries bundled in host glibc or termux libc.
    """
    if not depends_str or not depends_str.strip():
        return []

    # Standard host libc/glibc packages to ignore because they are host-managed
    IGNORED_SYSTEM_PKGS = frozenset(
        {
            "libc6",
            "libc6.1",
            "libc0.1",
            "libc0.3",
            "dpkg",
            "debconf",
            "gcc-14-base",
            "gcc-13-base",
            "gcc-12-base",
        }
    )

    dependencies: list[str] = []
    # Debian dependencies are comma-separated clauses
    for clause in depends_str.split(","):
        clause = clause.strip()
        if not clause:
            continue
        # For alternatives (e.g. "default-jre | java8-runtime"), take the first preferred option
        first_alt = clause.split("|", 1)[0].strip()
        # Strip version constraints inside parentheses: "libffi8 (>= 3.4)" -> "libffi8"
        pkg = re.sub(r"\(.*?\)", "", first_alt).strip()
        pkg_norm = normalize_package_name(pkg)
        if pkg_norm and pkg_norm not in IGNORED_SYSTEM_PKGS:
            dependencies.append(pkg_norm)

    return dependencies
