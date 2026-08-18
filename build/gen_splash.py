#!/usr/bin/env python3
"""Loading-splash assets (AMIGA-PORT).

Converts the PNGs in intro/ into the flat 8-bit chunky format the splash
module (native/amiga_splash.c) blits straight into the display buffer while
the mods load. Done on the PC at build time - the Amiga just freads.

Palette layout (one 256-entry palette per background file):
  0..229   background colours (quantised per image)
  230..252 logo colours (shared across all backgrounds)
  253      progress-bar fill (muted blue-green)
  254      black (bar background / bottom band)
  255      transparent marker in the logo data (never displayed)

Files (big-endian):
  bgN.spl : 'SPL1' u16 w u16 h  palette[256*3]  pixels[w*h]
  logo.spl: 'SPLG' u16 w u16 h  pixels[w*h]     (255 = transparent)
"""
import glob, os, struct, sys
from PIL import Image

BAR_FILL = (76, 140, 148)   # stonowany niebieski z domieszka zieleni
BLACK = (0, 0, 0)

def quant_logo(path):
    im = Image.open(path).convert("RGBA")
    rgb = im.convert("RGB")
    q = rgb.quantize(colors=23, method=Image.MEDIANCUT)
    pal = q.getpalette()[: 23 * 3]
    px = q.load()
    a = im.split()[3].load()
    data = bytearray()
    for y in range(im.height):
        for x in range(im.width):
            data.append(255 if a[x, y] <= 128 else 230 + px[x, y])
    return im.width, im.height, pal, bytes(data)

def main(intro_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    lw, lh, logo_pal, logo_px = quant_logo(os.path.join(intro_dir, "small_amixcom_logo.png"))
    with open(os.path.join(out_dir, "logo.spl"), "wb") as f:
        f.write(b"SPLG" + struct.pack(">HH", lw, lh) + logo_px)
    print("logo.spl %dx%d" % (lw, lh))

    bgs = sorted(g for g in glob.glob(os.path.join(intro_dir, "*.png"))
                 if "logo" not in os.path.basename(g).lower())
    for n, path in enumerate(bgs):
        im = Image.open(path).convert("RGB")
        q = im.quantize(colors=230, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG)
        bpal = q.getpalette()[: 230 * 3]
        pal = bytearray(768)
        pal[: len(bpal)] = bpal
        pal[230 * 3: 230 * 3 + len(logo_pal)] = logo_pal
        pal[253 * 3: 253 * 3 + 3] = bytes(BAR_FILL)
        pal[254 * 3: 254 * 3 + 3] = bytes(BLACK)
        pal[255 * 3: 255 * 3 + 3] = bytes(BLACK)
        with open(os.path.join(out_dir, "bg%d.spl" % n), "wb") as f:
            f.write(b"SPL1" + struct.pack(">HH", im.width, im.height))
            f.write(bytes(pal))
            f.write(q.tobytes())
        print("bg%d.spl %dx%d <- %s" % (n, im.width, im.height, os.path.basename(path)))
    print("splash: %d backgrounds" % len(bgs))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
