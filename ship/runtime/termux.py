"""Termux platform compatibility helpers and runtime launcher patcher."""

import platform
import shlex
import shutil
import socket
import subprocess
from pathlib import Path

from ship.api import (
    PatchReport,
    inspect_elf,
    read_elf_rpath,
    set_elf_interpreter,
    set_elf_rpath,
)
from ship.core.profile import get_active_profile
from ship.runtime.base import BinaryPatcher, LauncherTemplate, install_launcher
from ship.ui import warn


def termux_glibc_prefix() -> Path:
    return get_active_profile().paths.glibc_prefix


def ensure_termux_trampoline_loader(
    architecture: str | None = None,
    report: PatchReport | None = None,
) -> Path | None:
    """Ensure the freestanding PT_INTERP trampoline is compiled and available."""
    arch = (architecture or platform.machine()).lower()
    arch = {"arm64": "aarch64", "amd64": "x86_64", "x64": "x86_64"}.get(arch, arch)
    if arch != "aarch64":
        return None

    profile = get_active_profile()
    target_dir = profile.paths.prefix / "share" / "ship" / "runtime"
    trampoline_bin = target_dir / f"ld-termux-{arch}.so.1"
    if trampoline_bin.is_file():
        return trampoline_bin

    local_target = (
        profile.home
        / ".local"
        / "share"
        / "ship"
        / "runtime"
        / f"ld-termux-{arch}.so.1"
    )
    if local_target.is_file():
        return local_target

    c_source = Path(__file__).parent / "c" / f"ld-termux-{arch}.c"
    if not c_source.is_file():
        return None

    clang = shutil.which("clang")
    if not clang:
        return None

    out_path = trampoline_bin
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        out_path = local_target
        out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        clang,
        "-nostdlib",
        "-fPIC",
        "-shared",
        "-fno-builtin",
        "-Wl,-e,_start",
        "-Wl,-Bsymbolic",
        "-Os",
        "-o",
        str(out_path),
        str(c_source),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, check=False)
        if res.returncode == 0 and out_path.is_file():
            if report is not None:
                report.add(out_path, "compile freestanding PT_INTERP trampoline", arch)
            return out_path
    except OSError:
        pass

    return None


def ensure_termux_glibc_shim(report: PatchReport | None = None) -> Path | None:
    """Ensure the Termux glibc path virtualizer and redirector shim is compiled."""
    profile = get_active_profile()
    if not profile.is_termux:
        return None

    target_dir = profile.paths.prefix / "share" / "ship" / "runtime"
    shim_bin = target_dir / "libtermux_glibc_shim.so"
    if shim_bin.is_file():
        return shim_bin

    local_target = (
        profile.home
        / ".local"
        / "share"
        / "ship"
        / "runtime"
        / "libtermux_glibc_shim.so"
    )
    if local_target.is_file():
        return local_target

    c_source = Path(__file__).parent / "c" / "termux-glibc-shim.c"
    if not c_source.is_file():
        return None

    clang = shutil.which("clang")
    if not clang:
        return None

    glibc_lib = profile.paths.glibc_prefix / "lib" / "libc.so.6"
    glibc_inc = profile.paths.glibc_prefix / "include"
    if not glibc_lib.is_file():
        return None

    out_path = shim_bin
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        out_path = local_target
        out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        clang,
        "-shared",
        "-fPIC",
        "-O2",
        "-nostdlib",
        f"-I{glibc_inc}",
        str(c_source),
        str(glibc_lib),
        "-o",
        str(out_path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, check=False)
        if res.returncode == 0 and out_path.is_file():
            if report is not None:
                report.add(out_path, "compile glibc root virtualizer shim", "termux")
            return out_path
    except OSError:
        pass

    return None


def termux_trampoline_loader_path(architecture: str | None = None) -> Path | None:
    """Return the path to the freestanding PT_INTERP trampoline for Termux glibc if present."""
    return ensure_termux_trampoline_loader(architecture=architecture)


