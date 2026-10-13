#!/usr/bin/env python3
"""Repair FangSongCode and rebuild CodeSC from it.

The project copy of FangSongCode is outline-identical to the installed original,
apart from 13 missing PUA glyphs and already-zeroed combining-mark advances.
The installed original is therefore used as the complete, read-only source.

CodeSC geometry (three output variants):
  * 600-unit Latin cells become 560 units and outlines move left 20 units.
  * 1000-unit punctuation/symbol cells become 1120 units and outlines move
    right 60 units without scaling.
  * 1000-unit character cells become 1120 units with one of:
      x' = 1.05*x + 35
      x' = 1.06*x + 30
      x' = 1.07*x + 25
  * combining marks stay zero-width and follow the Latin x transformation.
"""

from __future__ import annotations

import math
import sys
import unicodedata
from pathlib import Path

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.ttLib import TTFont


INSTALLED_FANG = Path.home() / "Library/Fonts/FangSongCode.ttf"
INSTALLED_CODE = Path.home() / "Library/Fonts/CodeSC.ttf"
PROJECT_FANG = Path("FangSongCode-Regular.ttf")
FANG_OUTPUT = Path("FangSongCode-Regular-repaired.ttf")
CODE_OUTPUTS = {
    1.05: Path("CodeSC-Regular-1.05.ttf"),
    1.06: Path("CodeSC-Regular-1.06.ttf"),
    1.07: Path("CodeSC-Regular-1.07.ttf"),
}

MARK_CLASSES = {
    0: "MC_top",
    1: "MC_bottom",
    2: "MC_overlay",
    3: "MC_double_bottom",
    4: "MC_double_top",
}


def rounded(value: float) -> int:
    """Round halves away from zero, as is customary for font coordinates."""
    return math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)


def replace_name(font: TTFont, name_id: int, value: str) -> None:
    found = False
    for record in font["name"].names:
        if record.nameID == name_id:
            record.string = value.encode(record.getEncoding())
            found = True
    if not found:
        font["name"].setName(value, name_id, 3, 1, 0x409)


def mark_class(codepoint: int, glyph) -> int:
    if codepoint == 0x0334:
        return 2
    if codepoint == 0x035F:
        return 3
    if codepoint == 0x0361:
        return 4
    return 1 if glyph.yMax < 200 else 0


def anchor_x(width: int, y: int, italic_angle: float, *, double=False) -> int:
    origin = width if double else width / 2
    return rounded(origin - math.tan(math.radians(italic_angle)) * y)


def mark_anchor_y(class_id: int, glyph) -> int:
    if class_id in (0, 4):
        return glyph.yMin
    if class_id in (1, 3):
        return glyph.yMax
    return rounded((glyph.yMin + glyph.yMax) / 2)


def original_base_names(font: TTFont, mark_names: set[str]) -> list[str]:
    class_defs = font["GDEF"].table.GlyphClassDef.classDefs
    return [
        name
        for name in font.getGlyphOrder()
        if class_defs.get(name) == 1 and name not in mark_names
    ]


def collect_marks(font: TTFont) -> dict[str, tuple[int, int]]:
    cmap = font.getBestCmap()
    glyf = font["glyf"]
    result: dict[str, tuple[int, int]] = {}
    for codepoint, glyph_name in cmap.items():
        if unicodedata.category(chr(codepoint)).startswith("M"):
            result[glyph_name] = (
                codepoint,
                mark_class(codepoint, glyf[glyph_name]),
            )
    if len(result) != 54:
        raise RuntimeError(f"Expected 54 combining marks, found {len(result)}")
    return result


