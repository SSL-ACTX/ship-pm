"""Core runtime: profiles, settings, state, platform, and version helpers."""

from ship.core.platform import detect_target_keys
from ship.core.profile import (
    Profile,
    ProfilePaths,
    build_profile,
    get_active_profile,
    reset_active_profile,
    set_active_profile,
)
from ship.core.settings import get_pkgs_dir, settings
from ship.core.state import init_dirs, load_state, save_state

__all__ = [
    "Profile",
    "ProfilePaths",
    "build_profile",
    "detect_target_keys",
    "get_active_profile",
    "get_pkgs_dir",
    "init_dirs",
    "load_state",
    "reset_active_profile",
    "save_state",
    "set_active_profile",
    "settings",
]
