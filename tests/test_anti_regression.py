"""Anti-regression test suite for ship package manager."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ship.linker import clean_package_links
from ship.patchers import PATCHERS
from ship.patchers.api import (
    PackagePatch,
    PatchContext,
    PatchReport,
)
from ship.patchers.qemu import QemuRunnerPatcher
from ship.patchers.termux import TermuxPatcher
from ship.patches import get_package_patch
from ship.store import remove_package


class TestPatcherOrderRegression(unittest.TestCase):
    """Ensure emulation runners take precedence over native host wrappers on foreign binaries."""

    def test_patcher_order_qemu_before_termux(self):
        """Regression test: QemuRunnerPatcher must precede TermuxPatcher.

        Otherwise, foreign ELFs (e.g. x86_64 on aarch64) get replaced by a Termux shell
        launcher first, preventing QEMU emulation from wrapping the real binary and causing
        'cannot execute binary file: Exec format error'.
        """
        patcher_types = [type(p) for p in PATCHERS]
        self.assertIn(QemuRunnerPatcher, patcher_types)
        self.assertIn(TermuxPatcher, patcher_types)
        qemu_idx = patcher_types.index(QemuRunnerPatcher)
        termux_idx = patcher_types.index(TermuxPatcher)
        self.assertLess(
            qemu_idx,
            termux_idx,
            "QemuRunnerPatcher must be evaluated before TermuxPatcher in PATCHERS",
        )


class TestFStarSolverPatchRegression(unittest.TestCase):
    """Ensure F* package patch locates and patches bundled SMT solvers."""

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.install_dir = Path(self.test_dir.name)

    def tearDown(self):
        self.test_dir.cleanup()

    def test_fstar_patch_definition(self):
        fstar_patch = get_package_patch("fstar")
        self.assertIsNotNone(fstar_patch, "fstar PackagePatch must be registered")
        self.assertTrue(len(fstar_patch.pre_link) > 0, "fstar must have pre_link hooks")
        self.assertEqual(
            fstar_patch.export_policy.only,
            ("fstar", "fstar.exe", "krml"),
            "fstar export policy should only expose fstar, fstar.exe, krml",
        )

    @patch("ship.patches.fstar.apply_patchers")
    def test_fstar_patches_bundled_z3_solvers(self, mock_apply_patchers):
        """Regression test: bundled z3 under lib/fstar/z3-*/bin/z3 must receive apply_patchers."""
        # Create mock bundled solver directory layout matching F* releases
        z3_dir = self.install_dir / "lib" / "fstar" / "z3-5.3.0" / "bin"
        z3_dir.mkdir(parents=True, exist_ok=True)
        fake_z3 = z3_dir / "z3"

        # Minimal valid 64-bit ELF header
        # Bytes 0-3: \x7fELF, Byte 4: 2 (64-bit), Byte 5: 1 (LSB), Byte 18-19: 183 (aarch64)
        elf_header = bytearray(64)
        elf_header[0:4] = b"\x7fELF"
        elf_header[4] = 2  # ELFCLASS64
        elf_header[5] = 1  # ELFDATA2LSB
        elf_header[16:18] = (2).to_bytes(2, "little")  # ET_EXEC
        elf_header[18:20] = (183).to_bytes(2, "little")  # EM_AARCH64
        fake_z3.write_bytes(bytes(elf_header))

        fstar_patch = get_package_patch("fstar")
        report = PatchReport("fstar")
        context = PatchContext(
            package_name="fstar",
            stage="pre_link",
            install_dir=self.install_dir,
            target_key="aarch64-linux-gnu",
            report=report,
        )

        for hook in fstar_patch.pre_link:
            hook.handler(context)

        self.assertTrue(
            mock_apply_patchers.called,
            "apply_patchers must be invoked on bundled z3 solver",
        )
        called_path = mock_apply_patchers.call_args[0][0]
        self.assertEqual(called_path, fake_z3)


class TestShipRemoveAuditRegression(unittest.TestCase):
    """Ensure ship rm properly audits and unlinks all symlinks and cleans store."""

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.test_dir.name)
        self.bin_dir = self.root / "bin"
        self.internal_dir = self.root / "internal"
        self.store_dir = self.root / "store" / "pkg@1.0.0"

        self.bin_dir.mkdir(parents=True, exist_ok=True)
        self.internal_dir.mkdir(parents=True, exist_ok=True)
        self.store_dir.mkdir(parents=True, exist_ok=True)

        (self.store_dir / "mybin").write_text("bin")

        self.symlink1 = self.bin_dir / "mybin"
        self.symlink1.symlink_to(self.store_dir / "mybin")

        self.symlink2 = self.internal_dir / "mybin"
        self.symlink2.symlink_to(self.store_dir / "mybin")

    def tearDown(self):
        self.test_dir.cleanup()

    def test_clean_package_links_returns_unlinked_paths(self):
        fake_state = {
            "installed": {
                "pkg": {
                    "symlinks": [str(self.symlink1)],
                }
            }
        }
        with (
            patch("ship.linker.load_state", return_value=fake_state),
            patch("ship.linker.SHIP_BIN_DIR", self.bin_dir),
            patch("ship.linker.SHIP_INTERNAL_BIN", self.internal_dir),
        ):
            unlinked = clean_package_links("pkg", verbose=True)
            self.assertIn(self.symlink1, unlinked)
            self.assertIn(self.symlink2, unlinked)
            self.assertFalse(self.symlink1.exists())
            self.assertFalse(self.symlink2.exists())

    def test_remove_package_cleans_and_audits(self):
        fake_state = {
            "installed": {
                "pkg": {
                    "version": "1.0.0",
                    "install_dir": str(self.store_dir),
                    "symlinks": [str(self.symlink1)],
                }
            },
            "history": {"pkg": []},
        }

        with (
            patch("ship.store.load_state", return_value=fake_state),
            patch("ship.store.save_state") as mock_save,
            patch("ship.linker.SHIP_BIN_DIR", self.bin_dir),
            patch("ship.linker.SHIP_INTERNAL_BIN", self.internal_dir),
            patch("ship.store.status") as mock_status,
        ):
            remove_package("pkg")

            self.assertNotIn("pkg", fake_state["installed"])
            self.assertFalse(self.store_dir.exists(), "Store dir should be cleaned")
            self.assertTrue(mock_save.called, "State should be saved")

            status_actions = [call[0][0] for call in mock_status.call_args_list]
            self.assertIn("Cleaned", status_actions)
            self.assertIn("Removed", status_actions)


class TestPatcherApiStructureRegression(unittest.TestCase):
    """Ensure patchers API is formally exposed under ship.patchers.api and backwards-compatible."""

    def test_import_from_patchers_api(self):
        from ship.patchers.api import (
            inspect_elf,
        )

        self.assertTrue(callable(inspect_elf))
        self.assertTrue(issubclass(PackagePatch, object))

    def test_compatibility_import_from_patches_api(self):
        from ship.patches.api import (
            inspect_elf,
        )

        self.assertTrue(callable(inspect_elf))


if __name__ == "__main__":
    unittest.main()
