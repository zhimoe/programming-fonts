import sys
import os

from fontTools import ttLib

def main(argv):
    # command argument tests
    if len(argv) < 2:
        exit_with_error_msg(f"""
        [fontname.py] ERROR: you did not include enough arguments to the script."
        Usage: python3 fontname.py [NEW FAMILY NAME] [FONT PATH 1] <FONT PATH 2 ...>"
        """)
    try:
        new_family_name = str(argv[0])  # the first argument is the new typeface name
    except Exception as e:
        exit_with_error_msg(f"[fontname.py] ERROR: unable to convert argument 1 to string.")

    # all remaining arguments on command line are file paths to fonts
    font_path_list = argv[1:]

    # iterate through all paths provided on command line and rename to `new_font_name` defined by user
    for font_path in font_path_list:
        if not file_exists(font_path):
            exit_with_error_msg(f"[fontname.py] ERROR: the path '{font_path}' does not appear to be a valid file path.")

        tt = ttLib.TTFont(font_path)
        name_records = tt["name"].names
        # ------------------
        style = get_font_style(font_path, name_records)

        """
        PlatformID == 1
        NameRecord.nameID   |   String ID
        record.nameID==0        Copyright
        record.nameID==1        Family
        record.nameID==2        Styles(SubFamily): Regular/Bold/Italic/Bold Italic
        record.nameID==3        UniqueID
        record.nameID==4        Fullname: {family} {style}
        record.nameID==5        Version
        record.nameID==6        Postscript Fullname: {family no space}-{style}
        record.nameID==11       Preferred Family:
        record.nameID==12       Preferred Styles:
        """

        # Postscript name
        # - no spaces allowed in family name or the PostScript suffix. should be dash delimited
        postscript_name = f"{new_family_name.replace(' ', '')}-{style.replace(' ', '')}"

        # modify the opentype table data in memory with updated values
        for i in range(len(name_records) - 1, -1, -1):
            record = name_records[i]
            if record.nameID == 1:
                record.string = new_family_name
            elif record.nameID == 4:
                record.string = f"{new_family_name} {style}"
            elif record.nameID == 6:
                record.string = postscript_name
            else:
                ...
                # TODO: delete other table data like WS family name
                # del name_records[i]
        try:
            tt.save(font_path)
            print(f"[OK] Updated '{font_path}' with the name '{new_family_name}'")
        except Exception as e:
            exit_with_error_msg(f"""
            [fontname.py] ERROR: unable to write new name to OpenType name table for {font_path}.            
            """)


def get_font_style(font_path, name_records) -> str:
    style = ""
    # determine font style for this file path from name record nameID 2
    for record in name_records:
        if record.nameID == 2:
            style = str(record)
            break

    # test that a style name was found in the OpenType tables of the font
    if len(style) == 0:
        exit_with_error_msg(f"""
        [fontname.py] ERROR: unable to detect the font style from the OpenType name table in {font_path}.
                      Unable to complete execution of the script.
        """)
    return style


def exit_with_error_msg(err_msg):
    sys.stderr.write(err_msg)
    sys.exit(1)


def file_exists(filepath):
    """Tests for existence of a file on the string filepath"""
    return os.path.exists(filepath) and os.path.isfile(filepath)


if __name__ == "__main__":
    main(sys.argv[1:])
