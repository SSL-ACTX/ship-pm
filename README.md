# ship

Agnostic shell package orchestrator for pre-built binaries across Linux (GNU, Musl) and Android (Termux) user-space environments. Requires no root or sudo privileges.

## Install

```sh
curl -fsSL https://github.com/SSL-ACTX/ship-pm/raw/refs/heads/main/install.sh | bash
```

## Usage

```sh
# Install from registry or directly from GitHub
ship install <package> [version]
ship install <owner/repo> [tag]

# Publish a release to the central registry
ship publish <owner/repo> [tag]

# Manage packages and registry
ship list
ship search [query]
ship info <package>
ship update [package|registry|self]
ship remove <package>
ship rollback <binary>
ship clean
```

## Architecture

Ship core resolves versions and targets, downloads and verifies archives,
extracts package files, tracks installed versions, and links declared commands.
Shared operating environment compatibility lives in `ship/patchers/`.
Exceptional package-specific install or runtime behavior lives in
`ship/patches/<package>.py`; see [Package patches](docs/package-patches.md).

## Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `SHIP_ROOT` | Base directory for store, state, and cache | `~/.local/share/ship` (or `$PREFIX/share/ship` on Termux) |
| `SHIP_BIN_DIR` | Public symlink destination directory | `~/.local/bin` (or `$PREFIX/bin` on Termux) |
| `SHIP_REGISTRY_URL` | Remote registry definition URL | Default main registry |
| `NO_COLOR` | Disables colored output | unset |
