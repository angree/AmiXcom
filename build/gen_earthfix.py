#!/usr/bin/env python3
"""Precomputed globe shadow normals (AMIGA-PORT).

The first drawShadow() on each zoom level filled a 256x200 table of Q1.14
sphere normals - 307k soft-double sqrt calls, ~5 s per level on a -70% 040/40
(the "first zoom is horribly slow" complaint). The formula depends only on
the fixed 256x200 globe area and the six fixed zoom radii, so this script
computes all six tables once at build time; the game just freads the level
it needs (Globe.cpp, lazy fill in drawShadow).

Format (big-endian):
  'EFX1' | u16 width | u16 height | u16 levels | levels * u32 round(r*256)
  | levels * width*height * (s16 x, s16 y, s16 z)   # Q1.14, cordToFix rounding
"""
import math, struct, sys

W, H = 256, 200
RADII = [0.45 * H, 0.60 * H, 0.90 * H, 1.40 * H, 2.25 * H, 3.60 * H]

def fix(v):
    return int(math.floor(v * 16384.0 + 0.5))

def main(out_path):
    buf = bytearray()
    buf += b"EFX1"
    buf += struct.pack(">HHH", W, H, len(RADII))
    for r in RADII:
        buf += struct.pack(">I", int(round(r * 256.0)))
    for r in RADII:
        ox, oy = W / 2, H / 2
        limit = r * r
        norm = 1.0 / r
        for j in range(H):
            y = (j + 0.5) - oy
            for i in range(W):
                x = (i + 0.5) - ox
                temp = x * x + y * y
                if limit > temp:
                    cx, cy = x * norm, y * norm
                    cz = math.sqrt(limit - temp) * norm
                    fx, fy, fz = fix(cx), fix(cy), fix(cz)
                    if cz != 0.0 and fz == 0:
                        fz = 1
                else:
                    fx = fy = fz = 0
                buf += struct.pack(">hhh", fx, fy, fz)
    with open(out_path, "wb") as f:
        f.write(buf)
    print("earthfix: %s (%d bytes, %d levels)" % (out_path, len(buf), len(RADII)))

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "earthfix.dat")
