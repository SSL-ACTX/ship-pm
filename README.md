# Ship

> [![SSL-ACTX](https://github.com/SSL-ACTX.png?size=20)](https://github.com/SSL-ACTX) Built by [SSL-ACTX](https://github.com/SSL-ACTX) &nbsp;·&nbsp; [![Iris-Seravelle](https://github.com/Iris-Seravelle.png?size=20)](https://github.com/Iris-Seravelle) [Iris-Seravelle](https://github.com/Iris-Seravelle)

Zero-build binary installer and runtime relocator for command-line tools on Linux, macOS, and Android (Termux).

Ship fetches precompiled binaries (GitHub Releases, core registry, or Ubuntu `.deb` pools), isolates them in a store directory, relocates and patches ELFs to run natively on the host, and symlinks them to `~/.local/bin`.

## Key Capabilities

* **Zero-Build Installation**: Fetches prebuilt binaries directly from GitHub releases or Debian packages without compiling from source.
* **Native Termux Glibc Support**: Freestanding `PT_INTERP` trampoline (`ld-termux-aarch64`) unsets Bionic `LD_PRELOAD` on the stack before launching glibc ELFs, eliminating wrapper cloning.
* **Native Musl Support**: Relocates hardcoded `/etc/resolv.conf` and `/etc/hosts` in static musl ELFs via segment expansion and opcode rewriting—zero QEMU required.
* **Sandboxed Linking**: Links binaries into `~/.local/bin` while preserving rollback history (up to 10 versions).

## Quick Start

```sh
curl -fsSL https://github.com/SSL-ACTX/ship-pm/raw/refs/heads/main/install.sh | bash
```

```sh
# From core registry
ship install fd

# Direct from GitHub releases
ship install sharkdp/fd
ship install sharkdp/fd v10.5.0

# From Ubuntu deb pool
ship install zstd --deb

# Direct URL or local .deb
ship install ./my-package.deb
```

## Commands

| Command | Action |
| :--- | :--- |
| `ship install <pkg\|owner/repo> [ver]` | Install binary from registry, GitHub, or deb pool (`--deb`) |
| `ship update [--all\|<pkg>]` | Check and install updates concurrently |
| `ship rollback <package>` | Roll back to previous installed version |
| `ship rollback --binary <cmd>` | Restore host binary Ship backed up |
| `ship repatch <package>` | Reapply runtime and ELF patches to installed package |
| `ship remove <package> [--purge]` | Uninstall package and clear command links |
| `ship search <query> [--deb\|--all]` | Search package manifests or deb pools |
| `ship list` | List installed packages |
| `ship doctor [--heal]` | Verify and repair broken symlinks and ELF patches |
| `ship clean` | Clear cached downloads and orphaned store files |

## Configuration

| Variable | Purpose | Default |
| :--- | :--- | :--- |
| `SHIP_ROOT` | Store, cache, and state directory | `~/.local/share/ship`; `$PREFIX/share/ship` on Termux |
| `SHIP_BIN_DIR` | Directory for installed command symlinks | `~/.local/bin` |
| `SHIP_PROFILE` | Force host profile (`termux`, `linux`, `darwin`) | Auto-detected |
| `GLIBC_PREFIX` | glibc-compat root on Termux | `$PREFIX/glibc` |

## License

Licensed under the [Mozilla Public License 2.0](LICENSE)
