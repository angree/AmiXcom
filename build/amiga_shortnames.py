#!/usr/bin/env python3
"""Keep every name under data/ within the 30 characters an Amiga filesystem allows.

FFS truncates a longer name to 30 characters. Upstream's optional mods have
directory names up to 46 characters, and two of them share their first 30
("XcomUtil_Starting_Defensive_Improved_Base" and "..._TFTD"), so unpacking on
the Amiga asks "replace?" and one of them is lost (reported, 0.9.10). The
engine takes a mod's id from metadata.yml when it has one and from the
directory name otherwise, so a directory can be renamed as long as an `id:`
line keeps the old name - options.cfg entries then stay valid.

Rules, applied only to names over the limit (short ones are left alone):
  directories   abbreviate (table below), then assert <= 30 and unique;
                write `id: <old name>` into metadata.yml if it has none
  .rul files    same abbreviation on the stem, then the stem is cut to 26
  OpenGL        *.OpenGL.shader files are removed: there is no OpenGL here,
                and "5xBR_Semi-Rounded.OpenGL.shader" is 31 characters

Idempotent: a second run finds nothing to do. Run on the unpacked upstream
bin/ before deploy and on the deploy itself (build.sh does both), and on the
release folder by the packer.

  usage: amiga_shortnames.py <data dir>     (the dir that holds standard/)
"""
import os
import shutil
import sys

LIMIT = 30
STEM_LIMIT = 26                     # + ".rul" or ".sav" = 30

ABBREV = (
    ("XcomUtil_", "XU_"),
    ("UFOextender_", "UFOx_"),
    ("StrategyCore_", "SC_"),
    ("OpenXCom_", "OXC_"),
    ("Starting_", "Start_"),
    ("Defensive_", "Def_"),
    ("Improved_", "Impr_"),
    ("Capacities", "Caps"),
)


def shorten(name):
    for old, new in ABBREV:
        name = name.replace(old, new)
    return name


def add_id(metadata, mod_id):
    if not os.path.isfile(metadata):
        return
    text = open(metadata, encoding="utf-8", errors="replace").read()
    for line in text.splitlines():
        if line.strip().startswith("id:"):
            return
    if not text.endswith("\n"):
        text += "\n"
    text += "\n# AMIGA-PORT: the directory was renamed to fit a 30-character\n"
    text += "# filesystem; this keeps the id the engine and options.cfg use.\n"
    text += "id: %s\n" % mod_id
    open(metadata, "w", encoding="utf-8", newline="\n").write(text)


def main():
    if len(sys.argv) != 2 or not os.path.isdir(sys.argv[1]):
        sys.exit("usage: amiga_shortnames.py <data dir>")
    root = sys.argv[1]
    std = os.path.join(root, "standard")
    renamed = 0

    if os.path.isdir(std):
        for d in sorted(os.listdir(std)):
            path = os.path.join(std, d)
            if not os.path.isdir(path) or len(d) <= LIMIT:
                continue
            short = shorten(d)
            if len(short) > LIMIT:
                sys.exit("%s: still %d characters after abbreviation" % (d, len(short)))
            target = os.path.join(std, short)
            if os.path.exists(target):
                # a fresh long-named copy next to an already renamed one
                # (build.sh copies upstream bin/ without overwriting): the
                # renamed one is the same mod, drop the newcomer
                shutil.rmtree(path)
                print("  %s: duplicate of %s, removed" % (d, short))
                continue
            add_id(os.path.join(path, "metadata.yml"), d)
            os.rename(path, target)
            renamed += 1
            print("  %-46s -> %s" % (d, short))

    # files: over-long .rul stems, and OpenGL shaders nobody can use
    for dirpath, dirnames, filenames in os.walk(root):
        for f in filenames:
            if f.endswith(".OpenGL.shader"):
                os.remove(os.path.join(dirpath, f))
                renamed += 1
                print("  %s: removed (OpenGL)" % f)
                continue
            if len(f) <= LIMIT:
                continue
            stem, ext = os.path.splitext(f)
            stem = shorten(stem)[:STEM_LIMIT]
            new = stem + ext
            target = os.path.join(dirpath, new)
            if os.path.exists(target):
                sys.exit("%s: %s already exists" % (f, new))
            os.rename(os.path.join(dirpath, f), target)
            renamed += 1
            print("  %-46s -> %s" % (f, new))

    # prove it
    for dirpath, dirnames, filenames in os.walk(root):
        for n in dirnames + filenames:
            if len(n) > LIMIT:
                sys.exit("still over %d characters: %s/%s" % (LIMIT, dirpath, n))
    print("amiga_shortnames: %d renamed, every name within %d characters" % (renamed, LIMIT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