def build_mark_features(
    font: TTFont,
    mark_info: dict[str, tuple[int, int]],
    base_names: list[str],
    mark_cell_width: int,
) -> str:
    glyph_order = font.getGlyphOrder()
    glyf = font["glyf"]
    hmtx = font["hmtx"].metrics
    italic_angle = font["post"].italicAngle
    attachable_bases = [
        name
        for name in base_names
        if getattr(glyf[name], "numberOfContours", 0) != 0
        and hasattr(glyf[name], "yMin")
        and hasattr(glyf[name], "yMax")
    ]

    lines = [
        "languagesystem DFLT dflt;",
        "languagesystem latn dflt;",
        "languagesystem cyrl dflt;",
        "languagesystem grek dflt;",
        "",
    ]
    for glyph_name in glyph_order:
        if glyph_name not in mark_info:
            continue
        _, class_id = mark_info[glyph_name]
        glyph = glyf[glyph_name]
        y = mark_anchor_y(class_id, glyph)
        x = anchor_x(mark_cell_width, y, italic_angle)
        lines.append(
            f"markClass {glyph_name} <anchor {x} {y}> "
            f"@{MARK_CLASSES[class_id]};"
        )

    lines.extend(["", "feature mark {"])
    for glyph_name in attachable_bases:
        glyph = glyf[glyph_name]
        width = hmtx[glyph_name][0]
        top_y = glyph.yMax + 50
        bottom_y = glyph.yMin - 50
        middle_y = rounded((glyph.yMin + glyph.yMax) / 2)
        anchors = [
            (anchor_x(width, top_y, italic_angle), top_y, "MC_top"),
            (anchor_x(width, bottom_y, italic_angle), bottom_y, "MC_bottom"),
            (anchor_x(width, middle_y, italic_angle), middle_y, "MC_overlay"),
            (
                anchor_x(width, -300, italic_angle, double=True),
                -300,
                "MC_double_bottom",
            ),
            (
                anchor_x(width, 800, italic_angle, double=True),
                800,
                "MC_double_top",
            ),
        ]
        positioning = " ".join(
            f"<anchor {x} {y}> mark @{class_name}"
            for x, y, class_name in anchors
        )
        lines.append(f"  pos base {glyph_name} {positioning};")
    lines.extend(["} mark;", "", "feature mkmk {"])

    for glyph_name in glyph_order:
        if glyph_name not in mark_info:
            continue
        _, class_id = mark_info[glyph_name]
        if class_id == 2:
            continue
        glyph = glyf[glyph_name]
        if class_id in (0, 4):
            y1, y2 = glyph.yMax + 50, glyph.yMax + 70
            positioning = (
                f"<anchor {anchor_x(mark_cell_width, y1, italic_angle)} {y1}> "
                f"mark @MC_top "
                f"<anchor {anchor_x(mark_cell_width, y2, italic_angle, double=True)} "
                f"{y2}> mark @MC_double_top"
            )
        else:
            y1, y2 = glyph.yMin - 50, glyph.yMin - 70
            positioning = (
                f"<anchor {anchor_x(mark_cell_width, y1, italic_angle)} {y1}> "
                f"mark @MC_bottom "
                f"<anchor {anchor_x(mark_cell_width, y2, italic_angle, double=True)} "
                f"{y2}> mark @MC_double_bottom"
            )
        lines.append(f"  pos mark {glyph_name} {positioning};")
    lines.extend(["} mkmk;", ""])

    mark_names = [name for name in glyph_order if name in mark_info]
    lines.append(f"@GDEF_Base = [{' '.join(base_names)}];")
    lines.append(f"@GDEF_Mark = [{' '.join(mark_names)}];")
    lines.extend(
        [
            "table GDEF {",
            "  GlyphClassDef @GDEF_Base, , @GDEF_Mark, ;",
            "} GDEF;",
            "",
        ]
    )
    return "\n".join(lines)


def install_mark_positioning(
    font: TTFont,
    mark_info: dict[str, tuple[int, int]],
    base_names: list[str],
    mark_cell_width: int,
) -> None:
    for glyph_name in mark_info:
        _, lsb = font["hmtx"].metrics[glyph_name]
        font["hmtx"].metrics[glyph_name] = (0, lsb)
    features = build_mark_features(font, mark_info, base_names, mark_cell_width)
    addOpenTypeFeaturesFromString(font, features, tables={"GDEF", "GPOS"})


