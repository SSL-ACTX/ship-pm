"""Ubuntu Noble package registry — fetch, parse, and cache."""

from __future__ import annotations

import json
import lzma
import os
import time
import urllib.request
from pathlib import Path

from ship.core.settings import settings
from ship.ui import status, warn

UBUNTU_SOURCES = [
    "http://ports.ubuntu.com/ubuntu-ports/dists/noble/main/binary-arm64/Packages.xz",
    "http://ports.ubuntu.com/ubuntu-ports/dists/noble/universe/binary-arm64/Packages.xz",
]

TTL = int(os.environ.get("SHIP_UBUNTU_TTL", str(7 * 24 * 3600)))  # 7 days default


def _registry_path() -> Path:
    p = settings.ship_cache_dir / "registries" / "ubuntu-noble.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _meta_path() -> Path:
    return _registry_path().with_suffix(".meta.json")


def _is_fresh() -> bool:
    meta = _meta_path()
    reg = _registry_path()
    if not reg.is_file() or not meta.is_file():
        return False
    try:
        m = json.loads(meta.read_text())
        return time.time() < m.get("expires", 0)
    except (json.JSONDecodeError, OSError):
        return False


def _parse_packages(data: bytes) -> dict[str, dict]:
    pkgs: dict[str, dict] = {}
    current: dict[str, str] = {}
    for raw_line in data.decode("utf-8", errors="replace").splitlines():
        if raw_line == "":
            _commit(current, pkgs)
            current = {}
        elif ": " in raw_line and not raw_line.startswith(" "):
            k, _, v = raw_line.partition(": ")
            current[k] = v
    _commit(current, pkgs)
    return pkgs


def _commit(current: dict, pkgs: dict) -> None:
    name = current.get("Package", "").strip().lower()
    if not name:
        return
    ver = current.get("Version", "").strip()
    desc = current.get("Description", "").strip()
    url_path = current.get("Filename", "").strip()
    pkgs[name] = {
        "name": name,
        "version": ver,
        "description": desc,
        "_deb_url": f"http://ports.ubuntu.com/ubuntu-ports/{url_path}"
        if url_path
        else "",
        "_source": "ubuntu-noble",
    }


def _fetch_source(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ship-pm/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    dec = lzma.LZMADecompressor()
    return dec.decompress(raw)


def fetch_ubuntu_registry(force: bool = False) -> dict[str, dict]:
    """Download and rebuild the ubuntu-noble registry. Skips if still fresh."""
    reg_path = _registry_path()

    if not force and _is_fresh():
        return _load_cached()

    combined: dict[str, dict] = {}
    for url in UBUNTU_SOURCES:
        component = url.split("/dists/noble/")[1].split("/")[0]
        status("Fetching", f"ubuntu-noble {component} index...")
        try:
            data = _fetch_source(url)
            pkgs = _parse_packages(data)
            combined.update(pkgs)
            status("Parsed", f"{len(pkgs):,} packages from {component}")
        except (urllib.error.URLError, TimeoutError, OSError, lzma.LZMAError) as e:
            warn(f"Failed to fetch {component}: {e}")

    if not combined:
        warn("Ubuntu registry refresh failed — keeping existing data.")
        return _load_cached()

    tmp = reg_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(combined, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, reg_path)

    meta_tmp = _meta_path().with_suffix(".tmp")
    meta_tmp.write_text(
        json.dumps(
            {
                "expires": time.time() + TTL,
                "count": len(combined),
                "updated": time.time(),
            }
        ),
        encoding="utf-8",
    )
    os.replace(meta_tmp, _meta_path())

    status("Done", f"ubuntu-noble registry: {len(combined):,} packages cached")
    return combined


def _load_cached() -> dict[str, dict]:
    p = _registry_path()
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def load_ubuntu_registry() -> dict[str, dict]:
    """Load from cache; fetch if missing (not if just stale — use fetch_ubuntu_registry for refresh)."""
    reg_path = _registry_path()
    if not reg_path.is_file():
        return fetch_ubuntu_registry()
    return _load_cached()


def ubuntu_registry_meta() -> dict:
    try:
        return json.loads(_meta_path().read_text())
    except (json.JSONDecodeError, OSError):
        return {}
