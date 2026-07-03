"""Code-hook selection policy for the BBK 9588 emulator."""

from __future__ import annotations

from hwemu_defs import BDA_RETURN_PC, KNOWN_C200_STORE_DELAY_BRANCH_PCS
from hwemu_fastpaths import PORTRAIT_BLIT_LOOP_PCS
from hwemu_surface import SURFACE_TRANSPARENT_BLIT_PCS


BASE_FAST_CODE_HOOK_PCS = frozenset(
    {
        0x80903AA0,
        0x80901384,
        0x80901D2C,
        0x80901E24,
        0x80900F70,
        0x80900F78,
        0x80900F80,
        0x80902448,
        0x8090247C,
        0x80902524,
        0x80903BB0,
        0x80903BB8,
        0x80903BC0,
        0x80903BCC,
        0x80903BD4,
        0x80903BE8,
        0x80903C2C,
        0x80903EA4,
        0x80903EAC,
        0x80903EFC,
        0x80904EC8,
        0x80906780,
        0x809080A0,
        0x80908188,
        0x809081A0,
        0x809081A4,
        0x80908284,
        0x80908288,
        0x8090828C,
        0x80908294,
        0x80900D48,
        0x80905EA0,
        0x8000403C,
        0x80004074,
        0x800042F0,
        0x800043A0,
        0x800043CC,
        0x80004CC4,
        0x80004CD4,
        0x80006BD0,
        0x80006BF8,
        0x80006688,
        0x80006834,
        0x800074A0,
        0x800098C0,
        0x8000C15C,
        0x8000D990,
        0x8000FEC0,
        0x8000FE74,
        0x8000FEB4,
        0x800100C8,
        0x80008354,
        0x80008470,
        0x800080F0,
        0x800081A8,
        0x800087C4,
        0x800088AC,
        0x80008A84,
        0x80009950,
        0x800099F0,
        0x80010D70,
        0x80010D7C,
        0x80010D88,
        0x80010D94,
        0x80010DA0,
        0x800128CC,
        0x800128D4,
        0x800128F4,
        0x800128F8,
        0x800129AC,
        0x800133EC,
        0x800176E0,
        0x80017CB4,
        0x80017D54,
        0x80017DE8,
        0x80018C58,
        0x80018DAC,
        0x8001A3A0,
        0x8001A6B0,
        0x8001B464,
        0x8005BCD4,
        0x80058CB4,
        0x800A7B40,
        0x800A7C18,
        0x800A7DC0,
        0x800A7FD8,
        0x800A80E8,
        0x800A899C,
        0x800A89A4,
        0x800A89AC,
        0x800A89B4,
        0x800AC388,
        0x800BC944,
        0x800BC9AC,
        0x800BC9CC,
        0x800BC2E0,
        0x800BD840,
        0x800CE928,
        0x800CE968,
        0x800CE9F0,
        0x800CEA30,
        0x800D3368,
        0x800D3634,
        0x800DE150,
        0x800DE188,
        0x800DE190,
        0x800DE1C0,
        0x800DE1C8,
        0x800DE200,
        0x800DE5BC,
        0x81C0FA74,
        0x800E0D68,
        0x800E123C,
        0x800E1408,
        0x80170C74,
        0x8001920C,
        0x8001925C,
        0x8012A6A8,
        *PORTRAIT_BLIT_LOOP_PCS,
        0x80172840,
        0x8017B45C,
        0x8017B4E0,
        0x8012BDF4,
        0x8012BEA4,
        0x8012BE84,
        0x8012B034,
        0x8012B064,
        0x8012BF64,
        0x8012BFE8,
        *SURFACE_TRANSPARENT_BLIT_PCS,
        0x80173630,
        0x80173638,
        0x80173640,
        0x80173710,
        0x80173764,
        0x80173768,
        0x8017376C,
        0x80173504,
        0x801737B8,
        0x80173F14,
        0x80173F1C,
        0x80173F24,
        0x80173F2C,
        0x8017A860,
        0x8011B428,
        0x80175E40,
        0x80174C9C,
        0x80174CC0,
        0x80174CE4,
        0x8017BEF4,
        0x8017CA10,
        0x80181B6C,
        0x80183958,
        0x80184300,
        0x801838FC,
        0x801802E8,
        0x8017FDCC,
        0x8018057C,
        0x801813E0,
        0x80181400,
        0x80182A90,
        0x80182BF4,
        0x80182D58,
        0x80183E0C,
        0x80183E10,
        0x80183FA4,
        0x80183FA8,
        0x80184140,
        0x80184150,
        0x801841BC,
        0x801841CC,
        0x801843D8,
        0x801843DC,
        0x80184530,
        0x80183304,
        0x80184D08,
    }
)


class HwEmuHookPolicyMixin:
    def _fast_code_hook_pcs(self) -> set[int]:
        pcs = set(self.trace_pcs)
        pcs.update(self.stop_pcs)
        pcs.update(call.return_pc for call in self.scheduled_calls)
        if self.firmware_key_samples or self.touch_samples or (self.legacy_direct_bda and self.bda_launches):
            pcs.add(BDA_RETURN_PC)
        if self.fast_hook_image_jals:
            pcs.update(self._image_jal_pcs())
        pcs.update(self._store_delay_branch_hook_pcs())
        pcs.update(BASE_FAST_CODE_HOOK_PCS)
        return pcs

    def _store_delay_branch_hook_pcs(self) -> set[int]:
        cached = getattr(self, "store_delay_branch_pcs", None)
        if cached:
            return cached
        if self.store_delay_branch_hooks == "all":
            pcs = self._image_store_delay_branch_pcs()
        elif self.store_delay_branch_hooks == "known":
            pcs = set(KNOWN_C200_STORE_DELAY_BRANCH_PCS)
        else:
            pcs = set()
        self.store_delay_branch_pcs = pcs
        return pcs

    def _image_store_delay_branch_pcs(self) -> set[int]:
        data = self.image.read_bytes()
        pcs: set[int] = set()
        for off in range(0, len(data) - 7, 4):
            word = int.from_bytes(data[off : off + 4], "little")
            delay = int.from_bytes(data[off + 4 : off + 8], "little")
            if not self._is_recoverable_branch_word(word):
                continue
            delay_opcode = (delay >> 26) & 0x3F
            if delay_opcode in (40, 41, 43):  # sb/sh/sw
                pcs.add((self.base + off) & 0xFFFFFFFF)
        return pcs

    def _image_jal_pcs(self) -> set[int]:
        data = self.image.read_bytes()
        pcs: set[int] = set()
        for off in range(0, len(data) - 3, 4):
            word = int.from_bytes(data[off : off + 4], "little")
            if ((word >> 26) & 0x3F) == 3:
                pc = (self.base + off) & 0xFFFFFFFF
                target = ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
                pcs.add(pc)
                pcs.add(target & 0xFFFFFFFF)
        return pcs

    def _image_recoverable_branch_pcs(self) -> set[int]:
        data = self.image.read_bytes()
        pcs: set[int] = set()
        for off in range(0, len(data) - 3, 4):
            word = int.from_bytes(data[off : off + 4], "little")
            if self._is_recoverable_exception_word(word):
                pcs.add((self.base + off) & 0xFFFFFFFF)
        return pcs
