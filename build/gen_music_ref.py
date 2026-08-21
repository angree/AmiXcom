# -*- coding: utf-8 -*-
# Reference sample selection for the music bank, used by gen_music_bank.py.
# Needs FluidR3_GM.sf2 (MIT, e.g. Debian's fluid-soundfont source package)
# and the sf2utils package. Set AMX_SF2 to point at the soundfont.
# AmiXcom music prototype: GM.CAT tune -> 4-voice Paula-style render -> WAV
# Honest to the planned Amiga replayer:
#   4 voices, 8-bit samples at <=22050 Hz base, integer Paula periods,
#   volume 0..64, control updates at 50 Hz ticks, no mixing tricks.
import struct, sys, wave, warnings, os
import numpy as np
warnings.filterwarnings("ignore")
from sf2utils.sf2parse import Sf2File

GMCAT = os.environ.get('AMX_GMCAT', "GM.CAT")
SF2 = os.environ.get('AMX_SF2', "FluidR3_GM.sf2")
OUT_RATE = 44100
PAULA_CLK = 3546895.0
MAX_SECONDS = 170
TICK = 1.0 / 50.0   # replayer tick
NVOICES = int(os.environ.get('AMX_VOICES', '4'))
HQ = os.environ.get('AMX_HQ', '0') == '1'   # 16-bit samples, no Paula period quantization
OUTDIR = os.environ.get('AMX_OUTDIR', r'C:/temp/amiga_oxcom/music/preview')

# GMCat.cpp per-patch velocity table (verbatim)
VOLTAB = [
100,100,100,100,100, 90,100,100,100,100,100, 90,100,100,100,100,
100,100, 85,100,100,100,100,100,100,100,100,100, 90,90, 110, 80,
100,100,100, 90, 70,100,100,100,100,100,100,100,100,100,100,100,
100,100, 90,100,100,100,100,100,100,120,100,100,100,120,100,127,
100,100, 90,100,100,100,100,100,100, 95,100,100,100,100,100,100,
100,100,100,100,100,100,100,115,100,100,100,100,100,100,100,100,
100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,
100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100]

# ---------------- GM.CAT parsing (mirrors GMCat.cpp) ----------------

def load_entry(raw, idx):
    off, size = struct.unpack_from('<II', raw, idx*8)
    d = raw[off:off+size+64]
    namesize = d[0]
    if namesize <= 56:
        d = d[1+namesize:1+namesize+size]
    else:
        d = d[:size]
    pos = 0
    tempo = d[pos]; pos += 1
    nsubs = d[pos]; pos += 1
    subs = []
    for _ in range(nsubs):
        s = struct.unpack_from('<I', d, pos)[0]
        subs.append(d[pos+4:pos+s]); pos += s
    ntracks = d[pos]; pos += 1
    tracks = []
    for _ in range(ntracks):
        ch = d[pos]; pos += 1
        s = struct.unpack_from('<I', d, pos)[0]
        tracks.append((ch, d[pos+4:pos+s])); pos += s
    return tempo, subs, tracks

