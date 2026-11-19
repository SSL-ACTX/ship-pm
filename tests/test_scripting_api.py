"""Tests for the modernized patch authoring API and scripting primitives."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from ship.api import (
    InlineScript,
    PatchContext,
    PatchReport,
    WrapperBuilder,
    promote_nested_directory,
    resolve_soname_symlinks,
)


class TestScriptingAPI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_inline_script_rendering(self):
        profile = SimpleNamespace(
            paths=SimpleNamespace(
                bash=Path("/usr/bin/bash"),
                sh=Path("/bin/sh"),
                prefix=Path("/data/prefix"),
            ),
            is_termux=True,
        )
        script = InlineScript("""
            unset LD_PRELOAD
            export SSL_CERT_FILE=@profile.tls_cert@
            exec @cmd@ "$@"
        """)
        rendered = script.render(profile=profile, cmd="/bin/custom")
        self.assertTrue(rendered.startswith("#!/usr/bin/bash\n"))
        self.assertIn("unset LD_PRELOAD", rendered)
        self.assertIn(
            "export SSL_CERT_FILE=/data/data/com.termux/files/usr/etc/tls/cert.pem",
            rendered,
        )
        self.assertIn('exec /bin/custom "$@"', rendered)

    def test_inline_script_unrendered_placeholder_raises(self):
        script = InlineScript("echo @missing_variable@")
        with self.assertRaises(ValueError):
            script.render()

    def test_wrapper_builder(self):
        bin_dir = self.root / "bin"
        bin_dir.mkdir(parents=True)
        target = bin_dir / "my-tool"
        target.write_text("dummy binary content")
        target.chmod(0o755)

        report = PatchReport("test-pkg")
        context = PatchContext(
            package_name="test-pkg",
            stage="pre_link",
            install_dir=self.root,
            target_key="aarch64-linux-gnu",
            report=report,
        )

        builder = WrapperBuilder(
            target_binary="bin/my-tool",
            shebang="/bin/sh",
            environment={"TOOL_HOME": "/tmp"},
            rewrite_args={
                r"/lib/ld-linux*.so.*": "/compat/ld-linux.so",
            },
            append_args_if=[
                ("-dynamic", ["-rpath", "/compat/lib"]),
            ],
            exec_name="$0",
        )
        wrapper_path = builder.apply(context)

        real_binary = bin_dir / "my-tool-real"
        self.assertTrue(real_binary.is_file())
        self.assertEqual(real_binary.read_text(), "dummy binary content")

        wrapper_text = wrapper_path.read_text()
        self.assertTrue(wrapper_text.startswith("#!/bin/sh\n"))
        self.assertIn('export TOOL_HOME="/tmp"', wrapper_text)
        self.assertIn("/compat/ld-linux.so", wrapper_text)
        self.assertIn("-dynamic", wrapper_text)
        self.assertIn('exec -a "$0"', wrapper_text)
        self.assertTrue(report.changed)

    def test_promote_nested_directory(self):
        nested_bin = self.root / "pkg-1.2.3" / "bin"
        nested_bin.mkdir(parents=True)
        (nested_bin / "compiler").write_text("binary")

        report = PatchReport("test-pkg")
        context = PatchContext(
            package_name="test-pkg",
            stage="pre_link",
            install_dir=self.root,
            target_key="aarch64-linux-gnu",
            report=report,
        )

        promoted = promote_nested_directory(context, target_dir="bin")
        self.assertEqual(promoted, 1)

        top_compiler = self.root / "bin" / "compiler"
        self.assertTrue(top_compiler.is_symlink())
        self.assertEqual(top_compiler.resolve(), (nested_bin / "compiler").resolve())

    def test_resolve_soname_symlinks(self):
        glibc_lib = self.root / "glibc" / "lib"
        glibc_lib.mkdir(parents=True)
        (glibc_lib / "libedit.so.0.0.78").write_text("fake lib")

        pkg_lib = self.root / "pkg-root" / "lib"
        pkg_lib.mkdir(parents=True)

        profile = SimpleNamespace(
            is_termux=True,
            paths=SimpleNamespace(glibc_lib=glibc_lib),
        )
        report = PatchReport("test-pkg")
        context = PatchContext(
            package_name="test-pkg",
            stage="post_extract",
            install_dir=self.root,
            target_key="aarch64-linux-gnu",
            report=report,
            profile=profile,
        )

        count = resolve_soname_symlinks(context, {"libedit.so.2": "libedit.so.0.0.78"})
        self.assertEqual(count, 1)

        created_symlink = pkg_lib / "libedit.so.2"
        self.assertTrue(created_symlink.is_symlink())
        self.assertEqual(
            created_symlink.resolve(), (glibc_lib / "libedit.so.0.0.78").resolve()
        )

    def test_runtime_patch_declarative_env(self):
        from ship.api import RuntimePatch

        patch = RuntimePatch(
            binaries=("rocq",),
            prepend_path=("bin",),
            prepend_ld_library_path=("lib/custom",),
            env={"CUSTOM_HOME": "{install_dir}/share"},
        )
        real_bin = self.root / "bin" / "rocq-real"
        before_rendered = patch.render_before("rocq", real_bin, "aarch64-linux-gnu")
        self.assertIn(f'export PATH="{self.root / "bin"}:${{PATH:-}}"', before_rendered)
        self.assertIn(
            f'export LD_LIBRARY_PATH="{self.root / "lib/custom"}:${{LD_LIBRARY_PATH:-}}"',
            before_rendered,
        )
        self.assertIn(f'export CUSTOM_HOME="{self.root / "share"}"', before_rendered)

    def test_patch_subtree_binaries(self):
        from unittest.mock import MagicMock

        from ship.api import patch_subtree_binaries

        nested_dir = self.root / "lib" / "nested" / "bin"
        nested_dir.mkdir(parents=True)
        fake_bin = nested_dir / "solver"

        elf_header = bytearray(64)
        elf_header[0:4] = b"\x7fELF"
        elf_header[4] = 2  # ELFCLASS64
        elf_header[5] = 1  # ELFDATA2LSB
        elf_header[16:18] = (2).to_bytes(2, "little")  # ET_EXEC
        elf_header[18:20] = (183).to_bytes(2, "little")  # EM_AARCH64
        fake_bin.write_bytes(bytes(elf_header))

        report = PatchReport("test-pkg")
        context = PatchContext(
            package_name="test-pkg",
            stage="pre_link",
            install_dir=self.root,
            target_key="aarch64-linux-gnu",
            report=report,
        )

        mock_patcher = MagicMock()
        count = patch_subtree_binaries(context, "**/solver*", patcher_fn=mock_patcher)
        self.assertEqual(count, 1)
        self.assertTrue(mock_patcher.called)
        self.assertEqual(mock_patcher.call_args[0][0], fake_bin)

    def test_package_recipe_fluent_builder(self):
        from ship.api import PackageRecipe, on_platform

        recipe = (
            PackageRecipe("my-tool")
            .export(
                only=["my-tool", "my-sub"],
                exclude=["internal-helper"],
                aliases={"tool": "my-tool"},
            )
            .write_template(
                "config.conf",
                "install={install_dir}\ntarget={target_key}",
            )
            .symlink("config.conf", to="conf.link")
            .runtime(
                binaries=["my-tool"],
                prepend_path=["bin"],
                env={"MY_VAR": "val"},
            )
        )

        patch = recipe.to_patch()
        self.assertEqual(patch.export_policy.only, ("my-tool", "my-sub"))
        self.assertEqual(patch.export_policy.exclude, ("internal-helper",))
        self.assertEqual(patch.export_policy.aliases, {"tool": "my-tool"})
        self.assertEqual(len(patch.runtime), 1)
        self.assertEqual(patch.runtime[0].binaries, ("my-tool",))

        # Test execution of lifecycle hooks
        report = PatchReport("my-tool")
        context = PatchContext(
            package_name="my-tool",
            stage="pre_link",
            install_dir=self.root,
            target_key="x86_64-linux-gnu",
            report=report,
        )

        for hook in patch.pre_link:
            hook.handler(context)

        conf_file = self.root / "config.conf"
        self.assertTrue(conf_file.is_file())
        self.assertIn(f"install={self.root}", conf_file.read_text())
        self.assertIn("target=x86_64-linux-gnu", conf_file.read_text())

        link_file = self.root / "conf.link"
        self.assertTrue(link_file.is_symlink())

        # Test PlatformCondition
        cond_match = on_platform("linux", target="x86_64-*")
        cond_mismatch = on_platform("darwin")
        profile = SimpleNamespace(is_termux=False, os="linux")
        self.assertTrue(cond_match.check(profile, "x86_64-linux-gnu"))
        self.assertFalse(cond_mismatch.check(profile, "x86_64-linux-gnu"))
