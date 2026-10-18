"""Version parsing, classification, and channel sorting."""

import re


def classify_channel(version_str: str) -> str:
    """
    Classify a version string into 'nightly', 'prerelease', or 'stable'.
    """
    v = version_str.lower().strip()
    if "nightly" in v or "master" in v or "main" in v or "latest-build" in v:
        return "nightly"
    if any(pre in v for pre in ("-alpha", "-beta", "-rc", "-dev", "-preview", "-pre", "alpha.", "beta.", "rc.")):
        return "prerelease"
    return "stable"


def semver_sort_key(version_str: str) -> tuple:
    """
    Deterministic sort key prioritizing stable semver, with pre-releases ranked lower.
    """
    channel = classify_channel(version_str)
    channel_weight = 2 if channel == "stable" else (1 if channel == "prerelease" else 0)

    # Extract numeric components
    cleaned = re.sub(r"^[vV]", "", version_str)
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[.-](.*))?$", cleaned)
    if match:
        major = int(match.group(1))
        minor = int(match.group(2) or 0)
        patch = int(match.group(3) or 0)
        extra = match.group(4) or ""
        return (channel_weight, major, minor, patch, extra)

    return (channel_weight, 0, 0, 0, version_str)


def select_default_version(versions: dict | list) -> str | None:
    """
    Resolves the default version according to professional channel precedence:
    1. Highest Stable release.
    2. Highest Pre-release (if no stable exists).
    3. Nightly (only if no stable or pre-release exists).
    """
    if not versions:
        return None

    v_list = list(versions.keys()) if isinstance(versions, dict) else list(versions)
    if not v_list:
        return None

    stables = [v for v in v_list if classify_channel(v) == "stable"]
    if stables:
        return sorted(stables, key=semver_sort_key)[-1]

    prereleases = [v for v in v_list if classify_channel(v) == "prerelease"]
    if prereleases:
        return sorted(prereleases, key=semver_sort_key)[-1]

    return sorted(v_list, key=semver_sort_key)[-1]