def walk(seq, subs, ch, t, events, depth=0):
    """emit (tick, kind, ch, a, b); returns end tick."""
    if depth > 8: return t
    data = seq; i = 0; n = len(seq); cmd = None
    while i < n:
        delta = 0
        while i < n:
            c = data[i]; i += 1
            delta += c & 0x7F
            if not (c & 0x80): break
            delta <<= 7
        t += delta
        if i >= n: return t
        if data[i] & 0x80:
            cmd = data[i]; i += 1
            if cmd in (0xFF, 0xFD): return t
            if cmd == 0xFE:
                if i >= n: return t
                sub = data[i]; i += 1
                if sub < len(subs):
                    t = walk(subs[sub], subs, ch, t, events, depth+1)
                cmd = None
                continue
            cmd &= 0xF0
        elif cmd is None:
            return t
        if i >= n: return t
        d1 = data[i]; i += 1
        if cmd in (0x80, 0x90):
            if i >= n: return t
            d2 = data[i]; i += 1
            if cmd == 0x90 and d2:
                events.append((t, 'on', ch, d1, d2))
            else:
                events.append((t, 'off', ch, d1, 0))
        elif cmd == 0xC0:
            if d1 == 0x7E: return t      # restart marker = end for preview
            p = d1
            if p in (0x57, 0x3F): p = 0x3E
            events.append((t, 'patch', ch, p, 0))
        elif cmd == 0xB0:
            if i >= n: return t
            d2 = data[i]; i += 1
            if d1 == 0x7E: continue
            if d1 == 0:
                if d2: events.append((t, 'tempo', ch, 2*d2, 0))
                continue
            events.append((t, 'ctrl', ch, d1, d2))
        elif cmd == 0xE0:
            if i >= n: return t
            d2 = data[i]; i += 1
            events.append((t, 'bend', ch, d1, d2))
        else:
            return t
    return t

# ---------------- SF2 zone bank ----------------

class Zone(object):
    __slots__ = ('data8','rate','root','cents','loop_s','loop_e','looping',
                 'klo','khi','vlo','vhi','name','fadeoff','untuned')

def rng(r):
    if r is None: return 0, 127
    return r[0], r[1]

def build_zone(ib, pbag):
    s = ib.sample
    if s is None or not (s.is_mono or s.is_left):
        return None
    z = Zone()
    raw = np.frombuffer(s.raw_sample_data, dtype='<i2').astype(np.float32)
    rate = float(s.sample_rate)
    # downsample to <=22050 (what the Amiga bank will ship)
    while rate > 22051.0:
        m = len(raw)//2*2
        raw = (raw[0:m:2] + raw[1:m:2]) * 0.5
        rate *= 0.5
    scale = rate / float(s.sample_rate)
    if HQ:
        z.data8 = (raw / 256.0).astype(np.float32)
    else:
        z.data8 = np.clip(np.round(raw / 256.0), -128, 127).astype(np.float32)  # 8-bit grid
    z.rate = rate
    z.root = ib.base_note if ib.base_note is not None else s.original_pitch
    z.cents = (s.pitch_correction or 0) + (ib.fine_tuning or 0)
    tun = getattr(ib, 'tuning', None)
    if tun: z.root -= tun
    z.looping = bool(ib.sample_loop)
    ls = ib.cooked_loop_start if ib.cooked_loop_start is not None else 0
    le = ib.cooked_loop_end if ib.cooked_loop_end is not None else 0
    z.loop_s, z.loop_e = ls*scale, le*scale
    if not (0 <= z.loop_s < z.loop_e <= len(z.data8)):
        z.looping = False
    klo, khi = rng(ib.key_range); pklo, pkhi = rng(pbag.key_range)
    z.klo, z.khi = max(klo, pklo), min(khi, pkhi)
    vlo, vhi = rng(ib.velocity_range); pvlo, pvhi = rng(pbag.velocity_range)
    z.vlo, z.vhi = max(vlo, pvlo), min(vhi, pvhi)
    z.name = s.name
    z.fadeoff = False
    z.untuned = False
    return z

