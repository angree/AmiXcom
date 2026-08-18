#!/usr/bin/env python3
"""
Generate classic AmigaOS .info icons for the release: tool icons for the
binaries (with the 1 MB stack the game needs written into the icon, so a
Workbench start gets it too) and IconX project icons for the run scripts.

Format follows the OpenTTD 68k port's icon, which renders correctly here:
one image only (no SelectRender - Intuition complements the image when the
icon is selected) and Gadget flags GFLG_GADGIMAGE|GFLG_GADGHCOMP = 0x0004.
The earlier version used 0x0005 (GADGHBOX) plus a second image, which is
what the "see-through / broken" icons were.

Nothing is drawn in pen 0. Pen 0 is the Workbench background pen, so any
pixel left at 0 reads as a hole in the icon on a patterned desktop. Every
icon here is a solid block: black frame, solid field, solid glyph.

Usage: mkicon.py <output-dir>
"""
import os
import struct
import sys

W, H, DEPTH = 48, 40, 2       # 2 planes = Workbench pens 0..3
NO_POS = 0x80000000

# Workbench 3.x default pens: 0 grey (background), 1 black, 2 white, 3 blue.
BLACK, WHITE, BLUE = 1, 2, 3

# 5x7 glyphs, enough for the few letters the icons need.
FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "G": ("01110", "10001", "10000", "10011", "10001", "10001", "01110"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "?": ("01110", "10001", "00001", "00110", "00100", "00000", "00100"),
    "!": ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
}


def text(px, s, x0, y0, colour, scale=1):
    for ch in s:
        g = FONT.get(ch)
        if g is not None:
            for gy, row in enumerate(g):
                for gx, bit in enumerate(row):
                    if bit == "1":
                        for sy in range(scale):
                            for sx in range(scale):
                                x, y = x0 + gx * scale + sx, y0 + gy * scale + sy
                                if 0 <= x < W and 0 <= y < H:
                                    px[y][x] = colour
        x0 += (5 * scale) + scale


def draw(field, glyph, label):
    """Solid icon: black frame, `field` background, `glyph`-coloured art."""
    px = [[field] * W for _ in range(H)]

    # 1 px black frame plus a 1 px inner highlight, so the icon has an edge
    # against any desktop colour.
    for x in range(W):
        px[0][x] = px[H - 1][x] = BLACK
    for y in range(H):
        px[y][0] = px[y][W - 1] = BLACK

    # A big X across the upper part - the series is X-COM after all.
    for i in range(4, 26):
        for t in (0, 1):
            for x in (10 + i + t, 37 - i + t):
                if 1 < x < W - 2:
                    px[i][x] = glyph

    # Label along the bottom, centred.
    tw = len(label) * 6 - 1
    text(px, label, (W - tw) // 2, H - 11, glyph)
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
    # Image: LeftEdge, TopEdge, Width, Height, Depth, ImageData,
    #        PlanePick, PlaneOnOff, NextImage
    hdr = struct.pack(">hhhhhIBBI", 0, 0, W, H, DEPTH, 1, (1 << DEPTH) - 1, 0, 0)
    return hdr + planes(px)


def icon(kind, px, default_tool=None, tooltypes=(), stack=0):
    """kind: 3 = tool (WBTOOL), 4 = project (WBPROJECT)."""
    gadget = struct.pack(">IhhhhHHHIIIIIHI",
                         0, 0, 0, W, H,
                         0x0004,       # GFLG_GADGIMAGE | GFLG_GADGHCOMP
                         0x0003,       # RELVERIFY | GADGIMMEDIATE
                         0x0001,       # BOOLGADGET
                         1, 0,         # GadgetRender set, SelectRender none
                         0, 0, 0, 0, 0)
    body = struct.pack(">HH", 0xE310, 1) + gadget
    body += struct.pack(">BBIIIIIIi", kind, 0,
                        1 if default_tool else 0,
                        1 if tooltypes else 0,
                        NO_POS, NO_POS,
                        0, 0, stack)
    assert len(body) == 78, len(body)
    body += image(px)
    if default_tool:
        s = default_tool.encode("latin-1") + b"\0"
        body += struct.pack(">I", len(s)) + s
    if tooltypes:
        body += struct.pack(">I", (len(tooltypes) + 1) * 4)
        for t in tooltypes:
            s = t.encode("latin-1") + b"\0"
            body += struct.pack(">I", len(s)) + s
    return body


# binary name -> (background pen, glyph pen, label)
TOOLS = {
    "openxcom-aga":     (BLUE,  WHITE, "AGA"),
    "openxcom-aga-fpu": (WHITE, BLUE,  "FPU"),
    "openxcom-rtg":     (BLUE,  WHITE, "RTG"),
    "openxcom-ask":     (WHITE, BLACK, "ASK"),
}

SCRIPTS = {
    "run":     (WHITE, BLACK, "RUN"),
    "run-rtg": (WHITE, BLACK, "RTG"),
    "run-ask": (WHITE, BLACK, "ASK"),
    "run-fpu": (WHITE, BLUE,  "FPU"),
}


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    for name, (field, glyph, label) in TOOLS.items():
        px = draw(field, glyph, label)
        with open(os.path.join(out, name + ".info"), "wb") as f:
            f.write(icon(3, px, stack=1000000))
    for name, (field, glyph, label) in SCRIPTS.items():
        px = draw(field, glyph, label)
        with open(os.path.join(out, name + ".info"), "wb") as f:
            f.write(icon(4, px, default_tool="C:IconX",
                         tooltypes=("STACK=1000000",), stack=8192))
    print("icons written to", out)


if __name__ == "__main__":
    main()
