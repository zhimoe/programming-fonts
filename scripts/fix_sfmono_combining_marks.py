#!/usr/bin/env python3
"""Repair combining-mark shaping in the four local SF Mono styles.

The source fonts classify every glyph as a base and give combining marks a
600-unit advance.  This script makes Unicode marks zero-width GDEF marks and
adds geometry-derived mark-to-base and mark-to-mark GPOS anchors.
"""

from __future__ import annotations

import math
import sys
import unicodedata
from pathlib import Path

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.ttLib import TTFont


FONT_DIR = Path("SourceCodePro as SFMono")
SOURCES = [
    FONT_DIR / "SFMono-R.ttf",
    FONT_DIR / "SFMono-B.ttf",
    FONT_DIR / "SFMono-I.ttf",
    FONT_DIR / "SFMono-Z.ttf",
]

CLASS_NAMES = {
    0: "MC_top",
    1: "MC_bottom",
    2: "MC_overlay",
    3: "MC_double_bottom",
    4: "MC_double_top",
}

# The outlines of the two italic styles use an 11-degree slant even though
# the source files report -10 in their post and hhea metadata.
ITALIC_ANGLE_OVERRIDES = {
    "SFMono-I.ttf": -11.0,
    "SFMono-Z.ttf": -11.0,
}


def rounded(value: float) -> int:
    """Round halves away from zero for stable integer font coordinates."""
    if value >= 0:
        return math.floor(value + 0.5)
    return math.ceil(value - 0.5)


def anchor_x(width: int, y: int, italic_angle: float, *, double: bool = False) -> int:
    """Return an anchor on the font's slant axis at height *y*."""
    origin = width if double else width / 2
    return rounded(origin - math.tan(math.radians(italic_angle)) * y)


def replace_name(font: TTFont, name_id: int, value: str) -> None:
    for record in font["name"].names:
        if record.nameID == name_id:
            record.string = value.encode(record.getEncoding())


def mark_class(codepoint: int, glyph) -> int:
    if codepoint == 0x0334:
        return 2  # overlay
    if codepoint == 0x035F:
        return 3  # double mark below
    if codepoint == 0x0361:
        return 4  # double mark above
    return 1 if glyph.yMax < 200 else 0


def mark_anchor_y(class_id: int, glyph) -> int:
    if class_id in (0, 4):
        return glyph.yMin
    if class_id in (1, 3):
        return glyph.yMax
    return rounded((glyph.yMin + glyph.yMax) / 2)


