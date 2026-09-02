#!/usr/bin/env python3
"""Fetch OpenXcom's translations and keep the ones this port can draw.

WHERE THEY COME FROM. Upstream keeps only en-GB/en-US in git; every other
language lives on Transifex and is pulled by OpenXcom's OWN scheduled workflow
(.github/workflows/tx.yml), which publishes them as the `tx-translations`
artifact. The nightly workflow then packs bin/common and bin/standard - the
same files - into the archives the project distributes. So these are
OpenXcom's own files, distributed by OpenXcom, under OpenXcom's licence
(GPL-3.0) - the same licence as this port. Nothing about shipping them changes
what we may or must do.

WHICH ONES ARE KEPT. Two filters, both measured rather than guessed:

  glyphs   - the port draws text from Font.dat, and a letter that is not in it
             comes out blank. Japanese, Korean, Chinese, Arabic, Thai, Hebrew,
             Latvian, Serbian and Vietnamese need glyphs the standard fonts do
             not have, so they are dropped: English is better than gaps.
  coverage - these translations track upstream's master, this port is based on
             a 2016 commit. A language is kept when it carries at least
             MIN_COVERAGE of the keys OUR en-US asks for; whatever is missing
             falls back to English, and keys we do not have are ignored.

  usage:  fetch_translations.py [--zip tx.zip] [--list]

  Without --zip the artifact is downloaded with `gh` from OpenXcom's own
  repository (it is kept for 7 days, so the newest run is used).
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "data", "Language")
FONT = None                      # found below: the Font.dat we ship
MIN_COVERAGE = 60.0
SUBDIRS = (("common", "common"),
           ("standard/xcom1", "xcom1"),
           ("standard/xcom2", "xcom2"))

# Typographic punctuation the fonts do not have, and the plain equivalent that
# reads the same. Hungarian was being dropped over two quote marks; letters are
# never touched this way, only punctuation, and it happens on the way in so the
# installed file is what the game reads.
PUNCT = {
    "‘": "'", "’": "'", "‚": ",", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "–": "-", "—": "-", "―": "-", "−": "-",
    "…": "...", " ": " ", "•": "*", "‹": "<",
    "›": ">", "′": "'", "″": '"',
}


def depunct(text):
    for bad, good in PUNCT.items():
        if bad in text:
            text = text.replace(bad, good)
    return text


# A quote is not just a character here: it is what ENDS a YAML scalar. Folding
# a typographic quote to ASCII inside a double-quoted value therefore cuts the
# value in half, and the file stops parsing - which is exactly how 0.9.7 and
# 0.9.8 shipped an xcom2/de.yml that killed the game on the loading screen
# (line 706: `... unhandlich, aber "aeusserst wirksam ...`). So fold inside the
# scalar, and escape the quote the fold produced - only that one; quotes that
# upstream already escaped are left alone.
SCALAR = re.compile(r'^(\s*[^\s:#][^:]*:[ \t]+)(["\'])(.*)\2([ \t\r]*)$')
PLAIN = re.compile(r'^(\s*[^\s:#][^:]*:[ \t]+)(\S.*?)([ \t\r]*)$')


def fold_inner(inner, quote):
    """Fold punctuation inside a quoted scalar, keeping the scalar quoted."""
    out = []
    for ch in inner:
        rep = PUNCT.get(ch, ch)
        if rep == '"' and quote == '"':
            rep = '\\"'
        elif rep == "'" and quote == "'":
            rep = "''"
        out.append(rep)
    return "".join(out)


def escape_quotes(inner):
    """Escape every unescaped `"` in the body of a double-quoted scalar."""
    out, i = [], 0
    while i < len(inner):
        c = inner[i]
        if c == "\\" and i + 1 < len(inner):
            out.append(inner[i:i + 2])
            i += 2
        elif c == '"':
            out.append('\\"')
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def fold_yaml(text):
    """depunct(), but aware that it is editing YAML and not prose."""
    lines = text.split("\n")
    for n, line in enumerate(lines):
        m = SCALAR.match(line)
        if m:
            lines[n] = m.group(1) + m.group(2) + fold_inner(m.group(3), m.group(2)) \
                + m.group(2) + m.group(4)
            continue
        m = PLAIN.match(line)
        if m:
            v = depunct(m.group(2))
            # A plain scalar may hold a quote anywhere but at the front, where
            # it would turn the value into a quoted one that never ends.
            if v[:1] in ('"', "'"):
                v = '"' + escape_quotes(v) + '"'
            lines[n] = m.group(1) + v + m.group(3)
            continue
        lines[n] = depunct(line)
    return "\n".join(lines)


def check_yaml(path):
    """Parse what we just wrote. A translation that does not load is a crash."""
    try:
        import yaml
    except ImportError:
        sys.stderr.write("UWAGA: brak PyYAML - pliki NIE sa sprawdzane\n")
        return
    try:
        yaml.safe_load(open(path, encoding="utf-8").read())
    except Exception as e:
        mark = getattr(e, "problem_mark", None)
        where = " (linia %d, kolumna %d)" % (mark.line + 1, mark.column + 1) if mark else ""
        sys.exit("BLAD: %s nie jest poprawnym YAML-em%s: %s" % (path, where, e))


def run(cmd):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if p.returncode != 0:
        sys.stderr.write(p.stderr)
        sys.exit("polecenie nie powiodlo sie: %s" % cmd)
    return p.stdout.strip()


def download(dest):
    art = run("gh api repos/OpenXcom/OpenXcom/actions/artifacts "
              "--jq '[.artifacts[] | select(.name==\"tx-translations\" and .expired==false)][0].id'")
    if not art:
        sys.exit("brak niewygaslego artefaktu tx-translations (trzymane 7 dni)")
    print("artefakt tx-translations: %s" % art)
    with open(dest, "wb") as f:
        p = subprocess.run("gh api repos/OpenXcom/OpenXcom/actions/artifacts/%s/zip" % art,
                           shell=True, stdout=f, stderr=subprocess.PIPE)
    if p.returncode != 0 or os.path.getsize(dest) < 10000:
        sys.exit("pobranie artefaktu nie powiodlo sie")
    return dest


def find_font():
    for cand in ("/mnt/c/temp/amiga_oxcom/work/data/common/Language/Font.dat",
                 os.path.join(REPO, "data", "common", "Language", "Font.dat")):
        if os.path.isfile(cand):
            return cand
    return None


def font_chars(path):
    s = open(path, encoding="utf-8", errors="replace").read()
    chars = set()
    for name, block in re.findall(
            r"file: (\S+)\n\s+chars: >\n((?:\s+.*\n)+?)(?=\s*-|\s*\Z|\s+width|\s+id)", s):
        if "_jp" in name or "_ko" in name or "_zh" in name:
            continue        # separate fonts; those languages are dropped anyway
        chars |= set("".join(l.strip() for l in block.splitlines()))
    return chars | set(" \t\r\n")


def keys_of(path):
    out = set()
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.match(r"\s{2,}([A-Za-z0-9_]+):", line)
        if m:
            out.add(m.group(1))
    return out


def value_chars(path):
    out = set()
    for line in open(path, encoding="utf-8", errors="replace"):
        i = line.find(":")
        if i > 0:
            out |= set(depunct(line[i + 1:]))
    return out


def main():
    args = sys.argv[1:]
    only_list = "--list" in args
    zip_path = None
    if "--zip" in args:
        zip_path = args[args.index("--zip") + 1]

    font = find_font()
    if font is None:
        sys.exit("nie znalazlem Font.dat - potrzebny, zeby sprawdzic glify")
    fc = font_chars(font)

    tmp = tempfile.mkdtemp(prefix="oxctx_")
    try:
        if zip_path is None:
            zip_path = download(os.path.join(tmp, "tx.zip"))
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp)
        root = os.path.join(tmp, "openxcom")
        if not os.path.isdir(root):
            sys.exit("archiwum nie wyglada jak tx-translations")

        ours = os.path.join(os.path.dirname(font), "en-US.yml")
        our_keys = keys_of(ours)

        kept, dropped = [], []
        for fn in sorted(os.listdir(os.path.join(root, "common", "Language"))):
            if not fn.endswith(".yml") or fn.startswith("en-"):
                continue
            src = os.path.join(root, "common", "Language", fn)
            lang = fn[:-4]
            cover = 100.0 * len(our_keys & keys_of(src)) / max(1, len(our_keys))
            missing = sorted(c for c in (value_chars(src) - fc) if c.strip())
            if missing:
                dropped.append((lang, "brak %d glifow (%s)" % (len(missing), "".join(missing[:6]))))
            elif cover < MIN_COVERAGE:
                dropped.append((lang, "pokrycie %.0f%%" % cover))
            else:
                kept.append((lang, cover))

        print("zostaje %d jezykow:" % len(kept))
        for lang, cover in kept:
            print("  %-8s %.1f%% kluczy" % (lang, cover))
        print("odpada %d:" % len(dropped))
        for lang, why in dropped:
            print("  %-8s %s" % (lang, why))
        if only_list:
            return 0

        if os.path.isdir(OUT):
            shutil.rmtree(OUT)
        n = 0
        for src_dir, out_dir in SUBDIRS:
            d = os.path.join(OUT, out_dir)
            os.makedirs(d)
            for lang, _ in kept:
                s = os.path.join(root, src_dir, "Language", lang + ".yml")
                if os.path.isfile(s):
                    txt = open(s, encoding="utf-8", errors="replace").read()
                    with open(os.path.join(d, lang + ".yml"), "w",
                              encoding="utf-8", newline="") as out:
                        out.write(fold_yaml(txt))
                    check_yaml(os.path.join(d, lang + ".yml"))
                    n += 1
        with open(os.path.join(OUT, "SOURCE.txt"), "w", encoding="utf-8") as f:
            f.write("OpenXcom translations, pulled from Transifex by OpenXcom's own\n"
                    "workflow (.github/workflows/tx.yml) and published as the\n"
                    "tx-translations artifact of OpenXcom/OpenXcom.\n\n"
                    "Same project, same licence as OpenXcom itself: GPL-3.0.\n"
                    "Refresh with build/fetch_translations.py.\n")
        print("\nzapisane: %d plikow w %s" % (n, OUT))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
