# Ship

Ship installs prebuilt command-line programs from the package registry, GitHub
releases, and secondary package pools (such as Ubuntu Debian packages). It selects
an available build for the host, verifies archives when a SHA-256 checksum is provided,
stores downloads for reuse, and links the installed commands into the user's binary
directory.

## Requirements

- Python 3.11 or later
- Git, for installation from GitHub and primary registry synchronization
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
and `~/.local/share/ship` elsewhere. Set `SHIP_ROOT` or `SHIP_BIN_DIR` to
choose different locations.

## Use

Install a package from the core registry, Ubuntu deb repositories, a direct `.deb` archive,
or directly from a GitHub repository:

```sh
# Core registry
ship install fd
ship install fd 10.5.0

# GitHub releases
ship install sharkdp/fd
ship install sharkdp/fd v10.5.0

# Secondary Ubuntu deb registry (requires --deb flag)
ship install zstd --deb
# gdu is also a deb package; --deb is required when it's not in the core registry
ship install gdu --deb

# Direct URL or local .deb
ship install https://example.com/package_1.0_arm64.deb
ship install ./my-package.deb
```

The registry install uses its default version when none is specified. For a
GitHub repository, Ship resolves a release and selects a matching asset when
available. Command-specific flags such as `-t, --target <triple>`, `--select-target`,
`--asset <name>`, and `--deb` are available directly on `ship install`.

## Commands

| Command | Purpose |
| :--- | :--- |
| `ship install [OPTIONS] <package> [version]` | Install from the registry, Ubuntu pool (`--deb`), local `.deb`, or GitHub |
| `ship install <owner/repo> [tag]` | Install a GitHub release directly |
| `ship remove <package> [--purge]` | Remove a package and its command links |
| `ship rollback <package> [--yes]` | Reinstall the previous version of a package |
| `ship rollback --binary <command> [--yes]` | Restore a command Ship backed up when linking |
| `ship repatch <package>` | Reapply package and platform patches to an installed package |
| `ship update [--all\|--github]` | Check installed packages for updates concurrently (`--all` / `-a` checks GitHub installs too) |
| `ship update <package>` | Update one installed package |
| `ship update registry` | Sync the primary package registry |
| `ship update deb` | Fetch and update the cached Ubuntu package registry |
| `ship update self` | Update Ship itself |
| `ship check-upstream [package]` | Compare packages with their latest GitHub releases |
| `ship search <query> [--deb\|--all]` | Search registry (use `--deb` for Ubuntu packages) |
| `ship info <package>` | Show versions, target builds, and install size |
| `ship list` | List installed packages |
| `ship cache [stats\|clear]` | View or clear GitHub API response caches |
| `ship clean` | Remove cached downloads, backups, and orphaned stores |
| `ship auth status` | Show the active GitHub CLI account |
| `ship auth login` | Sign in with GitHub CLI |
| `ship publish <owner/repo> [tag]` | Submit a release for registry review |
| `ship admin sync [package]` | Trigger the upstream sync workflow on GitHub Actions (registry admins only) |
| `ship admin prs` | List open package submissions (registry admins only) |
| `ship admin review <PR>` | Show submission metadata and manifest diff (registry admins only) |
| `ship admin accept <PR> [--yes]` | Merge an eligible submission (registry admins only) |
| `ship admin reject <PR> [--reason TEXT] [--yes]` | Close a submission with a comment (registry admins only) |
| `ship doctor [--heal]` | Check symlinks, ELF patches, and store integrity; `--heal` auto-repairs fixable issues |
| `ship export <package> [output_bundle]` | Bundle an installed package into a portable offline archive |
| `ship import <bundle>` | Install a package from a local offline bundle |
| `ship sandbox <action> [target] [cmd...]` | Manage isolated sandbox areas (see **Sandbox** below) |
| `ship call <module:function> [args...]` | Dispatch an internal ship package entrypoint directly |

Run `ship --help` for global options. Target-specific options (`-t`, `--select-target`, `--asset`)
live directly under `ship install`.

## Package data and storage

Package manifests are JSON files in `pkgs/`. Each version lists target builds,
download URLs, checksums when available, and command paths. The registry is
synchronized from the Git repository configured by `SHIP_REGISTRY_GIT`.

In addition to core manifests, Ship supports secondary repositories:
- **Ubuntu Noble registry**: Over 69,000 packages indexed directly from Ubuntu Noble (`main` and `universe`).
  Stored in `$SHIP_ROOT/cache/registries/ubuntu-noble.json` with automatic TTL cache management. Updatable via `ship update deb`.
- **Search filtering**: Primary search (`ship search <query>`) queries core manifests first. Adding `--deb` searches Ubuntu deb packages, while `--all` searches both pools.

