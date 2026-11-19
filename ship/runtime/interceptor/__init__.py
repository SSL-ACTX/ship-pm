"""Syscall Interceptor Engine — transparent path redirection and syscall virtualization.

Provides a seccomp user-notification based supervisor that intercepts filesystem
and network syscalls (e.g. /etc/resolv.conf, /etc/hosts) and transparently
satisfies them with Termux/host resources without requiring root, PRoot, or QEMU.
"""

from __future__ import annotations

import ctypes
import errno
import os
import shutil
import socket
import subprocess
import threading
from collections.abc import Sequence
from pathlib import Path

from ship.core.settings import settings

# ARM64 / Linux standard syscall numbers
SYS_OPENAT = 56
SYS_OPENAT2 = 437


class SeccompData(ctypes.Structure):
    _fields_ = [
        ("nr", ctypes.c_int),
        ("arch", ctypes.c_uint32),
        ("instruction_pointer", ctypes.c_uint64),
        ("args", ctypes.c_uint64 * 6),
    ]


class SeccompNotif(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_uint64),
        ("pid", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("data", SeccompData),
    ]


class SyscallInterceptor:
    """Manages compiled C core interceptor and supervises child process syscalls."""

    _lib: ctypes.CDLL | None = None
    _tried_load: bool = False

    @classmethod
    def get_lib_path(cls) -> Path:
        """Search for compiled libship_interceptor.so."""
        # 1. In settings.ship_root / lib
        p1 = settings.ship_root / "lib" / "libship_interceptor.so"
        if p1.is_file():
            return p1
        # 2. In ship/runtime/interceptor
        p2 = Path(__file__).parent / "libship_interceptor.so"
        if p2.is_file():
            return p2
        # 3. In ship lib dir
        p3 = (
            settings.ship_root
            / "lib"
            / "ship"
            / "runtime"
            / "interceptor"
            / "libship_interceptor.so"
        )
        if p3.is_file():
            return p3
        return p1

    @classmethod
    def load_library(cls) -> ctypes.CDLL | None:
        if cls._tried_load:
            return cls._lib
        cls._tried_load = True

        lib_path = cls.get_lib_path()
        if not lib_path.is_file():
            # Attempt opportunistic on-demand compilation if clang/gcc is present
            cls.compile_core()

        if lib_path.is_file():
            try:
                cls._lib = ctypes.CDLL(str(lib_path))
                cls._setup_signatures(cls._lib)
            except OSError:
                cls._lib = None
        return cls._lib

    @classmethod
    def _setup_signatures(cls, lib: ctypes.CDLL) -> None:
        lib.ship_seccomp_supported.restype = ctypes.c_int
        lib.ship_seccomp_supported.argtypes = []

        lib.ship_send_fd.restype = ctypes.c_int
        lib.ship_send_fd.argtypes = [ctypes.c_int, ctypes.c_int]

        lib.ship_recv_fd.restype = ctypes.c_int
        lib.ship_recv_fd.argtypes = [ctypes.c_int]

        lib.ship_install_user_notif_filter.restype = ctypes.c_int
        lib.ship_install_user_notif_filter.argtypes = [
            ctypes.POINTER(ctypes.c_int),
            ctypes.c_size_t,
        ]

        lib.ship_read_process_string.restype = ctypes.c_ssize_t
        lib.ship_read_process_string.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint64,
            ctypes.c_char_p,
            ctypes.c_size_t,
        ]

        lib.ship_notif_recv.restype = ctypes.c_int
        lib.ship_notif_recv.argtypes = [ctypes.c_int, ctypes.POINTER(SeccompNotif)]

        lib.ship_notif_continue.restype = ctypes.c_int
        lib.ship_notif_continue.argtypes = [ctypes.c_int, ctypes.c_uint64]

        lib.ship_notif_return_error.restype = ctypes.c_int
        lib.ship_notif_return_error.argtypes = [
            ctypes.c_int,
            ctypes.c_uint64,
            ctypes.c_int,
        ]

        lib.ship_notif_return_value.restype = ctypes.c_int
        lib.ship_notif_return_value.argtypes = [
            ctypes.c_int,
            ctypes.c_uint64,
            ctypes.c_int64,
        ]

        lib.ship_notif_inject_fd.restype = ctypes.c_int
        lib.ship_notif_inject_fd.argtypes = [
            ctypes.c_int,
            ctypes.c_uint64,
            ctypes.c_int,
        ]

    @classmethod
    def is_available(cls) -> bool:
        """Check if native seccomp interceptor is compiled and supported by the kernel."""
        lib = cls.load_library()
        if not lib:
            return False
        try:
            return bool(lib.ship_seccomp_supported())
        except OSError:
            return False

    @classmethod
    def compile_core(cls, out_path: Path | None = None) -> bool:
        """Compile the native C interceptor core if clang or gcc is available."""
        cc = shutil.which("clang") or shutil.which("gcc")
        if not cc:
            return False

        src_file = Path(__file__).parent / "interceptor.c"
        if not src_file.is_file():
            return False

        target = out_path or (settings.ship_root / "lib" / "libship_interceptor.so")
        target.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            cc,
            "-O2",
            "-shared",
            "-fPIC",
            str(src_file),
            "-o",
            str(target),
        ]
        res = subprocess.run(cmd, capture_output=True, check=False)
        return res.returncode == 0 and target.is_file()

    @classmethod
    def run_with_redirection(
        cls,
        argv: Sequence[str],
        *,
        path_map: dict[str, str | Path],
        env: dict[str, str] | None = None,
        cwd: Path | str | None = None,
    ) -> int:
        """Execute a command while redirecting target filesystem paths using seccomp user notification.

        Example:
            SyscallInterceptor.run_with_redirection(
                ["juliaup", "update"],
                path_map={"/etc/resolv.conf": "/data/data/com.termux/files/usr/etc/resolv.conf"}
            )
        """
        lib = cls.load_library()
        if not lib or not cls.is_available():
            # Fall back to direct execution
            return subprocess.run(argv, env=env, cwd=cwd, check=False).returncode

        # Normalize path_map
        normalized_map: dict[str, str] = {k: str(v) for k, v in path_map.items()}

        # Create UNIX socket pair for passing listener FD
        parent_sock, child_sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        parent_sock_fd = parent_sock.fileno()
        child_sock_fd = child_sock.fileno()

        target_syscalls = (ctypes.c_int * 2)(SYS_OPENAT, SYS_OPENAT2)

        def _child_preexec() -> None:
            # Inside child: close parent socket
            parent_sock.close()

            # Install seccomp filter
            notif_fd = lib.ship_install_user_notif_filter(target_syscalls, 2)
            if notif_fd >= 0:
                lib.ship_send_fd(child_sock_fd, notif_fd)
                os.close(notif_fd)
            child_sock.close()

        proc = subprocess.Popen(
            argv,
            env=env,
            cwd=cwd,
            preexec_fn=_child_preexec,  # noqa: PLW1509
            pass_fds=(child_sock_fd,),
        )
        child_sock.close()

        # Receive listener FD from child
        listener_fd = lib.ship_recv_fd(parent_sock_fd)
        parent_sock.close()

        if listener_fd < 0:
            # Filter installation failed; let child run natively
            return proc.wait()

        # Supervisor loop in worker thread
        stop_event = threading.Event()

        def _supervisor_worker() -> None:
            import fcntl

            # Set non-blocking on listener_fd so we can check child status
            flags = fcntl.fcntl(listener_fd, fcntl.F_GETFL)
            fcntl.fcntl(listener_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            buf = ctypes.create_string_buffer(4096)
            notif = SeccompNotif()

            while not stop_event.is_set():
                if proc.poll() is not None:
                    break

                ret = lib.ship_notif_recv(listener_fd, ctypes.byref(notif))
                if ret < 0:
                    err = ctypes.get_errno()
                    if err in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EINTR):
                        stop_event.wait(0.005)
                        continue
                    break

                # Inspect syscall arguments
                # args[1] for openat is filename pointer
                target_pid = notif.pid
                filename_ptr = notif.data.args[1]

                read_len = lib.ship_read_process_string(
                    target_pid, filename_ptr, buf, 4096
                )
                if read_len > 0:
                    req_path = buf.value.decode("utf-8", errors="replace")
                    if req_path in normalized_map:
                        replacement = normalized_map[req_path]
                        try:
                            # Open replacement locally and inject into child
                            local_fd = os.open(replacement, os.O_RDONLY | os.O_CLOEXEC)
                            lib.ship_notif_inject_fd(listener_fd, notif.id, local_fd)
                            os.close(local_fd)
                            continue
                        except OSError:
                            pass

                # Default: continue natively
                lib.ship_notif_continue(listener_fd, notif.id)

            os.close(listener_fd)

        supervisor_thread = threading.Thread(target=_supervisor_worker, daemon=True)
        supervisor_thread.start()

        returncode = proc.wait()
        stop_event.set()
        supervisor_thread.join(timeout=0.2)
        return returncode
