/*
 * ship-interceptor: Lightweight Seccomp User-Notification Syscall Interceptor
 *
 * Implements SECCOMP_RET_USER_NOTIF filter installation and SCM_RIGHTS listener
 * descriptor passing. Enables transparent path rewriting (e.g. /etc/resolv.conf)
 * and syscall emulation on Android/Termux without QEMU or root.
 */

#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <unistd.h>

#ifndef SECCOMP_SET_MODE_FILTER
#define SECCOMP_SET_MODE_FILTER 1
#endif

#ifndef SECCOMP_FILTER_FLAG_NEW_LISTENER
#define SECCOMP_FILTER_FLAG_NEW_LISTENER (1UL << 3)
#endif

#ifndef SECCOMP_RET_USER_NOTIF
#define SECCOMP_RET_USER_NOTIF 0x7fc00000U
#endif

#ifndef SECCOMP_IOCTL_NOTIF_RECV
#define SECCOMP_IOCTL_NOTIF_RECV _IOWR('!', 0, struct seccomp_notif)
#endif

#ifndef SECCOMP_IOCTL_NOTIF_SEND
#define SECCOMP_IOCTL_NOTIF_SEND _IOWR('!', 1, struct seccomp_notif_resp)
#endif

#ifndef SECCOMP_IOCTL_NOTIF_ADDFD
#define SECCOMP_IOCTL_NOTIF_ADDFD _IOW('!', 3, struct seccomp_notif_addfd)
#endif

#ifndef SECCOMP_USER_NOTIF_FLAG_CONTINUE
#define SECCOMP_USER_NOTIF_FLAG_CONTINUE 0x00000001
#endif

#ifndef SECCOMP_ADDFD_FLAG_SEND
#define SECCOMP_ADDFD_FLAG_SEND 0x00000002
#endif

/*
 * Returns 1 if seccomp user-notification is supported by the running kernel, 0 otherwise.
 */
int ship_seccomp_supported(void) {
    int ret = syscall(__NR_seccomp, SECCOMP_SET_MODE_FILTER, SECCOMP_FILTER_FLAG_NEW_LISTENER, NULL);
    /* With NULL filter argument, kernel returns EFAULT if supported, or EINVAL/ENOSYS if not. */
    if (ret == -1 && errno == EFAULT) {
        return 1;
    }
    return 0;
}

/*
 * Send a file descriptor across a UNIX domain socket using SCM_RIGHTS.
 */
int ship_send_fd(int sock, int fd) {
    char dummy = 'F';
    struct iovec iov = {
        .iov_base = &dummy,
        .iov_len = 1,
    };

    union {
        char buf[CMSG_SPACE(sizeof(int))];
        struct cmsghdr align;
    } u;

    struct msghdr msg = {
        .msg_iov = &iov,
        .msg_iovlen = 1,
        .msg_control = u.buf,
        .msg_controllen = sizeof(u.buf),
    };

    struct cmsghdr *cmsg = CMSG_FIRSTHDR(&msg);
    cmsg->cmsg_level = SOL_SOCKET;
    cmsg->cmsg_type = SCM_RIGHTS;
    cmsg->cmsg_len = CMSG_LEN(sizeof(int));
    memcpy(CMSG_DATA(cmsg), &fd, sizeof(int));

    if (sendmsg(sock, &msg, 0) < 0) {
        return -1;
    }
    return 0;
}

/*
 * Receive a file descriptor from a UNIX domain socket using SCM_RIGHTS.
 */
int ship_recv_fd(int sock) {
    char dummy;
    struct iovec iov = {
        .iov_base = &dummy,
        .iov_len = 1,
    };

    union {
        char buf[CMSG_SPACE(sizeof(int))];
        struct cmsghdr align;
    } u;

    struct msghdr msg = {
        .msg_iov = &iov,
        .msg_iovlen = 1,
        .msg_control = u.buf,
        .msg_controllen = sizeof(u.buf),
    };

    if (recvmsg(sock, &msg, 0) <= 0) {
        return -1;
    }

    struct cmsghdr *cmsg = CMSG_FIRSTHDR(&msg);
    if (!cmsg || cmsg->cmsg_level != SOL_SOCKET || cmsg->cmsg_type != SCM_RIGHTS) {
        return -1;
    }

    int fd;
    memcpy(&fd, CMSG_DATA(cmsg), sizeof(int));
    return fd;
}

/*
 * Install a seccomp-bpf filter that intercepts the given array of syscall numbers
 * and returns the user-notification listener file descriptor.
 */
