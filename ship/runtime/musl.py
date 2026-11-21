"""Musl static binary path relocator for Termux environment.

Patches hardcoded /etc/resolv.conf and /etc/hosts references in statically linked
musl AArch64 binaries directly via ELF segment and instruction rewriting, allowing
them to run natively with full network access without QEMU or proot.
"""

from __future__ import annotations

import struct
from pathlib import Path

from ship.api import PatchReport
from ship.core.profile import get_active_profile


def patch_musl_static_paths(
    binary_path: Path, report: PatchReport | None = None
) -> bool:
    """Scan and patch static musl AArch64 binary to point /etc/resolv.conf and /etc/hosts to Termux."""
    try:
        data = bytearray(binary_path.read_bytes())
    except OSError:
        return False

    if len(data) < 64 or data[:4] != b"\x7fELF":
        return False
    if data[4] != 2 or data[5] != 1:  # 64-bit, little-endian
        return False

    machine = struct.unpack_from("<H", data, 18)[0]
    if machine != 183:  # EM_AARCH64 only
        return False

    profile = get_active_profile()
    prefix = str(profile.paths.prefix)
    resolv_target = f"{prefix}/etc/resolv.conf".encode()
    hosts_target = f"{prefix}/etc/hosts".encode()

    replacements: dict[bytes, bytes] = {
        b"/etc/resolv.conf": resolv_target,
        b"/etc/hosts": hosts_target,
    }

    phoff = struct.unpack_from("<Q", data, 32)[0]
    phentsize = struct.unpack_from("<H", data, 54)[0]
    phnum = struct.unpack_from("<H", data, 56)[0]

    load_headers: list[dict[str, int]] = []
    for i in range(phnum):
        off = phoff + i * phentsize
        p_type = struct.unpack_from("<I", data, off)[0]
        if p_type == 1:  # PT_LOAD
            p_flags = struct.unpack_from("<I", data, off + 4)[0]
            p_offset = struct.unpack_from("<Q", data, off + 8)[0]
            p_vaddr = struct.unpack_from("<Q", data, off + 16)[0]
            p_filesz = struct.unpack_from("<Q", data, off + 32)[0]
            p_memsz = struct.unpack_from("<Q", data, off + 40)[0]
            load_headers.append(
                {
                    "header_off": off,
                    "p_flags": p_flags,
                    "p_offset": p_offset,
                    "p_vaddr": p_vaddr,
                    "p_filesz": p_filesz,
                    "p_memsz": p_memsz,
                }
            )

    if not load_headers:
        return False

    target_vas: dict[int, bytes] = {}
    for target_str in replacements:
        idx = data.find(target_str)
        if idx == -1:
            continue
        for seg in load_headers:
            if seg["p_offset"] <= idx < seg["p_offset"] + seg["p_filesz"]:
                va = seg["p_vaddr"] + (idx - seg["p_offset"])
                target_vas[va] = target_str
                break

    if not target_vas:
        return False

    # Check if already patched to the replacement strings
    all_replacements_present = all(repl in data for repl in replacements.values())
    if all_replacements_present:
        if report is not None:
            report.add(
                binary_path, "verify musl network paths", "already relocated to Termux"
            )
        return True

    seg0 = load_headers[0]
    seg1 = load_headers[1] if len(load_headers) > 1 else None

    gap_file_offset = seg0["p_offset"] + seg0["p_filesz"]
    gap_size = (seg1["p_offset"] - gap_file_offset) if seg1 else 0

    needed = sum(len(replacements[s]) + 1 for s in target_vas.values())
    if gap_size < needed:
        return False

    new_vas: dict[int, int] = {}
    curr_file_off = gap_file_offset
    for va, orig_str in target_vas.items():
        repl = replacements[orig_str]
        data[curr_file_off : curr_file_off + len(repl) + 1] = repl + b"\x00"
        new_va = seg0["p_vaddr"] + (curr_file_off - seg0["p_offset"])
        new_vas[va] = new_va
        curr_file_off += len(repl) + 1

    new_filesz = curr_file_off - seg0["p_offset"]
    struct.pack_into("<Q", data, seg0["header_off"] + 32, new_filesz)
    struct.pack_into("<Q", data, seg0["header_off"] + 40, new_filesz)

    text_end = seg0["p_offset"] + seg0["p_filesz"]
    patched_count = 0
    regs: dict[int, tuple[int, int, int]] = {}

    for off in range(seg0["p_offset"], text_end, 4):
        pc = seg0["p_vaddr"] + (off - seg0["p_offset"])
        inst = struct.unpack_from("<I", data, off)[0]

        # ADRP
        if (inst & 0x9F000000) == 0x90000000:
            immlo = (inst >> 29) & 0x3
            immhi = (inst >> 5) & 0x7FFFF
            imm = (immhi << 2) | immlo
            if imm & 0x100000:
                imm -= 0x200000
            page = (pc & ~0xFFF) + (imm << 12)
            rd = inst & 0x1F
            regs[rd] = (page, pc, off)
            continue

        # ADD immediate (64-bit)
        if (inst & 0xFFC00000) == 0x91000000:
            rn = (inst >> 5) & 0x1F
            rd = inst & 0x1F
            imm12 = (inst >> 10) & 0xFFF
            if rn in regs:
                page, pc_adrp, off_adrp = regs[rn]
                computed_va = page + imm12
                if computed_va in target_vas:
                    new_target = new_vas[computed_va]
                    new_page_diff = (new_target & ~0xFFF) - (pc_adrp & ~0xFFF)
                    imm_pages = new_page_diff >> 12
                    immlo_new = imm_pages & 0x3
                    immhi_new = (imm_pages >> 2) & 0x7FFFF
                    adrp_rd = rn
                    new_adrp = (
                        0x90000000 | (immlo_new << 29) | (immhi_new << 5) | adrp_rd
                    )
                    new_imm12 = new_target & 0xFFF
                    new_add = (inst & ~0x003FFC00) | (new_imm12 << 10)

                    struct.pack_into("<I", data, off_adrp, new_adrp)
                    struct.pack_into("<I", data, off, new_add)
                    patched_count += 1
            if rd in regs and rd != rn:
                del regs[rd]
            continue

        if (inst & 0x7C000000) == 0x14000000 or (inst & 0xFFFFFC1F) == 0xD65F0000:
            regs.clear()

    if patched_count > 0:
        binary_path.write_bytes(data)
        if report is not None:
            report.add(
                binary_path,
                "relocate musl network paths",
                f"{patched_count} instructions",
            )
        return True

    return False
