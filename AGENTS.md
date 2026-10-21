# AGENTS.md

## Repository Overview

`ship` is a zero-build prebuilt package manager for command-line tools running on Linux, macOS, and Android (Termux). It fetches precompiled binaries from primary manifests (`pkgs/*.json`), direct GitHub releases, and secondary package pools (such as Ubuntu Debian packages). It handles archive extraction, target resolution, dynamic linker relocation, ELF patching, sandboxed linking, and rollback management.

## Environment & Tooling Constraints

- **Python**: Requires Python 3.11+. The active environment runs on Python 3.14 (aarch64 / Termux).
- **Prohibited Commands & Tools**:
  - Do **NOT** invoke `git` commands (commits, rebases, merges, staging).
  - Do **NOT** use `sed` for source code modifications. Use explicit file editing tools.
- **Code Quality & Linting**:
  - All changes must pass `ruff check .` with zero errors or warnings.
  - Never suppress linter warnings with blanket `# noqa` or blind `except Exception:` catches. Catch specific expected exceptions (`OSError`, `ValueError`, `json.JSONDecodeError`, `urllib.error.URLError`, etc.).
  - Explicit `check=False` or `check=True` required for all `subprocess.run` invocations.
- **Testing**:
  - All tests must pass before completing any task: `PYTHONPATH=. pytest -q`.

## Codebase Architecture

```
ship/
├── api/          # Public authoring API (PackagePatch, InlineScript, ELF & FS tools)
├── cli/          # CLI argument parser and command handlers (never hand-write help)
├── core/         # Settings, state, profiles, platform detection, version helpers
├── install/      # Pipeline: extraction, sources (registry, github, deb), state tracking
├── link/         # Binary discovery, symlink management, collision handling
├── net/          # HTTP fetching, atomic disk-based caching (GitHub API & deb sources)
├── packages/     # Per-package patch recipes (e.g. lean4.py, rustup.py)
├── registry/     # Primary manifest loaders and secondary indexers (ubuntu.py)
├── runtime/      # Host runtime adapters (Termux ELF patching, glibc compat, QEMU runner)
└── ui/           # Terminal UI, spinners, progress indicators, status styling
```

## Engineering Principles

1. **Host Abstraction**: Route all filesystem and environment lookups through `Profile` (`context.profile` / `get_active_profile()`). Never hardcode paths like `/data/data/com.termux` across core logic.
2. **Atomic Operations**: All cache entries, manifest updates, and state files must be written atomically using tempfiles and replaced via `os.replace`.
3. **No Interactive Interference**: Background tasks or threaded spinners must never share standard I/O streams with sequential downloads or user prompts.
4. **Idempotent Installation**: Every install pass must record package state, link binaries sandboxed to `SHIP_BIN_DIR`, validate ELF architectures when required, and cleanly handle rollback states.
