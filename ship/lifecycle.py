"""Generic package lifecycle operations driven by registry metadata."""

import os
import subprocess
from pathlib import Path

from ship.config import HOME, IS_TERMUX, PREFIX
from ship.ui import die, status


def run_post_install_hook(target_data: dict, install_dir: Path) -> None:
    """Run the legacy declarative post-install command, when present."""
    post_hook = target_data.get("hooks", {}).get("post_install")
    if not post_hook:
        return

    status("Hook", "Executing post_install hook...")
    env = os.environ.copy()
    env["INSTALL_DIR"] = str(install_dir)
    env["HOME"] = str(HOME)

    if IS_TERMUX:
        glibc_pfx = Path(os.environ.get("GLIBC_PREFIX", f"{PREFIX}/glibc"))
        env["PREFIX"] = str(PREFIX)
        env["GLIBC_PREFIX"] = str(glibc_pfx)
        for cert in (
            glibc_pfx / "etc/ssl/certs/ca-certificates.crt",
            PREFIX / "etc/tls/cert.pem",
            PREFIX / "etc/ssl/certs/ca-certificates.crt",
        ):
            if cert.is_file():
                env["SSL_CERT_FILE"] = str(cert)
                break

    try:
        subprocess.run(post_hook, shell=True, cwd=install_dir, env=env, check=True)
    except subprocess.SubprocessError as exc:
        die(f"post_install hook failed: {exc}")
