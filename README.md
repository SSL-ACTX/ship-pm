# Ship

Ship installs prebuilt command-line programs from the package registry or from
GitHub releases. It selects an available build for the host, verifies archives
when a SHA-256 checksum is provided, stores downloads for reuse, and links the
installed commands into the user's binary directory.

## Requirements

- Python 3.11 or later
- Git, for installation from GitHub and registry synchronization
- `gh` (GitHub CLI), only for publishing packages or using administrator commands

Ship does not build packages from source. QEMU user emulators can be used to run
some binaries built for a different CPU architecture.

## Install

Install the latest version from the project repository:

```sh
curl -fsSL https://github.com/SSL-ACTX/ship-pm/raw/refs/heads/main/install.sh | bash
```

The installer puts `ship` in a writable binary directory and configures `PATH`
when needed. Ship's data directory defaults to `$PREFIX/share/ship` on Termux
and `~/.local/share/ship` elsewhere. Set `SHIP_ROOT` or `SHIP_BIN_TARGET` to
choose different installer locations.

## Use

Install a package from the registry, or install a release directly from a
GitHub repository:

```sh
ship install fd
ship install fd 10.5.0
ship install sharkdp/fd
ship install sharkdp/fd v10.5.0
```

The registry install uses its default version when none is specified. For a
GitHub repository, Ship resolves a release and selects a matching asset when
available. Use `--target <triple>` to select a target explicitly or
`--select-target` to choose interactively.

## Commands

| Command | Purpose |
| :--- | :--- |
| `ship install <package> [version]` | Install from the registry |
| `ship install <owner/repo> [tag]` | Install a GitHub release directly |
| `ship remove <package>` | Remove a package and its command links |
| `ship rollback <package> [--yes]` | Reinstall the previous version of a package |
| `ship rollback --binary <command> [--yes]` | Restore a command Ship backed up when linking |
| `ship repatch <package>` | Reapply package and platform patches to an installed package |
| `ship update` | Sync the registry and update installed packages |
| `ship update <package>` | Update one installed package |
| `ship update registry` | Sync the package registry |
| `ship update self` | Update Ship |
| `ship check-upstream <package>` | Compare a package with its latest GitHub release |
| `ship search [query]` | Search registry names and descriptions |
| `ship info <package>` | Show versions, target builds, and install size when installed |
| `ship list` | List installed packages |
| `ship clean` | Remove cached downloads and backups |
| `ship auth status` | Show the active GitHub CLI account |
| `ship auth login` | Sign in with GitHub CLI |
| `ship publish <owner/repo> [tag]` | Submit a release for registry review |
| `ship admin prs` | List open package submissions (registry admins only) |
| `ship admin review <PR>` | Show submission metadata and manifest diff (registry admins only) |
| `ship admin accept <PR> [--yes]` | Merge an eligible submission (registry admins only) |
| `ship admin reject <PR> [--reason TEXT] [--yes]` | Close a submission with a comment (registry admins only) |

Run `ship --help` for global options. Install and update accept `-t <triple>`
or `--target <triple>`; `--select-target` opens an interactive target picker.

## Package data and storage

Package manifests are JSON files in `pkgs/`. Each version lists target builds,
download URLs, checksums when available, and command paths. The registry is
synchronized from the Git repository configured by `SHIP_REGISTRY_GIT`.

Ship stores archives, extracted packages, and state under `$SHIP_ROOT`. Repeated
installs reuse a cached archive; Ship verifies the cached file when the
manifest supplies a checksum. Installed commands link to files in the package
store. When an install changes a package's version or target, Ship records the
previous version for rollback, keeping up to ten entries per package. Rollback
reinstalls that release and reuses a cached archive when available.
`ship rollback --binary <command>` restores the most recent original command
backup saved when Ship first replaced that command.

## Patches

Use `ship/patchers/` for behavior shared across packages on a platform, such as
Termux runtime setup or launching a foreign-architecture binary through QEMU.
Use `ship/patches/<package>.py` for package-specific changes to installed files
or commands. Package names with hyphens use underscores in Python filenames.

New package patches use the typed `PATCH` recipe API in
`ship/patches/api.py`. Recipes can select target triples, edit files within the
package directory, inspect and modify ELF binaries, select binaries by
properties, and define runtime commands with arguments and environment
settings. Operations report changed files through a shared patch report. See
[Package patches](docs/package-patches.md) for handler types, helpers, and
examples.

Run `ship repatch <package>` to apply the package and platform patches again
to an installed package. It does not download the archive again; it refreshes
the installed package's links and reports file changes.

## Publishing and review

Publishing requires `gh` to be authenticated with `ship auth login`. Ship sends
the GitHub credential to the configured HTTPS bridge. The Worker verifies the
account, checks its access to the upstream repository, and dispatches the
request to the registry workflow. The workflow creates a pull request for
review; publishing does not merge the package automatically.

Registry administrators authenticate with `gh` as an administrator of the
registry repository. Use `ship admin review <PR>` to inspect the publisher,
labels, and manifest diff. `ship admin accept` requires a verified upstream
contributor submission that changes exactly one package manifest. Rejection
closes the submission and posts the supplied reason, or a default message.

## Configuration

| Variable | Purpose | Default |
| :--- | :--- | :--- |
| `SHIP_ROOT` | Ship data, cache, store, and state directory | `~/.local/share/ship`; `$PREFIX/share/ship` on Termux |
| `SHIP_BIN_DIR` | Directory for installed command links | `~/.local/bin`; `$PREFIX/bin` on Termux when writable |
| `SHIP_REGISTRY_GIT` | Git repository containing package manifests | `https://github.com/SSL-ACTX/ship-pm.git` |
| `SHIP_REGISTRY_REPO` | GitHub repository used for admin permission checks | Derived from `SHIP_REGISTRY_GIT` |
| `SHIP_REGISTRY_BRIDGE` | HTTPS Worker endpoint for `ship publish` | `https://corrupted-lily-1011.callixjeira.workers.dev/` |
| `SHIP_UPDATE_URL` | File used by `ship update self` outside a Git checkout | Project `bin/ship` on GitHub |
| `GH_TOKEN` / `GITHUB_TOKEN` | Optional GitHub API credential for release lookups | Unset |
| `NO_COLOR` | Disable colored terminal output when set | Unset |

The installer also accepts `SHIP_REPO_GIT` to choose the source repository and
`SHIP_BIN_TARGET` to choose where it installs the `ship` executable.
