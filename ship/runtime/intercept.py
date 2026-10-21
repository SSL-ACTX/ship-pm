"""Dynamic build interceptor dispatcher and toolchain wrappers (OPAM, Cargo, CMake)."""

from __future__ import annotations

import json
from pathlib import Path

from ship.core.settings import settings


class BuildInterceptor:
    """Configures and installs context-aware toolchain interceptors."""

    CONFIG_FILE = settings.ship_internal_bin / "interceptors.json"

    @classmethod
    def register_rule(
        cls,
        tool: str,
        env_trigger: str,
        packages: list[str],
        c_flags: list[str] | None = None,
        ld_flags: list[str] | None = None,
        polyfills: list[str] | None = None,
    ) -> None:
        """Register a build interception rule."""
        cls.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if cls.CONFIG_FILE.exists():
            try:
                data = json.loads(cls.CONFIG_FILE.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}

        rules = data.setdefault(tool, [])
        rules.append(
            {
                "env_trigger": env_trigger,
                "packages": packages,
                "c_flags": c_flags or [],
                "ld_flags": ld_flags or [],
                "polyfills": polyfills or [],
            }
        )
        cls.CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        cls.ensure_intercept_binary()

    @classmethod
    def ensure_intercept_binary(cls) -> Path:
        """Create or update the ship-intercept executable in internal bin."""
        target = settings.ship_internal_bin / "ship-intercept"
        script = (
            "#!/usr/bin/env python3\n"
            "import os, sys, json, subprocess\n"
            "from pathlib import Path\n"
            "\n"
            f"CONFIG_PATH = Path({str(cls.CONFIG_FILE)!r})\n"
            "rules_data = {}\n"
            "if CONFIG_PATH.exists():\n"
            "    try:\n"
            "        rules_data = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))\n"
            "    except Exception:\n"
            "        pass\n"
            "\n"
            "# Context-aware environment modification\n"
            "for tool, rules in rules_data.items():\n"
            "    for rule in rules:\n"
            "        trigger_var = rule.get('env_trigger', '')\n"
            "        pkg = os.environ.get(trigger_var, '')\n"
            "        if pkg and pkg in rule.get('packages', []):\n"
            "            c_flags = ' '.join(rule.get('c_flags', []))\n"
            "            if c_flags:\n"
            "                os.environ['CFLAGS'] = f\"{c_flags} {os.environ.get('CFLAGS', '')}\".strip()\n"
            "            ld_flags = ' '.join(rule.get('ld_flags', []))\n"
            "            if ld_flags:\n"
            "                os.environ['LDFLAGS'] = f\"{ld_flags} {os.environ.get('LDFLAGS', '')}\".strip()\n"
            "\n"
            "if len(sys.argv) > 1:\n"
            "    cmd = sys.argv[1:]\n"
            "    os.execvp(cmd[0], cmd)\n"
            "sys.exit(0)\n"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(script, encoding="utf-8")
        target.chmod(0o755)
        return target
