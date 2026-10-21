"""Full Sandbox Area Engine for safe package testing and isolated toolchain execution."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ship.core.settings import settings
from ship.ui import die, status, ui


class SandboxArea:
    """Manages isolated Ship environments for testing, dry-runs, and safe execution."""

    @classmethod
    def sandboxes_root(cls) -> Path:
        root = settings.ship_root / "sandboxes"
        root.mkdir(parents=True, exist_ok=True)
        return root

    @classmethod
    def get_sandbox_path(cls, name: str) -> Path:
        return cls.sandboxes_root() / name

    @classmethod
    def create(cls, name: str | None = None) -> Path:
        """Create a dedicated sandbox area."""
        if name:
            box_dir = cls.get_sandbox_path(name)
            if box_dir.exists():
                ui.warn(f"Sandbox '{name}' already exists at {box_dir}.")
                return box_dir
            box_dir.mkdir(parents=True, exist_ok=True)
        else:
            box_dir = Path(tempfile.mkdtemp(prefix="box-", dir=cls.sandboxes_root()))

        (box_dir / "bin").mkdir(exist_ok=True)
        (box_dir / "store").mkdir(exist_ok=True)
        (box_dir / "cache").mkdir(exist_ok=True)
        (box_dir / "backups").mkdir(exist_ok=True)

        # Share host registry and core library with sandbox
        reg_dir = settings.ship_root / "registry"
        if reg_dir.exists() and not (box_dir / "registry").exists():
            (box_dir / "registry").symlink_to(reg_dir)
        lib_dir = settings.ship_root / "lib"
        if lib_dir.exists() and not (box_dir / "lib").exists():
            (box_dir / "lib").symlink_to(lib_dir)

        state_file = box_dir / "state.json"
        state_file.write_text(
            json.dumps({"installed": {}, "history": {}}, indent=2), encoding="utf-8"
        )
        status("Created", f"sandbox area at {box_dir.name}")
        return box_dir

    @classmethod
    def list_sandboxes(cls) -> list[dict]:
        """List all registered sandbox areas."""
        root = cls.sandboxes_root()
        results = []
        if not root.is_dir():
            return results

        for item in sorted(root.iterdir()):
            if not item.is_dir():
                continue
            state_file = item / "state.json"
            installed_pkgs = []
            if state_file.is_file():
                try:
                    data = json.loads(state_file.read_text(encoding="utf-8"))
                    installed_pkgs = list(data.get("installed", {}).keys())
                except (OSError, json.JSONDecodeError):
                    installed_pkgs = []

            size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
            results.append(
                {
                    "name": item.name,
                    "path": str(item),
                    "packages": installed_pkgs,
                    "size_bytes": size,
                }
            )
        return results

    @classmethod
    def clean(cls, name: str | None = None) -> int:
        """Destroy one or all sandbox areas."""
        root = cls.sandboxes_root()
        if name:
            target = cls.get_sandbox_path(name)
            if not target.is_dir():
                die(f"Sandbox '{name}' does not exist.")
            shutil.rmtree(target, ignore_errors=True)
            status("Cleaned", f"sandbox area '{name}'")
            return 1

        count = 0
        for item in root.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
                count += 1
        status("Finished", f"purged {count} sandbox area(s)")
        return count

    @classmethod
    def build_env(cls, box_dir: Path) -> dict[str, str]:
        """Construct isolated environment variables for the sandbox."""
        env = dict(os.environ)
        bin_dir = box_dir / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        env["SHIP_ROOT"] = str(box_dir)
        env["SHIP_BIN_DIR"] = str(bin_dir)
        lib_dir = settings.ship_root / "lib"
        env["PYTHONPATH"] = f"{lib_dir}:{env.get('PYTHONPATH', '')}".rstrip(":")
        env["SHIP_PROFILE"] = os.environ.get(
            "SHIP_PROFILE", "termux" if settings.is_termux else "linux"
        )
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["PS1"] = f"(ship-box:{box_dir.name}) \\w $ "
        return env

    @classmethod
    def enter(cls, name: str = "default") -> None:
        """Spawn an interactive subshell inside an isolated sandbox."""
        box_dir = cls.get_sandbox_path(name)
        if not box_dir.exists():
            box_dir = cls.create(name)

        env = cls.build_env(box_dir)
        ui.heading(f"Entering Sandbox Area: {box_dir.name}")
        ui.info(f"Isolated Root: {box_dir}")
        ui.info("Type 'exit' to leave the sandbox.")
        ui.blank()

        shell = os.environ.get("SHELL", "/bin/sh")
        subprocess.run([shell], check=False, env=env)
        status("Exited", f"left sandbox area '{box_dir.name}'")

    @classmethod
    def run_command(cls, name: str, cmd: list[str]) -> int:
        """Run a command inside the designated sandbox."""
        box_dir = cls.get_sandbox_path(name)
        if not box_dir.exists():
            box_dir = cls.create(name)

        env = cls.build_env(box_dir)
        proc = subprocess.run(cmd, check=False, env=env)
        return proc.returncode

    @classmethod
    def test_install(cls, pkg_spec: str, *, keep: bool = False) -> bool:
        """Perform a complete test installation in a clean, ephemeral sandbox."""
        box_dir = cls.create()
        box_name = box_dir.name
        ui.heading(f"Running Sandbox Test for: {pkg_spec}")
        ui.info(f"Sandbox Directory: {box_dir}")
        ui.blank()

        ship_bin = shutil.which("ship") or str(settings.ship_bin_dir / "ship")
        env = cls.build_env(box_dir)

        # 1. Install package in sandbox
        ui.status("Testing", f"installing {pkg_spec} inside sandbox...")
        install_res = subprocess.run(
            [ship_bin, "install", pkg_spec], check=False, env=env
        )
        if install_res.returncode != 0:
            ui.warn(f"Sandbox installation failed for '{pkg_spec}'.")
            if not keep:
                shutil.rmtree(box_dir, ignore_errors=True)
                status("Cleaned", f"destroyed temporary sandbox {box_name}")
            return False

        # 2. Run diagnostics inside sandbox
        ui.status("Diagnosing", f"verifying {pkg_spec} health inside sandbox...")
        doc_res = subprocess.run([ship_bin, "doctor"], check=False, env=env)
        success = doc_res.returncode == 0

        # 3. Report test status and cleanup
        ui.blank()
        if success:
            ui.status(
                "Verified", f"{pkg_spec} passed sandbox installation and runtime checks"
            )
        else:
            ui.warn(
                f"{pkg_spec} installed with runtime warnings or missing dependencies."
            )

        if not keep:
            shutil.rmtree(box_dir, ignore_errors=True)
            status(
                "Cleaned",
                f"ephemeral sandbox {box_name} destroyed (host left untouched)",
            )
        else:
            ui.info(f"Sandbox preserved at {box_dir}")

        return success