class Bank(object):
    def __init__(self, sf2path):
        self.sf2 = Sf2File(open(sf2path, 'rb'))
        self.melodic = {}
        self.drumpreset = None
        for p in self.sf2.presets:
            b = getattr(p, 'bank', None)
            if b == 0:
                self.melodic[p.preset] = p
            elif b == 128 and getattr(p, 'preset', None) == 0:
                self.drumpreset = p
        self.cache = {}
        self.vs_mel, self.vs_dr = {}, {}
        if os.environ.get('AMX_BANK', 'fluid') == 'vsco':
            import vsco_bank
            self.vs_mel, self.vs_dr = vsco_bank.build(HQ)
    def zones_of(self, preset):
        out = []
        for pbag in preset.bags:
            if pbag.instrument is None: continue
            for ib in pbag.instrument.bags:
                if ib.sample is None: continue
                z = build_zone(ib, pbag)
                if z: out.append(z)
        return out
    def find(self, patch, key, vel, drum):
        if drum:
            for z in self.vs_dr.get(key, []):
                if z.vlo <= vel <= z.vhi:
                    return z
            if key in self.vs_dr:
                return self.vs_dr[key][0]
        elif patch in self.vs_mel:
            for z in self.vs_mel[patch]:
                if z.klo <= key <= z.khi:
                    return z
        ck = ('d', 0) if drum else ('m', patch)
        if ck not in self.cache:
            pr = self.drumpreset if drum else self.melodic.get(patch)
            self.cache[ck] = self.zones_of(pr) if pr else []
        zl = self.cache[ck]
        for z in zl:
            if z.klo <= key <= z.khi and z.vlo <= vel <= z.vhi:
                return z
        for z in zl:
            if z.klo <= key <= z.khi:
                return z
        return None

# ---------------- 4-voice Paula-style synth ----------------

class Voice(object):
    __slots__ = ('zone','pos','ratio','vol','targ','ch','key','age','on','fade','lastamp')
    def __init__(self):
        self.zone = None
        self.vol = 0.0; self.targ = 0; self.age = 0
        self.on = False; self.fade = 0
        self.pos = 0.0; self.ratio = 0.0; self.ch = 0; self.key = 0
        self.lastamp = 0.0

def period_quantize(rate_hz):
    if rate_hz <= 0: return 0.0
    if HQ:
        return rate_hz
    per = int(round(PAULA_CLK / rate_hz))
    per = max(124, min(65535, per))
    return PAULA_CLK / per