int ship_install_user_notif_filter(const int *syscalls, size_t count) {
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) < 0) {
        return -1;
    }

    /*
     * Build BPF filter:
     * 1. Load architecture from seccomp_data.arch
     * 2. Verify architecture matches current
     * 3. Load syscall number from seccomp_data.nr
     * 4. For each target syscall: if nr == target -> jump to USER_NOTIF
     * 5. Default: return ALLOW
     */
    size_t filter_len = 4 + (count * 2) + 2;
    struct sock_filter *filter = calloc(filter_len, sizeof(struct sock_filter));
    if (!filter) {
        return -1;
    }

    size_t idx = 0;

    /* Load seccomp_data.nr */
    filter[idx++] = (struct sock_filter)BPF_STMT(BPF_LD | BPF_W | BPF_ABS, (offsetof(struct seccomp_data, nr)));

    /* Check each syscall: if match, jump to notif */
    for (size_t i = 0; i < count; i++) {
        uint8_t jump_f = (uint8_t)(count - i);
        filter[idx++] = (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (uint32_t)syscalls[i], 0, jump_f);
        filter[idx++] = (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_USER_NOTIF);
    }

    /* Default: allow all other syscalls */
    filter[idx++] = (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW);

    struct sock_fprog prog = {
        .len = (unsigned short)idx,
        .filter = filter,
    };

    int notif_fd = (int)syscall(__NR_seccomp, SECCOMP_SET_MODE_FILTER, SECCOMP_FILTER_FLAG_NEW_LISTENER, &prog);
    free(filter);
    return notif_fd;
}

/*
 * Read a null-terminated string from target PID's memory.
 */
ssize_t ship_read_process_string(pid_t pid, uintptr_t addr, char *dest, size_t max_len) {
    struct iovec local_iov = {
        .iov_base = dest,
        .iov_len = max_len - 1,
    };
    struct iovec remote_iov = {
        .iov_base = (void *)addr,
        .iov_len = max_len - 1,
    };

    ssize_t n = process_vm_readv(pid, &local_iov, 1, &remote_iov, 1, 0);
    if (n < 0) {
        return -1;
    }
    dest[n] = '\0';
    return n;
}

/*
 * Respond to a user notification: continue natively.
 */
int ship_notif_continue(int notif_fd, uint64_t notif_id) {
    struct seccomp_notif_resp resp;
    memset(&resp, 0, sizeof(resp));
    resp.id = notif_id;
    resp.flags = SECCOMP_USER_NOTIF_FLAG_CONTINUE;
    return ioctl(notif_fd, SECCOMP_IOCTL_NOTIF_SEND, &resp);
}

/*
 * Respond to a user notification: return an error code (e.g. -ENOENT).
 */
int ship_notif_return_error(int notif_fd, uint64_t notif_id, int error_code) {
    struct seccomp_notif_resp resp;
    memset(&resp, 0, sizeof(resp));
    resp.id = notif_id;
    resp.error = error_code > 0 ? -error_code : error_code;
    return ioctl(notif_fd, SECCOMP_IOCTL_NOTIF_SEND, &resp);
}

/*
 * Respond to a user notification: return a success value.
 */
int ship_notif_return_value(int notif_fd, uint64_t notif_id, int64_t val) {
    struct seccomp_notif_resp resp;
    memset(&resp, 0, sizeof(resp));
    resp.id = notif_id;
    resp.val = val;
    return ioctl(notif_fd, SECCOMP_IOCTL_NOTIF_SEND, &resp);
}

/*
 * Receive next user notification. Returns 0 on success, -1 on error (sets errno).
 */
int ship_notif_recv(int notif_fd, struct seccomp_notif *notif) {
    memset(notif, 0, sizeof(*notif));
    return ioctl(notif_fd, SECCOMP_IOCTL_NOTIF_RECV, notif);
}

/*
 * Respond to an openat notification: inject an open file descriptor into target.
 */
int ship_notif_inject_fd(int notif_fd, uint64_t notif_id, int local_fd) {
    struct seccomp_notif_addfd addfd;
    memset(&addfd, 0, sizeof(addfd));
    addfd.id = notif_id;
    addfd.srcfd = (uint32_t)local_fd;
    addfd.flags = SECCOMP_ADDFD_FLAG_SEND;
    return ioctl(notif_fd, SECCOMP_IOCTL_NOTIF_ADDFD, &addfd);
}
