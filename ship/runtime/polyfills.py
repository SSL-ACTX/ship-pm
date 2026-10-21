"""Platform polyfill library for Bionic libc, Android shared memory, and non-standard POSIX."""

from __future__ import annotations

from pathlib import Path

from ship.api.code import SourcePatcher
from ship.core.settings import settings


class PolyfillEngine:
    """Manages zero-dependency platform compatibility shims."""

    @staticmethod
    def apply_bionic_compat(
        root_dir: Path, patcher: SourcePatcher | None = None
    ) -> int:
        """Inject guards for getentropy, getlogin_r, and pthread_cancel."""
        p = patcher or SourcePatcher(root_dir)
        count = 0

        # pthread_cancel stub
        pthread_cancel_guard = (
            "#if defined(__ANDROID__)\n"
            "#  ifndef pthread_cancel\n"
            "#    define pthread_cancel(t) 0\n"
            "#  endif\n"
            "#endif"
        )
        for h in p.find_files("**/*.h") + p.find_files("**/*.c"):
            if "pthread.h" in h.read_text(
                encoding="utf-8", errors="ignore"
            ) and p.inject_c_guard(h, "pthread.h", pthread_cancel_guard):
                count += 1

        # getentropy / getlogin_r guards for Android API < 28
        entropy_guard = (
            "#if defined(__ANDROID__) && __ANDROID_API__ < 28\n"
            "static inline int _ship_getentropy(void *buf, size_t buflen) {\n"
            '    int fd = open("/dev/urandom", 0);\n'
            "    if (fd < 0) return -1;\n"
            "    size_t r = read(fd, buf, buflen);\n"
            "    close(fd);\n"
            "    return (r == buflen) ? 0 : -1;\n"
            "}\n"
            "#define getentropy _ship_getentropy\n"
            "#endif"
        )
        for c in p.find_files("**/*.c"):
            txt = c.read_text(encoding="utf-8", errors="ignore")
            if (
                "getentropy" in txt
                and "sys/random.h" in txt
                and p.inject_c_guard(c, "sys/random.h", entropy_guard)
            ):
                count += 1

        return count

    @staticmethod
    def apply_android_shmem(
        root_dir: Path, patcher: SourcePatcher | None = None
    ) -> int:
        """Inject -landroid-shmem into build scripts, Makefiles, and configure scripts."""
        p = patcher or SourcePatcher(root_dir)
        count = 0

        # Makefile configs
        for mf in p.find_files("**/Makefile*") + p.find_files("**/configure*"):
            c = p.replace_regex(
                str(mf.relative_to(root_dir)),
                r"(-lpthread|-lc|-lm)\b",
                r"\1 -landroid-shmem",
            )
            count += c
        return count

    @staticmethod
    def apply_posix_shell(root_dir: Path, patcher: SourcePatcher | None = None) -> int:
        """Sanitize non-POSIX redirections in shell scripts."""
        p = patcher or SourcePatcher(root_dir)
        return (
            p.clean_posix_redirections("**/*.sh")
            + p.clean_posix_redirections("**/configure")
            + p.clean_posix_redirections("**/configure.ac")
        )

    @staticmethod
    def ensure_bwrap_shim() -> Path:
        """Installs a sandbox/namespace bypass shim for bwrap (Bubblewrap) in ship internal bin."""
        shim_path = settings.ship_internal_bin / "bwrap"
        if shim_path.exists() and not shim_path.is_symlink():
            return shim_path

        shim_content = (
            "#!/bin/sh\n"
            "# Ship v2 Bubblewrap Namespace Bypass Shim\n"
            "# Bypasses CLONE_NEWUSER restrictions on unprivileged/Android kernels\n"
            "while [ $# -gt 0 ]; do\n"
            '  case "$1" in\n'
            "    --) shift; break ;;\n"
            "    --ro-bind|--bind|--dev-bind) shift 2 ;;\n"
            "    --proc|--dev|--tmpfs|--dir) shift ;;\n"
            "    --setenv) shift 2 ;;\n"
            "    --unsetenv) shift ;;\n"
            '    --chdir) cd "$2" 2>/dev/null; shift 2 ;;\n'
            "    --die-with-parent|--unshare-all|--new-session) shift ;;\n"
            "    -*) shift ;;\n"
            "    *) break ;;\n"
            "  esac\n"
            "done\n"
            "if [ $# -eq 0 ]; then\n"
            "  exit 0\n"
            "fi\n"
            'exec "$@"\n'
        )
        shim_path.parent.mkdir(parents=True, exist_ok=True)
        shim_path.write_text(shim_content, encoding="utf-8")
        shim_path.chmod(0o755)
        return shim_path
