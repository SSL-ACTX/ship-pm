"""Termux runtime configuration and findlib environment for Frama-C (Debian prebuilts)."""

from __future__ import annotations

from ship.api import PackageRecipe, PatchContext
from ship.runtime import apply_patchers

_PUBLIC_COMMANDS = ("frama-c", "frama-c-gui")


def _setup_framac_environment(context: PatchContext) -> None:
    """Create local ocamlfind configuration and findlib META definitions for Frama-C plugins."""
    install_dir = context.install_dir
    lib_dir = install_dir / "lib"
    plugins_dir = lib_dir / "plugins"
    etc_dir = install_dir / "etc"
    etc_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate ocamlfind.conf pointing to local library paths
    ocamlfind_conf = etc_dir / "ocamlfind.conf"
    conf_content = (
        f'destdir="{lib_dir}"\npath="{lib_dir}:{plugins_dir}"\nldconf="ignore"\n'
    )
    ocamlfind_conf.write_text(conf_content, encoding="utf-8")
    context.record(ocamlfind_conf, "write", "ocamlfind configuration for Frama-C")

    # 2. Re-link individual plugin META files to standard package names
    if plugins_dir.is_dir():
        for meta in plugins_dir.glob("META.*"):
            pkg_name = meta.name.removeprefix("META.")
            pkg_dir = plugins_dir / pkg_name
            pkg_dir.mkdir(parents=True, exist_ok=True)
            target_meta = pkg_dir / "META"
            if not target_meta.exists() and not target_meta.is_symlink():
                target_meta.symlink_to(meta)
                context.record(target_meta, "symlink", f"-> {meta.name}")


PATCH = (
    PackageRecipe("frama_c_base")
    .export(only=_PUBLIC_COMMANDS)
    .hook(_setup_framac_environment, stage="pre_link")
    .patch_subtree(
        "**/*.cmxs",
        patcher_fn=lambda bin_path, target_key, report: apply_patchers(
            bin_path, target_key, report
        ),
    )
    .runtime(
        binaries=_PUBLIC_COMMANDS,
        targets=("*",),
        env={
            "OCAMLFIND_CONF": "{install_dir}/etc/ocamlfind.conf",
            "FRAMAC_SHARE": "{install_dir}/share/frama-c",
            "FRAMAC_LIB": "{install_dir}/lib",
            "FRAMAC_PLUGIN": "{install_dir}/lib/plugins",
        },
    )
    .to_patch()
)
