# .github/scripts/build_ubuntu_registry.py
"""Build ubuntu-noble.json and compress to ubuntu-noble.json.gz for release asset distribution."""

from __future__ import annotations

import gzip
import json
import lzma
import sys
import urllib.error
import urllib.request
from pathlib import Path

UBUNTU_SOURCES = [
    "http://ports.ubuntu.com/ubuntu-ports/dists/noble/main/binary-arm64/Packages.xz",
    "http://ports.ubuntu.com/ubuntu-ports/dists/noble/universe/binary-arm64/Packages.xz",
]


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


def _fetch_source(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ship-pm/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    dec = lzma.LZMADecompressor()
    return dec.decompress(raw)


def main() -> None:
    reg_dir = Path("registries")
    reg_dir.mkdir(parents=True, exist_ok=True)
    out_gz = reg_dir / "ubuntu-noble.json.gz"

    combined: dict[str, dict] = {}
    for url in UBUNTU_SOURCES:
        component = url.split("/dists/noble/")[1].split("/")[0]
        print(f"Fetching ubuntu-noble {component} index...", file=sys.stderr)
        try:
            data = _fetch_source(url)
            pkgs = _parse_packages(data)
            combined.update(pkgs)
            print(f"Parsed {len(pkgs):,} packages from {component}", file=sys.stderr)
        except (urllib.error.URLError, TimeoutError, OSError, lzma.LZMAError) as e:
            print(f"Error fetching {component}: {e}", file=sys.stderr)
            sys.exit(1)

    if not combined:
        print("No packages parsed from Ubuntu sources.", file=sys.stderr)
        sys.exit(1)

    raw_json = json.dumps(combined, separators=(",", ":")).encode("utf-8")
    with gzip.open(out_gz, "wb", compresslevel=9) as f:
        f.write(raw_json)

    size_mb = len(raw_json) / (1024 * 1024)
    gz_mb = out_gz.stat().st_size / (1024 * 1024)
    print(
        f"Generated {out_gz} with {len(combined):,} packages: {size_mb:.2f} MB raw -> {gz_mb:.2f} MB gzip"
    )


if __name__ == "__main__":
    main()
