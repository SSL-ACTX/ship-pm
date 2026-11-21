"""Declarative manifest indexing and distribution source authoring API.

Defines `ManifestRecipe`, `HttpIndex`, `HtmlDistIndex`, and target mappings for
packages that distribute prebuilt binaries from arbitrary web/HTTP servers, JSON
catalogs, or custom release portals rather than direct GitHub releases.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable


@dataclasses.dataclass(frozen=True)
class TargetAsset:
    url: str
    sha256: str
    binaries: dict[str, str]
    download_size_bytes: int | None = None

    def to_dict(self) -> dict:
        data: dict = {
            "url": self.url,
            "sha256": self.sha256,
            "binaries": self.binaries,
        }
        if self.download_size_bytes is not None:
            data["download_size_bytes"] = self.download_size_bytes
        return data


class HttpIndex:
    """Helper to query HTTP endpoints and extract version strings."""

    def __init__(self, url: str, headers: dict[str, str] | None = None):
        self.url = url
        self.headers = {"User-Agent": "ship-pm-indexer"}
        if headers:
            self.headers.update(headers)

    def fetch_text(self) -> str:
        req = urllib.request.Request(self.url, headers=self.headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def fetch_json(self) -> dict | list:
        req = urllib.request.Request(self.url, headers=self.headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def extract_regex(self, pattern: str) -> list[str]:
        text = self.fetch_text()
        matches = re.findall(pattern, text)
        # Deduplicate preserving order
        seen = set()
        res = []
        for m in matches:
            val = m if isinstance(m, str) else m[0]
            if val not in seen:
                seen.add(val)
                res.append(val)
        return res


@dataclasses.dataclass(frozen=True)
class _AssetEntry:
    filename: str
    url: str
    sha256: str
    size_bytes: int | None


class HtmlDistIndex(HttpIndex):
    """Scrapes an HTML distribution index page that lists assets with inline SHA256.

    Handles pages like ``https://www.cl.cam.ac.uk/research/hvg/Isabelle/dist/index.html``
    where each entry has the form::

        SHA256: <hex>  <a href=Filename.tar.gz>Filename.tar.gz</a>  (size / N bytes)

    Usage::

        idx = HtmlDistIndex(
            "https://www.cl.cam.ac.uk/research/hvg/Isabelle/dist/index.html",
            base_url="https://www.cl.cam.ac.uk/research/hvg/Isabelle/dist/",
            filename_pattern=r"Isabelle(\\d{4}(?:_RC\\d+)?)(?:_(linux|linux_arm|macos|macos_arm))?\\.tar\\.gz",
        )
        assets = idx.list_assets()          # list of _AssetEntry
        versions = idx.list_versions()      # deduplicated version strings
        targets = idx.resolve_targets(      # {triple: TargetAsset}
            version="2026",
            pkg_name="isabelle",
            triple_map={
                "linux":      ["x86_64-linux-gnu"],
                "linux_arm":  ["aarch64-linux-gnu"],
                "macos":      ["x86_64-apple-darwin"],
                "macos_arm":  ["aarch64-apple-darwin"],
            },
        )
    """

    def __init__(
        self,
        url: str,
        base_url: str | None = None,
        filename_pattern: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(url, headers)
        # base_url is prepended to relative hrefs; defaults to the directory of url
        if base_url is not None:
            self.base_url = base_url.rstrip("/") + "/"
        else:
            self.base_url = url.rsplit("/", 1)[0].rstrip("/") + "/"
        self.filename_pattern = filename_pattern

    def list_assets(self) -> list[_AssetEntry]:
        """Return all assets found on the page as ``_AssetEntry`` objects.

        Parses entries of the form::

            SHA256: <hex>  <a href=FILENAME>…</a>  (… / N bytes)

        Both quoted and unquoted ``href`` values are accepted.
        """
        text = self.fetch_text()
        # Match: SHA256 hex, href filename, optional size in bytes
        pattern = re.compile(
            r"([0-9a-fA-F]{64})\s+"
            r"<a\s+href=[\"']?([^\"'>]+)[\"']?",
            re.IGNORECASE,
        )
        size_pattern = re.compile(r"\(\s*[\d.]+[KMGTP]?\s*/\s*([\d]+)\s*bytes\s*\)")

        entries: list[_AssetEntry] = []
        for m in pattern.finditer(text):
            sha256 = m.group(1).lower()
            href = m.group(2).strip()
            filename = href.split("/")[-1]

            if self.filename_pattern and not re.search(
                self.filename_pattern, filename, re.IGNORECASE
            ):
                continue

            url = href if href.startswith("http") else self.base_url + href

            # Try to find size immediately after this match
            tail = text[m.end() : m.end() + 200]
            sm = size_pattern.search(tail)
            size_bytes = int(sm.group(1)) if sm else None

            entries.append(
                _AssetEntry(
                    filename=filename, url=url, sha256=sha256, size_bytes=size_bytes
                )
            )
        return entries

    def list_versions(self) -> list[str]:
        """Return deduplicated version strings extracted from asset filenames.

        Requires ``filename_pattern`` to contain a capture group for the version.
        Falls back to returning all matched filenames if no group is present.
        """
        if not self.filename_pattern:
            return [e.filename for e in self.list_assets()]
        seen: set[str] = set()
        result: list[str] = []
        for entry in self.list_assets():
            m = re.search(self.filename_pattern, entry.filename, re.IGNORECASE)
            if m and m.lastindex and m.lastindex >= 1:
                ver = m.group(1)
                if ver not in seen:
                    seen.add(ver)
                    result.append(ver)
        return result

    def resolve_targets(
        self,
        version: str,
        pkg_name: str,
        triple_map: dict[str, list[str]],
        binaries: dict[str, str] | None = None,
    ) -> dict[str, TargetAsset]:
        """Map assets for *version* to target triples.

        Args:
            version:   Version string to filter assets for (must match group 1
                       of ``filename_pattern``).
            pkg_name:  Package name used as the binary key when ``binaries`` is
                       not provided.
            triple_map: Maps platform suffix strings (e.g. ``"linux_arm"``) to a
                        list of target triples (e.g. ``["aarch64-linux-gnu"]``).
                        A ``None`` key or ``""`` matches assets with no platform
                        suffix — i.e. the generic/universal tarball.
            binaries:  Optional explicit ``{name: path}`` mapping.  Defaults to
                       ``{pkg_name: "bin/<pkg_name>"}``.

        Returns:
            ``{triple: TargetAsset}`` ready to pass to ``ManifestRecipe.resolve_targets``.
        """
        if binaries is None:
            binaries = {pkg_name: f"bin/{pkg_name}"}

        assets = self.list_assets()
        result: dict[str, TargetAsset] = {}

        for platform_suffix, triples in triple_map.items():
            matched: _AssetEntry | None = None
            for entry in assets:
                m = re.search(
                    self.filename_pattern or "", entry.filename, re.IGNORECASE
                )
                if not m:
                    continue
                ver_in_file = m.group(1) if m.lastindex and m.lastindex >= 1 else ""
                if ver_in_file != version:
                    continue
                plat_in_file = m.group(2) if m.lastindex and m.lastindex >= 2 else ""
                if platform_suffix in ("", None):
                    if not plat_in_file:
                        matched = entry
                        break
                elif plat_in_file == platform_suffix:
                    matched = entry
                    break

            if matched:
                asset = TargetAsset(
                    url=matched.url,
                    sha256=matched.sha256,
                    binaries=binaries,
                    download_size_bytes=matched.size_bytes,
                )
                for triple in triples:
                    result[triple] = asset

        return result


class ManifestRecipe:
    """Builder for custom package manifest discovery and resolution."""

    def __init__(self, name: str):
        self.name = name
        self._description: str = ""
        self._author: str = ""
        self._homepage: str = ""
        self._repository: str = ""
        self._license: str = ""
        self._version_extractor: Callable[[], list[str]] | None = None
        self._target_resolver: Callable[[str], dict[str, TargetAsset | dict]] | None = (
            None
        )

    def description(self, desc: str) -> ManifestRecipe:
        self._description = desc
        return self

    def author(self, auth: str) -> ManifestRecipe:
        self._author = auth
        return self

    def homepage(self, hp: str) -> ManifestRecipe:
        self._homepage = hp
        return self

    def repository(self, repo: str) -> ManifestRecipe:
        self._repository = repo
        return self

    def license(self, lic: str) -> ManifestRecipe:
        self._license = lic
        return self

    def versions_from(
        self, extractor: HttpIndex | Callable[[], list[str]]
    ) -> ManifestRecipe:
        if isinstance(extractor, HttpIndex):
            self._version_extractor = lambda: extractor.extract_regex(
                r'href=["\']([0-9]+\.[0-9]+(?:\.[0-9]+)*)/?["\']'
            )
        else:
            self._version_extractor = extractor
        return self

    def versions_from_regex(self, url: str, pattern: str) -> ManifestRecipe:
        idx = HttpIndex(url)
        self._version_extractor = lambda: idx.extract_regex(pattern)
        return self

    def resolve_targets(
        self,
        resolver: Callable[[str], dict[str, TargetAsset | dict]],
    ) -> ManifestRecipe:
        self._target_resolver = resolver
        return self

    def discover_versions(self) -> list[str]:
        if not self._version_extractor:
            return []
        try:
            return self._version_extractor()
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return []

    def resolve_version_targets(self, version: str) -> dict[str, dict]:
        if not self._target_resolver:
            return {}
        try:
            raw = self._target_resolver(version)
            res = {}
            for k, v in raw.items():
                if isinstance(v, TargetAsset):
                    res[k] = v.to_dict()
                elif isinstance(v, dict):
                    res[k] = v
            return res
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError):
            return {}

    def build_version_manifest(self, version: str, channel: str = "stable") -> dict:
        targets = self.resolve_version_targets(version)
        return {
            "channel": channel,
            "targets": targets,
        }

    def generate_full_manifest(self, versions: list[str] | None = None) -> dict:
        if versions is None:
            versions = self.discover_versions()
        ver_dict = {}
        for v in versions:
            v_manifest = self.build_version_manifest(v)
            if v_manifest.get("targets"):
                ver_dict[v] = v_manifest

        data: dict = {
            "description": self._description,
            "author": self._author,
            "repository": self._repository,
            "versions": ver_dict,
        }
        if self._homepage:
            data["homepage"] = self._homepage
        if self._license:
            data["license"] = self._license
        return data


def compute_url_sha256(url: str) -> str:
    """Stream and compute SHA256 for a remote binary asset."""
    req = urllib.request.Request(url, headers={"User-Agent": "ship-pm-indexer"})
    hasher = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=60) as resp:
        while chunk := resp.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()
