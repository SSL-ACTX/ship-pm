"""Abstract base class for binary patchers and emulation runners."""

import shutil
import stat
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from ship.patches.api import PatchReport


@dataclass
class LauncherTemplate:
    """Inputs for the shared shell launcher used by platform patchers."""

    interpreter: str
    comment: str
    command: str
    environment: list[str] = field(default_factory=list)
    before: str = ""
    after: str = ""
    unset: list[str] = field(default_factory=lambda: ["LD_PRELOAD"])


def install_launcher(
    binary_path: Path,
    template: LauncherTemplate,
    *,
    report: PatchReport | None = None,
) -> Path:
    """Move an executable aside and render a consistent argument-preserving launcher."""
    real_binary = binary_path.with_name(f"{binary_path.name}-real")
    changed = False
    if not real_binary.exists():
        shutil.move(binary_path, real_binary)
        changed = True
    lines = [f"#!{template.interpreter}", f"# {template.comment}"]
    lines.extend(f"unset {name}" for name in template.unset)
    lines.extend(template.environment)
    if template.before:
        lines.append(template.before.rstrip())
    lines.extend([template.command, "EXIT_CODE=$?"])
    if template.after:
        lines.append(template.after.rstrip())
    lines.append("exit $EXIT_CODE")
    content = "\n".join(lines) + "\n"
    if not binary_path.is_file() or binary_path.read_bytes() != content.encode("utf-8"):
        binary_path.write_text(content, encoding="utf-8")
        changed = True
    for path in (binary_path, real_binary):
        if stat.S_IMODE(path.stat().st_mode) != 0o755:
            path.chmod(0o755)
            changed = True
    if changed and report is not None:
        report.add(binary_path, "install runtime launcher", template.comment)
    return binary_path


class BinaryPatcher(ABC):
    """Protocol for target environment binary patchers and runners."""

    name: str

    @abstractmethod
    def should_patch(self, binary_path: Path, target_key: str) -> bool:
        """Return True if this patcher applies to the given binary."""

    @abstractmethod
    def patch(
        self,
        binary_path: Path,
        target_key: str,
        report: PatchReport | None = None,
    ) -> Path:
        """
        Patch or wrap the binary.
        Returns the path to the executable that should be symlinked.
        """
