"""Install subsystem: sources, shared pipeline, and package lifecycle."""

from ship.install.extract import extract_archive
from ship.install.github_source import install_from_github
from ship.install.history import record_package_history
from ship.install.lifecycle import (
    remove_package,
    repatch_package,
    rollback_binary,
    rollback_package,
)
from ship.install.registry_source import install_package

__all__ = [
    "extract_archive",
    "install_from_github",
    "install_package",
    "record_package_history",
    "remove_package",
    "repatch_package",
    "rollback_binary",
    "rollback_package",
]