def set_identity(font: TTFont, family: str, ps_family: str, version: str) -> None:
    values = {
        1: family,
        2: "Regular",
        3: f"{version};{ps_family};{ps_family}-Regular",
        4: f"{family} Regular",
        5: f"Version {version}",
        6: f"{ps_family}-Regular",
        16: family,
        17: "Regular",
    }
    for name_id, value in values.items():
        replace_name(font, name_id, value)
    font["head"].fontRevision = float(version)


def repair_fangsong() -> tuple[TTFont, dict[str, tuple[int, int]], list[str]]:
    if not INSTALLED_FANG.exists():
        raise FileNotFoundError(f"Complete source font not found: {INSTALLED_FANG}")
    font = TTFont(INSTALLED_FANG)
    mark_info = collect_marks(font)
    base_names = original_base_names(font, set(mark_info))
    install_mark_positioning(font, mark_info, base_names, 600)

    font["OS/2"].xAvgCharWidth = 600
    font["post"].isFixedPitch = 0
    set_identity(font, "FangSongCode", "FangSongCode", "2.044")
    font.save(FANG_OUTPUT, reorderTables=False)
    return font, mark_info, base_names


def symbol_glyphs_from_reference(source: TTFont) -> set[str]:
    """Recover the old CodeSC punctuation/symbol selection exactly.

    The old CodeSC moved these glyphs by exactly +60. Everything else in a
    1000-unit cell was the horizontally enlarged character class. The empty
    ideographic-space glyph is also treated as a symbol.
    """
    if not INSTALLED_CODE.exists():
        raise FileNotFoundError(f"Reference font not found: {INSTALLED_CODE}")
    reference = TTFont(INSTALLED_CODE)
    source_glyf = source["glyf"]
    reference_glyf = reference["glyf"]
    source_hmtx = source["hmtx"].metrics
    symbols: set[str] = set()
    for name in source.getGlyphOrder():
        if source_hmtx[name][0] != 1000:
            continue
        source_glyph = source_glyf[name]
        target_glyph = reference_glyf[name]
        coordinates = getattr(source_glyph, "coordinates", None)
        if coordinates is None or len(coordinates) == 0:
            symbols.add(name)
            continue
        target_coordinates = getattr(target_glyph, "coordinates", None)
        if target_coordinates is None or len(coordinates) != len(target_coordinates):
            raise RuntimeError(f"Cannot classify wide glyph {name}")
        if all(
            target_x == source_x + 60 and target_y == source_y
            for (source_x, source_y), (target_x, target_y)
            in zip(coordinates, target_coordinates)
        ):
            symbols.add(name)
    return symbols


def transform_simple_glyph(glyph, scale: float, offset: int) -> None:
    coordinates = getattr(glyph, "coordinates", None)
    if coordinates is None:
        return
    for index, (x, y) in enumerate(coordinates):
        coordinates[index] = (rounded(scale * x + offset), y)


def recalc_horizontal_metrics(font: TTFont) -> None:
    glyf = font["glyf"]
    hmtx = font["hmtx"].metrics
    for name in font.getGlyphOrder():
        glyph = glyf[name]
        if glyph.isComposite():
            glyph.recalcBounds(glyf)
        advance, old_lsb = hmtx[name]
        lsb = glyph.xMin if hasattr(glyph, "xMin") else old_lsb
        hmtx[name] = (advance, lsb)

    extents = []
    for name in font.getGlyphOrder():
        glyph = glyf[name]
        advance, lsb = hmtx[name]
        if hasattr(glyph, "xMin") and hasattr(glyph, "xMax"):
            width = glyph.xMax - glyph.xMin
            extents.append((advance, lsb, advance - lsb - width, lsb + width))
        else:
            extents.append((advance, lsb, advance - lsb, lsb))
    hhea = font["hhea"]
    hhea.advanceWidthMax = max(item[0] for item in extents)
    hhea.minLeftSideBearing = min(item[1] for item in extents)
    hhea.minRightSideBearing = min(item[2] for item in extents)
    hhea.xMaxExtent = max(item[3] for item in extents)