def build_features(
    font: TTFont,
    mark_info: dict[str, tuple[int, int]],
    italic_angle: float,
) -> str:
    glyph_order = font.getGlyphOrder()
    glyf = font["glyf"]
    hmtx = font["hmtx"]
    mark_names = set(mark_info)

    base_names = [g for g in glyph_order if g != ".notdef" and g not in mark_names]
    attachable_bases = [
        g
        for g in base_names
        if getattr(glyf[g], "numberOfContours", 0) != 0
        and hasattr(glyf[g], "yMin")
        and hasattr(glyf[g], "yMax")
    ]

    lines = [
        "languagesystem DFLT dflt;",
        "languagesystem latn dflt;",
        "languagesystem cyrl dflt;",
        "languagesystem grek dflt;",
        "",
    ]

    # Declare the five attachment classes.
    for glyph_name in glyph_order:
        if glyph_name not in mark_info:
            continue
        codepoint, class_id = mark_info[glyph_name]
        glyph = glyf[glyph_name]
        width = 600  # source mark cell before its advance is changed to zero
        y = mark_anchor_y(class_id, glyph)
        x = anchor_x(width, y, italic_angle)
        lines.append(
            f"markClass {glyph_name} <anchor {x} {y}> @{CLASS_NAMES[class_id]};"
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
            (anchor_x(width, -300, italic_angle, double=True), -300, "MC_double_bottom"),
            (anchor_x(width, 800, italic_angle, double=True), 800, "MC_double_top"),
        ]
        positioning = " ".join(
            f"<anchor {x} {y}> mark @{class_name}" for x, y, class_name in anchors
        )
        lines.append(f"  pos base {glyph_name} {positioning};")
    lines.extend(["} mark;", "", "feature mkmk {"])

    # Stack top marks above top marks and bottom marks below bottom marks.
    # Overlay marks do not form a useful stacking surface.
    for glyph_name in glyph_order:
        if glyph_name not in mark_info:
            continue
        _, class_id = mark_info[glyph_name]
        if class_id == 2:
            continue
        glyph = glyf[glyph_name]
        width = 600
        if class_id in (0, 4):
            y1, y2 = glyph.yMax + 50, glyph.yMax + 70
            positioning = (
                f"<anchor {anchor_x(width, y1, italic_angle)} {y1}> mark @MC_top "
                f"<anchor {anchor_x(width, y2, italic_angle, double=True)} {y2}> mark @MC_double_top"
            )
        else:
            y1, y2 = glyph.yMin - 50, glyph.yMin - 70
            positioning = (
                f"<anchor {anchor_x(width, y1, italic_angle)} {y1}> mark @MC_bottom "
                f"<anchor {anchor_x(width, y2, italic_angle, double=True)} {y2}> mark @MC_double_bottom"
            )
        lines.append(f"  pos mark {glyph_name} {positioning};")
    lines.extend(["} mkmk;", ""])

    lines.append(f"@GDEF_Base = [{' '.join(base_names)}];")
    lines.append(f"@GDEF_Mark = [{' '.join(g for g in glyph_order if g in mark_names)}];")
    lines.extend(
        [
            "table GDEF {",
            "  GlyphClassDef @GDEF_Base, , @GDEF_Mark, ;",
            "} GDEF;",
            "",
        ]
    )
    return "\n".join(lines)


def repair(source: Path) -> Path:
    font = TTFont(source)
    cmap = font.getBestCmap()
    glyf = font["glyf"]

    mark_info: dict[str, tuple[int, int]] = {}
    for codepoint, glyph_name in cmap.items():
        if not unicodedata.category(chr(codepoint)).startswith("M"):
            continue
        glyph = glyf[glyph_name]
        mark_info[glyph_name] = (codepoint, mark_class(codepoint, glyph))

    if len(mark_info) != 54:
        raise RuntimeError(
            f"{source}: expected 54 combining marks, found {len(mark_info)}"
        )

    italic_angle = ITALIC_ANGLE_OVERRIDES.get(source.name, font["post"].italicAngle)
    features = build_features(font, mark_info, italic_angle)
    addOpenTypeFeaturesFromString(font, features, tables={"GDEF", "GPOS"})

    # Combining marks must not consume a terminal cell.
    for glyph_name in mark_info:
        _, lsb = font["hmtx"][glyph_name]
        font["hmtx"][glyph_name] = (0, lsb)

    if italic_angle:
        font["post"].italicAngle = italic_angle
        font["hhea"].caretSlopeRise = 100
        font["hhea"].caretSlopeRun = rounded(
            math.tan(math.radians(-italic_angle)) * 100
        )
        font["hhea"].caretOffset = 0

    style = font["name"].getDebugName(2) or "Regular"
    style_ps = style.replace(" ", "")
    replacement_names = {
        1: "SF Mono Fixed",
        3: f"2.043;SFMonoFixed;SFMonoFixed-{style_ps}",
        4: f"SF Mono Fixed {style}",
        5: "Version 2.043",
        6: f"SFMonoFixed-{style_ps}",
    }
    for name_id, value in replacement_names.items():
        replace_name(font, name_id, value)
    font["head"].fontRevision = 2.043

    output = source.with_name(f"{source.stem}-fixed.ttf")
    font.save(output, reorderTables=False)
    return output


def main() -> None:
    sources = [Path(arg) for arg in sys.argv[1:]] or SOURCES
    for source in sources:
        output = repair(source)
        print(f"Wrote {output}")


if __name__ == "__main__":
    main()
