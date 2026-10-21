"""Platform compatibility patches and runtime configuration for Rocq (Coq) prebuilts."""

from pathlib import Path

from ship.api import (
    ExportPolicy,
    InstallPatch,
    PackagePatch,
    PatchContext,
    RuntimeCommand,
    RuntimePatch,
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
    "exp-rocq-prebuilts",
)


def _setup_rocq_environment(context: PatchContext) -> None:
    """Configure findlib metadata, plugins, and worker symlinks for Rocq.

    Rocq 9.x split into rocq-core, rocq-stdlib, and rocq-runtime.
    At runtime, coqc uses findlib to locate the rocqworker binary and
    dynamic plugins (e.g., micromega, ltac, ring).

    This patch:
      1. Generates an ocamlfind.conf pointing to the package lib dir.
      2. Symlinks lib/rocq-runtime -> coq so findlib can locate package rocq-runtime.
      3. Generates lib/coq/META declaring the rocqworker path and all plugin subpackages.
    """
    # Locate install prefix (handles nested archive folder if present)
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

    # 1. Symlink lib/rocq-runtime -> coq
    rocq_runtime_link = lib_dir / "rocq-runtime"
    if not rocq_runtime_link.exists() and not rocq_runtime_link.is_symlink():
        rocq_runtime_link.symlink_to("coq")
        context.record(rocq_runtime_link, "symlink", "-> coq")

    # 2. Write ocamlfind.conf
    ocamlfind_conf = target_prefix / "ocamlfind.conf"
    conf_content = f'destdir="{lib_dir}"\npath="{lib_dir}"\n'
    ocamlfind_conf.write_text(conf_content, encoding="utf-8")
    context.record(ocamlfind_conf, "write", "ocamlfind configuration")

    # 3. Generate findlib META for rocq-runtime and its plugins
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


def _rocq_before(binary_name: str, real_binary: Path, target_key: str) -> str:
    """Set up library paths and ocamlfind configuration before execution."""
    install_dir = real_binary.parent.parent
    gmp_lib = install_dir / "lib" / "aarch64-linux-gnu"
    stub_lib = install_dir / "lib" / "stublibs"
    ocamlfind_conf = install_dir / "ocamlfind.conf"

    exports = [
        f"export LD_LIBRARY_PATH={gmp_lib}:${{LD_LIBRARY_PATH:-}}",
        f"export CAML_LD_LIBRARY_PATH={stub_lib}:${{CAML_LD_LIBRARY_PATH:-}}",
        f"export OCAMLFIND_CONF={ocamlfind_conf}",
    ]
    return "\n".join(exports)


def _rocq_runtime(
    binary_name: str, real_binary: Path, target_key: str
) -> RuntimeCommand | None:
    """Inject ROCQLIB, ROCQRUNTIMELIB, and PATH into the runtime environment."""
    install_dir = real_binary.parent.parent
    coq_dir = install_dir / "lib" / "coq"
    bin_dir = real_binary.parent

    return RuntimeCommand(
        argv=(real_binary,),
        environment=(
            ("ROCQLIB", coq_dir),
            ("COQLIB", coq_dir),
            ("ROCQRUNTIMELIB", coq_dir),
            ("COQCORELIB", coq_dir),
            ("PATH", f"{bin_dir}:${{PATH}}"),
        ),
    )


PATCH = PackagePatch(
    export_policy=ExportPolicy(
        only=_ROCQ_COMMANDS,
    ),
    pre_link=(InstallPatch(_setup_rocq_environment),),
    runtime=(
        RuntimePatch(
            binaries=_ROCQ_COMMANDS,
            before=_rocq_before,
            command=_rocq_runtime,
        ),
    ),
)