def rebuild_codesc(
    scale: float,
    output: Path,
    mark_info: dict[str, tuple[int, int]],
    base_names: list[str],
    symbols: set[str],
) -> None:
    # Reload the just-saved file so all compiled tables and glyph bounds are
    # in the same state users will receive.
    font = TTFont(FANG_OUTPUT)
    glyf = font["glyf"]
    hmtx = font["hmtx"].metrics
    character_offset = rounded((1120 - 1000 * scale) / 2)

    for name in font.getGlyphOrder():
        glyph = glyf[name]
        advance, lsb = hmtx[name]
        if advance == 600:
            # Components are not moved: all 661 composites reference only
            # other 600-unit glyphs, whose outlines receive this same shift.
            if not glyph.isComposite():
                transform_simple_glyph(glyph, 1.0, -20)
            hmtx[name] = (560, lsb - 20)
        elif advance == 0 and name in mark_info:
            transform_simple_glyph(glyph, 1.0, -20)
            hmtx[name] = (0, lsb - 20)
        elif advance == 1000:
            if name in symbols:
                transform_simple_glyph(glyph, 1.0, 60)
                hmtx[name] = (1120, lsb + 60)
            else:
                transform_simple_glyph(glyph, scale, character_offset)
                hmtx[name] = (
                    1120,
                    rounded(lsb * scale + character_offset),
                )
        else:
            raise RuntimeError(f"Unexpected advance width {advance} for {name}")

    # Recalculate simple bounds after direct coordinate edits, then composite
    # bounds and all horizontal metric extrema.
    for name in font.getGlyphOrder():
        glyph = glyf[name]
        if not glyph.isComposite():
            glyph.recalcBounds(glyf)
    recalc_horizontal_metrics(font)

    # Coordinates changed, so old per-glyph TrueType instructions are unsafe.
    for name in font.getGlyphOrder():
        glyph = glyf[name]
        if hasattr(glyph, "program"):
            glyph.program.fromBytecode([])

    install_mark_positioning(font, mark_info, base_names, 560)
    font["OS/2"].xAvgCharWidth = 560
    font["post"].isFixedPitch = 1
    set_identity(font, "CodeSC", "CodeSC", "2.044")
    font.save(output, reorderTables=False)

    print(
        f"{output}: scale={scale:.2f}, offset={character_offset}, "
        f"symbols={len(symbols)}, characters={21522 - len(symbols)}"
    )


def verify_project_relationship() -> None:
    """Refuse to proceed if the local file is not the audited source."""
    if not PROJECT_FANG.exists():
        raise FileNotFoundError(PROJECT_FANG)
    installed = TTFont(INSTALLED_FANG)
    project = TTFont(PROJECT_FANG)
    installed_names = set(installed.getGlyphOrder())
    project_names = set(project.getGlyphOrder())
    missing = installed_names - project_names
    expected = {f"uni{codepoint:04X}" for codepoint in range(0xE7E7, 0xE7F4)}
    if missing != expected or project_names - installed_names:
        raise RuntimeError("Project FangSongCode no longer matches the audited source")


def main() -> None:
    verify_project_relationship()
    _, marks, bases = repair_fangsong()
    symbols = symbol_glyphs_from_reference(TTFont(INSTALLED_FANG))
    for scale, output in CODE_OUTPUTS.items():
        rebuild_codesc(scale, output, marks, bases, symbols)
    print(f"Wrote {FANG_OUTPUT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise
