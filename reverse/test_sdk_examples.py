from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bda_compile_c import bundled_prefix, find_tool
from bda_validate import validate_bda


class SdkExamplesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        prefix = bundled_prefix() or "mipsel-none-elf-"
        try:
            find_tool(prefix, "gcc")
            find_tool(prefix, "objcopy")
        except SystemExit as exc:
            raise unittest.SkipTest(str(exc))
        cls.prefix = prefix
        cls.out_dir = Path("build") / "test_sdk_examples"
        cls.out_dir.mkdir(parents=True, exist_ok=True)

    def build_and_validate(
        self,
        source: str,
        title: str,
        include_dirs: tuple[str, ...] = (),
        category: int = 9,
        icon_png: str | None = None,
    ) -> dict[str, object]:
        output = self.out_dir / f"{title}.bda"
        command = [
            sys.executable,
            "reverse/bda_compile_c.py",
            source,
            "--prefix",
            self.prefix,
            "--title",
            title,
            "--category",
            str(category),
        ]
        for include_dir in include_dirs:
            command.extend(["-I", include_dir])
        if icon_png is not None:
            command.extend(["--icon-png", icon_png])
        command.extend(["-o", str(output)])
        output_text = subprocess.check_output(command)
        report = validate_bda(output)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["title"], title)
        self.assertEqual(report["category"], category)
        self.assertEqual(report["entry_offset"], 0x95F8)
        return report

    def test_hello_msgbox_example_builds(self) -> None:
        self.build_and_validate("sdk/api/examples/hello_msgbox.c", "HelloC")

    def test_gui_rect_contains_example_builds(self) -> None:
        self.build_and_validate(
            "sdk/api/examples/gui_rect_contains_demo.c", "RectDemo", ("sdk/api",)
        )

    def test_gui_screen_width_example_builds(self) -> None:
        self.build_and_validate(
            "sdk/api/examples/gui_screen_width_demo.c", "WidthDemo", ("sdk/api",)
        )

    def test_input_state_example_builds(self) -> None:
        self.build_and_validate(
            "sdk/api/examples/input_state_demo.c", "Input", ("sdk/api",)
        )

    def test_mem_alloc_example_builds(self) -> None:
        self.build_and_validate(
            "sdk/api/examples/mem_alloc_demo.c", "MemDemo", ("sdk/api",)
        )

    def test_fs_read_example_builds(self) -> None:
        self.build_and_validate(
            "sdk/api/examples/fs_read_demo.c", "FsRead", ("sdk/api",)
        )

    def test_fs_read_raw_example_builds(self) -> None:
        self.build_and_validate(
            "sdk/api/examples/fs_read_raw_demo.c", "FsRaw", ("sdk/api",)
        )

    def test_fs_write_example_builds(self) -> None:
        self.build_and_validate("sdk/api/examples/fs_write_demo.c", "FsWrite")

    def test_key_msgbox_example_builds(self) -> None:
        self.build_and_validate("sdk/api/examples/key_msgbox_demo.c", "KeyInput")

    def test_touch_press_example_builds(self) -> None:
        self.build_and_validate("sdk/api/examples/touch_press_demo.c", "Touch")

    def test_touch_crosshair_example_builds(self) -> None:
        self.build_and_validate(
            "sdk/api/examples/touch_crosshair_demo.c", "TouchXY"
        )

    def test_touch_stage_v12_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/touch_input_stage_probe_v12.c", "TouchV12"
        )

    def test_touch_stage_v13_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/touch_input_stage_probe_v13.c", "TouchV13"
        )

    def test_touch_stage_v14_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/touch_input_stage_probe_v14.c", "TouchV14"
        )

    def test_touch_stage_v15_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/touch_input_stage_probe_v15.c", "TouchV15"
        )

    def test_touch_stage_v16_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/touch_input_stage_probe_v16.c", "TouchV16"
        )

    def test_touch_stage_v17_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/touch_input_stage_probe_v17.c", "TouchV17"
        )

    def test_touch_stage_v18_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/touch_input_stage_probe_v18.c", "TouchV18"
        )

    def test_touch_stage_v19_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/touch_input_stage_probe_v19.c", "TouchV19"
        )

    def test_touch_stage_v20_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/touch_input_stage_probe_v20.c", "TouchV20"
        )

    def test_touch_stage_v21_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/touch_input_stage_probe_v21.c", "TouchV21"
        )

    def test_touch_stage_v22_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/touch_input_stage_probe_v22.c", "TouchV22"
        )

    def test_touch_stage_v23_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/touch_input_stage_probe_v23.c", "TouchV23"
        )

    def test_graphics_primitives_example_builds(self) -> None:
        self.build_and_validate("sdk/api/examples/graphics_primitives_demo.c", "Graphics")

    def test_fs_find_example_builds(self) -> None:
        self.build_and_validate(
            "sdk/api/examples/fs_find_demo.c", "FsFind", ("sdk/api",)
        )

    def test_fs_diskinfo_example_builds(self) -> None:
        self.build_and_validate(
            "sdk/api/examples/fs_diskinfo_demo.c", "FsDisk", ("sdk/api",)
        )

    def test_fs_status_example_builds(self) -> None:
        self.build_and_validate(
            "sdk/api/examples/fs_status_demo.c", "FsStat", ("sdk/api",)
        )

    def test_res_state_example_builds(self) -> None:
        self.build_and_validate(
            "sdk/api/examples/res_state_demo.c", "ResState", ("sdk/api",)
        )

    def test_tile_blit_probe_builds(self) -> None:
        self.build_and_validate(
            "sdk/api/examples/tile_blit_probe.c", "TileBlit", ("sdk/api",)
        )

    def test_time_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/time_probe.c", "TimeProbe", ("sdk/api",)
        )

    def test_game_api_probe_builds(self) -> None:
        self.build_and_validate("reverse/examples/game_api_probe.c", "GameApiV1")

    def test_game_audio_probe_builds(self) -> None:
        self.build_and_validate("reverse/examples/game_audio_probe.c", "GameAudioV2")

    def test_game_graphics_probe_builds(self) -> None:
        self.build_and_validate("reverse/examples/game_graphics_probe.c", "GameGfxV3")

    def test_game_image_probe_builds(self) -> None:
        self.build_and_validate("reverse/examples/game_image_probe.c", "GameImgV4")

    def test_game_image_render_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/game_image_render_probe.c", "GameImgV5"
        )

    def test_game_image_compat_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/game_image_compat_probe.c", "GameImgV6"
        )

    def test_game_jpeg_probe_builds(self) -> None:
        self.build_and_validate("reverse/examples/game_jpeg_probe.c", "GameJpgV7")

    def test_game_compat_animation_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/game_compat_animation_probe.c", "GameAnimV8"
        )

    def test_game_tick_probe_builds(self) -> None:
        self.build_and_validate("reverse/examples/game_tick_probe.c", "GameTickV9")

    def test_game_polyline_clip_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/game_polyline_clip_probe.c", "GameGfxV10"
        )

    def test_game_ellipse_probe_builds(self) -> None:
        self.build_and_validate("reverse/examples/game_ellipse_probe.c", "GameGfxV11")

    def test_game_arc_round_rect_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/game_arc_round_rect_probe.c", "GameGfxV12"
        )

    def test_game_map_mode_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/game_map_mode_probe.c", "GameGfxV13"
        )

    def test_game_coordinate_transform_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/game_coordinate_transform_probe.c", "GameGfxV14"
        )

    def test_game_clip_select_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/game_clip_select_probe.c", "GameGfxV15"
        )

    def test_game_clip_exclude_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/game_clip_exclude_probe.c", "GameGfxV16"
        )

    def test_game_clip_union_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/game_clip_union_probe.c", "GameGfxV17"
        )

    def test_game_clip_intersect_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/game_clip_intersect_probe.c", "GameGfxV18"
        )

    def test_game_double_buffer_sprite_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/game_double_buffer_sprite_probe.c", "GameGfxV19"
        )

    def test_game_color_key_sprite_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/game_color_key_sprite_probe.c", "GameGfxV20"
        )

    def test_game_dirty_rect_sprite_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/game_dirty_rect_sprite_probe.c", "GameGfxV21"
        )

    def test_showcase_stage_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/showcase_stage_probe.c", "StageProbe", ("sdk/api",)
        )

    def test_file_selector_probe_builds(self) -> None:
        self.build_and_validate(
            "reverse/examples/file_selector_probe.c", "FileSel", ("sdk/api",)
        )

    def test_minesweeper_example_builds(self) -> None:
        self.build_and_validate(
            "sdk/api/examples/minesweeper_bda.c",
            "Mines",
            category=4,
            icon_png="sdk/assets/minesweeper_icon.png",
        )
        source = Path("sdk/api/examples/minesweeper_bda.c").read_text(
            encoding="utf-8"
        )
        self.assertIn("#define BOARD_WIDTH 9", source)
        self.assertIn("bda_gui_compatible_context_create", source)
        self.assertIn("bda_gui_compatible_context_free", source)
        self.assertIn("bda_gui_context_copy", source)
        self.assertIn("bda_gui_tick_count_25ms", source)
        self.assertIn("BDA_MSG_TOUCH_RELEASE", source)
        self.assertNotIn("_like", source)
        self.assertNotIn("_LIKE", source)
        self.assertNotIn("0x81c0fdb8", source.lower())
        self.assertNotIn("draw_object_create_like(15)", source)

    def test_no_template_build_includes_bss_zero_fill(self) -> None:
        source = self.out_dir / "bss_probe.c"
        output = self.out_dir / "BssProbe.bda"
        source.write_text(
            """
#include "bda_sdk.h"

static u8 g_scratch[1024];

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    g_scratch[1023] = 7;
    return g_scratch[0];
}
""".lstrip(),
            encoding="ascii",
        )

        output_text = subprocess.check_output(
            [
                sys.executable,
                "reverse/bda_compile_c.py",
                str(source),
                "--prefix",
                self.prefix,
                "--title",
                "BssProbe",
                "--category",
                "9",
                "-o",
                str(output),
            ],
            text=True,
            encoding="utf-8",
        )
        self.assertIn("runtime_file_base=0x81bf6a28", output_text)

        report = validate_bda(output)
        self.assertTrue(report["ok"], report)
        self.assertGreaterEqual(output.stat().st_size, 0x95F8 + 1024)

    def test_call5_wrapper_places_fifth_argument_on_stack(self) -> None:
        source = self.out_dir / "call5_probe.c"
        output = self.out_dir / "Call5Probe.bda"
        source.write_text(
            """
#include "bda_sdk.h"

static u16 g_buf[4];

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    return bda_gui_blit_like(1, 2, 3, 4, g_buf);
}
""".lstrip(),
            encoding="ascii",
        )

        subprocess.check_call(
            [
                sys.executable,
                "reverse/bda_compile_c.py",
                str(source),
                "--prefix",
                self.prefix,
                "--title",
                "Call5",
                "--category",
                "9",
                "-I",
                "sdk/api",
                "-o",
                str(output),
            ]
        )
        disasm = subprocess.check_output(
            [
                sys.executable,
                "reverse/bda_disasm_preview.py",
                str(output),
                "--offset",
                "0x95f8",
                "--base",
                "0x81bf6a28",
                "--count",
                "40",
            ],
            text=True,
            encoding="utf-8",
        )

        self.assertRegex(disasm, r"sw\s+\$[a-z0-9]+,\s+0x10\(\$sp\)")
        self.assertIn("lw       $v0, 0x3f8", disasm)
        self.assertIn("addiu    $a3, $zero, 4", disasm)
        self.assertIn("addiu    $a2, $zero, 3", disasm)
        self.assertIn("addiu    $a1, $zero, 2", disasm)
        self.assertIn("addiu    $a0, $zero, 1", disasm)


if __name__ == "__main__":
    unittest.main()
