"""Robust GitHub API client with token auto-detection, header rotation, and HTML/Atom fallbacks."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from ship import __version__
from ship.ui import die

# ---------------------------------------------------------------------------
# Disk-based TTL cache for GitHub API responses
# ---------------------------------------------------------------------------

#: Default TTL in seconds (1 hour).  Override with SHIP_CACHE_TTL env var.
_DEFAULT_TTL = int(os.environ.get("SHIP_CACHE_TTL", "3600"))

#: Set SHIP_NO_CACHE=1 to bypass the cache entirely (force live fetch).
_NO_CACHE = bool(os.environ.get("SHIP_NO_CACHE", ""))


def _cache_dir() -> Path:
    """Return (and create) the API response cache directory."""
    from ship.core.settings import settings  # local import to avoid circular

    d = settings.ship_cache_dir / "api_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_key(url: str) -> Path:
    h = hashlib.sha1(url.encode()).hexdigest()
    return _cache_dir() / f"{h}.json"


def _cache_load(url: str) -> dict | list | None:
    """Return cached data if present and not expired, else None."""
    if _NO_CACHE:
        return None
    path = _cache_key(url)
    if not path.exists():
        return None
    try:
        with path.open() as f:
            entry = json.load(f)
        if time.time() < entry.get("expires", 0):
            return entry["data"]
        # Expired — remove stale file
        path.unlink(missing_ok=True)
    except (json.JSONDecodeError, OSError):
        path.unlink(missing_ok=True)
    return None


def _cache_store(url: str, data: dict | list, ttl: int = _DEFAULT_TTL) -> None:
    """Atomically write data to the cache with an expiry timestamp."""
    if _NO_CACHE or ttl <= 0:
        return
    path = _cache_key(url)
    entry = {"expires": time.time() + ttl, "url": url, "data": data}
    try:
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(entry, f, separators=(",", ":"))
        os.replace(tmp, path)
    except (OSError, TypeError, ValueError):
        try:
            os.unlink(tmp)
        except OSError:
            pass


def cache_clear(pattern: str = "*") -> int:
    """Remove matching cache entries.  Returns count removed."""
    removed = 0
    try:
        for p in _cache_dir().glob(f"{pattern}.json"):
            p.unlink(missing_ok=True)
            removed += 1
    except OSError:
        pass
    return removed


def cache_stats() -> dict:
    """Return basic cache statistics."""
    now = time.time()
    total = valid = expired = 0
    try:
        for p in _cache_dir().glob("*.json"):
            total += 1
            try:
                entry = json.loads(p.read_text())
                if now < entry.get("expires", 0):
                    valid += 1
                else:
                    expired += 1
            except (json.JSONDecodeError, OSError):
                expired += 1
    except OSError:
        pass
    return {"total": total, "valid": valid, "expired": expired}


_USER_AGENTS = [
    f"ship/{__version__}",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "curl/8.7.1",
]


def _get_github_tokens() -> list[str]:
    """Collect available GitHub tokens from environment, git credentials, and gh CLI."""
    tokens: list[str] = []

    for env_var in ("GH_TOKEN", "GITHUB_TOKEN", "SHIP_GITHUB_TOKEN"):
        val = os.environ.get(env_var)
        if val and val.strip() and val.strip() not in tokens:
            tokens.append(val.strip())

    # Try gh auth token if installed and no env tokens were found
    if not tokens:
        gh_bin = shutil.which("gh")
        if gh_bin:
            try:
                proc = subprocess.run(
                    [gh_bin, "auth", "token"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
                t = proc.stdout.strip()
                if t and t not in tokens:
                    tokens.append(t)
            except (OSError, subprocess.SubprocessError):
                pass

    return tokens


def parse_repo_slug(raw_input: str) -> tuple[str, str]:
    slug = re.sub(r"^https?://github\.com/", "", raw_input).strip()
    slug = slug.rstrip("/")
    slug = slug.removesuffix(".git")
    slug = slug.rstrip("/")
    if "/" not in slug:
        die(f"Invalid repository format: '{raw_input}'. Expected 'owner/repo'.")
    parts = slug.split("/", 1)
    return parts[0], parts[1]


def fetch_github_json(url: str, *, ttl: int | None = None) -> dict | list | None:
    """Fetch JSON from GitHub API with caching, header rotation, and fallbacks.

    Args:
        url: Full GitHub API URL.
        ttl: Cache TTL in seconds (default: SHIP_CACHE_TTL env or 3600).
             Pass 0 to skip caching for this call.
    """
    effective_ttl = _DEFAULT_TTL if ttl is None else ttl

    # Check cache
    cached = _cache_load(url)
    if cached is not None:
        return cached

    # Live fetch
    result = _fetch_github_json_live(url)

    # Store in cache (only on success, never cache None/errors)
    if result is not None and effective_ttl > 0:
        _cache_store(url, result, ttl=effective_ttl)

    return result


def _fetch_github_json_live(url: str) -> dict | list | None:
    """Network-only fetch: token rotation → curl fallback → Atom/HTML fallbacks."""
    tokens = _get_github_tokens()
    token_candidates: list[str | None] = list(tokens) + [None] if tokens else [None]

    # Try token / agent rotation
    for token in token_candidates:
        for ua in _USER_AGENTS[:2]:
            headers = {
                "Accept": "application/vnd.github+json",
                "User-Agent": ua,
            }
            if token:
                headers["Authorization"] = f"Bearer {token}"

            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as he:
                if he.code in (403, 429):
                    # Rate limit hit, try next token or fallback
                    continue
                if he.code == 404:
                    return None
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
                continue

    # Try curl subprocess fallback with alternative user agents if urllib failed
    curl_bin = shutil.which("curl")
    if curl_bin:
        for token in token_candidates:
            for ua in _USER_AGENTS:
                cmd = [
                    curl_bin,
                    "-sL",
                    "-A",
                    ua,
                    "-H",
                    "Accept: application/vnd.github+json",
                ]
                if token:
                    cmd.extend(["-H", f"Authorization: Bearer {token}"])
                cmd.append(url)
                try:
                    proc = subprocess.run(
                        cmd,
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if proc.returncode == 0 and proc.stdout.strip().startswith(
                        ("{", "[")
                    ):
                        parsed = json.loads(proc.stdout)
                        if (
                            isinstance(parsed, dict)
                            and "message" in parsed
                            and "API rate limit" in parsed["message"]
                        ):
                            continue
                        return parsed
                except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
                    continue

    # Secondary fallback for releases listing: parse GitHub releases atom feed
    if "/releases" in url and not url.endswith((".tar.gz", ".zip", ".json")):
        slug_match = re.search(r"repos/([^/]+/[^/]+)/releases", url)
        if slug_match:
            slug = slug_match.group(1)
            atom_result = _fallback_fetch_releases_atom(slug)
            if atom_result:
                return atom_result

    return None


def _fallback_fetch_releases_atom(repo_slug: str) -> list[dict] | None:
    """Fallback parser using GitHub's Atom feed when API rate limit (60 req/hr) is exhausted."""
    atom_url = f"https://github.com/{repo_slug}/releases.atom"
    try:
        req = urllib.request.Request(atom_url, headers={"User-Agent": _USER_AGENTS[1]})
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml_text = resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError):
        curl = shutil.which("curl")
        if not curl:
            return None
        try:
            p = subprocess.run(
                [curl, "-sL", "-A", _USER_AGENTS[1], atom_url],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if p.returncode != 0:
                return None
            xml_text = p.stdout
        except (subprocess.SubprocessError, OSError):
            return None

    # Parse tags from <entry><id>.../tag/TAG</id> or <title>TAG</title>
    entries: list[dict] = []
    # Match tags e.g. <link rel="alternate" type="text/html" href="https://github.com/owner/repo/releases/tag/v1.0.0"/>
    tag_matches = re.findall(rf"{re.escape(repo_slug)}/releases/tag/([^\"]+)", xml_text)
    seen = set()
    for raw_tag in tag_matches:
        tag = raw_tag.split("?")[0].strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        entries.append(
            {
                "tag_name": tag,
                "name": tag,
                "prerelease": "nightly" in tag.lower()
                or "alpha" in tag.lower()
                or "beta" in tag.lower()
                or "rc" in tag.lower(),
                "assets": _fetch_expanded_assets_html(repo_slug, tag),
            }
        )
    return entries if entries else None


def _fetch_expanded_assets_html(repo_slug: str, tag: str) -> list[dict]:
    """Scrape release assets from HTML when API is rate-limited."""
    url = f"https://github.com/{repo_slug}/releases/expanded_assets/{tag}"
    html = ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENTS[1]})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError):
        curl = shutil.which("curl")
        if curl:
            try:
                p = subprocess.run(
                    [curl, "-sL", "-A", _USER_AGENTS[1], url],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if p.returncode == 0:
                    html = p.stdout
            except (subprocess.SubprocessError, OSError):
                pass

    assets: list[dict] = []
    # Extract /releases/download/tag/filename
    matches = re.findall(
        rf"href=\"(/[^\"]+/releases/download/{re.escape(tag)}/[^\"]+)\"", html
    )
    seen = set()
    for rel_path in matches:
        full_url = f"https://github.com{rel_path}"
        filename = rel_path.split("/")[-1]
        if filename in seen:
            continue
        seen.add(filename)
        assets.append(
            {
                "name": filename,
                "browser_download_url": full_url,
            }
        )
    return assets