def termux_glibc_loader_path(architecture: str | None = None) -> Path | None:
    arch = (architecture or platform.machine()).lower()
    arch = {"arm64": "aarch64", "amd64": "x86_64", "x64": "x86_64"}.get(arch, arch)
    loaders = {
        "aarch64": "ld-linux-aarch64.so.1",
        "x86_64": "ld-linux-x86-64.so.2",
        "arm": "ld-linux-armhf.so.3",
        "armv7l": "ld-linux-armhf.so.3",
        "armv8l": "ld-linux-armhf.so.3",
        "i386": "ld-linux.so.2",
        "i486": "ld-linux.so.2",
        "i586": "ld-linux.so.2",
        "i686": "ld-linux.so.2",
        "riscv64": "ld-linux-riscv64-lp64d.so.1",
    }
    name = loaders.get(arch)
    if name is None and arch.startswith("arm"):
        name = "ld-linux-armhf.so.3"
    return termux_glibc_prefix() / "lib" / name if name else None


def get_termux_ssl_cert_file() -> str:
    for candidate in get_active_profile().paths.cert_candidates:
        if candidate.is_file():
            return str(candidate)
    return ""


def is_dns_server_reachable(ip: str, port: int = 53, timeout: float = 0.3) -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        s.connect((ip, port))
        s.close()
        return True
    except OSError:
        return False


