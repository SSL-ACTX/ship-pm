"""Environment, directory layout, and persistent state management."""

import json
import os
from pathlib import Path

HOME = Path.home()
IS_TERMUX = "TERMUX_VERSION" in os.environ or os.path.exists("/data/data/com.termux")
PREFIX = Path(
    os.environ.get(
        "PREFIX", "/data/data/com.termux/files/usr" if IS_TERMUX else "/usr/local"
    )
)

if "SHIP_ROOT" in os.environ:
    SHIP_ROOT = Path(os.environ["SHIP_ROOT"])
elif IS_TERMUX:
    SHIP_ROOT = PREFIX / "share" / "ship"
else:
    SHIP_ROOT = HOME / ".local" / "share" / "ship"

if "SHIP_BIN_DIR" in os.environ:
    SHIP_BIN_DIR = Path(os.environ["SHIP_BIN_DIR"])
elif IS_TERMUX:
    termux_bin = PREFIX / "bin"
    if termux_bin.is_dir() and os.access(termux_bin, os.W_OK):
        SHIP_BIN_DIR = termux_bin
    else:
        SHIP_BIN_DIR = HOME / ".local" / "bin"
else:
    if (HOME / ".local" / "bin").is_dir() and os.access(
        HOME / ".local" / "bin", os.W_OK
    ):
        SHIP_BIN_DIR = HOME / ".local" / "bin"
    elif Path("/usr/local/bin").is_dir() and os.access("/usr/local/bin", os.W_OK):
        SHIP_BIN_DIR = Path("/usr/local/bin")
    else:
        SHIP_BIN_DIR = HOME / ".local" / "bin"

SHIP_CACHE_DIR = SHIP_ROOT / "cache"
SHIP_STORE_DIR = SHIP_ROOT / "store"
SHIP_INTERNAL_BIN = SHIP_ROOT / "bin"
SHIP_BACKUP_DIR = SHIP_ROOT / "backups"
SHIP_STATE_FILE = SHIP_ROOT / "state.json"
SHIP_REGISTRY_DIR = SHIP_ROOT / "registry"

SHIP_REGISTRY_GIT = os.environ.get(
    "SHIP_REGISTRY_GIT", "https://github.com/SSL-ACTX/ship-pm.git"
)
_registry_git = SHIP_REGISTRY_GIT.strip()
if _registry_git.startswith("git@github.com:"):
    _registry_repo_default = _registry_git.removeprefix("git@github.com:")
else:
    _registry_repo_default = _registry_git.removeprefix("https://github.com/")
_registry_repo_default = _registry_repo_default.removesuffix(".git").strip("/")
SHIP_REGISTRY_REPO = os.environ.get(
    "SHIP_REGISTRY_REPO", _registry_repo_default or "SSL-ACTX/ship-pm"
)
SHIP_UPDATE_URL = os.environ.get(
    "SHIP_UPDATE_URL",
    "https://github.com/SSL-ACTX/ship-pm/raw/refs/heads/main/bin/ship",
)
SHIP_BRIDGE_URL = os.environ.get(
    "SHIP_REGISTRY_BRIDGE",
    "https://corrupted-lily-1011.callixjeira.workers.dev/",
)


def init_dirs() -> None:
    for p in (
        SHIP_ROOT,
        SHIP_CACHE_DIR,
        SHIP_STORE_DIR,
        SHIP_INTERNAL_BIN,
        SHIP_BIN_DIR,
        SHIP_BACKUP_DIR,
        SHIP_REGISTRY_DIR,
    ):
        p.mkdir(parents=True, exist_ok=True)
    if not SHIP_STATE_FILE.exists():
        SHIP_STATE_FILE.write_text('{"installed":{},"backups":{}}\n')


def load_state() -> dict:
    init_dirs()
    try:
        return json.loads(SHIP_STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {"installed": {}, "backups": {}}


def save_state(state: dict) -> None:
    SHIP_STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def get_pkgs_dir() -> Path:
    if Path("./pkgs").is_dir():
        return Path("./pkgs").resolve()
    script_dir = Path(__file__).resolve().parent
    if (script_dir.parent / "pkgs").is_dir():
        return (script_dir.parent / "pkgs").resolve()
    return SHIP_REGISTRY_DIR / "pkgs"
