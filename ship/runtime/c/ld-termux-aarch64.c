// ld-termux-aarch64.c — freestanding PT_INTERP trampoline for Termux glibc
typedef unsigned char uint8_t;
typedef unsigned short uint16_t;
typedef unsigned int uint32_t;
typedef unsigned long long uint64_t;
typedef unsigned long size_t;

#define REAL_LD_SO "/data/data/com.termux/files/usr/glibc/lib/ld-linux-aarch64.so.1"

#define AT_FDCWD    (-100)
#define O_RDONLY    0
#define PROT_NONE   0x0
#define PROT_READ   0x1
#define PROT_WRITE  0x2
#define PROT_EXEC   0x4
#define MAP_PRIVATE 0x02
#define MAP_FIXED   0x10
#define MAP_ANON    0x20

#define PT_LOAD 1
#define PF_X 1
#define PF_W 2
#define PF_R 4

#define AT_NULL   0
#define AT_PAGESZ 6
#define AT_BASE   7

typedef struct {
    uint8_t  e_ident[16];
    uint16_t e_type, e_machine;
    uint32_t e_version;
    uint64_t e_entry, e_phoff, e_shoff;
    uint32_t e_flags;
    uint16_t e_ehsize, e_phentsize, e_phnum, e_shentsize, e_shnum, e_shstrndx;
} Elf64_Ehdr;

typedef struct {
    uint32_t p_type, p_flags;
    uint64_t p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_align;
} Elf64_Phdr;

typedef struct {
    uint64_t a_type;
    uint64_t a_val;
} Elf64_auxv_t;

static inline long sys6(long n, long a0, long a1, long a2, long a3, long a4, long a5) {
    register long x8 __asm__("x8") = n;
    register long x0 __asm__("x0") = a0;
    register long x1 __asm__("x1") = a1;
    register long x2 __asm__("x2") = a2;
    register long x3 __asm__("x3") = a3;
    register long x4 __asm__("x4") = a4;
    register long x5 __asm__("x5") = a5;
    __asm__ volatile("svc #0"
        : "+r"(x0)
        : "r"(x8), "r"(x1), "r"(x2), "r"(x3), "r"(x4), "r"(x5)
        : "memory");
    return x0;
}

#define sys_openat(dfd, p, f, m)    sys6(56, (long)(dfd), (long)(p), (f), (m), 0, 0)
#define sys_close(fd)               sys6(57, (fd), 0, 0, 0, 0, 0)
#define sys_pread64(fd, b, c, o)    sys6(67, (fd), (long)(b), (long)(c), (long)(o), 0, 0)
#define sys_exit(c)                 sys6(94, (c), 0, 0, 0, 0, 0)
#define sys_mmap(a, l, p, f, fd, o) sys6(222, (long)(a), (long)(l), (p), (f), (fd), (long)(o))
#define sys_mprotect(a, l, p)       sys6(226, (long)(a), (long)(l), (p), 0, 0, 0)

static int starts_with(const char *s, const char *pfx) {
    while (*pfx) {
        if (*s++ != *pfx++) return 0;
    }
    return 1;
}

static int contains(const char *s, const char *needle) {
    for (; *s; s++) {
        if (starts_with(s, needle)) return 1;
    }
    return 0;
}

