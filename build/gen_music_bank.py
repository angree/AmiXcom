# -*- coding: utf-8 -*-
# AmiXcom music bank builder v2.
#
# The v1 builder invented its own key->sample mapping and therefore played
# different samples than the reference render (audible: harp, bass, GM92 pad).
# v2 asks the reference selector for every single key and stores the answer as
# a plain key->zone map, so the Amiga picks exactly the sample the reference does.
#
# Layout (big-endian):
#   char magic[4]  "AXM2"
#   u16  version(2), u16 flags(bit2 = 16-bit samples)
#   u16  nzones,     u16 nmaps
#   u32  sampleBytes
#   u16  patchMap[128]     index into the map table, 0xFFFF = instrument absent
#   u16  drumMap[128]      zone index per percussion key, 0xFFFF = absent
#   maps: nmaps x 128 x u16 zone index (0xFFFF = silent)
#   zones: nzones x 24 bytes
#        u8 flags (bit0 looping, bit1 untuned), u8 root, u16 pad
#        u32 rate      Hz at 'root', cents already folded in
#        u32 offset    byte offset into the sample blob
#        u32 length    samples
#        u32 loopStart, u32 loopEnd
#   blob: signed 8-bit (or 16-bit big-endian when flag set)
import struct, os, warnings
import numpy as np
warnings.filterwarnings("ignore")

os.environ.setdefault('AMX_HQ', '0')
import gen_music_ref as R  # the reference selector and sample processing

OUT = os.environ.get('AMX_BANKOUT', "music.bnk")
VELREP = int(os.environ.get('AMX_VEL', '81'))     # median velocity of the 22 tunes
BITS16 = os.environ.get('AMX_BITS16', '0') == '1'

PATCHES = [0, 1, 2, 9, 40, 42, 43, 45, 46, 47, 48, 54, 56, 57, 60, 68, 71, 74, 92, 125]
DRUMKEYS = [40, 46, 49, 51, 69]

def main():
    ref = R.Bank(R.SF2)
    zones = []          # list of reference Zone objects, in bank order
    index = {}          # id(zone) -> bank index
    maps = []           # list of 128-entry lists
    patch_map = [0xFFFF] * 128
    drum_map = [0xFFFF] * 128

    def zone_index(z):
        k = id(z)
        if k not in index:
            index[k] = len(zones)
            zones.append(z)
        return index[k]

    for p in PATCHES:
        m = []
        for key in range(128):
            z = ref.find(p, key, VELREP, False)
            m.append(0xFFFF if z is None else zone_index(z))
        if all(v == 0xFFFF for v in m):
            print("  !! GM %d: brak sampli" % p); continue
        patch_map[p] = len(maps)
        maps.append(m)
        used = sorted(set(v for v in m if v != 0xFFFF))
        print("GM %3d: %2d sampli  %s" % (p, len(used), zones[used[0]].name))

    for key in DRUMKEYS:
        z = ref.find(0, key, VELREP, True)
        if z is None:
            print("  !! perkusja %d: brak" % key); continue
        drum_map[key] = zone_index(z)
        print("PERK %3d: %s" % (key, z.name))

    # serialize samples
    blob = bytearray()
    meta = []
    for z in zones:
        data = z.data8
        ls, le = int(z.loop_s), int(z.loop_e)
        looping = bool(z.looping) and 0 <= ls < le <= len(data)
        if looping:
            data = data[:le]            # never played past the loop end
        else:
            ls = le = 0
            nz = np.nonzero(np.abs(data) > 0.5)[0]
            if len(nz):
                data = data[:int(nz[-1]) + 2]
        if BITS16:
            arr = np.clip(np.round(data * 256.0), -32768, 32767).astype('>i2')
        else:
            arr = np.clip(np.round(data), -128, 127).astype(np.int8)
        off = len(blob)
        # one guard sample past the end so the mixer's interpolation partner
        # sd[ip+1] is always readable without a bounds test: for a looping
        # sample that is the one it wraps to, otherwise the last sample again
        gi = ls if (looping and ls < len(arr)) else (len(arr) - 1)
        blob += arr.tobytes()
        blob += arr[gi:gi+1].tobytes() if len(arr) else bytes(1)
        while len(blob) & 1:
            blob += b'\0'
        # fold the SF2 cents correction into the stored rate, so the replayer
        # needs nothing but the semitone table
        rate = int(round(z.rate * (2.0 ** (z.cents / 1200.0))))
        meta.append({'flags': (1 if looping else 0) | (2 if z.untuned else 0),
                     'root': int(z.root) & 0x7f, 'rate': rate, 'off': off,
                     'len': len(arr), 'ls': ls, 'le': le})

    out = bytearray()
    out += b'AXM2'
    out += struct.pack('>HHHH', 2, (4 if BITS16 else 0), len(zones), len(maps))
    out += struct.pack('>I', len(blob))
    for i in range(128):
        out += struct.pack('>H', patch_map[i])
    for i in range(128):
        out += struct.pack('>H', drum_map[i])
    for m in maps:
        for v in m:
            out += struct.pack('>H', v)
    for z in meta:
        out += struct.pack('>BBHIIIII', z['flags'], z['root'], 0,
                           z['rate'], z['off'], z['len'], z['ls'], z['le'])
    hdr = len(out)
    out += blob
    open(OUT, 'wb').write(out)
    print("\nbank v2: %d sampli, %d map, naglowek %.1f KB, dane %.2f MB, razem %.2f MB"
          % (len(zones), len(maps), hdr/1024.0, len(blob)/1048576.0, len(out)/1048576.0))
    print("-> %s" % OUT)

main()
