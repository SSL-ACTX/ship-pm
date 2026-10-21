"""Semantic code and source tree transformation engine."""

from __future__ import annotations

import fnmatch
import os
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ship.api import PatchReport


class SourcePatcher:
    """AST/pattern-based code transformation engine for unpacked source and package trees."""

    def __init__(self, root_dir: Path | str, report: PatchReport | None = None) -> None:
        self.root_dir = Path(root_dir)
        self.report = report

    def file_exists(self, rel_path: str) -> bool:
        """Check if relative path exists inside the root tree."""
        return (self.root_dir / rel_path).exists()

    def find_files(self, file_glob: str) -> list[Path]:
        """Find matching files inside root_dir matching a glob pattern."""
        matches: list[Path] = []
        for root, _, files in os.walk(self.root_dir):
            rel_root = Path(root).relative_to(self.root_dir)
            for f in files:
                rel_file = rel_root / f if str(rel_root) != "." else Path(f)
                if fnmatch.fnmatch(str(rel_file), file_glob) or fnmatch.fnmatch(
                    f, file_glob
                ):
                    matches.append(Path(root) / f)
        return sorted(matches)

    def replace_regex(self, file_glob: str, pattern: str, replacement: str) -> int:
        """Safe multi-file regex replacement with atomic writes."""
        rx = re.compile(pattern)
        changed_count = 0
        for path in self.find_files(file_glob):
            try:
                content = path.read_text(encoding="utf-8", errors="surrogateescape")
            except OSError:
                continue
            new_content, n = rx.subn(replacement, content)
            if n > 0 and new_content != content:
                self._atomic_write(path, new_content)
                changed_count += n
                if self.report:
                    self.report.record(
                        path, "patch", f"replaced regex '{pattern}' ({n} times)"
                    )
        return changed_count

    def inject_c_guard(
        self,
        file_path: str | Path,
        after_include: str,
        guard_code: str,
    ) -> bool:
        """Idempotently injects C preprocessor directives after a specified include."""
        target = self.root_dir / file_path if isinstance(file_path, str) else file_path
        if not target.is_file():
            return False

        content = target.read_text(encoding="utf-8", errors="surrogateescape")
        if guard_code.strip() in content:
            return False  # Already injected

        pattern = rf"(#\s*include\s*[<\"{re.escape(after_include)}[>\"][^\n]*\n)"
        match = re.search(pattern, content)
        if not match:
            return False

        idx = match.end()
        new_content = (
            content[:idx]
            + f"\n/* Ship Bionic Compat Guard */\n{guard_code.strip()}\n\n"
            + content[idx:]
        )
        self._atomic_write(target, new_content)
        if self.report:
            self.report.record(
                target, "patch", f"injected C guard after {after_include}"
            )
        return True

    def patch_record_fields(
        self,
        file_glob: str,
        target_field: str,
        inject_field: str,
    ) -> int:
        """Injects missing language-specific record fields idempotently."""
        pattern = rf"(\b{re.escape(target_field)}\s*=[^;]+;)"
        matches = 0
        for path in self.find_files(file_glob):
            try:
                content = path.read_text(encoding="utf-8", errors="surrogateescape")
            except OSError:
                continue
            if inject_field.strip() in content:
                continue
            new_content, n = re.subn(
                pattern, rf"\1\n    {inject_field.strip()}", content
            )
            if n > 0 and new_content != content:
                self._atomic_write(path, new_content)
                matches += n
                if self.report:
                    self.report.record(
                        path, "patch", f"injected record field '{inject_field.strip()}'"
                    )
        return matches

    def clean_posix_redirections(self, file_glob: str = "**/*.sh") -> int:
        """Transforms non-POSIX bashisms (such as &> /dev/null) to POSIX > /dev/null 2>&1."""
        count = 0
        pattern = re.compile(r"&>\s*(\S+)")
        for path in self.find_files(file_glob):
            try:
                content = path.read_text(encoding="utf-8", errors="surrogateescape")
            except OSError:
                continue
            new_content, n = pattern.subn(r"> \1 2>&1", content)
            if n > 0 and new_content != content:
                self._atomic_write(path, new_content)
                count += n
                if self.report:
                    self.report.record(
                        path, "patch", f"sanitized {n} non-POSIX redirections"
                    )
        return count

    def _atomic_write(self, path: Path, content: str) -> None:
        """Atomically replace file content via tempfile."""
        dir_name = path.parent
        dir_name.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".ship_patch_")
        with os.fdopen(fd, "w", encoding="utf-8", errors="surrogateescape") as f:
            f.write(content)
        os.replace(tmp_path, path)
