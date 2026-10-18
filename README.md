# `ship` - Agnostic Shell Package Orchestrator

Lightweight, user-space, zero-root package orchestrator for distributing and managing custom pre-built binaries across **Linux (GNU, Musl)** and **Android / Termux**.

---

## Features

- **Zero Root Needed:** Operates entirely in user-space (`~/.local/share/ship` or `$PREFIX/share/ship` in Termux).
- **Multi-Environment & Architecture Aware:** Automatically resolves architecture (`aarch64`, `x86_64`, `armv7`, `riscv64`, `i686`) and matches `musl`, `gnu`, `android`, or `termux` targets.
- **Direct GitHub Releases Support:** Install any tool directly from GitHub without needing a registry entry:
  ```sh
  ship install https://github.com/sharkdp/fd
  # or
  ship from-github sharkdp/fd v9.0.0
  ```
- **Declarative Central Registry:** Supports querying and installing pre-cataloged tools via `registry.json`.
- **Smart Hook Engine & Android/Termux Glibc Fallback:** Automatically provides dynamic glibc loader resolution (`ld-linux-...`), CA certificate paths (`$SSL_CERT_FILE`), and `auto_patch` helpers via `patchelf` on Termux, while leaving standard Linux untouched.
- **Robust POSIX Engine:** Runs in pure POSIX shell with zero-dependency fallback chain (`jq` $\rightarrow$ `python3`).
- **Cryptographic Verification:** Strict SHA-256 integrity verification before archive extraction.
- **Multiple Archive Formats:** Extracts `.tar.gz`, `.tar.xz`, `.tar.bz2`, `.zip`, and raw executable binaries.

---

## Installation

### One-line Bootstrap
```sh
curl -fsSL https://raw.githubusercontent.com/YourOrg/ship/main/install.sh | sh
```

### Local / Manual
Clone the repository and add `./bin` to your `$PATH`:
```sh
git clone https://github.com/YourOrg/ship.git
export PATH="$PWD/ship/bin:$PATH"
```

---

## Usage

```sh
# Install from central registry
ship install <package> [version]

# Install directly from GitHub Releases (by URL or shorthand)
ship install https://github.com/owner/repo
ship from-github owner/repo [tag]

# Update packages (specific or all installed)
ship update [package]

# Remove package and clean symlinks
ship remove <package>

# List installed packages & installation dates
ship list

# Search packages in central registry
ship search [query]

# Inspect package metadata & available versions
ship info <package>

# Clean downloaded archives and temp files
ship clean

# Refresh registry cache
ship registry update

# Show version & help
ship version
ship help
```

---

## Directory & State Topology

```text
[SHIP_ROOT]/                  # Default: ~/.local/share/ship/ or $PREFIX/share/ship/
├── bin/                      # Internal symlink hub
├── store/                    # Versioned unpacked artifacts (e.g. tool@1.0.0/)
├── cache/                    # Downloaded archives & temporary registry cache
└── state.json                # Local lockfile tracking installed tools & symlinks
```

---

## License

MIT / Apache-2.0
