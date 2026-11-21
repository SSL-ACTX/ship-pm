// termux-glibc-shim.c — Lightweight dynamic preload/needed shim for Termux glibc
// Virtualizes non-readable Android / and /data paths and redirects /usr lookups to Termux glibc.

#define _GNU_SOURCE
#include <dirent.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#define GLIBC_PREFIX "/data/data/com.termux/files/usr/glibc"

static DIR *(*libc_opendir)(const char *name);
static struct dirent *(*libc_readdir)(DIR *dirp);
static int (*libc_closedir)(DIR *dirp);
static int (*libc_stat)(const char *pathname, struct stat *statbuf);
static int (*libc_lstat)(const char *pathname, struct stat *statbuf);
static int (*libc_access)(const char *pathname, int mode);
static int (*libc_open)(const char *pathname, int flags, ...);
static int (*libc_openat)(int dirfd, const char *pathname, int flags, ...);
static FILE *(*libc_fopen)(const char *pathname, const char *mode);
static char *(*libc_realpath)(const char *path, char *resolved_path);

struct fake_dir {
    int kind; // 1 = /, 2 = /data, 3 = /data/data
    int idx;
};

static struct fake_dir fake_dirs[16];
static int fake_dir_cnt = 0;

static struct dirent ent_data = {
    .d_ino = 1,
    .d_off = 0,
    .d_reclen = sizeof(struct dirent),
    .d_type = DT_DIR,
    .d_name = "data"
};

static struct dirent ent_termux = {
    .d_ino = 2,
    .d_off = 0,
    .d_reclen = sizeof(struct dirent),
    .d_type = DT_DIR,
    .d_name = "com.termux"
};

static void resolve_symbols(void) {
    if (!libc_opendir) {
        void *h = dlopen("/data/data/com.termux/files/usr/glibc/lib/libc.so.6", RTLD_LAZY | RTLD_GLOBAL);
        if (h) {
            libc_opendir = (DIR *(*)(const char *))dlsym(h, "opendir");
            libc_readdir = (struct dirent *(*)(DIR *))dlsym(h, "readdir");
            libc_closedir = (int (*)(DIR *))dlsym(h, "closedir");
            libc_stat = (int (*)(const char *, struct stat *))dlsym(h, "stat");
            libc_lstat = (int (*)(const char *, struct stat *))dlsym(h, "lstat");
            libc_access = (int (*)(const char *, int))dlsym(h, "access");
            libc_open = (int (*)(const char *, int, ...))dlsym(h, "open");
            libc_openat = (int (*)(int, const char *, int, ...))dlsym(h, "openat");
            libc_fopen = (FILE *(*)(const char *, const char *))dlsym(h, "fopen");
            libc_realpath = (char *(*)(const char *, char *))dlsym(h, "realpath");
        }
    }
}

static const char *redirect_path(const char *pathname, char *buf, size_t buflen) {
    if (!pathname) return pathname;
    if (strncmp(pathname, "/usr/", 5) == 0) {
        size_t pfxlen = strlen(GLIBC_PREFIX);
        size_t sublen = strlen(pathname);
        if (pfxlen + sublen + 1 < buflen) {
            memcpy(buf, GLIBC_PREFIX, pfxlen);
            memcpy(buf + pfxlen, pathname, sublen + 1);
            return buf;
        }
    }
    return pathname;
}

static int is_dotdot_root(const char *p) {
    if (!p) return 0;
    size_t len = strlen(p);
    if (len >= 3 && p[len - 1] == '.' && p[len - 2] == '.' && p[len - 3] == '/') {
        return 1;
    }
    return 0;
}

