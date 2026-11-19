# Package patches

Package-specific behavior lives in `ship/packages/<package_name>.py`; hyphens
in package names become underscores. Platform-wide compatibility belongs in
`ship/runtime/`.

Import the public authoring API from `ship.api` only.

Package modules declare install, layout, and runtime behavior through the modern
declarative `PackageRecipe` builder (which compiles down to `PackagePatch`).

## Declarative PackageRecipe API

The `PackageRecipe` builder unifies layout normalization, config generation,
ELF mutations, proxy multiplexing, and runtime launcher wrappers into a single
fluent specification:

```python
from ship.api import PackageRecipe, on_platform, on_termux, raise_tls_alignment

PATCH = (
    PackageRecipe("my-tool")
    # 1. Archive & Layout normalization
    .flatten_nested_root("my-tool-*")
    .symlink("lib/my-tool", to="lib/runtime")
    .ensure_dirs("cache", "stublibs")
    # 2. Config templates with automatic interpolation
    .write_template(
        "etc/tool.conf",
        """
        install_prefix = "{install_dir}"
        bin_dir = "{bin_dir}"
        profile_prefix = "{profile.prefix}"
        """,
    )
    # 3. Export policy & binary visibility
    .export(
        only=("my-tool", "my-tool-cli"),
        internal_only=("tool-worker", "tool-backend"),
        aliases={"tool": "my-tool"},
        discover_all_bins=True,
    )
    # 4. ELF & toolchain compatibility
    .raise_tls_alignment(
        ("bin/my-tool",),
        alignment=64,
        condition=on_termux(arch="aarch64"),
    )
    .resolve_sonames(
        {"libedit.so.2": "libedit.so.0.0.78"},
        stage="post_extract",
        condition=on_platform(target="*-linux-*"),
    )
    .patch_subtree("**/solvers/**/z3*")
    # 5. Public launcher environment & runtime behavior
    .runtime(
        binaries=("my-tool",),
        prepend_path=("bin",),
        prepend_ld_library_path=("lib",),
        env={
            "TOOL_HOME": "{install_dir}/share",
            "TOOL_CONF": "{install_dir}/etc/tool.conf",
        },
    )
    .to_patch()
)
```

`PackageRecipe` also directly proxies attributes of `PackagePatch`, meaning you can return either `recipe.to_patch()` or assign `PATCH = recipe`.

---

## High-Level Recipe Primitives

### 1. Multi-Binary Proxy Multiplexing (`.multiplex_proxies`)
Used for toolchains where multiple commands route back to a central dispatcher (e.g. `rustup`, `cargo`, `rustc`, `rustfmt`).

```python
PATCH = (
    PackageRecipe("rustup")
    .multiplex_proxies(
        target_binary="rustup",
        proxies=("rustup", "rustc", "cargo", "rustfmt", "rust-analyzer"),
        extra_dirs=[Path.home() / ".cargo" / "bin"],
        environment={
            "SSL_CERT_FILE": "/data/data/com.termux/files/usr/etc/tls/cert.pem",
            "SSL_CERT_DIR": "/data/data/com.termux/files/usr/etc/tls",
        },
        condition=on_termux(),
    )
    .to_patch()
)
```

### 2. Maintenance Subcommand Triggers (`.on_subcommand`)
Automatically triggers toolchain re-patching or maintenance tasks after a command runs specific subcommands (such as `rustup toolchain install` or `juliaup update`):

```python
PATCH = (
    PackageRecipe("juliaup")
    .on_subcommand(
        binaries=("juliaup",),
        triggers=("add", "update", "install", "default"),
        post_exec_call="ship.packages.juliaup:patch_toolchain_dir",
        targets=("aarch64-*",),
    )
    .on_reapply(patch_toolchain_dir)
    .to_patch()
)
```

### 3. Compile-and-Run Interception (`.intercept_compiler_run`)
For compilers whose `run` subcommand builds an ephemeral ELF binary and immediately executes it (preventing Ship from fixing up PT_TLS or interpreters). This intercepts the command, builds into an isolated tempdir with `-out:`, applies the post-build fixup, and transparently executes the binary while passing through all exit codes and POSIX signals:

```python
PATCH = (
    PackageRecipe("odin")
    .intercept_compiler_run(
        binary="odin",
        subcommand="run",
        build_subcommand="build",
        output_flag="-out:{output}",
        unsupported_flags=RUN_UNSUPPORTED_FLAGS,
        fixup=lambda out: raise_tls_alignment(out, alignment=64),
        condition=on_termux(arch="aarch64"),
    )
    .to_patch()
)
```

### 4. Platform Conditions
Instead of manual `if not profile.is_termux:` guards, attach conditions directly to any recipe action:

- `on_platform(platform="linux"|"darwin"|"termux", arch="aarch64"|"x86_64", target="*-linux-*")`
- `on_termux(arch="aarch64")`

---

## Low-Level & Scripting Helpers

For custom logic that needs imperative control, drop into `.hook(...)` or use the underlying primitives:

```python
from ship.api import (
    InlineScript,
    WrapperBuilder,
    promote_nested_directory,
    resolve_soname_symlinks,
    patch_subtree_binaries,
)

# Inline shell scripts with safe substitution
script = InlineScript("""
    unset LD_PRELOAD
    export SSL_CERT_FILE=@profile.tls_cert@
    exec -a "$0" @wrapper@ "$@"
""")
rendered = script.render(profile=context.profile, wrapper="/path/to/real")

# In-tree binary wrapper with arg rewriting
WrapperBuilder(
    target_binary="bin/ld.lld",
    rewrite_args={r"/lib/ld-linux*.so.*": glibc_loader},
    append_args_if=[("-dynamic-linker", ["-rpath", str(glibc_lib)])],
).apply(context)

# Auto-link missing glibc sonames into package lib/
resolve_soname_symlinks(context, {"libedit.so.2": "libedit.so.0.0.78"})

# Discovers and patches internal bundled ELF binaries
patch_subtree_binaries(context, "**/z3*/**/z3*")
```

---

## Domain-Oriented Imports

All APIs are re-exported from `ship.api` for convenience, but modular imports are also available:

- `ship.api.recipes` — `PackageRecipe`, `PackagePatch`, `on_platform`, `on_termux`, `PlatformCondition`
- `ship.api.toolkit` — `RuntimePatch`, `RuntimeCommand`, `ExportPolicy`, `InstallPatch`
- `ship.api.context` — `PatchContext`, `PatchReport`
- `ship.api.fs` — Filesystem mutation helpers (`write_text`, `create_symlink`, `make_executable`)
- `ship.api.elf` — ELF inspection and mutation (`inspect_elf`, `raise_tls_alignment`, `set_elf_rpath`)
- `ship.api.scripting` — `WrapperBuilder`, `InlineScript`, `promote_nested_directory`

---

## Re-applying Patches

`ship repatch <package>` reapplies package handlers and platform runtime adapters to an installed package, runs its optional `.on_reapply(...)` handlers, refreshes links, and displays reported changes without downloading the archive again.
