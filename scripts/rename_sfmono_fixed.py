#!/usr/bin/env python3
"""Restore the repaired SF Mono files to their production family identity."""

from pathlib import Path

from fontTools.ttLib import TTFont


FONT_DIR = Path("SourceCodePro as SFMono")

STYLES = {
    "R": {
        "subfamily": "Regular",
        "ps_style": "Regular",
        "mac_style": 0,
        "fs_selection": 0x40,
        "weight": 400,
        "italic_angle": 0.0,
        "caret": (1, 0),
    },
    "B": {
        "subfamily": "Bold",
        "ps_style": "Bold",
        "mac_style": 1,
        "fs_selection": 0x20,
        "weight": 700,
        "italic_angle": 0.0,
        "caret": (1, 0),
    },
    "I": {
        "subfamily": "Italic",
        "ps_style": "Italic",
        "mac_style": 2,
        "fs_selection": 0x01,
        "weight": 400,
        "italic_angle": -11.0,
        "caret": (100, 19),
    },
    "Z": {
        "subfamily": "Bold Italic",
        "ps_style": "BoldItalic",
        "mac_style": 3,
        "fs_selection": 0x21,
        "weight": 700,
        "italic_angle": -11.0,
        "caret": (100, 19),
    },
}


def replace_name(font: TTFont, name_id: int, value: str) -> None:
    for record in font["name"].names:
        if record.nameID == name_id:
            record.string = value.encode(record.getEncoding())


def restore_style(code: str, properties: dict[str, object]) -> None:
    source = FONT_DIR / f"SFMono-{code}-fixed.ttf"
    target = FONT_DIR / f"SFMono-{code}.ttf"
    temporary = FONT_DIR / f".SFMono-{code}.renaming.ttf"

    if not source.exists():
        raise FileNotFoundError(source)
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite existing target: {target}")

    font = TTFont(source)
    subfamily = str(properties["subfamily"])
    ps_style = str(properties["ps_style"])

    names = {
        1: "SF Mono",
        2: subfamily,
        3: f"2.043;SFMono;SFMono-{ps_style}",
        4: f"SF Mono {subfamily}",
        5: "Version 2.043",
        6: f"SFMono-{ps_style}",
    }
    for name_id, value in names.items():
        replace_name(font, name_id, value)

    font["head"].fontRevision = 2.043
    font["head"].macStyle = int(properties["mac_style"])
    font["OS/2"].fsSelection = int(properties["fs_selection"])
    font["OS/2"].usWeightClass = int(properties["weight"])
    font["post"].italicAngle = float(properties["italic_angle"])
    rise, run = properties["caret"]
    font["hhea"].caretSlopeRise = int(rise)
    font["hhea"].caretSlopeRun = int(run)
    font["hhea"].caretOffset = 0

    font.save(temporary, reorderTables=False)

    # Validate the written file before replacing the fixed-name input.
    check = TTFont(temporary)
    expected = ("SF Mono", subfamily, f"SFMono-{ps_style}")
    actual = tuple(check["name"].getDebugName(i) for i in (1, 2, 6))
    if actual != expected:
        raise RuntimeError(f"Name verification failed for {temporary}: {actual}")
    for tag in ("GDEF", "GPOS", "GSUB"):
        check[tag].compile(check)
    check.close()

    temporary.replace(target)
    source.unlink()
    print(f"Renamed {source.name} -> {target.name}")


def main() -> None:
    for code, properties in STYLES.items():
        restore_style(code, properties)


if __name__ == "__main__":
    main()