def ensure_termux_resolv_conf(report: PatchReport | None = None) -> None:
    resolv_file = get_active_profile().paths.resolv_conf
    if resolv_file is None:
        return
    raw_candidates: list[str] = []
    anycast_defaults = ["1.1.1.1", "8.8.8.8", "1.0.0.1", "8.8.4.4"]

    for prop in ("net.dns1", "net.dns2"):
        try:
            val = subprocess.run(
                ["getprop", prop],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
            if val and not val.startswith("127.") and val not in raw_candidates:
                raw_candidates.append(val)
        except OSError:
            pass

    for ac in anycast_defaults:
        if ac not in raw_candidates:
            raw_candidates.append(ac)

    active_servers: list[str] = []
    for ip in raw_candidates:
        if is_dns_server_reachable(ip):
            active_servers.append(ip)
        if len(active_servers) >= 3:
            break

    if not active_servers:
        active_servers = ["1.1.1.1", "8.8.8.8"]

    content = "# Generated by ship for Termux DNS stability\noptions timeout:1 attempts:2 rotate\n"
    for s in active_servers:
        content += f"nameserver {s}\n"

    try:
        resolv_file.parent.mkdir(parents=True, exist_ok=True)
        if (
            not resolv_file.is_file()
            or resolv_file.read_text(encoding="utf-8") != content
        ):
            resolv_file.write_text(content, encoding="utf-8")
            if report is not None:
                report.add(resolv_file, "write", "Termux resolver configuration")
    except OSError:
        pass


class TermuxPatcher(BinaryPatcher):
    name = "termux-runtime"

    @staticmethod
    def is_elf(file_path: Path) -> bool:
        try:
            return inspect_elf(file_path) is not None
        except OSError:
            return False

    def should_patch(self, binary_path: Path, target_key: str) -> bool:
        return get_active_profile().is_termux and self.is_elf(binary_path)

    def patch(
        self,
        binary_path: Path,
        target_key: str,
        report: PatchReport | None = None,
    ) -> Path:
        glibc_pfx = termux_glibc_prefix()
        host_arch = platform.machine().lower()
        host_arch = {"arm64": "aarch64", "amd64": "x86_64", "x64": "x86_64"}.get(
            host_arch, host_arch
        )

        target_arch = target_key.split("-", 1)[0].lower()
        target_arch = {
            "arm64": "aarch64",
            "amd64": "x86_64",
            "i686": "i386",
            "armv7": "arm",
            "armv6": "arm",
        }.get(target_arch, target_arch)

        elf_info = inspect_elf(binary_path)
        is_glibc = bool(elf_info and elf_info.abi == "glibc")
        bin_arch = elf_info.architecture if elf_info else target_arch
        is_foreign_arch = (target_arch != host_arch) or (bin_arch != host_arch)

        loader_path = ensure_termux_trampoline_loader(
            host_arch, report=report
        ) or termux_glibc_loader_path(host_arch)

        # Glibc ELF binary patching
        if is_glibc and not is_foreign_arch and loader_path and loader_path.is_file():
            patchelf_bin = shutil.which("patchelf")
            if patchelf_bin:
                try:
                    rpath = str(glibc_pfx / "lib")
                    existing_rpath = (
                        read_elf_rpath(binary_path, patchelf=patchelf_bin) or ""
                    )
                    rpath_parts = [rpath]
                    for part in existing_rpath.split(":"):
                        if part and part not in rpath_parts:
                            rpath_parts.append(part)
                    effective_rpath = ":".join(rpath_parts)
                    changed = set_elf_interpreter(
                        binary_path, loader_path, patchelf=patchelf_bin
                    )
                    changed |= set_elf_rpath(
                        binary_path, effective_rpath, patchelf=patchelf_bin
                    )
                    shim_path = ensure_termux_glibc_shim(report=report)
                    if shim_path and shim_path.is_file():
                        subprocess.run(
                            [
                                patchelf_bin,
                                "--add-needed",
                                str(shim_path),
                                str(binary_path),
                            ],
                            check=False,
                            capture_output=True,
                        )
                    if changed and report is not None:
                        report.add(
                            binary_path,
                            "configure glibc runtime",
                            "interpreter and RPATH",
                        )
                except subprocess.SubprocessError as e:
                    warn(f"patchelf failed for {binary_path.name}: {e}")

        ensure_termux_resolv_conf(report)

        # Musl static binary patch: relocate /etc/resolv.conf and /etc/hosts directly
        if not is_glibc and not is_foreign_arch:
            from ship.runtime.musl import patch_musl_static_paths

            patch_musl_static_paths(binary_path, report=report)

        # Runtime launcher wrapper: only needed if package requests custom hooks/commands
        cert_file = get_termux_ssl_cert_file()
        real_binary = binary_path.parent / f"{binary_path.name}-real"
        if not real_binary.exists():
            from ship.patches import get_runtime_patch

            pre_exec_hook, post_exec_hook, package_exec_cmd = get_runtime_patch(
                binary_path.name, real_binary, target_key
            )

            # If the binary has the trampoline loader and needs no custom hooks, it runs purely as a native ELF!
            has_trampoline = (
                loader_path and loader_path == termux_trampoline_loader_path(host_arch)
            )
            has_custom_hooks = bool(package_exec_cmd or pre_exec_hook or post_exec_hook)

            if has_custom_hooks or not has_trampoline:
                environment: list[str] = []
                if cert_file:
                    cert_dir = str(Path(cert_file).parent)
                    environment = [
                        f"export SSL_CERT_FILE={shlex.quote(cert_file)}",
                        f"export SSL_CERT_DIR={shlex.quote(cert_dir)}",
                    ]

                bash_bin = str(get_active_profile().paths.bash)

                # Package runtime command ALWAYS takes precedence
                if package_exec_cmd:
                    exec_cmd = package_exec_cmd
                elif post_exec_hook:
                    exec_cmd = f'{shlex.quote(str(real_binary))} "$@"'
                else:
                    exec_cmd = f'exec -a "$0" {shlex.quote(str(real_binary))} "$@"'

                install_launcher(
                    binary_path,
                    LauncherTemplate(
                        interpreter=bash_bin,
                        comment="Termux",
                        command=exec_cmd,
                        environment=environment,
                        before=pre_exec_hook,
                        after=post_exec_hook,
                    ),
                    report=report,
                )

        return binary_path