DIR *opendir(const char *name) {
    resolve_symbols();
    int kind = 0;
    if (name) {
        if (strcmp(name, "/") == 0 || is_dotdot_root(name)) kind = 1;
        else if (strcmp(name, "/data") == 0 || strcmp(name, "/data/") == 0) kind = 2;
        else if (strcmp(name, "/data/data") == 0 || strcmp(name, "/data/data/") == 0) kind = 3;
    }
    if (kind != 0 && fake_dir_cnt < 16) {
        struct fake_dir *d = &fake_dirs[fake_dir_cnt++];
        d->kind = kind;
        d->idx = 0;
        return (DIR *)d;
    }

    char buf[1024];
    const char *p = redirect_path(name, buf, sizeof(buf));
    if (libc_opendir) return libc_opendir(p);
    errno = ENOENT;
    return NULL;
}

struct dirent *readdir(DIR *dirp) {
    for (int i = 0; i < fake_dir_cnt; i++) {
        if (dirp == (DIR *)&fake_dirs[i]) {
            struct fake_dir *d = &fake_dirs[i];
            if (d->kind == 1) {
                if (d->idx++ == 0) return &ent_data;
                return NULL;
            } else if (d->kind == 2) {
                if (d->idx++ == 0) return &ent_data;
                return NULL;
            } else if (d->kind == 3) {
                if (d->idx++ == 0) return &ent_termux;
                return NULL;
            }
        }
    }
    if (libc_readdir) return libc_readdir(dirp);
    return NULL;
}

int closedir(DIR *dirp) {
    for (int i = 0; i < fake_dir_cnt; i++) {
        if (dirp == (DIR *)&fake_dirs[i]) {
            fake_dirs[i] = fake_dirs[--fake_dir_cnt];
            return 0;
        }
    }
    if (libc_closedir) return libc_closedir(dirp);
    return 0;
}

int access(const char *pathname, int mode) {
    resolve_symbols();
    char buf[1024];
    const char *p = redirect_path(pathname, buf, sizeof(buf));
    if (libc_access) return libc_access(p, mode);
    errno = ENOENT;
    return -1;
}

int stat(const char *pathname, struct stat *statbuf) {
    resolve_symbols();
    char buf[1024];
    const char *p = redirect_path(pathname, buf, sizeof(buf));
    if (libc_stat) return libc_stat(p, statbuf);
    errno = ENOENT;
    return -1;
}

int lstat(const char *pathname, struct stat *statbuf) {
    resolve_symbols();
    char buf[1024];
    const char *p = redirect_path(pathname, buf, sizeof(buf));
    if (libc_lstat) return libc_lstat(p, statbuf);
    errno = ENOENT;
    return -1;
}

char *canonicalize_file_name(const char *name) {
    resolve_symbols();
    char buf[1024];
    const char *p = redirect_path(name, buf, sizeof(buf));
    if (libc_realpath) return libc_realpath(p, NULL);
    return NULL;
}

char *realpath(const char *path, char *resolved_path) {
    resolve_symbols();
    char buf[1024];
    const char *p = redirect_path(path, buf, sizeof(buf));
    if (libc_realpath) return libc_realpath(p, resolved_path);
    return NULL;
}

int open(const char *pathname, int flags, ...) {
    resolve_symbols();
    char buf[1024];
    const char *p = redirect_path(pathname, buf, sizeof(buf));
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list args;
        va_start(args, flags);
        mode = va_arg(args, mode_t);
        va_end(args);
        if (libc_open) return libc_open(p, flags, mode);
    }
    if (libc_open) return libc_open(p, flags);
    errno = ENOENT;
    return -1;
}

int openat(int dirfd, const char *pathname, int flags, ...) {
    resolve_symbols();
    char buf[1024];
    const char *p = redirect_path(pathname, buf, sizeof(buf));
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list args;
        va_start(args, flags);
        mode = va_arg(args, mode_t);
        va_end(args);
        if (libc_openat) return libc_openat(dirfd, p, flags, mode);
    }
    if (libc_openat) return libc_openat(dirfd, p, flags);
    errno = ENOENT;
    return -1;
}

FILE *fopen(const char *pathname, const char *mode) {
    resolve_symbols();
    char buf[1024];
    const char *p = redirect_path(pathname, buf, sizeof(buf));
    if (libc_fopen) return libc_fopen(p, mode);
    errno = ENOENT;
    return NULL;
}