def render(tune_idx, outpath, bank, raw):
    tempo, subs, tracks = load_entry(raw, tune_idx)
    events = []
    for ch, seq in tracks:
        walk(seq, subs, ch, 0, events)
    events.sort(key=lambda e: e[0])
    patch = [0]*16
    stats = {'on':0, 'drop':0, 'steal':0}
    chvol = [127]*16
    bend = [0.0]*16
    voices = [Voice() for _ in range(NVOICES)]
    out = np.zeros((int(OUT_RATE*MAX_SECONDS)+2*OUT_RATE, 2), dtype=np.float32)
    state = {'spt': 60.0/(tempo*24.0), 'now': 0.0, 'lasttick': 0, 'written': 0.0}
    PAN = [(0.75,0.25),(0.25,0.75),(0.25,0.75),(0.75,0.25)]  # LRRL

    def mix_until(tsec):
        while state['written'] < tsec - 1e-9:
            step = min(TICK, tsec - state['written'])
            n0 = int(round(state['written']*OUT_RATE))
            n1 = int(round((state['written']+step)*OUT_RATE))
            ns = n1 - n0
            if ns > 0:
                for vi in range(NVOICES):
                    v = voices[vi]
                    if v.zone is None: continue
                    if v.fade > 0: v.targ = 0
                    dv = v.targ - v.vol
                    if dv > 16: dv = 16
                    if dv < -16: dv = -16
                    v.vol += dv
                    if v.fade > 0 and v.vol <= 0:
                        v.zone = None; continue
                    g = (v.vol / 64.0) * (0.85 if NVOICES <= 4 else 0.45)
                    z = v.zone
                    idx = v.pos + v.ratio*np.arange(ns, dtype=np.float64)
                    if z.looping:
                        over = idx >= z.loop_e
                        if over.any():
                            ll = z.loop_e - z.loop_s
                            idx[over] = z.loop_s + np.mod(idx[over]-z.loop_s, ll)
                        v.pos = idx[-1] + v.ratio
                        if v.pos >= z.loop_e:
                            v.pos = z.loop_s + ((v.pos - z.loop_s) % (z.loop_e - z.loop_s))
                    else:
                        if idx[0] >= len(z.data8)-1:
                            v.zone = None; continue
                        idx = np.minimum(idx, len(z.data8)-1.001)
                        v.pos = idx[-1] + v.ratio
                    i0 = idx.astype(np.int64)
                    fr = (idx - i0).astype(np.float32)
                    smp = z.data8[i0]*(1-fr) + z.data8[np.minimum(i0+1, len(z.data8)-1)]*fr
                    smp = (smp/128.0) * g
                    v.lastamp = float(np.abs(smp).max()) if ns else v.lastamp
                    out[n0:n1,0] += smp*PAN[vi % 4][0]
                    out[n0:n1,1] += smp*PAN[vi % 4][1]
                    if not z.looping and v.pos >= len(z.data8)-1:
                        v.zone = None
                for v in voices:
                    if v.zone is not None: v.age += 1
            state['written'] += step

    def note_rate(z, key, ch):
        if z.untuned:
            return period_quantize(z.rate)
        semis = (key - z.root) + z.cents/100.0 + bend[ch]*2.0
        return period_quantize(z.rate * (2.0 ** (semis/12.0)))

    for (tick, kind, ch, a, b) in events:
        tsec = state['now'] + (tick - state['lasttick']) * state['spt']
        if tsec > MAX_SECONDS: break
        mix_until(tsec)
        state['now'] = tsec; state['lasttick'] = tick
        if kind == 'tempo':
            state['spt'] = 60.0/(a*24.0)
        elif kind == 'patch':
            patch[ch] = a
        elif kind == 'ctrl':
            if a == 7: chvol[ch] = b
        elif kind == 'bend':
            bend[ch] = ((a | (b<<7)) - 8192) / 8192.0
        elif kind == 'off':
            for v in voices:
                if v.zone is not None and v.ch == ch and v.key == a and v.on:
                    v.on = False
                    if v.zone.looping or v.zone.fadeoff: v.fade = 1
        elif kind == 'on':
            drum = (ch == 9)
            vscaled = (b * (80 if drum else VOLTAB[patch[ch]])) >> 7
            z = bank.find(patch[ch], a, max(1, vscaled), drum)
            if z is None: continue
            vol64 = int(round(64.0 * (vscaled/127.0) * (chvol[ch]/127.0)))
            if vol64 <= 0: continue
            if vol64 > 64: vol64 = 64
            stats['on'] += 1
            cand = None
            for v in voices:
                if v.zone is None: cand = v; break
            if cand is None:
                cand = min(voices, key=lambda v: (v.lastamp*(1.0 if v.on else 0.6), -v.age))
                newamp = (vol64/64.0) * 0.5
                if cand.on and cand.lastamp > newamp*1.5:
                    stats['drop'] += 1
                    continue  # do not steal a much louder note
                stats['steal'] += 1
            cand.zone = z; cand.pos = 0.0
            cand.ratio = note_rate(z, a, ch) / OUT_RATE
            cand.vol = 0.0 if z.looping else float(vol64)
            cand.targ = vol64
            cand.ch = ch; cand.key = a; cand.age = 0; cand.on = True; cand.fade = 0
            cand.lastamp = (vol64/64.0) * 0.5
    mix_until(min(state['now'] + 2.0, MAX_SECONDS))
    n = int(state['written']*OUT_RATE)
    data = np.clip(out[:n]*32767.0, -32768, 32767).astype('<i2')
    w = wave.open(outpath, 'wb')
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(OUT_RATE)
    w.writeframes(data.tobytes()); w.close()
    return state['written'], len(events), stats

if __name__ == '__main__':
    raw = open(GMCAT, 'rb').read()
    bank = Bank(SF2)
    for spec in sys.argv[1:]:
        idx, name = spec.split(':')
        secs, nev, stats = render(int(idx), os.path.join(OUTDIR, "%s.wav" % name), bank, raw)
        print("tune %s -> %s.wav  %.1fs  %d events  notes=%d stolen=%d dropped=%d" % (idx, name, secs, nev, stats['on'], stats['steal'], stats['drop']))
