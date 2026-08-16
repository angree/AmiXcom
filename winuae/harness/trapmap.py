#!/usr/bin/env python3
"""
trapmap.py - map a "CPU TRAP" report from oxc.log onto symbols.

Run inside WSL (the m68k tools live there):
    python3 trapmap.py [oxc.log] [binary]
Defaults: /mnt/c/temp/amiga_oxcom/work/oxc.log and ~/build/openxcom-aga.

Reads the LAST trap report in the log, takes the textbase from its
"textbase: amiga_trap_land is at 0x..." line, runs m68k-amigaos-nm on the
unstripped binary, and prints:
  * the faulting PC as symbol+offset (if inside the text hunk),
  * every stack longword that lands inside the text hunk, as symbol+offset -
    that is the backtrace, newest first (a few are stale frames, ignore those
    that make no sense),
  * every register that lands inside the text hunk.
"""
import bisect, os, re, subprocess, sys

log = sys.argv[1] if len(sys.argv) > 1 else "/mnt/c/temp/amiga_oxcom/work/oxc.log"
binary = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser("~/build/openxcom-aga")
NM = "/opt/amiga/bin/m68k-amigaos-nm"
CXXFILT = "/opt/amiga/bin/m68k-amigaos-c++filt"

text = open(log, errors="replace").read()
reports = [m.start() for m in re.finditer(r"CPU TRAP \d+", text)]
if not reports:
    sys.exit("no CPU TRAP report in " + log)
rep = text[reports[-1]:]
rep = rep[:rep.find("\n\n")] if "\n\n" in rep else rep
# The report may be echoed twice (SDLmini_Log and Log()); take one copy.
lines = []
for l in rep.splitlines():
    l = re.sub(r"^\S+:\s", "", l) if l.startswith("amiga:") else l
    lines.append(l)
    if l.startswith("  usp+") and int(l.split(":")[0].split("+")[1], 16) >= 0x1f8:
        break
rep = "\n".join(lines)
print(rep)
print("=" * 70)

m = re.search(r"amiga_trap_land is at 0x([0-9a-f]+)", rep)
if not m:
    sys.exit("no textbase line")
land_run = int(m.group(1), 16)

syms = []
out = subprocess.run([NM, "-n", binary], capture_output=True, text=True).stdout
for l in out.splitlines():
    p = l.split()
    if len(p) == 3 and p[1] in "tT":
        syms.append((int(p[0], 16), p[2]))
syms.sort()
addrs = [a for a, _ in syms]
land_file = dict((n, a) for a, n in syms)["_amiga_trap_land"]
textbase = land_run - land_file
textend = textbase + syms[-1][0] + 0x1000
print("textbase 0x%08x  text end ~0x%08x" % (textbase, textend))


def demangle(names):
    r = subprocess.run([CXXFILT], input="\n".join(names), capture_output=True, text=True)
    return r.stdout.splitlines()


def lookup(v):
    if not (textbase <= v < textend):
        return None
    off = v - textbase
    i = bisect.bisect_right(addrs, off) - 1
    if i < 0:
        return None
    a, n = syms[i]
    return (n, off - a)


hits = []
m = re.search(r"at PC 0x([0-9a-f]+)", rep)
pc = int(m.group(1), 16)
hits.append(("PC", pc))
for l in rep.splitlines():
    if re.match(r"\s*d0-d7:", l) or re.match(r"\s*a0-a7:", l):
        base = "d" if "d0" in l else "a"
        for i, w in enumerate(l.split(":")[1].split()):
            hits.append(("%s%d" % (base, i), int(w, 16)))
    mm = re.match(r"\s*usp\+([0-9a-f]+):(.*)", l)
    if mm:
        o = int(mm.group(1), 16)
        for i, w in enumerate(mm.group(2).split()):
            hits.append(("usp+%03x" % (o + 4 * i), int(w, 16)))

resolved = [(tag, v, lookup(v)) for tag, v in hits]
names = [r[2][0] for r in resolved if r[2]]
dem = dict(zip(names, demangle(names))) if names else {}
for tag, v, r in resolved:
    if r:
        print("%-8s %08x  %s+0x%x" % (tag, v, dem.get(r[0], r[0]), r[1]))
    elif tag == "PC":
        print("%-8s %08x  (outside text hunk)" % (tag, v))
