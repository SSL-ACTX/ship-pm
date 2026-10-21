"""Ship — agnostic shell package orchestrator for pre-built binaries.

Public surface for package authors::

    from ship.api import PackagePatch, ExportPolicy, InstallPatch, ...

Package layout::

    ship.api        public patch authoring API
    ship.core       profiles, settings, state, platform, version
    ship.net        downloads and provider clients
    ship.registry   registry sync and manifests
    ship.install    install sources, shared pipeline, lifecycle
    ship.link       discovery and linking
    ship.runtime    platform adapters (QEMU, Termux, …)
    ship.packages   per-package PATCH recipes
    ship.cli        command-line interface
    ship.admin      registry administration
"""

__version__ = "0.0.4"

__all__ = ["__version__"]
