"""Self-healing runtime diagnostic and repair engine (ship doctor)."""

from __future__ import annotations

import os
from pathlib import Path

from ship.api import inspect_elf
from ship.core.settings import settings
from ship.core.state import load_state
from ship.install.lifecycle import repatch_package
from ship.ui import ui


class DoctorEngine:
    """Diagnoses and heals broken toolchains, missing libraries, and dangling symlinks."""

    @classmethod
    def diagnose(cls, *, heal: bool = False) -> int:
        state = load_state()
        installed = state.get("installed", {})
        ui.heading("Running Ship Environment Diagnostics...")
        ui.blank()

        issues_found = 0
        healed_count = 0

        # 1. Verify bin symlinks
        bin_dir = settings.ship_bin_dir
        ui.status("Checking", f"public symlinks in {bin_dir}...")
        broken_symlinks = []
        if bin_dir.is_dir():
            for link in bin_dir.iterdir():
                if link.is_symlink() and not link.resolve().exists():
                    broken_symlinks.append(link)
                    issues_found += 1
                    ui.warn(
                        f"Broken symlink detected: {link.name} -> {os.readlink(link)}"
                    )

        # 2. Check installed package health
        for pkg_name, data in installed.items():
            version = data.get("version", "unknown")
            inst_dir = Path(data.get("install_dir", ""))

            if not inst_dir.is_dir():
                issues_found += 1
                ui.warn(
                    f"Package store directory missing for {pkg_name}@{version}: {inst_dir}"
                )
                continue

            pkg_issues: list[str] = []
            # Check ELF binaries and internal symlinks
            for root, _, files in os.walk(inst_dir):
                for f in files:
                    p = Path(root) / f
                    if p.is_symlink():
                        if not p.resolve().exists():
                            pkg_issues.append(
                                f"Dangling internal symlink: {p.relative_to(inst_dir)}"
                            )
                        continue

                    # Check ELF
                    elf_info = inspect_elf(p)
                    if elf_info and elf_info.interpreter:
                        # If binary is wrapped by a Ship runtime launcher (-real companion), the launcher handles execution
                        if (
                            p.name.endswith("-real")
                            and p.with_name(p.name[:-5]).is_file()
                        ):
                            continue
                        if not Path(elf_info.interpreter).exists():
                            pkg_issues.append(
                                f"Missing interpreter {elf_info.interpreter} for {p.name}"
                            )

            if pkg_issues:
                issues_found += len(pkg_issues)
                for issue in pkg_issues:
                    ui.warn(f"[{pkg_name}] {issue}")

                if heal:
                    ui.status("Healing", f"repatching and relinking {pkg_name}...")
                    try:
                        repatch_package(pkg_name)
                        healed_count += 1
                    except (OSError, RuntimeError) as e:
                        ui.warn(f"Failed to heal {pkg_name}: {e}")

        # Clean dangling symlinks if healing
        if heal and broken_symlinks:
            for b in broken_symlinks:
                b.unlink(missing_ok=True)
                ui.status("Removed", f"dangling symlink {b.name}")
            healed_count += len(broken_symlinks)

        ui.blank()
        if issues_found == 0:
            ui.status("Healthy", "all packages and runtime links are in optimal state")
            return 0

        if heal:
            ui.status(
                "Finished", f"diagnosed {issues_found} issue(s), healed {healed_count}"
            )
        else:
            ui.warn(
                f"Found {issues_found} issue(s). Run 'ship doctor --heal' to automatically repair."
            )
        return 1 if issues_found and not heal else 0