Ship stores archives, extracted packages, and state under `$SHIP_ROOT`. Repeated
installs reuse a cached archive; Ship verifies the cached file when the
manifest supplies a checksum. Installed commands link to files in the package
store. When an install changes a package's version or target, Ship records the
previous version for rollback, keeping up to ten entries per package. Rollback
reinstalls that release and reuses a cached archive when available.

Ship extracts `.deb` files natively or through `DebArchive`, `.7z` releases with
an installed `7zz`/`7z`/`7za`/`bsdtar`, and `.tar.zst` with `zstd` or `unzstd`.
`ship rollback --binary <command>` restores the most recent original command
backup saved when Ship first replaced that command.

## Architecture

Ship is organized into explicit packages with a single public authoring API:

| Package | Role |
| :--- | :--- |
| `ship.api` | Public patch authoring surface (`PackagePatch`, ELF/FS helpers) |
| `ship.core` | Profiles, settings, state, platform targets, version helpers |
| `ship.net` | Downloads, GitHub API/atom clients, and response caching |
| `ship.registry` | Primary registry sync, Ubuntu deb registry indexer, and manifest loader |
| `ship.install` | Shared install pipeline, deb extraction, sources, remove/rollback/repatch |
| `ship.link` | Binary discovery and sandboxed linking |
| `ship.runtime` | Platform adapters (QEMU runner, Termux ELF patching, glibc compat) |
| `ship.packages` | Per-package `PATCH` recipes |
| `ship.cli` | Command-line interface |

## Profiles

Host defaults come from a resolved **profile** (`termux`, `linux`, `darwin`, …),
not scattered Termux checks. Override with `SHIP_PROFILE`, or let Ship detect
the host. Profile-owned paths (prefix, glibc lib, bash, certs) are what package
patches should use via `context.profile` / `get_active_profile()`.

## Patches

Use `ship/runtime/` for behavior shared across packages on a platform, such as
Termux runtime setup or launching a foreign-architecture binary through QEMU.
Use `ship/packages/<package>.py` for package-specific changes to installed files
or commands. Package names with hyphens use underscores in Python filenames.

New package patches use the typed `PATCH` recipe API in `ship.api`. Recipes can
select target triples, edit files within the package directory, inspect and
modify ELF binaries, select binaries by properties, and define runtime commands
with arguments and environment settings. Operations report changed files through
a shared patch report. See [Package patches](docs/package-patches.md) for
handler types, helpers, and examples.

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
registry repository. Use `ship admin sync [package]` to dispatch the upstream
sync workflow on GitHub Actions. Use `ship admin review <PR>` to inspect the publisher,
labels, and manifest diff. `ship admin accept` lets the registry administrator
approve a submission after review; publisher upstream permissions are shown as
context and do not replace the administrator's decision. Acceptance still
requires a generated submission PR with the required labels and exactly one
package manifest change. Rejection closes the submission and posts the supplied
reason, or a default message.

## Configuration

| Variable | Purpose | Default |
| :--- | :--- | :--- |
| `SHIP_PROFILE` | Force a host profile (`termux`, `linux`, `darwin`, …) | Auto-detected |
| `SHIP_ROOT` | Ship data, cache, store, and state directory | `~/.local/share/ship`; `$PREFIX/share/ship` on Termux |
| `SHIP_BIN_DIR` | Directory for installed command links | `~/.local/bin` (never `$PREFIX/bin`) |
| `PREFIX` | Host prefix used by the active profile | Termux `$PREFIX` / `/usr` / `/usr/local` |
| `GLIBC_PREFIX` | glibc-compat root on Termux-like hosts | `$PREFIX/glibc` on Termux |
| `SHIP_REGISTRY_GIT` | Git repository containing package manifests | `https://github.com/SSL-ACTX/ship-pm.git` |
| `SHIP_REGISTRY_REPO` | GitHub repository used for admin permission checks | Derived from `SHIP_REGISTRY_GIT` |
| `SHIP_REGISTRY_BRIDGE` | HTTPS Worker endpoint for `ship publish` | `https://corrupted-lily-1011.callixjeira.workers.dev/` |
| `SHIP_UPDATE_URL` | File used by `ship update self` outside a Git checkout | Project `bin/ship` on GitHub |
| `SHIP_CACHE_TTL` | Cache TTL in seconds for GitHub API responses | `3600` (1 hour) |
| `SHIP_UBUNTU_TTL` | Cache TTL in seconds for Ubuntu package index | `604800` (7 days) |
| `GH_TOKEN` / `GITHUB_TOKEN` | Optional GitHub API credential for release lookups | Unset |
| `NO_COLOR` | Disable colored terminal output when set | Unset |