uint64_t trampoline_main(uint64_t *sp) {
    uint64_t argc = sp[0];
    char **argv = (char **)&sp[1];
    char **envp = &argv[argc + 1];

    char **e = envp;
    while (*e) e++;
    Elf64_auxv_t *auxv = (Elf64_auxv_t *)(e + 1);

    // Null out Termux/Android LD_PRELOAD variables in-place without shifting
    // so glibc dynamic linker ignores them and auxv stays intact.
    for (size_t i = 0; envp[i] != 0; i++) {
        if (starts_with(envp[i], "LD_PRELOAD=")) {
            // Overwrite prefix to harmless dummy variable
            char *p = envp[i];
            p[0] = '_';
            p[1] = '_';
        }
    }

    uint64_t pagesz = 4096;
    for (Elf64_auxv_t *a = auxv; a->a_type != AT_NULL; a++) {
        if (a->a_type == AT_PAGESZ && a->a_val != 0) {
            pagesz = a->a_val;
            break;
        }
    }

    long fd = sys_openat(AT_FDCWD, REAL_LD_SO, O_RDONLY, 0);
    if (fd < 0) sys_exit(127);

    Elf64_Ehdr eh;
    if (sys_pread64(fd, &eh, sizeof(eh), 0) != (long)sizeof(eh)) sys_exit(127);
    if (eh.e_phnum > 32) sys_exit(127);

    Elf64_Phdr phs[32];
    size_t ph_bytes = (size_t)eh.e_phnum * sizeof(Elf64_Phdr);
    if (sys_pread64(fd, phs, ph_bytes, eh.e_phoff) != (long)ph_bytes) sys_exit(127);

    uint64_t min_va = ~0ULL, max_va = 0;
    for (uint16_t i = 0; i < eh.e_phnum; i++) {
        if (phs[i].p_type != PT_LOAD) continue;
        uint64_t lo = phs[i].p_vaddr & ~(pagesz - 1);
        uint64_t hi = (phs[i].p_vaddr + phs[i].p_memsz + pagesz - 1) & ~(pagesz - 1);
        if (lo < min_va) min_va = lo;
        if (hi > max_va) max_va = hi;
    }

    long res = sys_mmap(0, max_va - min_va, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0);
    if (res < 0 && res > -4096) sys_exit(127);
    uint64_t bias = (uint64_t)res - min_va;

    for (uint16_t i = 0; i < eh.e_phnum; i++) {
        if (phs[i].p_type != PT_LOAD) continue;
        uint64_t seg_start = phs[i].p_vaddr & ~(pagesz - 1);
        uint64_t file_end  = (phs[i].p_vaddr + phs[i].p_filesz + pagesz - 1) & ~(pagesz - 1);
        uint64_t mem_end   = (phs[i].p_vaddr + phs[i].p_memsz  + pagesz - 1) & ~(pagesz - 1);
        uint64_t file_off  = phs[i].p_offset & ~(pagesz - 1);

        int prot = ((phs[i].p_flags & PF_R) ? PROT_READ  : 0) |
                   ((phs[i].p_flags & PF_W) ? PROT_WRITE : 0) |
                   ((phs[i].p_flags & PF_X) ? PROT_EXEC  : 0);

        int has_bss = phs[i].p_memsz > phs[i].p_filesz;
        if (file_end > seg_start) {
            int map_prot = has_bss ? (prot | PROT_WRITE) : prot;
            long m = sys_mmap(bias + seg_start, file_end - seg_start,
                              map_prot, MAP_PRIVATE | MAP_FIXED, fd, file_off);
            if (m < 0 && m > -4096) sys_exit(127);

            if (has_bss) {
                volatile uint8_t *z = (volatile uint8_t *)(bias + phs[i].p_vaddr + phs[i].p_filesz);
                volatile uint8_t *z_end = (volatile uint8_t *)(bias + file_end);
                while (z < z_end) *z++ = 0;
                if (!(prot & PROT_WRITE)) {
                    sys_mprotect(bias + seg_start, file_end - seg_start, prot);
                }
            }
        }
        if (mem_end > file_end) {
            long m = sys_mmap(bias + file_end, mem_end - file_end,
                              prot, MAP_PRIVATE | MAP_ANON | MAP_FIXED, -1, 0);
            if (m < 0 && m > -4096) sys_exit(127);
        }
    }

    sys_close(fd);

    for (Elf64_auxv_t *a = auxv; a->a_type != AT_NULL; a++) {
        if (a->a_type == AT_BASE) {
            a->a_val = bias;
            break;
        }
    }

    return bias + eh.e_entry;
}

__attribute__((naked)) void _start(void) {
    __asm__ volatile(
        "mov x0, sp\n"
        "bl trampoline_main\n"
        "mov x16, x0\n"
        "mov x0, #0\n"
        "br x16\n"
    );
}
