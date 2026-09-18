#!/usr/bin/env python3
"""Pair the "retro" loading pictures with ours and cut them to our frame.

A player sent 8-bit-looking redraws of the six loading backgrounds
(NEWGFX/, 2026-09-11). They come as 320x196 / 320x200 files plus the large
originals they were made from. Ours are 320x184: the band under the picture
holds the progress bars and the corner logo.

Pairing is by scene, and it is recorded in the file NAME: intro/retro/X.png
is the retro version of intro/X.png, so build/gen_splash.py emits both sets in
the same order and one random pick shows the same scene in either style.

Cutting: the pictures are downscales (their 320x196 matches a Lanczos 4x
reduction of the 1280x784 original, mean error 2.2 of 255), so they are cut,
not resized again - an even number of rows off the top and the bottom.

The war room had no small version. It is made the way the sender made the
others: the 1363x784 original cropped to 1280x784 around its centre, reduced
4x with Lanczos to 320x196, then cut like the rest.

  usage: prep_retro_intro.py [NEWGFX dir] [intro dir]
"""
import os
import sys

from PIL import Image

W, H = 320, 184

# ours (intro/)              <- theirs (NEWGFX/)
PAIRS = (
    ("amixcom_47383.png", "320x200/320x200 (3).png"),   # autopsy
    ("amixcom_47387.png", "320x200/320x200 (5).png"),   # psionic panic
    ("amixcom_47389.png", "320x200/320x200 (4).png"),   # squad in the hangar
    ("amixcom_47394.png", "320x200/320x200 (6).png"),   # cattle abduction
    ("amixcom_47398.png", "320x200/320x200 (1).png"),   # UFO in the sea
    ("amixcom_47400.png", "full-res (3).png"),          # war room: no small one sent
)


def small_from_large(im):
    """The sender's own method: centre-crop to 1280x784, Lanczos to 320x196."""
    cw = min(im.width, im.height * 1280 // 784)
    x0 = (im.width - cw) // 2
    return im.crop((x0, 0, x0 + cw, im.height)).resize((320, 196), Image.LANCZOS)


def cut(im):
    if im.width != W or im.height < H:
        sys.exit("unexpected size %s" % (im.size,))
    top = (im.height - H) // 2
    return im.crop((0, top, W, top + H))


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "NEWGFX"
    dst_root = sys.argv[2] if len(sys.argv) > 2 else "intro"
    dst = os.path.join(dst_root, "retro")
    os.makedirs(dst, exist_ok=True)
    for ours, theirs in PAIRS:
        if not os.path.isfile(os.path.join(dst_root, ours)):
            sys.exit("no %s in %s - the pairing is by name" % (ours, dst_root))
        im = Image.open(os.path.join(src, theirs)).convert("RGB")
        if im.width > 400:
            im = small_from_large(im)
        out = cut(im)
        out.save(os.path.join(dst, ours))
        print("%-20s <- %-26s %s -> %dx%d" % (ours, theirs, im.size, W, H))
    return 0


if __name__ == "__main__":
    sys.exit(main())
