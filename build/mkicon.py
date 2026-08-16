#!/usr/bin/env python3
"""
Generate classic AmigaOS .info icons for the release: tool icons for the
three binaries (with the 1 MB stack the game needs written into the icon,
so a Workbench start gets it too) and IconX project icons for the run scripts.

Usage: mkicon.py <output-dir>
"""
import math
import os
import struct
import sys

W, H, DEPTH = 48, 26, 2       # 2 planes = Workbench colours 0..3
NO_POS = 0x80000000


def draw(selected):
    """Return list of rows, each a list of colour indices 0..3
    (0 grey, 1 black, 2 white, 3 blue)."""
    px = [[0] * W for _ in range(H)]
    # frame
    for x in range(W):
        px[0][x] = 1
        px[H - 1][x] = 1
    for y in range(H):
        px[y][0] = 1
        px[y][W - 1] = 1
    # globe: blue disc with a white highlight
    cx, cy, r = 13, 13, 9
    for y in range(H):
        for x in range(W):
            d = math.hypot(x - cx, (y - cy) * 1.15)
            if d <= r:
                px[y][x] = 3
            if d <= r and math.hypot(x - cx + 3, (y - cy + 3) * 1.15) <= 3:
                px[y][x] = 2
            if r < d <= r + 0.9:
                px[y][x] = 1
    # a big X to the right (2 px thick diagonals)
    x0, x1, y0, y1 = 27, 44, 4, H - 5
    for t in range(0, 100):
        f = t / 99.0
        for dx in (0, 1):
            xa = int(round(x0 + f * (x1 - x0))) + dx
            ya = int(round(y0 + f * (y1 - y0)))
            xb = int(round(x1 - f * (x1 - x0))) + dx
            if 0 < xa < W - 1 and 0 < ya < H - 1:
                px[ya][xa] = 1
            if 0 < xb < W - 1 and 0 < ya < H - 1:
                px[ya][xb] = 1
    if selected:
        for y in range(H):
            for x in range(W):
                if px[y][x] == 0:
                    px[y][x] = 3
                elif px[y][x] == 3:
                    px[y][x] = 0
    return px


def planes(px):
    row_bytes = ((W + 15) // 16) * 2
    out = bytearray()
    for p in range(DEPTH):
        for y in range(H):
            row = bytearray(row_bytes)
            for x in range(W):
                if (px[y][x] >> p) & 1:
                    row[x >> 3] |= 0x80 >> (x & 7)
            out += row
    return bytes(out)


def image(px):
    data = planes(px)
    hdr = struct.pack(">hhhhhIBBI", 0, 0, W, H, DEPTH, 1, (1 << DEPTH) - 1, 0, 0)
    return hdr + data


def icon(kind, default_tool=None, tooltypes=(), stack=0):
    """kind: 3 = tool, 4 = project."""
    gadget = struct.pack(">IhhhhHHHIIIIIHI",
                         0, 0, 0, W, H,
                         0x0005,       # GADGIMAGE | GADGHBOX
                         0x0003,       # RELVERIFY | GADGIMMEDIATE
                         0x0001,       # BOOLGADGET
                         1, 1,         # GadgetRender, SelectRender (non-zero = present)
                         0, 0, 0, 0, 0)
    body = struct.pack(">HH", 0xE310, 1) + gadget
    body += struct.pack(">BBIIIIIIi", kind, 0,
                        1 if default_tool else 0,
                        1 if tooltypes else 0,
                        NO_POS, NO_POS,
                        0, 0, stack)
    assert len(body) == 78, len(body)
    body += image(draw(False)) + image(draw(True))
    if default_tool:
        s = default_tool.encode("latin-1") + b"\0"
        body += struct.pack(">I", len(s)) + s
    if tooltypes:
        body += struct.pack(">I", (len(tooltypes) + 1) * 4)
        for t in tooltypes:
            s = t.encode("latin-1") + b"\0"
            body += struct.pack(">I", len(s)) + s
    return body


def main():
    out = sys.argv[1]
    for name in ("openxcom-aga", "openxcom-rtg", "openxcom-ask"):
        with open(os.path.join(out, name + ".info"), "wb") as f:
            f.write(icon(3, stack=1000000))
    for name in ("run", "run-rtg", "run-ask"):
        with open(os.path.join(out, name + ".info"), "wb") as f:
            f.write(icon(4, default_tool="C:IconX", tooltypes=("STACK=1000000",),
                         stack=8192))
    print("icons written to", out)


if __name__ == "__main__":
    main()
