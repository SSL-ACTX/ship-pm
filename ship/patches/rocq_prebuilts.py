"""Platform compatibility patches and runtime configuration for Rocq (Coq) prebuilts."""

from ship.api import (
    PackageRecipe,
    PatchContext,
)

# All user-facing Rocq/Coq commands shipped in the prebuilt bundle.
_ROCQ_COMMANDS = (
    "coq-tex",
    "coq_makefile",
    "coqc",
    "coqchk",
    "coqdep",
    "coqdoc",
    "coqidetop",
    "coqnative",
    "coqpp",
    "coqtop",
    "coqwc",
    "coqworkmgr",
    "menhir",
    "rocq",
    "rocqchk",
    "rocq-prebuilts",
)

_ROCQ_WORKERS = (
    "rocqworker",
    "rocqnative",
    "rocqworker_with_drop",
)

_ALL_ROCQ_BINARIES = _ROCQ_COMMANDS + _ROCQ_WORKERS


def _setup_rocq_environment(context: PatchContext) -> None:
    """Configure findlib metadata, plugins, and worker symlinks for Rocq."""
    target_prefix = context.install_dir
    nested = list(context.install_dir.glob("rocq-prover-*"))
    if nested and nested[0].is_dir():
        target_prefix = nested[0]

    lib_dir = target_prefix / "lib"
    coq_dir = lib_dir / "coq"
    bin_dir = target_prefix / "bin"
    plugins_dir = coq_dir / "plugins"

    if not coq_dir.exists():
        return

    # Symlink lib/rocq-runtime -> coq
    rocq_runtime_link = lib_dir / "rocq-runtime"
    if not rocq_runtime_link.exists() and not rocq_runtime_link.is_symlink():
        rocq_runtime_link.symlink_to("coq")
        context.record(rocq_runtime_link, "symlink", "-> coq")

    # Write ocamlfind.conf
    ocamlfind_conf = target_prefix / "ocamlfind.conf"
    conf_content = f'destdir="{lib_dir}"\npath="{lib_dir}"\n'
    ocamlfind_conf.write_text(conf_content, encoding="utf-8")
    context.record(ocamlfind_conf, "write", "ocamlfind configuration")

    # Generate findlib META for rocq-runtime and its plugins
    meta_lines = [
        'description = "Rocq runtime"',
        'version = "9.2"',
        f'directory = "{bin_dir}"',
        'package "plugins" (',
        f'  directory = "{plugins_dir}"',
    ]

    if plugins_dir.is_dir():
        for plugin in sorted(plugins_dir.iterdir()):
            if not plugin.is_dir():
                continue
            pname = plugin.name
            cmas = list(plugin.glob("*.cma"))
            cmxss = list(plugin.glob("*.cmxs"))
            cma = cmas[0].name if cmas else ""
            cmxs = cmxss[0].name if cmxss else ""
            meta_lines.append(f'  package "{pname}" (')
            meta_lines.append(f'    directory = "{plugin.resolve()}"')
            if cma:
                meta_lines.append(f'    archive(byte) = "{cma}"')
            if cmxs:
                meta_lines.append(f'    archive(native) = "{cmxs}"')
            meta_lines.append("  )")

    meta_lines.append(")")
    meta_file = coq_dir / "META"
    meta_file.write_text("\n".join(meta_lines) + "\n", encoding="utf-8")
    context.record(meta_file, "write", "findlib META for rocq-runtime plugins")

    # Symlink rocqworker, rocqnative, rocqworker_with_drop in rocq-runtime to bin
    runtime_dir = (coq_dir.parent / "rocq-runtime").resolve()
    if runtime_dir.is_dir():
        for name in _ROCQ_WORKERS:
            bin_target = bin_dir / name
            worker_file = runtime_dir / name
            if bin_target.exists():
                worker_file.unlink(missing_ok=True)
                worker_file.symlink_to(bin_target)
                context.record(worker_file, "symlink", f"-> {bin_target}")


PATCH = (
    PackageRecipe("rocq-prebuilts")
    .export(only=_ROCQ_COMMANDS)
    .hook(_setup_rocq_environment, stage="pre_link")
    .runtime(
        binaries=_ALL_ROCQ_BINARIES,
        prepend_path=("bin",),
        prepend_ld_library_path=("lib/aarch64-linux-gnu",),
        env={
            "CAML_LD_LIBRARY_PATH": "{install_dir}/lib/stublibs:${CAML_LD_LIBRARY_PATH:-}",
            "OCAMLFIND_CONF": "{install_dir}/ocamlfind.conf",
            "ROCQLIB": "{install_dir}/lib/coq",
            "COQLIB": "{install_dir}/lib/coq",
            "ROCQRUNTIMELIB": "{install_dir}/lib/coq",
            "COQCORELIB": "{install_dir}/lib/coq",
        },
    )
    .to_patch()
)
