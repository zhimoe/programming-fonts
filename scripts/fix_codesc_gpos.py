#!/usr/bin/env python3
"""Remove the two malformed pair-positioning lookups from CodeSC.ttf.

The valid mark-to-base and mark-to-mark lookups are retained so decomposed
Unicode combining accents continue to attach to their base letters.
"""

from pathlib import Path

from fontTools.ttLib import TTFont


SOURCE = Path("CodeSC.ttf")
OUTPUT = Path("CodeSC-fixed.ttf")


def replace_name(font: TTFont, name_id: int, value: str) -> None:
    """Replace every existing localized record for a name ID."""
    for record in font["name"].names:
        if record.nameID == name_id:
            record.string = value.encode(record.getEncoding())


def main() -> None:
    font = TTFont(SOURCE)
    gpos = font["GPOS"].table

    old_lookups = gpos.LookupList.Lookup
    if [lookup.LookupType for lookup in old_lookups] != [9, 2, 2, 6]:
        raise RuntimeError("Unexpected GPOS layout; refusing to modify the font")

    # Old lookup indexes 1 and 2 contain PairPos rules such as
    #   a + bar -> move the first glyph vertically.
    # Keep lookup 0 (mark-to-base) and lookup 3 (mark-to-mark).
    gpos.LookupList.Lookup = [old_lookups[0], old_lookups[3]]
    gpos.LookupList.LookupCount = 2

    for feature_record in gpos.FeatureList.FeatureRecord:
        if feature_record.FeatureTag == "mark":
            feature_record.Feature.LookupListIndex = [0]
            feature_record.Feature.LookupCount = 1
        elif feature_record.FeatureTag == "mkmk":
            feature_record.Feature.LookupListIndex = [1]
            feature_record.Feature.LookupCount = 1
        else:
            raise RuntimeError(
                f"Unexpected GPOS feature {feature_record.FeatureTag!r}; refusing to modify"
            )

    # Give the repaired font a distinct identity so Windows can install it next
    # to the original without returning a stale font-cache entry.
    replacement_names = {
        1: "CodeSC Fixed",
        3: "2.043;CodeSCFixed;CodeSCFixed-Regular",
        4: "CodeSC Fixed Regular",
        5: "Version 2.043",
        6: "CodeSCFixed-Regular",
        16: "CodeSC Fixed",
        17: "Regular",
    }
    for name_id, value in replacement_names.items():
        replace_name(font, name_id, value)
    font["head"].fontRevision = 2.043

    font.save(OUTPUT, reorderTables=False)
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
