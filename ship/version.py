"""Version parsing, classification, and channel sorting."""

import re

# Nightly/rolling-release version prefixes (case-insensitive).
# Packages like Odin use "dev-YYYY-MM" for their monthly rolling releases.
_NIGHTLY_PREFIXES = ("nightly", "master", "main", "latest-build", "dev-")
_NIGHTLY_SUBSTRINGS = ("nightly", "master", "main", "latest-build")


def format_version(version: str | None) -> str:
    """Format a version for display without prefixing development labels."""
    value = str(version or "unknown").strip()
    if not value or value == "unknown":
        return "unknown"
    if value[0].lower() == "v":
        unprefixed = value[1:]
        return f"v{unprefixed}" if unprefixed[:1].isdigit() else unprefixed
    return f"v{value}" if value[0].isdigit() else value


def classify_channel(version_str: str, version_data: dict | None = None) -> str:
    """
    Classify a version string into 'nightly', 'prerelease', or 'stable'.

    If the manifest entry for this version includes a ``channel`` key that
    field takes precedence over heuristic detection, allowing package
    maintainers to explicitly label rolling/dev releases (e.g. Odin's
    ``dev-YYYY-MM`` scheme) without requiring the string to contain a
    nightly keyword.

    Args:
        version_str: The raw version string from the manifest.
        version_data: Optional dict of per-version manifest data (the value
            under ``versions[version_str]``).  When provided and it contains
            a ``"channel"`` key, that value is authoritative.
    """
    # Manifest-declared channel wins over heuristics — but only when it
    # *demotes* a version (e.g. declares nightly/prerelease for an otherwise
    # stable-looking string).  We never let a manifest promote an obviously
    # nightly/dev version to "stable", because that would hide rolling releases
    # from update logic and confuse channel-pinned installs.
    if version_data and isinstance(version_data, dict):
        declared = str(version_data.get("channel", "")).strip().lower()
        if declared in ("nightly", "prerelease"):
            return declared
        # "stable" from manifest is accepted only when the version string
        # doesn't look like a nightly/dev build.
        if declared == "stable":
            v_check = version_str.lower().strip()
            is_dev_like = v_check.startswith("dev-") or any(
                sub in v_check for sub in _NIGHTLY_SUBSTRINGS
            )
            if not is_dev_like:
                return "stable"
        # If declared is invalid or manifest tried to force stable on a dev
        # string, fall through to heuristics below.

    v = version_str.lower().strip()

    # Check common nightly substrings first.
    if any(sub in v for sub in _NIGHTLY_SUBSTRINGS):
        return "nightly"

    # Treat "dev-" prefix as nightly (e.g. Odin's "dev-2026-10" releases).
    if v.startswith("dev-"):
        return "nightly"

    if any(
        pre in v
        for pre in (
            "-alpha",
            "-beta",
            "-rc",
            "-dev",
            "-preview",
            "-pre",
            "alpha.",
            "beta.",
            "rc.",
        )
    ):
        return "prerelease"
    return "stable"


def semver_sort_key(version_str: str, version_data: dict | None = None) -> tuple:
    """
    Deterministic sort key for version strings.

    Stable releases sort highest, pre-releases next, nightly lowest.
    Within each channel, numeric components (major.minor.patch) are compared
    numerically.  Non-semver strings (e.g. "dev-2026-10") are sorted
    lexicographically as a fallback within their channel bucket so that
    chronological dev-release names still sort correctly.
    """
    channel = classify_channel(version_str, version_data)
    channel_weight = 2 if channel == "stable" else (1 if channel == "prerelease" else 0)

    # Strip leading "v" / "V".
    cleaned = re.sub(r"^[vV]", "", version_str)

    # Standard numeric semver: e.g. "1.2.3", "1.2.3-rc.1".
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[.-](.*))?$", cleaned)
    if match:
        major = int(match.group(1))
        minor = int(match.group(2) or 0)
        patch = int(match.group(3) or 0)
        extra = match.group(4) or ""
        return (channel_weight, major, minor, patch, extra)

    # Non-numeric version (e.g. "dev-2026-10"): sort lexicographically within
    # the channel bucket.  This keeps chronological dev-release names ordered
    # correctly as long as the naming scheme is consistent (YYYY-MM sorts fine
    # as a string).
    return (channel_weight, 0, 0, 0, cleaned)


def classify_channel_for_version(
    version_str: str, versions_dict: dict | None = None
) -> str:
    """
    Classify a version string, consulting the manifest versions dict when
    available so that per-version ``channel`` overrides are respected.

    Args:
        version_str: The version key.
        versions_dict: The full ``manifest["versions"]`` dict.  When given,
            the per-version data is extracted and passed to
            :func:`classify_channel`.
    """
    version_data = (versions_dict or {}).get(version_str)
    return classify_channel(version_str, version_data)


def select_latest_in_channel(
    versions: dict | list, channel: str
) -> str | None:
    """Return the highest version in *versions* that belongs to *channel*."""
    v_list = list(versions.keys()) if isinstance(versions, dict) else list(versions)
    versions_dict = versions if isinstance(versions, dict) else {}

    candidates = [
        v for v in v_list
        if classify_channel_for_version(v, versions_dict) == channel
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda v: semver_sort_key(v, versions_dict.get(v)),
    )


def select_default_version(versions: dict | list) -> str | None:
    """
    Resolve the default version according to channel precedence:

    1. Highest stable release.
    2. Highest pre-release (if no stable exists).
    3. Highest nightly (only if no stable or pre-release exists).
    """
    if not versions:
        return None

    v_list = list(versions.keys()) if isinstance(versions, dict) else list(versions)
    if not v_list:
        return None

    versions_dict = versions if isinstance(versions, dict) else {}

    for channel in ("stable", "prerelease", "nightly"):
        best = select_latest_in_channel(versions_dict or {v: {} for v in v_list}, channel)
        if best:
            return best

    return None
