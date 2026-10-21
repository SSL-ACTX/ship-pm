"""Local and offline artifact distribution engine (ship export / import)."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

from ship.core.settings import settings
from ship.core.state import load_state, save_state
from ship.link.discovery import resolve_command_binaries
from ship.link.linker import link_package
from ship.ui import die, status


class ArtifactBundle:
    """Exports and imports pre-patched store directories for zero-overhead distribution."""

    MANIFEST_NAME = "ship-bundle.json"

    @classmethod
    def export(cls, pkg_name: str, output_path: Path | str | None = None) -> Path:
        state = load_state()
        installed = state.get("installed", {})
        if pkg_name not in installed:
            die(f"Package '{pkg_name}' is not installed.")

        data = installed[pkg_name]
        inst_dir = Path(data.get("install_dir", ""))
        version = data.get("version", "unknown")
        if not inst_dir.is_dir():
            die(f"Store directory for '{pkg_name}' does not exist: {inst_dir}")

        out = (
            Path(output_path)
            if output_path
            else Path.cwd() / f"{pkg_name}-{version}.ship.tar.gz"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        status("Exporting", f"{pkg_name}@{version} -> {out.name}...")

        bundle_meta = {
            "name": pkg_name,
            "version": version,
            "state": data,
        }

        with tarfile.open(out, "w:gz") as tf:
            # Store payload
            tf.add(inst_dir, arcname="payload")
            # Store bundle manifest
            meta_bytes = json.dumps(bundle_meta, indent=2).encode("utf-8")
            ti = tarfile.TarInfo(name=cls.MANIFEST_NAME)
            ti.size = len(meta_bytes)
            import io

            tf.addfile(ti, io.BytesIO(meta_bytes))

        status("Exported", f"bundle created ({out.stat().st_size} bytes)")
        return out

    @classmethod
    def import_bundle(cls, bundle_path: Path | str) -> str:
        bpath = Path(bundle_path)
        if not bpath.is_file():
            die(f"Bundle file not found: {bpath}")

        status("Importing", f"reading bundle {bpath.name}...")
        meta: dict = {}
        with tarfile.open(bpath, "r:*") as tf:
            try:
                mf = tf.extractfile(cls.MANIFEST_NAME)
                if mf:
                    meta = json.loads(mf.read().decode("utf-8"))
            except (OSError, KeyError, json.JSONDecodeError):
                die(f"Invalid or missing {cls.MANIFEST_NAME} in bundle.")

        pkg_name = meta.get("name")
        version = meta.get("version", "unknown")
        stored_state = meta.get("state", {})
        if not pkg_name:
            die("Bundle manifest missing package name.")

        dest_dir = settings.ship_store_dir / f"{pkg_name}@{version}"
        dest_dir.mkdir(parents=True, exist_ok=True)

        with tarfile.open(bpath, "r:*") as tf:
            for member in tf.getmembers():
                if member.name.startswith("payload/"):
                    member.name = member.name.removeprefix("payload/")
                    if member.name:
                        tf.extract(member, path=dest_dir)

        # Relink binaries
        status("Linking", f"relinking {pkg_name} binaries...")
        from ship.api import PatchReport

        report = PatchReport(pkg_name)
        target_key = stored_state.get("target_key", "")
        commands = resolve_command_binaries(dest_dir, pkg_name, target_key=target_key)
        linked = link_package(pkg_name, commands, target_key, report)

        state = load_state()
        stored_state["install_dir"] = str(dest_dir)
        stored_state["symlinks"] = linked
        state.setdefault("installed", {})[pkg_name] = stored_state
        save_state(state)

        status("Imported", f"{pkg_name}@{version} ({len(linked)} binaries linked)")
        return pkg_name
