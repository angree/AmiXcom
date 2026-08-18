#!/usr/bin/env python3
"""
Apply the Amiga port's changes to a pristine OpenXcom source tree.

Mechanical and idempotent, on purpose: the repository never stores a modified
copy of OpenXcom, so the port is exactly this script plus native/ - and a
missing patch has to fail loudly rather than leave a subtly different game.

Usage:  apply-amiga-patches.py <path-to-openxcom/src>
"""

import os
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPLACE = os.path.join(REPO, "native", "oxc-replace")

MARK = "/* AMIGA-PORT:"


def edit(path, old, new, why):
    """Replace `old` with `new` in `path`. Idempotent: if `old` is already
    gone and `new` is present, the patch counts as applied."""
    with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
        text = f.read()

    if new in text:
        return "already"
    if old not in text:
        raise SystemExit("PATCH FAILED (%s): cannot find in %s:\n%s" % (why, path, old))

    text = text.replace(old, new, 1)
    with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(text)
    return "applied"


def replace_file(src_root, relative):
    src = os.path.join(REPLACE, relative)
    dst = os.path.join(src_root, relative)
    shutil.copyfile(src, dst)
    return "copied"


def patch_yamlcpp(yamldir):
    """yaml-cpp reads files through std::ifstream, which hangs on close with
    this toolchain (see native/amiga_fstream.h). Both LoadFile entry points are
    rewritten to read the file with stdio and parse from a string."""
    path = os.path.join(yamldir, "src", "parse.cpp")
    if not os.path.isfile(path):
        return "skipped (no yaml-cpp at %s)" % yamldir

    with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
        text = f.read()
    if "amiga_slurp" in text:
        return "already"

    helper = """
// AMIGA-PORT: std::ifstream::close() never returns on m68k-amigaos libstdc++,
// so the file is read with stdio and parsed from memory instead.
#include <cstdio>
static bool amiga_slurp(const std::string& filename, std::string& out) {
  FILE* f = fopen(filename.c_str(), "rb");
  if (!f) return false;
  char buf[4096];
  size_t n;
  while ((n = fread(buf, 1, sizeof(buf), f)) > 0) out.append(buf, n);
  fclose(f);
  return true;
}
"""
    text = text.replace("namespace YAML {", helper + "\nnamespace YAML {", 1)
    text = text.replace(
        "  std::ifstream fin(filename.c_str());\n"
        "  if (!fin) {\n"
        "    throw BadFile();\n"
        "  }\n"
        "  return Load(fin);",
        "  std::string text;\n"
        "  if (!amiga_slurp(filename, text)) {\n"
        "    throw BadFile();\n"
        "  }\n"
        "  return Load(text);")
    text = text.replace(
        "  std::ifstream fin(filename.c_str());\n"
        "  if (!fin) {\n"
        "    throw BadFile();\n"
        "  }\n"
        "  return LoadAll(fin);",
        "  std::string text;\n"
        "  if (!amiga_slurp(filename, text)) {\n"
        "    throw BadFile();\n"
        "  }\n"
        "  return LoadAll(text);")

    if "amiga_slurp" not in text:
        raise SystemExit("PATCH FAILED: could not rewrite yaml-cpp LoadFile in %s" % path)
    with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(text)
    return "applied"


def patch_yamlcpp_convert(yamldir):
    """Every scalar encode/decode in yaml-cpp 0.6.3 constructs a
    std::stringstream (locale machinery, soft-float num_put) - measured as the
    dominant cost of Options::save/SavedGame::save on the 68020. Replaced with
    manual integer conversion, snprintf for float/double and strtol/strtod for
    parsing. char keeps its original single-CHARACTER semantics."""
    path = os.path.join(yamldir, "include", "yaml-cpp", "node", "convert.h")
    if not os.path.isfile(path):
        return "skipped (no yaml-cpp at %s)" % yamldir
    with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
        text = f.read()
    if "amiga_to_string" in text:
        return "already"

    new_block = r"""// AMIGA-PORT: fast scalar conversion. The original macro constructed a
// std::stringstream per scalar (encode AND decode) - locale machinery plus
// soft-float num_put on a 68020 made saves take a minute. Manual conversion,
// same semantics (base prefixes on parse, .inf/.nan words, char = one
// CHARACTER not a number).
#include <cstdio>
#include <cstdlib>
#include <cerrno>
namespace conversion {
inline std::string amiga_to_string(long long v) {
  char b[24]; char* p = b + sizeof(b);
  unsigned long long u = (v < 0) ? 0ULL - (unsigned long long)v : (unsigned long long)v;
  do { *--p = (char)('0' + (int)(u % 10)); u /= 10; } while (u);
  if (v < 0) *--p = '-';
  return std::string(p, (std::size_t)(b + sizeof(b) - p));
}
inline std::string amiga_to_string(unsigned long long v) {
  char b[24]; char* p = b + sizeof(b);
  do { *--p = (char)('0' + (int)(v % 10)); v /= 10; } while (v);
  return std::string(p, (std::size_t)(b + sizeof(b) - p));
}
inline std::string amiga_to_string(int v)            { return amiga_to_string((long long)v); }
inline std::string amiga_to_string(short v)          { return amiga_to_string((long long)v); }
inline std::string amiga_to_string(long v)           { return amiga_to_string((long long)v); }
inline std::string amiga_to_string(unsigned v)       { return amiga_to_string((unsigned long long)v); }
inline std::string amiga_to_string(unsigned short v) { return amiga_to_string((unsigned long long)v); }
inline std::string amiga_to_string(unsigned long v)  { return amiga_to_string((unsigned long long)v); }
inline std::string amiga_to_string(float v)  { char b[48]; std::snprintf(b, sizeof(b), "%.9g", (double)v); return std::string(b); }
inline std::string amiga_to_string(double v) { char b[48]; std::snprintf(b, sizeof(b), "%.17g", v); return std::string(b); }
inline std::string amiga_to_string(char v)          { return std::string(1, v); }
inline std::string amiga_to_string(signed char v)   { return std::string(1, (char)v); }
inline std::string amiga_to_string(unsigned char v) { return std::string(1, (char)v); }

inline bool amiga_parse_l(const std::string& in, long& out) {
  if (in.empty()) return false;
  errno = 0; char* e = 0;
  long v = std::strtol(in.c_str(), &e, 0);
  if (e != in.c_str() + in.size() || errno == ERANGE) return false;
  out = v; return true;
}
inline bool amiga_parse_ul(const std::string& in, unsigned long& out) {
  if (in.empty() || in[0] == '-') return false;
  errno = 0; char* e = 0;
  unsigned long v = std::strtoul(in.c_str(), &e, 0);
  if (e != in.c_str() + in.size() || errno == ERANGE) return false;
  out = v; return true;
}
inline bool amiga_from_string(const std::string& in, int& r)   { long v; if (!amiga_parse_l(in, v) || v < (long)std::numeric_limits<int>::min() || v > (long)std::numeric_limits<int>::max()) return false; r = (int)v; return true; }
inline bool amiga_from_string(const std::string& in, short& r) { long v; if (!amiga_parse_l(in, v) || v < (long)std::numeric_limits<short>::min() || v > (long)std::numeric_limits<short>::max()) return false; r = (short)v; return true; }
inline bool amiga_from_string(const std::string& in, long& r)  { return amiga_parse_l(in, r); }
inline bool amiga_parse_ull10(const std::string& in, std::string::size_type i, unsigned long long& out) {
  /* 64-bit decimal parse - strtoul is only 32 bits on m68k, which made the
   * 64-bit rng seed in every save fail to load ("bad conversion"). */
  if (i >= in.size()) return false;
  unsigned long long v = 0;
  for (; i < in.size(); ++i) {
    char c = in[i];
    if (c < '0' || c > '9') return false;
    unsigned long long nv = v * 10ULL + (unsigned long long)(c - '0');
    if (nv / 10ULL != v) return false;  /* overflow */
    v = nv;
  }
  out = v; return true;
}
inline bool amiga_from_string(const std::string& in, long long& r) {
  if (in.empty()) return false;
  bool neg = (in[0] == '-');
  unsigned long long u;
  if (amiga_parse_ull10(in, (in[0] == '-' || in[0] == '+') ? 1 : 0, u)) {
    if (neg) { if (u > 9223372036854775808ULL) return false; r = -(long long)u; }
    else     { if (u > 9223372036854775807ULL) return false; r = (long long)u; }
    return true;
  }
  long v; if (!amiga_parse_l(in, v)) return false; r = v; return true;  /* hex/octal */
}
inline bool amiga_from_string(const std::string& in, unsigned& r)       { unsigned long v; if (!amiga_parse_ul(in, v) || v > (unsigned long)std::numeric_limits<unsigned>::max()) return false; r = (unsigned)v; return true; }
inline bool amiga_from_string(const std::string& in, unsigned short& r) { unsigned long v; if (!amiga_parse_ul(in, v) || v > (unsigned long)std::numeric_limits<unsigned short>::max()) return false; r = (unsigned short)v; return true; }
inline bool amiga_from_string(const std::string& in, unsigned long& r)  { return amiga_parse_ul(in, r); }
inline bool amiga_from_string(const std::string& in, unsigned long long& r) {
  if (in.empty() || in[0] == '-') return false;
  unsigned long long u;
  if (amiga_parse_ull10(in, (in[0] == '+') ? 1 : 0, u)) { r = u; return true; }
  unsigned long v; if (!amiga_parse_ul(in, v)) return false; r = v; return true;  /* hex/octal */
}
inline bool amiga_from_string(const std::string& in, double& r) {
  if (!in.empty()) {
    errno = 0; char* e = 0;
    double v = std::strtod(in.c_str(), &e);
    if (e == in.c_str() + in.size() && errno != ERANGE) { r = v; return true; }
  }
  if (IsInfinity(in))         { r = std::numeric_limits<double>::infinity();  return true; }
  if (IsNegativeInfinity(in)) { r = -std::numeric_limits<double>::infinity(); return true; }
  if (IsNaN(in))              { r = std::numeric_limits<double>::quiet_NaN(); return true; }
  return false;
}
inline bool amiga_from_string(const std::string& in, float& r) {
  double v; if (!amiga_from_string(in, v)) return false; r = (float)v; return true;
}
inline bool amiga_from_string(const std::string& in, char& r)          { if (in.size() != 1) return false; r = in[0]; return true; }
inline bool amiga_from_string(const std::string& in, signed char& r)   { if (in.size() != 1) return false; r = (signed char)in[0]; return true; }
inline bool amiga_from_string(const std::string& in, unsigned char& r) { if (in.size() != 1) return false; r = (unsigned char)in[0]; return true; }
inline std::string amiga_to_string(long double v) { return amiga_to_string((double)v); }
inline bool amiga_from_string(const std::string& in, long double& r) { double v; if (!amiga_from_string(in, v)) return false; r = v; return true; }
}  // namespace conversion

#define YAML_DEFINE_CONVERT_STREAMABLE(type, negative_op)                \
  template <>                                                            \
  struct convert<type> {                                                 \
    static Node encode(const type& rhs) {                                \
      return Node(conversion::amiga_to_string(rhs));                     \
    }                                                                    \
                                                                         \
    static bool decode(const Node& node, type& rhs) {                    \
      if (node.Type() != NodeType::Scalar)                               \
        return false;                                                    \
      return conversion::amiga_from_string(node.Scalar(), rhs);          \
    }                                                                    \
  }
"""

    # slice out the whole original macro by its start and end markers -
    # exact-text matching on 37 backslash-padded lines is too fragile
    m0 = text.index("#define YAML_DEFINE_CONVERT_STREAMABLE(type, negative_op)")
    m1 = text.index("#define YAML_DEFINE_CONVERT_STREAMABLE_SIGNED(type)")
    text = text[:m0] + new_block + "\n" + text[m1:]
    with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(text)
    return "applied"


def patch_yamlcpp_memory(yamldir):
    """yaml-cpp 0.6.3 memory pools: assigning a subtree into a parent inserts
    the child pool's ENTIRE node set into the parent's std::set - bottom-up
    tree building (every save()/load() in the game) is quadratic. Measured:
    building the 17 KB new-game save took 16.9 s at full JIT speed. Upstream
    fixed it later with small-to-large merging; this ports that fix."""
    path = os.path.join(yamldir, "src", "memory.cpp")
    hpath = os.path.join(yamldir, "include", "yaml-cpp", "node", "detail", "memory.h")
    if not (os.path.isfile(path) and os.path.isfile(hpath)):
        return "skipped (no yaml-cpp at %s)" % yamldir
    with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
        text = f.read()
    if "small-to-large" in text:
        return "already"
    old = (
"void memory_holder::merge(memory_holder& rhs) {\n"
"  if (m_pMemory == rhs.m_pMemory)\n"
"    return;\n"
"\n"
"  m_pMemory->merge(*rhs.m_pMemory);\n"
"  rhs.m_pMemory = m_pMemory;\n"
"}\n")
    new = (
"void memory_holder::merge(memory_holder& rhs) {\n"
"  if (m_pMemory == rhs.m_pMemory)\n"
"    return;\n"
"\n"
"  /* AMIGA-PORT: small-to-large (later upstream fix). Always insert the\n"
"   * smaller pool into the larger one, then share the larger. Without this\n"
"   * bottom-up node-tree building is quadratic in total nodes. */\n"
"  if (m_pMemory->size() < rhs.m_pMemory->size())\n"
"    m_pMemory.swap(rhs.m_pMemory);\n"
"  m_pMemory->merge(*rhs.m_pMemory);\n"
"  rhs.m_pMemory = m_pMemory;\n"
"}\n")
    if old not in text:
        raise SystemExit("PATCH FAILED: memory_holder::merge not found in %s" % path)
    text = text.replace(old, new, 1)
    with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(text)

    with open(hpath, "r", encoding="utf-8", errors="surrogateescape") as f:
        h = f.read()
    if "std::size_t size() const" not in h:
        oldh = "  node& create_node();\n  void merge(const memory& rhs);\n"
        newh = ("  node& create_node();\n  void merge(const memory& rhs);\n"
                "  std::size_t size() const { return m_nodes.size(); } /* AMIGA-PORT */\n")
        if oldh not in h:
            raise SystemExit("PATCH FAILED: memory class body not found in %s" % hpath)
        h = h.replace(oldh, newh, 1)
        with open(hpath, "w", encoding="utf-8", errors="surrogateescape") as f:
            f.write(h)
    return "applied"


def patch_yamlcpp_ice(yamldir):
    """gcc 6.5.0b segfaults (ICE) compiling Node::AssignData at -O1 in EVERY
    file that includes yaml.h - build.sh then silently retried those 22 files
    at -O0, which put the whole save/load path (SavedGame, BattleUnit, Tile,
    Mod.cpp ruleset parsing...) at -O0 since the beginning of the port.
    Compiling just this one function at -O0 dodges the ICE; everything else
    in those files returns to -O1."""
    path = os.path.join(yamldir, "include", "yaml-cpp", "node", "impl.h")
    if not os.path.isfile(path):
        return "skipped (no yaml-cpp at %s)" % yamldir
    with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
        text = f.read()
    if "AMIGA-PORT: gcc 6.5 ICE" in text:
        return "already"
    old = "inline void Node::AssignData(const Node& rhs) {\n"
    new = ("__attribute__((optimize(0))) /* AMIGA-PORT: gcc 6.5 ICE at -O1 */\n"
           "inline void Node::AssignData(const Node& rhs) {\n")
    if old not in text:
        raise SystemExit("PATCH FAILED: Node::AssignData not found in %s" % path)
    text = text.replace(old, new, 1)
    with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(text)

    # second ICE site: detail::node::set_data (node.h)
    npath = os.path.join(yamldir, "include", "yaml-cpp", "node", "detail", "node.h")
    with open(npath, "r", encoding="utf-8", errors="surrogateescape") as f:
        ntext = f.read()
    if "AMIGA-PORT: gcc 6.5 ICE" not in ntext:
        nold = "  void set_data(const node& rhs) {\n"
        nnew = ("  __attribute__((optimize(0))) /* AMIGA-PORT: gcc 6.5 ICE at -O1 */\n"
                "  void set_data(const node& rhs) {\n")
        if nold not in ntext:
            raise SystemExit("PATCH FAILED: node::set_data not found in %s" % npath)
        ntext = ntext.replace(nold, nnew, 1)
        with open(npath, "w", encoding="utf-8", errors="surrogateescape") as f:
            f.write(ntext)
    return "applied"



# ---- 6f fast battlescape save: C++ bodies (kept verbatim, appended by edits) --
KILLS_FAST = r"""
	/* AMIGA-PORT: sequence-entry writer, mirrors save() above. */
	void saveFastAmiga(std::string &o, int ind) const
	{
		const int i2 = ind + 2;
		o.append((std::string::size_type)ind, ' '); o += "-\n";
		if (!name.empty()) ay_s(o, i2, "name", Language::wstrToUtf8(name));
		if (!type.empty()) ay_s(o, i2, "type", type);
		ay_s(o, i2, "rank", rank);
		ay_s(o, i2, "race", race);
		ay_s(o, i2, "weapon", weapon);
		ay_s(o, i2, "weaponAmmo", weaponAmmo);
		ay_i(o, i2, "status", (int)status);
		ay_i(o, i2, "faction", (int)faction);
		ay_i(o, i2, "mission", mission);
		ay_i(o, i2, "turn", turn);
		ay_i(o, i2, "side", (int)side);
		ay_i(o, i2, "bodypart", (int)bodypart);
		ay_i(o, i2, "id", id);
	}
"""

STATS_FAST = r"""
	/* AMIGA-PORT: map-body writer at indent ind, mirrors save() above. */
	void saveFastAmiga(std::string &o, int ind) const
	{
		ay_b(o, ind, "wasUnconcious", wasUnconcious);
		if (!kills.empty())
		{
			ay_key(o, ind, "kills"); o += '\n';
			for (std::vector<BattleUnitKills*>::const_iterator i = kills.begin(); i != kills.end(); ++i)
				(*i)->saveFastAmiga(o, ind + 2);
		}
		if (shotAtCounter) ay_i(o, ind, "shotAtCounter", shotAtCounter);
		if (hitCounter) ay_i(o, ind, "hitCounter", hitCounter);
		if (shotByFriendlyCounter) ay_i(o, ind, "shotByFriendlyCounter", shotByFriendlyCounter);
		if (shotFriendlyCounter) ay_i(o, ind, "shotFriendlyCounter", shotFriendlyCounter);
		if (loneSurvivor) ay_b(o, ind, "loneSurvivor", loneSurvivor);
		if (ironMan) ay_b(o, ind, "ironMan", ironMan);
		if (longDistanceHitCounter) ay_i(o, ind, "longDistanceHitCounter", longDistanceHitCounter);
		if (lowAccuracyHitCounter) ay_i(o, ind, "lowAccuracyHitCounter", lowAccuracyHitCounter);
		if (shotsFiredCounter) ay_i(o, ind, "shotsFiredCounter", shotsFiredCounter);
		if (shotsLandedCounter) ay_i(o, ind, "shotsLandedCounter", shotsLandedCounter);
		if (nikeCross) ay_b(o, ind, "nikeCross", nikeCross);
		if (mercyCross) ay_b(o, ind, "mercyCross", mercyCross);
		if (woundsHealed) ay_i(o, ind, "woundsHealed", woundsHealed);
		if (appliedStimulant) ay_i(o, ind, "appliedStimulant", appliedStimulant);
		if (appliedPainKill) ay_i(o, ind, "appliedPainKill", appliedPainKill);
		if (revivedSoldier) ay_i(o, ind, "revivedSoldier", revivedSoldier);
		if (martyr) ay_i(o, ind, "martyr", martyr);
		if (slaveKills) ay_i(o, ind, "slaveKills", slaveKills);
	}
"""

AI_FAST = r"""
/* AMIGA-PORT: map-body writer at indent ind, mirrors save() above. */
void AIModule::saveFastAmiga(std::string &o, int ind) const
{
	int fromNodeID = -1, toNodeID = -1;
	if (_fromNode)
		fromNodeID = _fromNode->getID();
	if (_toNode)
		toNodeID = _toNode->getID();
	ay_i(o, ind, "fromNode", fromNodeID);
	ay_i(o, ind, "toNode", toNodeID);
	ay_i(o, ind, "AIMode", _AIMode);
	ay_iv(o, ind, "wasHitBy", _wasHitBy.empty() ? 0 : &_wasHitBy[0], _wasHitBy.size());
}
"""

NODE_FAST = r"""
/* AMIGA-PORT: sequence-entry writer, mirrors save() above. */
void Node::saveFastAmiga(std::string &o, int ind) const
{
	const int i2 = ind + 2;
	ay_entry_i(o, ind, "id", _id);
	ay_xyz(o, i2, "position", _pos.x, _pos.y, _pos.z);
	ay_i(o, i2, "type", _type);
	ay_i(o, i2, "rank", _rank);
	ay_i(o, i2, "flags", _flags);
	ay_i(o, i2, "reserved", _reserved);
	ay_i(o, i2, "priority", _priority);
	ay_b(o, i2, "allocated", _allocated);
	ay_iv(o, i2, "links", _nodeLinks.empty() ? 0 : &_nodeLinks[0], _nodeLinks.size());
	ay_b(o, i2, "dummy", _dummy);
}
"""

ITEM_FAST = r"""
/* AMIGA-PORT: sequence-entry writer, mirrors save() above. */
void BattleItem::saveFastAmiga(std::string &o, int ind) const
{
	const int i2 = ind + 2;
	ay_entry_i(o, ind, "id", _id);
	ay_s(o, i2, "type", _rules->getType());
	ay_i(o, i2, "owner", _owner ? _owner->getId() : -1);
	if (_previousOwner)
		ay_i(o, i2, "previousOwner", _previousOwner->getId());
	ay_i(o, i2, "unit", _unit ? _unit->getId() : -1);
	if (_inventorySlot)
		ay_s(o, i2, "inventoryslot", _inventorySlot->getId());
	else
		ay_s(o, i2, "inventoryslot", std::string("NULL"));
	ay_i(o, i2, "inventoryX", _inventoryX);
	ay_i(o, i2, "inventoryY", _inventoryY);
	if (_tile)
		ay_xyz(o, i2, "position", _tile->getPosition().x, _tile->getPosition().y, _tile->getPosition().z);
	else
		ay_xyz(o, i2, "position", -1, -1, -1);
	ay_i(o, i2, "ammoqty", _ammoQuantity);
	ay_i(o, i2, "ammoItem", _ammoItem ? _ammoItem->getId() : -1);
	ay_i(o, i2, "painKiller", _painKiller);
	ay_i(o, i2, "heal", _heal);
	ay_i(o, i2, "stimulant", _stimulant);
	ay_i(o, i2, "fuseTimer", _fuseTimer);
	if (_droppedOnAlienTurn)
		ay_b(o, i2, "droppedOnAlienTurn", _droppedOnAlienTurn);
}
"""

UNIT_FAST = r"""
/* AMIGA-PORT: sequence-entry writer, mirrors save() above. */
void BattleUnit::saveFastAmiga(std::string &o, int ind) const
{
	const int i2 = ind + 2;
	ay_entry_i(o, ind, "id", _id);
	ay_s(o, i2, "genUnitType", _type);
	ay_s(o, i2, "genUnitArmor", _armor->getType());
	ay_i(o, i2, "faction", (int)_faction);
	ay_i(o, i2, "status", (int)_status);
	ay_xyz(o, i2, "position", _pos.x, _pos.y, _pos.z);
	ay_i(o, i2, "direction", _direction);
	ay_i(o, i2, "directionTurret", _directionTurret);
	ay_i(o, i2, "tu", _tu);
	ay_i(o, i2, "health", _health);
	ay_i(o, i2, "stunlevel", _stunlevel);
	ay_i(o, i2, "energy", _energy);
	ay_i(o, i2, "morale", _morale);
	ay_b(o, i2, "kneeled", _kneeled);
	ay_b(o, i2, "floating", _floating);
	ay_iv(o, i2, "armor", _currentArmor, 5);
	ay_iv(o, i2, "fatalWounds", _fatalWounds, 6);
	ay_i(o, i2, "fire", _fire);
	ay_i(o, i2, "expBravery", _expBravery);
	ay_i(o, i2, "expReactions", _expReactions);
	ay_i(o, i2, "expFiring", _expFiring);
	ay_i(o, i2, "expThrowing", _expThrowing);
	ay_i(o, i2, "expPsiSkill", _expPsiSkill);
	ay_i(o, i2, "expPsiStrength", _expPsiStrength);
	ay_i(o, i2, "expMelee", _expMelee);
	ay_i(o, i2, "turretType", _turretType);
	ay_b(o, i2, "visible", _visible);
	ay_i(o, i2, "turnsSinceSpotted", _turnsSinceSpotted);
	ay_i(o, i2, "rankInt", _rankInt);
	ay_i(o, i2, "moraleRestored", _moraleRestored);
	if (getAIModule())
	{
		ay_key(o, i2, "AI"); o += '\n';
		getAIModule()->saveFastAmiga(o, i2 + 2);
	}
	ay_i(o, i2, "killedBy", (int)_killedBy);
	if (_originalFaction != _faction)
		ay_i(o, i2, "originalFaction", (int)_originalFaction);
	if (_kills)
		ay_i(o, i2, "kills", _kills);
	if (_faction == FACTION_PLAYER && _dontReselect)
		ay_b(o, i2, "dontReselect", _dontReselect);
	if (!_spawnUnit.empty())
		ay_s(o, i2, "spawnUnit", _spawnUnit);
	ay_i(o, i2, "motionPoints", _motionPoints);
	ay_b(o, i2, "respawn", _respawn);
	ay_s(o, i2, "activeHand", _activeHand);
	ay_key(o, i2, "tempUnitStatistics"); o += '\n';
	_statistics->saveFastAmiga(o, i2 + 2);
	ay_i(o, i2, "murdererId", _murdererId);
	ay_i(o, i2, "fatalShotSide", (int)_fatalShotSide);
	ay_i(o, i2, "fatalShotBodyPart", (int)_fatalShotBodyPart);
	ay_s(o, i2, "murdererWeapon", _murdererWeapon);
	ay_s(o, i2, "murdererWeaponAmmo", _murdererWeaponAmmo);
	if (!_recolor.empty())
	{
		ay_key(o, i2, "recolor"); o += '\n';
		for (std::string::size_type ri = 0; ri < _recolor.size(); ++ri)
		{
			o.append((std::string::size_type)(i2 + 2), ' ');
			o += "- [";
			o += YAML::conversion::amiga_to_string((long long)(int)_recolor[ri].first);
			o += ", ";
			o += YAML::conversion::amiga_to_string((long long)(int)_recolor[ri].second);
			o += "]\n";
		}
	}
	ay_i(o, i2, "mindControllerID", _mindControllerID);
}
"""

SBG_FAST = r"""
/* AMIGA-PORT: writes the battleGame map body at indent 2, mirroring save()
 * field by field - no YAML::Node tree, straight text (see amiga_yamlout.h). */
void SavedBattleGame::saveFastAmiga(std::string &o) const
{
	const int ind = 2;
	if (_objectivesNeeded)
	{
		ay_i(o, ind, "objectivesDestroyed", _objectivesDestroyed);
		ay_i(o, ind, "objectivesNeeded", _objectivesNeeded);
		ay_i(o, ind, "objectiveType", _objectiveType);
	}
	ay_i(o, ind, "width", _mapsize_x);
	ay_i(o, ind, "length", _mapsize_y);
	ay_i(o, ind, "height", _mapsize_z);
	ay_s(o, ind, "missionType", _missionType);
	ay_i(o, ind, "globalshade", _globalShade);
	ay_i(o, ind, "turn", _turn);
	ay_i(o, ind, "selectedUnit", (_selectedUnit ? _selectedUnit->getId() : -1));
	if (!_mapDataSets.empty())
	{
		ay_key(o, ind, "mapdatasets"); o += '\n';
		for (std::vector<MapDataSet*>::const_iterator i = _mapDataSets.begin(); i != _mapDataSets.end(); ++i)
		{
			o.append((std::string::size_type)(ind + 2), ' ');
			o += "- ";
			AmigaYamlScalar(o, (*i)->getName());
			o += '\n';
		}
	}
	/* The loader reads these six with as<Uint8>, which has CHARACTER
	 * semantics (that is how upstream round-tripped them: "\x04"). Writing
	 * them as numbers made as<Uint8>("4") return 52 -> unserializeInt
	 * assert -> returncode 127 on every load. tileTotalBytesPer is read
	 * as<Uint32> and stays numeric. */
	ay_s(o, ind, "tileIndexSize", std::string(1, (char)Tile::serializationKey.index));
	ay_i(o, ind, "tileTotalBytesPer", (int)Tile::serializationKey.totalBytes);
	ay_s(o, ind, "tileFireSize", std::string(1, (char)Tile::serializationKey._fire));
	ay_s(o, ind, "tileSmokeSize", std::string(1, (char)Tile::serializationKey._smoke));
	ay_s(o, ind, "tileIDSize", std::string(1, (char)Tile::serializationKey._mapDataID));
	ay_s(o, ind, "tileSetIDSize", std::string(1, (char)Tile::serializationKey._mapDataSetID));
	ay_s(o, ind, "tileBoolFieldsSize", std::string(1, (char)Tile::serializationKey.boolFields));
	{
		size_t tileDataSize = Tile::serializationKey.totalBytes * _mapsize_z * _mapsize_y * _mapsize_x;
		Uint8* tileData = (Uint8*) calloc(tileDataSize, 1);
		Uint8* w = tileData;
		for (int i = 0; i < _mapsize_z * _mapsize_y * _mapsize_x; ++i)
		{
			if (!_tiles[i]->isVoid())
			{
				serializeInt(&w, Tile::serializationKey.index, i);
				_tiles[i]->saveBinary(&w);
			}
			else
			{
				tileDataSize -= Tile::serializationKey.totalBytes;
			}
		}
		ay_u(o, ind, "totalTiles", tileDataSize / Tile::serializationKey.totalBytes);
		/* single-quoted: yaml-cpp's PLAIN-scalar scanner hangs (quadratic) on a
		 * 95 KB unquoted token; the quoted scanner is linear. Base64 contains
		 * no quotes, so no escaping needed. */
		ay_key(o, ind, "binTiles");
		o += " '";
		o += YAML::EncodeBase64(tileData, tileDataSize);
		o += "'\n";
		free(tileData);
	}
	if (!_nodes.empty())
	{
		ay_key(o, ind, "nodes"); o += '\n';
		for (std::vector<Node*>::const_iterator i = _nodes.begin(); i != _nodes.end(); ++i)
			(*i)->saveFastAmiga(o, ind + 2);
	}
	if (_missionType == "STR_BASE_DEFENSE")
	{
		ay_key(o, ind, "moduleMap"); o += '\n';
		for (std::vector< std::vector<std::pair<int, int> > >::const_iterator r = _baseModules.begin(); r != _baseModules.end(); ++r)
		{
			o.append((std::string::size_type)(ind + 2), ' ');
			o += "-\n";
			for (std::vector<std::pair<int, int> >::const_iterator c = r->begin(); c != r->end(); ++c)
			{
				o.append((std::string::size_type)(ind + 4), ' ');
				o += "- [";
				o += YAML::conversion::amiga_to_string((long long)c->first);
				o += ", ";
				o += YAML::conversion::amiga_to_string((long long)c->second);
				o += "]\n";
			}
		}
	}
	if (!_units.empty())
	{
		ay_key(o, ind, "units"); o += '\n';
		for (std::vector<BattleUnit*>::const_iterator i = _units.begin(); i != _units.end(); ++i)
			(*i)->saveFastAmiga(o, ind + 2);
	}
	if (!_items.empty())
	{
		ay_key(o, ind, "items"); o += '\n';
		for (std::vector<BattleItem*>::const_iterator i = _items.begin(); i != _items.end(); ++i)
			(*i)->saveFastAmiga(o, ind + 2);
	}
	ay_i(o, ind, "tuReserved", (int)_tuReserved);
	ay_b(o, ind, "kneelReserved", _kneelReserved);
	ay_i(o, ind, "depth", _depth);
	ay_i(o, ind, "ambience", _ambience);
	ay_d(o, ind, "ambientVolume", _ambientVolume);
	if (!_recoverGuaranteed.empty())
	{
		ay_key(o, ind, "recoverGuaranteed"); o += '\n';
		for (std::vector<BattleItem*>::const_iterator i = _recoverGuaranteed.begin(); i != _recoverGuaranteed.end(); ++i)
			(*i)->saveFastAmiga(o, ind + 2);
	}
	if (!_recoverConditional.empty())
	{
		ay_key(o, ind, "recoverConditional"); o += '\n';
		for (std::vector<BattleItem*>::const_iterator i = _recoverConditional.begin(); i != _recoverConditional.end(); ++i)
			(*i)->saveFastAmiga(o, ind + 2);
	}
	ay_s(o, ind, "music", _music);
	ay_i(o, ind, "turnLimit", _turnLimit);
	ay_i(o, ind, "chronoTrigger", (int)_chronoTrigger);
	ay_i(o, ind, "cheatTurn", _cheatTurn);
}
"""


GLOBE_CACHE_OLD = r'''void Globe::cache(std::list<Polygon*> *polygons, std::list<Polygon*> *cache)
{
	// Clear existing cache
	for (std::list<Polygon*>::iterator i = cache->begin(); i != cache->end(); ++i)
	{
		delete *i;
	}
	cache->clear();

	// Pre-calculate values to cache
	for (std::list<Polygon*>::iterator i = polygons->begin(); i != polygons->end(); ++i)
	{
		// Is quad on the back face?
		double closest = 0.0;
		double z;
		double furthest = 0.0;
		for (int j = 0; j < (*i)->getPoints(); ++j)
		{
			z = cos(_cenLat) * cos((*i)->getLatitude(j)) * cos((*i)->getLongitude(j) - _cenLon) + sin(_cenLat) * sin((*i)->getLatitude(j));
			if (z > closest)
				closest = z;
			else if (z < furthest)
				furthest = z;
		}
		if (-furthest > closest)
			continue;

		Polygon* p = new Polygon(**i);

		// Convert coordinates
		for (int j = 0; j < p->getPoints(); ++j)
		{
			Sint16 x, y;
			polarToCart(p->getLongitude(j), p->getLatitude(j), &x, &y);
			p->setX(j, x);
			p->setY(j, y);
		}

		cache->push_back(p);
	}
}
'''

GLOBE_CACHE_NEW = r'''/* AMIGA-PORT: per-cached-polygon view-space normals (Q1.14), parallel to
 * _cacheLand order; consumed by the flat-shaded drawLand (amigaFlatGlobe). */
static std::vector<CordFix> s_polyNorm_;

void Globe::cache(std::list<Polygon*> *polygons, std::list<Polygon*> *cache)
{
	// Clear existing cache
	for (std::list<Polygon*>::iterator i = cache->begin(); i != cache->end(); ++i)
	{
		delete *i;
	}
	cache->clear();
	s_polyNorm_.clear();

	/* AMIGA-PORT pkt 4: the whole recache is integer Q1.14. Vertex sin/cos
	 * are precomputed ONCE as Sint16; a recache does 4 trig calls for the
	 * screen centre and then only 32-bit multiplies. Shared vertices compute
	 * identically, so adjacent polygons cannot crack. Radius is Q4 (1/16 px
	 * quantisation - invisible at 320x200). */
	static std::vector<Sint16> vt_;
	static const void *vtSrc_ = 0;
	if (vtSrc_ != (const void *)polygons)
	{
		vt_.clear();
		for (std::list<Polygon*>::iterator i = polygons->begin(); i != polygons->end(); ++i)
			for (int j = 0; j < (*i)->getPoints(); ++j)
			{
				vt_.push_back((Sint16)floor(sin((*i)->getLatitude(j)) * 16384.0 + 0.5));
				vt_.push_back((Sint16)floor(cos((*i)->getLatitude(j)) * 16384.0 + 0.5));
				vt_.push_back((Sint16)floor(sin((*i)->getLongitude(j)) * 16384.0 + 0.5));
				vt_.push_back((Sint16)floor(cos((*i)->getLongitude(j)) * 16384.0 + 0.5));
			}
		vtSrc_ = (const void *)polygons;
	}
	const Sint32 sCLat = (Sint32)floor(sin(_cenLat) * 16384.0 + 0.5);
	const Sint32 cCLat = (Sint32)floor(cos(_cenLat) * 16384.0 + 0.5);
	const Sint32 sCLon = (Sint32)floor(sin(_cenLon) * 16384.0 + 0.5);
	const Sint32 cCLon = (Sint32)floor(cos(_cenLon) * 16384.0 + 0.5);
	const Sint32 radQ = (Sint32)(_radius * 16.0 + 0.5);

	size_t vi = 0;
	for (std::list<Polygon*>::iterator i = polygons->begin(); i != polygons->end(); ++i)
	{
		// Is quad on the back face?
		Sint32 closest = 0;
		Sint32 furthest = 0;
		const size_t vbase = vi;
		for (int j = 0; j < (*i)->getPoints(); ++j, vi += 4)
		{
			const Sint32 sLat = vt_[vi], cLat = vt_[vi + 1];
			const Sint32 sLon = vt_[vi + 2], cLon = vt_[vi + 3];
			const Sint32 cosDiff = (cLon * cCLon + sLon * sCLon) >> 14;
			const Sint32 z = ((((cCLat * cLat) >> 14) * cosDiff) >> 14) + ((sCLat * sLat) >> 14);
			if (z > closest)
				closest = z;
			else if (z < furthest)
				furthest = z;
		}
		if (-furthest > closest)
			continue;

		Polygon* p = new Polygon(**i);

		// Convert coordinates - same projection as polarToCart, in Q1.14
		size_t vj = vbase;
		Sint32 nX = 0, nY = 0, nZ = 0;
		for (int j = 0; j < p->getPoints(); ++j, vj += 4)
		{
			const Sint32 sLat = vt_[vj], cLat = vt_[vj + 1];
			const Sint32 sLon = vt_[vj + 2], cLon = vt_[vj + 3];
			const Sint32 cosDiff = (cLon * cCLon + sLon * sCLon) >> 14;
			const Sint32 sinDiff = (sLon * cCLon - cLon * sCLon) >> 14;
			const Sint32 vx = (cLat * sinDiff) >> 14;
			const Sint32 vy = ((cCLat * sLat) >> 14) - ((((sCLat * cLat) >> 14) * cosDiff) >> 14);
			const Sint32 vz = ((((cCLat * cLat) >> 14) * cosDiff) >> 14) + ((sCLat * sLat) >> 14);
			p->setX(j, (Sint16)(_cenX + ((radQ * vx) >> 18)));
			p->setY(j, (Sint16)(_cenY + ((radQ * vy) >> 18)));
			nX += vx; nY += vy; nZ += vz;
		}
		{
			const int np_ = p->getPoints();
			CordFix nf_;
			nf_.x = (Sint16)(nX / np_);
			nf_.y = (Sint16)(nY / np_);
			nf_.z = (Sint16)(nZ / np_);
			s_polyNorm_.push_back(nf_);
		}

		cache->push_back(p);
	}
}
'''


GLOBE_LAND_OLD = r'''void Globe::drawLand()
{
	Sint16 x[4], y[4];

	for (std::list<Polygon*>::iterator i = _cacheLand.begin(); i != _cacheLand.end(); ++i)
	{
		// Convert coordinates
		for (int j = 0; j < (*i)->getPoints(); ++j)
		{
			x[j] = (*i)->getX(j);
			y[j] = (*i)->getY(j);
		}

		// Apply textures according to zoom and shade
		drawTexturedPolygon(x, y, (*i)->getPoints(), _texture->getFrame((*i)->getTexture() + _zoomTexture), 0, 0);
	}
}
'''

GLOBE_LAND_NEW = r'''void Globe::drawLand()
{
	Sint16 x[4], y[4];

#ifdef __AMIGA__
	if (Options::amigaFlatGlobe)
	{
		/* AMIGA-PORT: flat sun-shaded polygons - see the patch script. */
		static Uint8 texBase_[128];
		static bool texInit_ = false;
		if (!texInit_)
		{
			memset(texBase_, 0xFF, sizeof(texBase_));
			texInit_ = true;
		}
		const CordFix sunF_ = cordToFix(getSunDirection(_cenLon, _cenLat));
		size_t k_ = 0;
		for (std::list<Polygon*>::iterator i = _cacheLand.begin(); i != _cacheLand.end(); ++i, ++k_)
		{
			for (int j = 0; j < (*i)->getPoints(); ++j)
			{
				x[j] = (*i)->getX(j);
				y[j] = (*i)->getY(j);
			}
			const int ti_ = (*i)->getTexture() + _zoomTexture;
			Uint8 base_ = 16;
			if (ti_ >= 0 && ti_ < 128)
			{
				if (texBase_[ti_] == 0xFF)
				{
					/* dominant colour of this texture tile, found once */
					Surface *fr_ = _texture->getFrame(ti_);
					static int cnt_[256];
					memset(cnt_, 0, sizeof(cnt_));
					if (fr_)
					{
						SDL_Surface *fs_ = fr_->getSurface();
						for (int yy_ = 0; yy_ < fs_->h; ++yy_)
						{
							const Uint8 *row_ = (const Uint8 *)fs_->pixels + (size_t)yy_ * fs_->pitch;
							for (int xx_ = 0; xx_ < fs_->w; ++xx_)
								++cnt_[row_[xx_]];
						}
					}
					int best_ = 1;
					for (int c_ = 2; c_ < 256; ++c_)
						if (cnt_[c_] > cnt_[best_]) best_ = c_;
					texBase_[ti_] = (Uint8)best_;
				}
				base_ = texBase_[ti_];
			}
			int off_ = 0;
			if (k_ < s_polyNorm_.size())
			{
				const CordFix &n_ = s_polyNorm_[k_];
				const Sint32 dot_ = ((Sint32)n_.x * sunF_.x + (Sint32)n_.y * sunF_.y + (Sint32)n_.z * sunF_.z) >> 14;
				off_ = (int)(((16384L - (long)dot_) * 5L) >> 15);
			}
			const int g_ = base_ & 0xF0;
			int s_ = (base_ & 15) + off_ - 1;
			if (s_ < 0) s_ = 0;
			if (s_ > 15) s_ = 15;
			drawPolygon(x, y, (*i)->getPoints(), (Uint8)(g_ + s_));
		}
		return;
	}
#endif
	for (std::list<Polygon*>::iterator i = _cacheLand.begin(); i != _cacheLand.end(); ++i)
	{
		// Convert coordinates
		for (int j = 0; j < (*i)->getPoints(); ++j)
		{
			x[j] = (*i)->getX(j);
			y[j] = (*i)->getY(j);
		}

		// Apply textures according to zoom and shade
		drawTexturedPolygon(x, y, (*i)->getPoints(), _texture->getFrame((*i)->getTexture() + _zoomTexture), 0, 0);
	}
}
'''


GLOBE_CIRCLE_OLD = r'''void Globe::drawGlobeCircle(double lat, double lon, double radius, int segments)
{
	double x, y, x2 = 0, y2 = 0;
	double lat1, lon1;
	double seg = M_PI / (static_cast<double>(segments) / 2);
	for (double az = 0; az <= M_PI*2+0.01; az+=seg) //48 circle segments
	{
		//calculating sphere-projected circle
		lat1 = asin(sin(lat) * cos(radius) + cos(lat) * sin(radius) * cos(az));
		lon1 = lon + atan2(sin(az) * sin(radius) * cos(lat), cos(radius) - sin(lat) * sin(lat1));
		polarToCart(lon1, lat1, &x, &y);
		if ( AreSame(az, 0.0) ) //first vertex is for initialization only
		{
			x2=x;
			y2=y;
			continue;
		}
		if (!pointBack(lon1,lat1))
			XuLine(_radars, this, x, y, x2, y2, 4);
		x2=x; y2=y;
	}
}
'''

GLOBE_CIRCLE_NEW = r'''void Globe::drawGlobeCircle(double lat, double lon, double radius, int segments)
{
	/* AMIGA-PORT: pure vector form. A circle of angular radius r around the
	 * unit vector C is P(t) = C*cos r + (N1*cos t + N2*sin t)*sin r with
	 * N1/N2 an orthonormal basis at C; P rotates into view space with the
	 * same identities the polygon cache uses. No asin/atan2 per segment. */
	static double lutC[64], lutS[64];
	static int lutN = 0;
	if (segments < 3 || segments > 64) segments = 48;
	if (lutN != segments)
	{
		for (int k = 0; k < segments; ++k)
		{
			lutC[k] = cos(2.0 * M_PI * (double)k / (double)segments);
			lutS[k] = sin(2.0 * M_PI * (double)k / (double)segments);
		}
		lutN = segments;
	}
	const double sLat = sin(lat), cLat = cos(lat);
	const double sLon = sin(lon), cLon = cos(lon);
	const double cR = cos(radius), sR = sin(radius);
	const double Cx = cLat * cLon, Cy = cLat * sLon, Cz = sLat;
	const double N1x = -sLat * cLon, N1y = -sLat * sLon, N1z = cLat;
	const double N2x = -sLon, N2y = cLon, N2z = 0.0;
	const double sCLat = sin(_cenLat), cCLat = cos(_cenLat);
	const double sCLon = sin(_cenLon), cCLon = cos(_cenLon);
	double px = 0.0, py = 0.0;
	int have = 0, backPrev = 1;
	for (int k = 0; k <= lutN; ++k)
	{
		const int ki = (k == lutN) ? 0 : k;
		const double Px = Cx * cR + (N1x * lutC[ki] + N2x * lutS[ki]) * sR;
		const double Py = Cy * cR + (N1y * lutC[ki] + N2y * lutS[ki]) * sR;
		const double Pz = Cz * cR + (N1z * lutC[ki] + N2z * lutS[ki]) * sR;
		/* world (Px,Py,Pz) -> view: cosLat*cos(dLon) etc. fall out directly */
		const double cd = Px * cCLon + Py * sCLon;
		const double sd = Py * cCLon - Px * sCLon;
		const double vy = cCLat * Pz - sCLat * cd;
		const double vz = cCLat * cd + sCLat * Pz;
		const double sx = _cenX + _radius * sd;
		const double sy = _cenY + _radius * vy;
		const int back = (vz < 0.0);
		if (have && !back && !backPrev)
			XuLine(_radars, this, sx, sy, px, py, 4);
		px = sx; py = sy; have = 1; backPrev = back;
	}
}
'''

GLOBE_XULINE_OLD = r'''	double deltax = x2-x1, deltay = y2-y1;
	bool inv;
	Sint16 tcol;
	double len,x0,y0,SX,SY;
	if (abs((int)y2-(int)y1) > abs((int)x2-(int)x1))
	{
		len=abs((int)y2-(int)y1);
		inv=false;
	}
	else
	{
		len=abs((int)x2-(int)x1);
		inv=true;
	}

	if (y2<y1) {
	SY=-1;
  } else if ( AreSame(deltay, 0.0) ) {
	SY=0;
  } else {
	SY=1;
  }

	if (x2<x1) {
	SX=-1;
  } else if ( AreSame(deltax, 0.0) ) {
	SX=0;
  } else {
	SX=1;
  }

	x0=x1;  y0=y1;
	if (inv)
		SY=(deltay/len);
	else
		SX=(deltax/len);

	while (len>0)
	{
		tcol=src->getPixel((int)x0,(int)y0);
		if (tcol)
		{
			const int d = tcol & helper::ColorGroup;
			if (d ==  OCEAN_COLOR || d ==  OCEAN_COLOR + 16)
			{
				//this pixel is ocean
				tcol = OCEAN_COLOR + shade + 8;
			}
			else
			{
				const int e = tcol + shade;
				if (e > d + helper::ColorShade)
					tcol = d + helper::ColorShade;
				else tcol = e;
			}
			surface->setPixel((int)x0,(int)y0,tcol);
		}
		x0+=SX;
		y0+=SY;
		len-=1.0;
	}
}
'''

GLOBE_XULINE_NEW = r'''	/* AMIGA-PORT: 16.16 fixed-point walk - the original stepped x0/y0 as
	 * doubles with a double->int cast per pixel (soft-float on this CPU). */
	Sint16 tcol;
	Sint32 fx1 = (Sint32)(x1 * 65536.0), fy1 = (Sint32)(y1 * 65536.0);
	Sint32 fx2 = (Sint32)(x2 * 65536.0), fy2 = (Sint32)(y2 * 65536.0);
	Sint32 adx = (fx2 > fx1) ? fx2 - fx1 : fx1 - fx2;
	Sint32 ady = (fy2 > fy1) ? fy2 - fy1 : fy1 - fy2;
	int ilen = (int)(((adx > ady) ? adx : ady) >> 16);
	if (ilen < 1) ilen = 1;
	const Sint32 stx = (fx2 - fx1) / ilen;
	const Sint32 sty = (fy2 - fy1) / ilen;
	Sint32 x0 = fx1, y0 = fy1;
	for (int i_ = 0; i_ < ilen; ++i_)
	{
		tcol = src->getPixel((int)(x0 >> 16), (int)(y0 >> 16));
		if (tcol)
		{
			const int d = tcol & helper::ColorGroup;
			if (d ==  OCEAN_COLOR || d ==  OCEAN_COLOR + 16)
			{
				//this pixel is ocean
				tcol = OCEAN_COLOR + shade + 8;
			}
			else
			{
				const int e = tcol + shade;
				if (e > d + helper::ColorShade)
					tcol = d + helper::ColorShade;
				else tcol = e;
			}
			surface->setPixel((int)(x0 >> 16), (int)(y0 >> 16), tcol);
		}
		x0 += stx;
		y0 += sty;
	}
}
'''


def patch_yamlcpp_tick(yamldir):
    """Progress hook for long single-file parses (the language file takes
    ~22 s on the 040/40 with nothing moving on the loading bar). Stream::get
    counts consumed characters and fires an optional callback every 8 KB."""
    path = os.path.join(yamldir, "src", "stream.cpp")
    if not os.path.isfile(path):
        return "skipped (no yaml-cpp at %s)" % yamldir
    with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
        text = f.read()
    if "YamlTickHook" in text:
        return "already"
    old = "char Stream::get() {\n  char ch = peek();\n"
    new = ("/* AMIGA-PORT: parse-progress hook (loading splash) */\n"
           "extern \"C\" {\n"
           "void (*YamlTickHook)(unsigned long) = 0;\n"
           "unsigned long YamlTickCount = 0;\n"
           "}\n\n"
           "char Stream::get() {\n  char ch = peek();\n"
           "  if ((++YamlTickCount & 0x1FFF) == 0 && YamlTickHook)\n"
           "    YamlTickHook(YamlTickCount);\n")
    if old not in text:
        raise SystemExit("PATCH FAILED: Stream::get not found in %s" % path)
    text = text.replace(old, new, 1)
    with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(text)
    return "applied"


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit(__doc__)
    src = sys.argv[1]
    if len(sys.argv) == 3:
        print("  %-24s %s" % ("yaml-cpp LoadFile", patch_yamlcpp(sys.argv[2])))
        print("  %-24s %s" % ("yaml-cpp fast convert", patch_yamlcpp_convert(sys.argv[2])))
        print("  %-24s %s" % ("yaml-cpp pool merge", patch_yamlcpp_memory(sys.argv[2])))
        print("  %-24s %s" % ("yaml-cpp ICE dodge", patch_yamlcpp_ice(sys.argv[2])))
        print("  %-24s %s" % ("yaml-cpp tick hook", patch_yamlcpp_tick(sys.argv[2])))
    if not os.path.isdir(os.path.join(src, "Engine")):
        raise SystemExit("not an OpenXcom src directory: %s" % src)

    results = []

    # 1. Zoom: upstream scales 320x200 up through SDL_gfx, HQX/xBRZ and SSE2.
    #    The port runs at native resolution and needs none of it.
    results.append(("Engine/Zoom.cpp", replace_file(src, "Engine/Zoom.cpp")))

    # 1b. CrossPlatform: upstream is Win32 + X11 + POSIX in one file, none of
    #     which exists here. Replaced wholesale rather than #ifdef'd.
    results.append(("Engine/CrossPlatform.cpp", replace_file(src, "Engine/CrossPlatform.cpp")))

    # 2. Video defaults. Upstream has a small-screen branch for the Dingoo
    #    handheld that is exactly what an Amiga wants - 320x200, fullscreen,
    #    no async blit - except for the keyboard, which we do have.
    results.append(("Engine/Options.cpp", edit(
        os.path.join(src, "Engine", "Options.cpp"),
        "#ifdef DINGOO\n"
        "\t_info.push_back(OptionInfo(\"displayWidth\", &displayWidth, Screen::ORIGINAL_WIDTH));\n"
        "\t_info.push_back(OptionInfo(\"displayHeight\", &displayHeight, Screen::ORIGINAL_HEIGHT));\n"
        "\t_info.push_back(OptionInfo(\"fullscreen\", &fullscreen, true));\n"
        "\t_info.push_back(OptionInfo(\"asyncBlit\", &asyncBlit, false));\n"
        "\t_info.push_back(OptionInfo(\"keyboardMode\", (int*)&keyboardMode, KEYBOARD_OFF));",
        MARK + " Amiga shares the Dingoo small-screen defaults, but has a real keyboard. */\n"
        "#if defined(DINGOO) || defined(__AMIGA__)\n"
        "\t_info.push_back(OptionInfo(\"displayWidth\", &displayWidth, Screen::ORIGINAL_WIDTH));\n"
        "\t_info.push_back(OptionInfo(\"displayHeight\", &displayHeight, Screen::ORIGINAL_HEIGHT));\n"
        "\t_info.push_back(OptionInfo(\"fullscreen\", &fullscreen, true));\n"
        "\t_info.push_back(OptionInfo(\"asyncBlit\", &asyncBlit, false));\n"
        "#ifdef __AMIGA__\n"
        "\t_info.push_back(OptionInfo(\"keyboardMode\", (int*)&keyboardMode, KEYBOARD_ON));\n"
        "#else\n"
        "\t_info.push_back(OptionInfo(\"keyboardMode\", (int*)&keyboardMode, KEYBOARD_OFF));\n"
        "#endif",
        "small-screen video defaults")))

    # 2a. Aligned surface buffers. libnix has no posix_memalign, and upstream
    #     already has a branch for exactly this situation - MorphOS uses plain
    #     calloc. AmigaOS joins it: malloc here is AllocMem-backed and hands
    #     out 8-byte aligned blocks, which is all the blitters in this port
    #     need (nothing uses 16-byte SIMD loads on a 68020).
    results.append(("Engine/Surface.cpp", edit(
        os.path.join(src, "Engine", "Surface.cpp"),
        "\t#ifdef __MORPHOS__\n"
        "\n"
        "\tbuffer = calloc( total, 1 );",
        "\t#if defined(__MORPHOS__) || defined(__AMIGA__)\n"
        "\n"
        "\tbuffer = calloc( total, 1 );",
        "no posix_memalign in libnix")))

    # 2b. src/dirent.h is a Microsoft Visual Studio shim whose non-MSVC branch
    #     says #include <dirent.h> - which finds itself again, because the
    #     build puts src/ on the include path. The real libnix dirent.h then
    #     never gets included and getFolderContents does not compile. The shim
    #     has no purpose in this build, so it goes.
    dirent = os.path.join(src, "dirent.h")
    if os.path.exists(dirent):
        os.remove(dirent)
        results.append(("dirent.h", "removed (MSVC shim)"))
    else:
        results.append(("dirent.h", "already"))

    # 3. The one Amiga-specific line in the game's own source: pick the
    #    display before anything opens one. Everything it needs lives in
    #    native/, so this stays a single call rather than a block of code.
    results.append(("main.cpp", edit(
        os.path.join(src, "main.cpp"),
        "\tif (!Options::init(argc, argv))",
        MARK + " choose AGA / RTG (or ask) before any screen exists. */\n"
        "#ifdef __AMIGA__\n"
        "\tamiga_select_backend(argc, argv);\n"
        "#endif\n"
        "\tif (!Options::init(argc, argv))",
        "display backend selection")))

    results.append(("main.cpp (include)", edit(
        os.path.join(src, "main.cpp"),
        "#include \"Menu/StartState.h\"",
        "#include \"Menu/StartState.h\"\n"
        "#ifdef __AMIGA__\n"
        "#include \"amiga_startup.h\"\n"
        "#include \"amiga_trap.h\"\n"
        "#include <cstdio>\n"
        "#include <cstdlib>\n"
        "#endif",
        "display backend selection include")))

    # 3b. Name and version of the port. The main menu and the window title
    #     say "AmiXcom 0.3.5 alpha" instead of "OpenXcom 1.0 Dev".
    results.append(("version.h (AmiXcom)", edit(
        os.path.join(src, "version.h"),
        '#define OPENXCOM_VERSION_SHORT "1.0"\n'
        '#define OPENXCOM_VERSION_LONG "1.0.0.0"\n'
        '#define OPENXCOM_VERSION_NUMBER 1,0,0,0\n',
        '#ifdef AMIGA_FPU_BUILD\n'
        '#define OPENXCOM_VERSION_SHORT "0.6.0 FPU"\n'
        '#else\n'
        '#define OPENXCOM_VERSION_SHORT "0.6.0"\n'
        '#endif\n'
        '#define OPENXCOM_VERSION_LONG "0.6.0.0"\n'
        '#define OPENXCOM_VERSION_NUMBER 0,6,0,0\n'
        '#define OPENXCOM_VERSION_GIT ""\n',
        "port version")))
    results.append(("MainMenuState.cpp (AmiXcom title)", edit(
        os.path.join(src, "Menu", "MainMenuState.cpp"),
        '\ttitle << tr("STR_OPENXCOM") << L"\\x02";\n',
        '\ttitle << L"AmiXcom 68K" << L"\\x02";\n',
        "port name in main menu")))
    results.append(("main.cpp (AmiXcom title)", edit(
        os.path.join(src, "main.cpp"),
        '\ttitle << "OpenXcom " << OPENXCOM_VERSION_SHORT << OPENXCOM_VERSION_GIT;\n',
        '\ttitle << "AmiXcom 68K " << OPENXCOM_VERSION_SHORT << OPENXCOM_VERSION_GIT;\n',
        "port name in window title")))

    # 3c. FPS counter on by default - the user wants it in the corner while the
    #     port is being optimised (a fresh options.cfg would otherwise hide it).
    results.append(("Options.cpp (fpsCounter default on)", edit(
        os.path.join(src, "Engine", "Options.cpp"),
        '\t_info.push_back(OptionInfo("fpsCounter", &fpsCounter, false));\n',
        '\t_info.push_back(OptionInfo("fpsCounter", &fpsCounter, true)); /* AMIGA-PORT: default on */\n',
        "fps counter default")))

    # 3d. The "Amiga" options tab (step 1 of the user's plan, 2026-08-16):
    #     first tab of the options screen, holding the port's own settings -
    #     Amiga screen title bar on/off and mouse pointer original/Amiga-only.
    #     The screen itself is a new file pair (native/oxc-replace/Menu/
    #     OptionsAmigaState.*); everything below wires it in.
    results.append(("Menu/OptionsAmigaState.h", replace_file(src, os.path.join("Menu", "OptionsAmigaState.h"))))
    results.append(("Menu/OptionsAmigaState.cpp", replace_file(src, os.path.join("Menu", "OptionsAmigaState.cpp"))))
    results.append(("Options.inc.h (amiga options)", edit(
        os.path.join(src, "Engine", "Options.inc.h"),
        "OPT std::string language, useOpenGLShader;\n",
        "OPT std::string language, useOpenGLShader;\n"
        "// AMIGA-PORT: the \"Amiga\" options tab\n"
        "OPT bool amigaAppBar;\n"
        "OPT int amigaCursor;\n"
        "OPT int amigaAccurateFov; /* 0 fast, 1 accurate, 2 test */\n",
        "amiga option variables")))
    results.append(("Options.cpp (amiga OptionInfo)", edit(
        os.path.join(src, "Engine", "Options.cpp"),
        "\t_info.push_back(OptionInfo(\"fpsCounter\", &fpsCounter, true)); /* AMIGA-PORT: default on */\n",
        "\t_info.push_back(OptionInfo(\"fpsCounter\", &fpsCounter, true)); /* AMIGA-PORT: default on */\n"
        "\t_info.push_back(OptionInfo(\"amigaAppBar\", &amigaAppBar, true));\n"
        "\t_info.push_back(OptionInfo(\"amigaCursor\", &amigaCursor, 1)); /* default: Amiga pointer */\n"
        "\t_info.push_back(OptionInfo(\"amigaAccurateFov\", &amigaAccurateFov, 1)); /* default: Accurate - same speed since the pair-update */\n",
        "amiga OptionInfo")))
    results.append(("OptionsBaseState.h (btnAmiga)", edit(
        os.path.join(src, "Menu", "OptionsBaseState.h"),
        "\tTextButton *_btnVideo, *_btnAudio, *_btnControls, *_btnGeoscape, *_btnBattlescape, *_btnAdvanced, *_btnMods;\n",
        "\tTextButton *_btnAmiga, *_btnVideo, *_btnAudio, *_btnControls, *_btnGeoscape, *_btnBattlescape, *_btnAdvanced, *_btnMods;\n",
        "amiga tab button member")))
    results.append(("OptionsBaseState.cpp (include)", edit(
        os.path.join(src, "Menu", "OptionsBaseState.cpp"),
        "#include \"OptionsVideoState.h\"\n",
        "#include \"OptionsVideoState.h\"\n"
        "#include \"OptionsAmigaState.h\"\n",
        "amiga tab include")))
    results.append(("OptionsBaseState.cpp (buttons)", edit(
        os.path.join(src, "Menu", "OptionsBaseState.cpp"),
        "\t_btnVideo = new TextButton(80, 16, 8, 8);\n"
        "\t_btnAudio = new TextButton(80, 16, 8, 28);\n"
        "\t_btnControls = new TextButton(80, 16, 8, 48);\n"
        "\t_btnGeoscape = new TextButton(80, 16, 8, 68);\n"
        "\t_btnBattlescape = new TextButton(80, 16, 8, 88);\n"
        "\t_btnAdvanced = new TextButton(80, 16, 8, 108);\n"
        "\t_btnMods = new TextButton(80, 16, 8, 128);\n",
        "\t/* AMIGA-PORT: an eighth tab, \"Amiga\", first; the column is packed to 17 px\n"
        "\t * per button so the tooltip at y=148 keeps its place. */\n"
        "\t_btnAmiga = new TextButton(80, 16, 8, 8);\n"
        "\t_btnVideo = new TextButton(80, 16, 8, 25);\n"
        "\t_btnAudio = new TextButton(80, 16, 8, 42);\n"
        "\t_btnControls = new TextButton(80, 16, 8, 59);\n"
        "\t_btnGeoscape = new TextButton(80, 16, 8, 76);\n"
        "\t_btnBattlescape = new TextButton(80, 16, 8, 93);\n"
        "\t_btnAdvanced = new TextButton(80, 16, 8, 110);\n"
        "\t_btnMods = new TextButton(80, 16, 8, 127);\n",
        "amiga tab button")))
    results.append(("OptionsBaseState.cpp (add)", edit(
        os.path.join(src, "Menu", "OptionsBaseState.cpp"),
        "\tadd(_btnVideo, \"button\", \"optionsMenu\");\n",
        "\tadd(_btnAmiga, \"button\", \"optionsMenu\");\n"
        "\tadd(_btnVideo, \"button\", \"optionsMenu\");\n",
        "amiga tab add")))
    results.append(("OptionsBaseState.cpp (text)", edit(
        os.path.join(src, "Menu", "OptionsBaseState.cpp"),
        "\t_btnVideo->setText(tr(\"STR_VIDEO\"));\n",
        "\t_btnAmiga->setText(tr(\"STR_AMIGA\"));\n"
        "\t_btnAmiga->onMousePress((ActionHandler)&OptionsBaseState::btnGroupPress, SDL_BUTTON_LEFT);\n"
        "\n"
        "\t_btnVideo->setText(tr(\"STR_VIDEO\"));\n",
        "amiga tab text")))
    results.append(("OptionsBaseState.cpp (group)", edit(
        os.path.join(src, "Menu", "OptionsBaseState.cpp"),
        "\t_group = button;\n"
        "\t_btnVideo->setGroup(&_group);\n",
        "\t_group = button;\n"
        "\t_btnAmiga->setGroup(&_group);\n"
        "\t_btnVideo->setGroup(&_group);\n",
        "amiga tab group")))
    results.append(("OptionsBaseState.cpp (press)", edit(
        os.path.join(src, "Menu", "OptionsBaseState.cpp"),
        "\t\tif (sender == _btnVideo)\n"
        "\t\t{\n"
        "\t\t\t_game->pushState(new OptionsVideoState(_origin));\n"
        "\t\t}\n",
        "\t\tif (sender == _btnAmiga)\n"
        "\t\t{\n"
        "\t\t\t_game->pushState(new OptionsAmigaState(_origin));\n"
        "\t\t}\n"
        "\t\telse if (sender == _btnVideo)\n"
        "\t\t{\n"
        "\t\t\t_game->pushState(new OptionsVideoState(_origin));\n"
        "\t\t}\n",
        "amiga tab press")))
    results.append(("en-US.yml (amiga strings)", edit(
        os.path.join(src, "..", "bin", "common", "Language", "en-US.yml"),
        "  STR_MODS: \"MODS\"\n",
        "  STR_MODS: \"MODS\"\n"
        "  STR_AMIGA: \"AMIGA\"\n"
        "  STR_AMIGA_APP_BAR: \"Amiga screen title bar\"\n"
        "  STR_AMIGA_APP_BAR_DESC: \"Keep the Amiga screen title bar (with the depth gadget) so you can flip to Workbench. Opens a 320x256 screen. Takes effect at the next start.\"\n"
        "  STR_AMIGA_CURSOR: \"Mouse pointer\"\n"
        "  STR_AMIGA_CURSOR_DESC: \"Original: the game draws its own cursor. Amiga: only the system pointer is shown - nothing to redraw, so it moves smoothly.\"\n"
        "  STR_AMIGA_CURSOR_ORIGINAL: \"Original (game-drawn)\"\n"
        "  STR_AMIGA_CURSOR_AMIGA: \"Amiga pointer only\"\n"
        "  STR_AMIGA_FOV: \"Map reveal\"\n"
        "  STR_AMIGA_FOV_DESC: \"Fast: quick fog reveal, may leave the odd tile covered. Accurate: fuller reveal after every step, noticeably slower on real hardware.\"\n"
        "  STR_AMIGA_FOV_FAST: \"Fast\"\n"
        "  STR_AMIGA_FOV_ACCURATE: \"Accurate (slower)\"\n"
        "  STR_AMIGA_FOV_TEST: \"Test\"\n"
        "  STR_AMIGA_OFF: \"Off\"\n"
        "  STR_AMIGA_ON: \"On\"\n",
        "amiga language strings")))
    # 4. Startup markers. An early crash on this hardware does not produce a
    #    Guru - the CPU double-faults and the emulator stops dead - so the only
    #    way to know how far the game got is a line written and flushed at each
    #    step. Removed once the port starts reliably.
    results.append(("main.cpp (markers)", edit(
        os.path.join(src, "main.cpp"),
        "\tgame = new Game(title.str());\n"
        "\tState::setGamePtr(game);\n"
        "\tgame->setState(new StartState);\n"
        "\tgame->run();",
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"main: options initialised\");\n"
        "#endif\n"
        "\tgame = new Game(title.str());\n"
        "\tState::setGamePtr(game);\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"main: game constructed\");\n"
        "#endif\n"
        "\tgame->setState(new StartState);\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"main: entering main loop\");\n"
        "\t/* AMIGA-PORT: a CPU exception anywhere below lands here with the\n"
        "\t * faulting PC and registers, logs them, and exits - instead of a\n"
        "\t * Software Failure requester that says only #8000000B. */\n"
        "\tif (amiga_trap_arm())\n"
        "\t{\n"
        "\t\tchar b[2048];\n"
        "\t\tamiga_trap_describe(b, sizeof(b));\n"
        "\t\tSDLmini_Log(b);\n"
        "\t\tLog(LOG_FATAL) << b;\n"
        "\t\tamiga_trap_disarm();\n"
        "\t\texit(20);\n"
        "\t}\n"
        "#endif\n"
        "\tgame->run();",
        "startup markers")))

    # 5. Markers inside Options::init. The port currently hangs somewhere in
    #    here, before the game's own log file exists, so these are the only
    #    visible steps. Removed once startup is reliable.
    results.append(("Engine/Options.cpp (markers)", edit(
        os.path.join(src, "Engine", "Options.cpp"),
        "\tcreate();\n"
        "\tresetDefault();\n"
        "\tloadArgs(argc, argv);\n"
        "\tsetFolders();\n"
        "\t_setDefaultMods();\n"
        "\tupdateOptions();",
        "#ifdef __AMIGA__\n"
        "#define AMIGA_STEP(x) SDLmini_Log(\"options: \" x)\n"
        "#else\n"
        "#define AMIGA_STEP(x)\n"
        "#endif\n"
        "\tAMIGA_STEP(\"create\");\n"
        "\tcreate();\n"
        "\tAMIGA_STEP(\"resetDefault\");\n"
        "\tresetDefault();\n"
        "\tAMIGA_STEP(\"loadArgs\");\n"
        "\tloadArgs(argc, argv);\n"
        "\tAMIGA_STEP(\"setFolders\");\n"
        "\tsetFolders();\n"
        "\tAMIGA_STEP(\"_setDefaultMods\");\n"
        "\t_setDefaultMods();\n"
        "\tAMIGA_STEP(\"updateOptions\");\n"
        "\tupdateOptions();\n"
        "\tAMIGA_STEP(\"options done\");",
        "Options::init markers")))

    results.append(("Engine/Options.cpp (mod markers)", edit(
        os.path.join(src, "Engine", "Options.cpp"),
        "\tFileMap::load(\"common\", CrossPlatform::searchDataFolder(\"common\"), true);\n"
        "\n"
        "\tstd::string modPath = CrossPlatform::searchDataFolder(\"standard\");",
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"mods: loading common\");\n"
        "#endif\n"
        "\tFileMap::load(\"common\", CrossPlatform::searchDataFolder(\"common\"), true);\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"mods: common loaded\");\n"
        "#endif\n"
        "\n"
        "\tstd::string modPath = CrossPlatform::searchDataFolder(\"standard\");",
        "updateMods markers")))

    # 5b. Markers around resource loading. Mod::loadResources writes nothing
    #     to the game's own log, so a crash in the middle of the sound sets is
    #     otherwise indistinguishable from a hang. Removed once startup is
    #     reliable.
    results.append(("Mod/Mod.cpp (resource markers)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t\t\t\t\t\tsound = new SoundSet();\n"
        "\t\t\t\t\t\tsound->loadCat(FileMap::getFilePath(\"SOUND/\" + cats[j][i]), wav);",
        "\t\t\t\t\t\tsound = new SoundSet();\n"
        "#ifdef __AMIGA__\n"
        "\t\t\t\t\t\tSDLmini_Log((\"mods: sound cat \" + cats[j][i]).c_str());\n"
        "#endif\n"
        "\t\t\t\t\t\tsound->loadCat(FileMap::getFilePath(\"SOUND/\" + cats[j][i]), wav);",
        "sound cat marker")))

    results.append(("Mod/Mod.cpp (resources done marker)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\tTextButton::soundPress = getSound(\"GEO.CAT\", Mod::BUTTON_PRESS);",
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"mods: sounds loaded\");\n"
        "#endif\n"
        "\tTextButton::soundPress = getSound(\"GEO.CAT\", Mod::BUTTON_PRESS);",
        "sounds done marker")))

    results.append(("Mod/Mod.cpp (battlescape marker)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\tloadBattlescapeResources(); //",
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"mods: loading battlescape resources\");\n"
        "#endif\n"
        "\tloadBattlescapeResources(); //",
        "battlescape resources marker")))

    results.append(("Mod/Mod.cpp (include)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "#include \"Mod.h\"",
        "#include \"Mod.h\"\n"
        "#ifdef __AMIGA__\n"
        "#include \"amiga_startup.h\"\n"
        "#endif",
        "Mod.cpp marker include")))

    # 5c. Instrumentation inside SoundSet::loadCat. The CAT index is read
    #     correctly by a standalone test on the same machine but the game gets
    #     absurd object sizes out of it, so the loop logs what it actually sees.
    results.append(("Engine/SoundSet.cpp (cat markers)", edit(
        os.path.join(src, "Engine", "SoundSet.cpp"),
        "\t\tunsigned char *sound = (unsigned char*) sndFile.load(i);\n"
        "\t\tunsigned int size = sndFile.getObjectSize(i);",
        "\t\tunsigned char *sound = (unsigned char*) sndFile.load(i);\n"
        "\t\tunsigned int size = sndFile.getObjectSize(i);\n"
        "#ifdef __AMIGA__\n"
        "\t\tif (i < 3 || size > 1000000) {\n"
        "\t\t\tchar amsg[128];\n"
        "\t\t\tsprintf(amsg, \"cat: %s i=%d/%d size=%lu wav=%d\",\n"
        "\t\t\t        filename.c_str(), i, sndFile.getAmount(),\n"
        "\t\t\t        (unsigned long)size, (int)wav);\n"
        "\t\t\tSDLmini_Log(amsg);\n"
        "\t\t}\n"
        "#endif",
        "loadCat instrumentation")))

    results.append(("Engine/SoundSet.cpp (include)", edit(
        os.path.join(src, "Engine", "SoundSet.cpp"),
        "#include \"SoundSet.h\"",
        "#include \"SoundSet.h\"\n"
        "#ifdef __AMIGA__\n"
        "#include <cstdio>\n"
        "#include \"amiga_startup.h\"\n"
        "#endif",
        "SoundSet.cpp marker include")))

    # 5d. A missing sound CAT is not a reason to lose the game.
    #     Upstream throws when it cannot find the second sound set, which
    #     aborts mod loading and takes the whole game down. On a machine where
    #     the player copies X-COM over by hand, one absent file then looks
    #     exactly like a port bug (it cost a full debugging session here: the
    #     test data has SAMPLE.CAT but no SAMPLE2.CAT). The port logs it and
    #     carries on with a silent sound set instead.
    results.append(("Mod/Mod.cpp (missing sound cat)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t\t\t\tif (sound == 0)\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\tthrow Exception(catsWin[i] + \" not found\");\n"
        "\t\t\t\t}",
        "\t\t\t\tif (sound == 0)\n"
        "\t\t\t\t{\n"
        "#ifdef __AMIGA__\n"
        "\t\t\t\t\tLog(LOG_WARNING) << catsWin[i] << \" not found - \" << catsId[i]\n"
        "\t\t\t\t\t          << \" will be silent\";\n"
        "\t\t\t\t\tSDLmini_Log((\"mods: missing sound cat \" + catsWin[i]).c_str());\n"
        "\t\t\t\t\t_sounds[catsId[i]] = new SoundSet();\n"
        "\t\t\t\t\tcontinue;\n"
        "#else\n"
        "\t\t\t\t\tthrow Exception(catsWin[i] + \" not found\");\n"
        "#endif\n"
        "\t\t\t\t}",
        "missing sound cat is not fatal")))

    # 5e. Surface::loadImage sends the path through
    #     wstrToUtf8(fsToWstr(filename)) before IMG_Load, because SDL on a
    #     desktop wants UTF-8. That round trip goes through the C library's
    #     wide-character conversion, which on libnix produces garbage - the
    #     path came out as "P\xe3 \xad\xf5\xa5\xbc\xb0" and every image load
    #     failed with "cannot open". AmigaOS filenames are plain 8-bit bytes,
    #     so the path is handed over untouched.
    results.append(("Engine/Surface.cpp (utf-8 filename round trip)", edit(
        os.path.join(src, "Engine", "Surface.cpp"),
        "\t\tstd::string utf8 = Language::wstrToUtf8(Language::fsToWstr(filename));\n"
        "\t\t_surface = IMG_Load(utf8.c_str());",
        "#ifdef __AMIGA__\n"
        "\t\t_surface = IMG_Load(filename.c_str());\n"
        "#else\n"
        "\t\tstd::string utf8 = Language::wstrToUtf8(Language::fsToWstr(filename));\n"
        "\t\t_surface = IMG_Load(utf8.c_str());\n"
        "#endif",
        "no utf-8 round trip on the filename")))

    # 5i. Name every image as it is loaded, through SDLmini's log rather than
    #     the game's. Resource loading crashes at a point that moves between
    #     runs, and the game's own log only names images at verbose level -
    #     which is thousands of lines through the shared folder and slow enough
    #     to change the timing being investigated. This is ~200 lines.
    results.append(("Engine/Surface.cpp (image markers)", edit(
        os.path.join(src, "Engine", "Surface.cpp"),
        "\tLog(LOG_VERBOSE) << \"Loading image: \" << filename;",
        "\tLog(LOG_VERBOSE) << \"Loading image: \" << filename;\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log((\"img: \" + filename).c_str());\n"
        "#endif",
        "per-image marker")))

    results.append(("Engine/Surface.cpp (marker include)", edit(
        os.path.join(src, "Engine", "Surface.cpp"),
        "#include \"Surface.h\"",
        "#include \"Surface.h\"\n"
        "#ifdef __AMIGA__\n"
        "#include \"amiga_startup.h\"\n"
        "#endif",
        "Surface.cpp marker include")))

    # 5j. The last thing the port logs before it dies is the last extra
    #     resource, globe_ufo.png, which is the one sprite sheet that goes
    #     down the "subdivide into 9 frames with blitNShade at negative
    #     offsets" path. These two markers say whether the crash is inside
    #     that loop or after it.
    results.append(("Mod/Mod.cpp (subdivide markers)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t\t\t\t\t\tSurface *temp = new Surface(spritePack->getWidth(), spritePack->getHeight());",
        "#ifdef __AMIGA__\n"
        "\t\t\t\t\t\tSDLmini_Log(\"subdivide: start\");\n"
        "#endif\n"
        "\t\t\t\t\t\tSurface *temp = new Surface(spritePack->getWidth(), spritePack->getHeight());",
        "subdivide start marker")))

    results.append(("Mod/Mod.cpp (subdivide done marker)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t\t\t\t\t\tdelete temp;",
        "#ifdef __AMIGA__\n"
        "\t\t\t\t\t\tSDLmini_Log(\"subdivide: blits done\");\n"
        "#endif\n"
        "\t\t\t\t\t\tdelete temp;\n"
        "#ifdef __AMIGA__\n"
        "\t\t\t\t\t\tSDLmini_Log(\"subdivide: temp deleted\");\n"
        "#endif",
        "subdivide done marker")))

    # 5k. modResources() runs after the last resource is loaded and is the
    #     last thing before "Data loaded successfully". It reaches into
    #     _surfaces[...] and _sets[...] by name with operator[], which yields a
    #     NULL pointer for anything the data set does not have - and this data
    #     set is already known to be missing files. A NULL Surface* here is
    #     dereferenced immediately, and on a 68k that reads address 0 (which is
    #     the vector table, i.e. plausible-looking garbage) and then writes
    #     through it: a wild pointer whose address changes run to run, which is
    #     exactly the random Guru we are chasing.
    results.append(("Mod/Mod.cpp (modResources markers)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\tint newWidth = 320 - 64, newHeight = 200;",
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"modres: start\");\n"
        "\t{\n"
        "\t\t/* Name every surface this function assumes exists, before it is\n"
        "\t\t * used. Cheap, and it turns a wild-pointer Guru into a line of\n"
        "\t\t * text naming the missing file. */\n"
        "\t\tstatic const char* const needed[] = {\n"
        "\t\t\t\"GEOBORD.SCR\", \"BACK06.SCR\", \"UNIBORD.PCK\", 0 };\n"
        "\t\tint n_;\n"
        "\t\tfor (n_ = 0; needed[n_]; ++n_)\n"
        "\t\t{\n"
        "\t\t\tif (_surfaces.find(needed[n_]) == _surfaces.end() || _surfaces[needed[n_]] == 0)\n"
        "\t\t\t\tSDLmini_Log((std::string(\"modres: MISSING surface \") + needed[n_]).c_str());\n"
        "\t\t}\n"
        "\t\tif (_sets.find(\"HANDOB.PCK\") == _sets.end() || _sets[\"HANDOB.PCK\"] == 0)\n"
        "\t\t\tSDLmini_Log(\"modres: MISSING set HANDOB.PCK\");\n"
        "\t}\n"
        "#endif\n"
        "\tint newWidth = 320 - 64, newHeight = 200;",
        "modResources start marker")))

    results.append(("Mod/Mod.cpp (modResources altgeobord)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t_surfaces[\"ALTGEOBORD.SCR\"] = newGeo;",
        "\t_surfaces[\"ALTGEOBORD.SCR\"] = newGeo;\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"modres: ALTGEOBORD built\");\n"
        "#endif",
        "modResources altgeobord marker")))

    results.append(("Mod/Mod.cpp (modResources back06)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t// we create extra rows on the soldier stat screens by shrinking them all down one pixel.",
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"modres: ALTBACK07 built\");\n"
        "#endif\n"
        "\t// we create extra rows on the soldier stat screens by shrinking them all down one pixel.",
        "modResources altback07 marker")))

    results.append(("Mod/Mod.cpp (modResources uniborder)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t// now, let's adjust the battlescape info screen.",
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"modres: BACK06 adjusted\");\n"
        "#endif\n"
        "\t// now, let's adjust the battlescape info screen.",
        "modResources unibord marker")))

    results.append(("Mod/Mod.cpp (modResources handob)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t_sets[\"HANDOB2.PCK\"] = new SurfaceSet(_sets[\"HANDOB.PCK\"]->getWidth(), _sets[\"HANDOB.PCK\"]->getHeight());",
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"modres: UNIBORD adjusted\");\n"
        "#endif\n"
        "\t_sets[\"HANDOB2.PCK\"] = new SurfaceSet(_sets[\"HANDOB.PCK\"]->getWidth(), _sets[\"HANDOB.PCK\"]->getHeight());",
        "modResources handob marker")))

    results.append(("Mod/Mod.cpp (handob loop markers)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t\tSurface *surface1 = _sets[\"HANDOB2.PCK\"]->addFrame(i->first);\n"
        "\t\tSurface *surface2 = i->second;\n"
        "\t\tsurface1->setPalette(surface2->getPalette());\n"
        "\t\tsurface2->blit(surface1);",
        "\t\tSurface *surface1 = _sets[\"HANDOB2.PCK\"]->addFrame(i->first);\n"
        "\t\tSurface *surface2 = i->second;\n"
        "#ifdef __AMIGA__\n"
        "\t\t{\n"
        "\t\t\tchar m_[128];\n"
        "\t\t\tsnprintf(m_, sizeof(m_), \"handob: frame %ld src %ldx%ld dst %ldx%ld\",\n"
        "\t\t\t        (long)i->first,\n"
        "\t\t\t        surface2 ? (long)surface2->getWidth() : -1L,\n"
        "\t\t\t        surface2 ? (long)surface2->getHeight() : -1L,\n"
        "\t\t\t        surface1 ? (long)surface1->getWidth() : -1L,\n"
        "\t\t\t        surface1 ? (long)surface1->getHeight() : -1L);\n"
        "\t\t\tSDLmini_Log(m_);\n"
        "\t\t}\n"
        "#endif\n"
        "\t\tsurface1->setPalette(surface2->getPalette());\n"
        "\t\tsurface2->blit(surface1);",
        "handob loop markers")))

    results.append(("Mod/Mod.cpp (modResources done)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t\tsurface2->blit(surface1);\n"
        "\t}\n"
        "}",
        "\t\tsurface2->blit(surface1);\n"
        "\t}\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"modres: done\");\n"
        "#endif\n"
        "}",
        "modResources done marker")))

    # 5l. modResources() finishes, so loadAll() and loadMods() both return -
    #     and the very next statement, a Log(LOG_INFO), never appears. Mark
    #     the same points through SDLmini's log, which is a different file
    #     written by different code, so "the game crashed here" and "the
    #     game's logger stopped working here" stop looking identical.
    results.append(("Menu/StartState.cpp (load markers)", edit(
        os.path.join(src, "Menu", "StartState.cpp"),
        "\t\tOptions::updateMods();\n"
        "\t\tgame->loadMods();\n"
        "\t\tLog(LOG_INFO) << \"Data loaded successfully.\";",
        "\t\tOptions::updateMods();\n"
        "#ifdef __AMIGA__\n"
        "\t\tSDLmini_Log(\"start: mods updated, loading them\");\n"
        "#endif\n"
        "\t\tgame->loadMods();\n"
        "#ifdef __AMIGA__\n"
        "\t\tSDLmini_Log(\"start: loadMods returned\");\n"
        "#endif\n"
        "\t\tLog(LOG_INFO) << \"Data loaded successfully.\";\n"
        "#ifdef __AMIGA__\n"
        "\t\tSDLmini_Log(\"start: data loaded\");\n"
        "#endif",
        "StartState load markers")))

    results.append(("Menu/StartState.cpp (language markers)", edit(
        os.path.join(src, "Menu", "StartState.cpp"),
        "\t\tgame->defaultLanguage();\n"
        "\t\tLog(LOG_INFO) << \"Language loaded successfully.\";\n"
        "\t\tloading = LOADING_SUCCESSFUL;",
        "\t\tgame->defaultLanguage();\n"
        "#ifdef __AMIGA__\n"
        "\t\tSDLmini_Log(\"start: language loaded\");\n"
        "#endif\n"
        "\t\tLog(LOG_INFO) << \"Language loaded successfully.\";\n"
        "\t\tloading = LOADING_SUCCESSFUL;\n"
        "#ifdef __AMIGA__\n"
        "\t\tSDLmini_Log(\"start: loading marked successful\");\n"
        "#endif",
        "StartState language markers")))

    results.append(("Menu/StartState.cpp (marker include)", edit(
        os.path.join(src, "Menu", "StartState.cpp"),
        "#include \"StartState.h\"",
        "#include \"StartState.h\"\n"
        "#ifdef __AMIGA__\n"
        "#include \"amiga_startup.h\"\n"
        "#endif",
        "StartState.cpp marker include")))

    # 5f. First-frame markers in Game::run. Everything up to
    #     "OpenXcom started successfully" is logged by the game itself; the
    #     first drawn frame is not, and that is where the port now dies.
    results.append(("Engine/Game.cpp (frame markers)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\twhile (!_quit)\n"
        "\t{\n"
        "\t\t// Clean up states",
        "#ifdef __AMIGA__\n"
        "#include <typeinfo>\n"
        "static Uint32 AmigaSlow_think, AmigaSlow_blit;\n"
        "#define AMIGA_FRAME(x) do { static int o_; if (!o_) { o_ = 1; SDLmini_Log(\"frame: \" x); } } while (0)\n"
        "\tSDLmini_Log(\"frame: entering Game::run loop\");\n"
        "#else\n"
        "#define AMIGA_FRAME(x)\n"
        "#endif\n"
        "\twhile (!_quit)\n"
        "\t{\n"
        "\t\tAMIGA_FRAME(\"loop iteration\");\n"
        "\t\t// Clean up states",
        "Game::run frame markers")))

    # 5m. The run stops dead after StartState hands over to the main menu, and
    #     no frame is ever drawn, so the crash is in bringing the new state up.
    #     These markers are NOT one-shot: state changes are what we are
    #     watching, and there are only a handful of them before the menu.
    results.append(("Engine/Game.cpp (state init markers)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\tif (!_init)\n"
        "\t\t{\n"
        "\t\t\t_init = true;\n"
        "\t\t\t_states.back()->init();\n"
        "\n"
        "\t\t\t// Unpress buttons\n"
        "\t\t\t_states.back()->resetAll();",
        "\t\tif (!_init)\n"
        "\t\t{\n"
        "\t\t\t_init = true;\n"
        "#ifdef __AMIGA__\n"
        "\t\t\tSDLmini_Log(\"state: init\");\n"
        "#endif\n"
        "\t\t\t_states.back()->init();\n"
        "#ifdef __AMIGA__\n"
        "\t\t\tSDLmini_Log(\"state: init done\");\n"
        "#endif\n"
        "\n"
        "\t\t\t// Unpress buttons\n"
        "\t\t\t_states.back()->resetAll();\n"
        "#ifdef __AMIGA__\n"
        "\t\t\tSDLmini_Log(\"state: resetAll done\");\n"
        "#endif",
        "state init markers")))

    results.append(("Engine/Game.cpp (think markers)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\t\t// Process logic\n"
        "\t\t\t_states.back()->think();",
        "\t\t\t// Process logic\n"
        "#ifdef __AMIGA__\n"
        "\t\t\tAMIGA_FRAME(\"state: think\");\n"
        "#endif\n"
        "\t\t\tAmigaSlow_think = SDL_GetTicks();\n"
        "\t\t\t_states.back()->think();\n"
        "\t\t\tAmigaSlow_think = SDL_GetTicks() - AmigaSlow_think;\n"
        "#ifdef __AMIGA__\n"
        "\t\t\tAMIGA_FRAME(\"state: think done\");\n"
        "#endif",
        "think markers")))

    # 5n. "state: think done" is the last thing the port ever logs. What runs
    #     next is the top of the loop deleting the state that just handed over
    #     - StartState, which owns the loading "thread". Mark the deletion, and
    #     mark each step of that destructor.
    results.append(("Engine/Game.cpp (delete markers)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\twhile (!_deleted.empty())\n"
        "\t\t{\n"
        "\t\t\tdelete _deleted.back();\n"
        "\t\t\t_deleted.pop_back();\n"
        "\t\t}",
        "\t\twhile (!_deleted.empty())\n"
        "\t\t{\n"
        "#ifdef __AMIGA__\n"
        "\t\t\tAMIGA_FRAME(\"state: deleting a retired state\");\n"
        "#endif\n"
        "\t\t\tdelete _deleted.back();\n"
        "#ifdef __AMIGA__\n"
        "\t\t\tAMIGA_FRAME(\"state: retired state deleted\");\n"
        "#endif\n"
        "\t\t\t_deleted.pop_back();\n"
        "\t\t}",
        "retired state delete markers")))

    results.append(("Engine/Game.cpp (post-think markers)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\t\t_fpsCounter->think();\n"
        "\t\t\tif (Options::FPS > 0 && !(Options::useOpenGL && Options::vSyncForOpenGL))\n"
        "\t\t\t{\n"
        "\t\t\t\t// Update our FPS delay time based on the time of the last draw.\n"
        "\t\t\t\tint fps = SDL_GetAppState() & SDL_APPINPUTFOCUS ? Options::FPS : Options::FPSInactive;\n"
        "\n"
        "\t\t\t\t_timeUntilNextFrame = (1000.0f / fps) - (SDL_GetTicks() - _timeOfLastFrame);\n"
        "\t\t\t}",
        "\t\t\t_fpsCounter->think();\n"
        "#ifdef __AMIGA__\n"
        "\t\t\tAMIGA_FRAME(\"loop: fps counter thought\");\n"
        "#endif\n"
        "\t\t\tif (Options::FPS > 0 && !(Options::useOpenGL && Options::vSyncForOpenGL))\n"
        "\t\t\t{\n"
        "\t\t\t\t// Update our FPS delay time based on the time of the last draw.\n"
        "\t\t\t\tint fps = SDL_GetAppState() & SDL_APPINPUTFOCUS ? Options::FPS : Options::FPSInactive;\n"
        "\n"
        "\t\t\t\t_timeUntilNextFrame = (1000.0f / fps) - (SDL_GetTicks() - _timeOfLastFrame);\n"
        "#ifdef __AMIGA__\n"
        "\t\t\t\tAMIGA_FRAME(\"loop: frame delay computed\");\n"
        "#endif\n"
        "\t\t\t}",
        "post-think markers")))

    results.append(("Engine/Game.cpp (delay marker)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\t// Save on CPU\n"
        "\t\tswitch (runningState)",
        "#ifdef __AMIGA__\n"
        "\t\tAMIGA_FRAME(\"loop: reached the CPU-saving delay\");\n"
        "#endif\n"
        "\t\t// Save on CPU\n"
        "\t\tswitch (runningState)",
        "delay marker")))

    # Who ends the game? quit() is reached from a Quit button, Ctrl/Amiga+Q,
    # StartState's "any key after a load error", or an SDL_QUIT event; the
    # log otherwise shows a clean exit with no reason at all.
    results.append(("Engine/Game.cpp (quit marker)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "void Game::quit()\n"
        "{\n",
        "void Game::quit()\n"
        "{\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"game: quit() called\");\n"
        "#endif\n",
        "quit marker")))
    results.append(("Engine/Game.cpp (SDL_QUIT marker)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\t\t\tcase SDL_QUIT:\n"
        "\t\t\t\t\tquit();",
        "\t\t\t\tcase SDL_QUIT:\n"
        "#ifdef __AMIGA__\n"
        "\t\t\t\t\tSDLmini_Log(\"game: SDL_QUIT event\");\n"
        "#endif\n"
        "\t\t\t\t\tquit();",
        "SDL_QUIT marker")))
    results.append(("Menu/StartState.cpp (key-quit marker)", edit(
        os.path.join(src, "Menu", "StartState.cpp"),
        "\t\tif (action->getDetails()->type == SDL_KEYDOWN)\n"
        "\t\t{\n"
        "\t\t\t_game->quit();",
        "\t\tif (action->getDetails()->type == SDL_KEYDOWN)\n"
        "\t\t{\n"
        "#ifdef __AMIGA__\n"
        "\t\t\tSDLmini_Log(\"StartState: key pressed after a load error - quitting\");\n"
        "#endif\n"
        "\t\t\t_game->quit();",
        "StartState key-quit marker")))

    results.append(("Menu/StartState.cpp (destructor markers)", edit(
        os.path.join(src, "Menu", "StartState.cpp"),
        "\tif (_thread != 0)\n"
        "\t{\n"
        "\t\tSDL_KillThread(_thread);\n"
        "\t}\n"
        "\tdelete _font;\n"
        "\tdelete _timer;\n"
        "\tdelete _lang;",
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"~StartState: entered\");\n"
        "#endif\n"
        "\tif (_thread != 0)\n"
        "\t{\n"
        "\t\tSDL_KillThread(_thread);\n"
        "\t}\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"~StartState: thread killed\");\n"
        "#endif\n"
        "\tdelete _font;\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"~StartState: font deleted\");\n"
        "#endif\n"
        "\tdelete _timer;\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"~StartState: timer deleted\");\n"
        "#endif\n"
        "\tdelete _lang;\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"~StartState: lang deleted\");\n"
        "#endif",
        "StartState destructor markers")))

    results.append(("Engine/Game.cpp (draw markers)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\t\t\t_screen->clear();",
        "\t\t\t\tAmigaSlow_blit = SDL_GetTicks();\n"
        "\t\t\t\tAMIGA_FRAME(\"screen clear\");\n"
        "\t\t\t\t_screen->clear();",
        "Game::run clear marker")))

    results.append(("Engine/Game.cpp (blit markers)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\t\t\t\t(*i)->blit();",
        "\t\t\t\t\tAMIGA_FRAME(\"state blit\");\n"
        "\t\t\t\t\t(*i)->blit();\n"
        "\t\t\t\t\tAMIGA_FRAME(\"state blit done\");",
        "Game::run blit markers")))

    results.append(("Engine/Game.cpp (flip markers)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\t\t\t_fpsCounter->blit(_screen->getSurface());\n"
        "\t\t\t\t_cursor->blit(_screen->getSurface());\n"
        "\t\t\t\t_screen->flip();",
        "\t\t\t\tAMIGA_FRAME(\"fps blit\");\n"
        "\t\t\t\t_fpsCounter->blit(_screen->getSurface());\n"
        "\t\t\t\tAMIGA_FRAME(\"cursor blit\");\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\t/* AMIGA-PORT: Options::amigaCursor (Amiga tab): 1 = show the Intuition\n"
        "\t\t\t\t\t * pointer and do not blit the game cursor; 0 = as upstream. Checked\n"
        "\t\t\t\t\t * every frame so an options change takes effect at once. */\n"
        "\t\t\t\t\tstatic int pointerShown_ = -1;\n"
        "\t\t\t\t\tint want = Options::amigaCursor ? 1 : 0;\n"
        "\t\t\t\t\tif (want != pointerShown_)\n"
        "\t\t\t\t\t{\n"
        "\t\t\t\t\t\tSDL_ShowCursor(want ? SDL_ENABLE : SDL_DISABLE);\n"
        "\t\t\t\t\t\tpointerShown_ = want;\n"
        "\t\t\t\t\t}\n"
        "\t\t\t\t\tif (!want)\n"
        "\t\t\t\t\t\t_cursor->blit(_screen->getSurface());\n"
        "\t\t\t\t}\n"
        "\t\t\t\tAMIGA_FRAME(\"screen flip\");\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\tUint32 tf_ = SDL_GetTicks();\n"
        "\t\t\t\t\tAmigaSlow_blit = tf_ - AmigaSlow_blit;\n"
        "\t\t\t\t\t_screen->flip();\n"
        "\t\t\t\t\ttf_ = SDL_GetTicks() - tf_;\n"
        "\t\t\t\t\t/* AMIGA-PORT TEMP: name any frame that stalls (>=300 ms) and say\n"
        "\t\t\t\t\t * which phase ate it - the battlescape freezes after every unit\n"
        "\t\t\t\t\t * step and this pinpoints the eater. */\n"
        "\t\t\t\t\tif (AmigaSlow_think + AmigaSlow_blit + tf_ >= 300)\n"
        "\t\t\t\t\t{\n"
        "\t\t\t\t\t\tchar sb_[160];\n"
        "\t\t\t\t\t\tsnprintf(sb_, sizeof sb_, \"slow frame: think %lu blit %lu flip %lu ms in %s\",\n"
        "\t\t\t\t\t\t\t(unsigned long)AmigaSlow_think, (unsigned long)AmigaSlow_blit, (unsigned long)tf_,\n"
        "\t\t\t\t\t\t\ttypeid(*_states.back()).name());\n"
        "\t\t\t\t\t\tSDLmini_Log(sb_);\n"
        "\t\t\t\t\t}\n"
        "\t\t\t\t}\n"
        "\t\t\t\tAMIGA_FRAME(\"screen flip done\");",
        "Game::run flip markers")))

    # TEMP. A geoscape frame can take 20 s with an FPU present while the globe
    #       probe says the globe itself did 0 ms of work and the blit counters
    #       are unchanged. Account for the whole frame unconditionally, and
    #       time the two geoscape clock handlers separately, so the stall can
    #       be pinned on logic or on drawing instead of guessed at.
    results.append(("Engine/Game.cpp (geo frame accounting)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\t\t\t\ttf_ = SDL_GetTicks() - tf_;\n",
        "\t\t\t\t\ttf_ = SDL_GetTicks() - tf_;\n"
        "\t\t\t\t\t{\n"
        "\t\t\t\t\t\tstatic Uint32 agT_ = 0, agTh_ = 0, agBl_ = 0, agFl_ = 0;\n"
        "\t\t\t\t\t\tstatic int agN_ = 0;\n"
        "\t\t\t\t\t\tif (agT_ == 0) agT_ = SDL_GetTicks();\n"
        "\t\t\t\t\t\tagTh_ += AmigaSlow_think; agBl_ += AmigaSlow_blit; agFl_ += tf_;\n"
        "\t\t\t\t\t\tif (++agN_ >= 100)\n"
        "\t\t\t\t\t\t{\n"
        "\t\t\t\t\t\t\tUint32 now_ = SDL_GetTicks();\n"
        "\t\t\t\t\t\t\tUint32 w_ = now_ - agT_;\n"
        "\t\t\t\t\t\t\tchar gb_[224];\n"
        "\t\t\t\t\t\t\tif (AmigaMapMs > 0)\n"
        "\t\t\t\t\t\t\t\tsnprintf(gb_, sizeof gb_, \"prof: 100 frames in %lu ms | think %lu (%lu%%) | map %lu (%lu%%) | ui %lu (%lu%%) | flip %lu (%lu%%) | ev %lu (%lu%%) | tiles %lu, sprites %lu, anim %lu ms/%lu | %s\",\n"
        "\t\t\t\t\t\t\t\t\t(unsigned long)w_,\n"
        "\t\t\t\t\t\t\t\t\t(unsigned long)agTh_, (unsigned long)(w_ ? agTh_ * 100UL / w_ : 0),\n"
        "\t\t\t\t\t\t\t\t\tAmigaMapMs, (unsigned long)(w_ ? AmigaMapMs * 100UL / w_ : 0),\n"
        "\t\t\t\t\t\t\t\t\t(unsigned long)(agBl_ > AmigaMapMs ? agBl_ - AmigaMapMs : 0),\n"
        "\t\t\t\t\t\t\t\t\t(unsigned long)(w_ ? (agBl_ > AmigaMapMs ? agBl_ - AmigaMapMs : 0) * 100UL / w_ : 0),\n"
        "\t\t\t\t\t\t\t\t\t(unsigned long)agFl_, (unsigned long)(w_ ? agFl_ * 100UL / w_ : 0),\n"
        "\t\t\t\t\t\t\t\t\tAmigaEvMs, (unsigned long)(w_ ? AmigaEvMs * 100UL / w_ : 0),\n"
        "\t\t\t\t\t\t\t\t\tAmigaTileN, AmigaShadeN, AmigaAnimMs, AmigaAnimN, typeid(*_states.back()).name());\n"
        "\t\t\t\t\t\t\telse\n"
        "\t\t\t\t\t\t\tsnprintf(gb_, sizeof gb_, \"geo: 100 frames in %lu ms: think %lu, blit %lu, flip %lu, events %lu/%lu, other %ld ms; t5s %lu ms/%lu, t10m %lu ms/%lu in %s\",\n"
        "\t\t\t\t\t\t\t\t(unsigned long)w_, (unsigned long)agTh_, (unsigned long)agBl_, (unsigned long)agFl_,\n"
        "\t\t\t\t\t\t\t\tAmigaEvMs, AmigaEvN,\n"
        "\t\t\t\t\t\t\t\t(long)w_ - (long)(agTh_ + agBl_ + agFl_ + AmigaEvMs),\n"
        "\t\t\t\t\t\t\t\tAmigaGeo5Ms, AmigaGeo5N, AmigaGeo10Ms, AmigaGeo10N,\n"
        "\t\t\t\t\t\t\t\ttypeid(*_states.back()).name());\n"
        "\t\t\t\t\t\t\tSDLmini_Log(gb_);\n"
        "\t\t\t\t\t\t\tif (AmigaMapMs > 0 || AmigaCacheHitN() > 0) { char cb_[224]; AmigaCacheReport(cb_, sizeof cb_); SDLmini_Log(cb_); }\n"
        "\t\t\t\t\t\t\tagT_ = now_; agTh_ = agBl_ = agFl_ = 0; agN_ = 0;\n"
        "\t\t\t\t\t\t\tAmigaGeo5Ms = AmigaGeo5N = AmigaGeo10Ms = AmigaGeo10N = 0;\n"
        "\t\t\t\t\t\t\tAmigaEvMs = AmigaEvN = 0;\n"
        "\t\t\t\t\t\t\tAmigaMapMs = AmigaMapN = AmigaTileN = AmigaShadeN = 0;\n"
        "\t\t\t\t\t\t\tAmigaAnimMs = AmigaAnimN = 0;\n"
        "\t\t\t\t\t\t}\n"
        "\t\t\t\t\t}\n",
        "geo frame accounting")))

    results.append(("Engine/Game.cpp (event pump probe)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\t// Process events\n"
        "\t\twhile (SDL_PollEvent(&_event))\n",
        "\t\tAmigaEvT0 = SDL_GetTicks();\n"
        "\t\t// Process events\n"
        "\t\twhile (SDL_PollEvent(&_event))\n",
        "event pump probe")))

    results.append(("Engine/Game.cpp (event pump probe end)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\t// Process rendering\n",
        "\t\tAmigaEvMs += SDL_GetTicks() - AmigaEvT0; ++AmigaEvN;\n"
        "\t\t// Process rendering\n",
        "event pump probe end")))

    # TEMP. Full per-frame accounting in ONE build: every phase of the main
    #       loop, plus the pump's own split (autoinput vs IDCMP). Any frame
    #       over 300 ms prints the complete breakdown, so a single stall is a
    #       single line and needs no follow-up probe.
    results.append(("Engine/Game.cpp (frame profile top)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\tAMIGA_FRAME(\"loop iteration\");\n"
        "\t\t// Clean up states\n",
        "\t\tAMIGA_FRAME(\"loop iteration\");\n"
        "\t\tAmigaFrTop = SDL_GetTicks();\n"
        "\t\t// Clean up states\n",
        "frame profile top")))

    results.append(("Engine/Game.cpp (frame profile clean)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\t// Initialize active state\n",
        "\t\tAmigaFrClean = SDL_GetTicks() - AmigaFrTop;\n"
        "\t\t// Initialize active state\n",
        "frame profile clean")))

    results.append(("Engine/Game.cpp (frame profile events)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\tAmigaEvMs += SDL_GetTicks() - AmigaEvT0; ++AmigaEvN;\n",
        "\t\tAmigaFrEv = SDL_GetTicks() - AmigaEvT0;\n"
        "\t\tAmigaEvMs += AmigaFrEv; ++AmigaEvN;\n",
        "frame profile events")))

    results.append(("Engine/Game.cpp (frame profile flip)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\t\t\t\ttf_ = SDL_GetTicks() - tf_;\n",
        "\t\t\t\t\ttf_ = SDL_GetTicks() - tf_;\n"
        "\t\t\t\t\tAmigaFrFlip = tf_;\n",
        "frame profile flip")))

    results.append(("Engine/Game.cpp (frame profile dump)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\t// Save on CPU\n"
        "\t\tswitch (runningState)\n"
        "\t\t{\n"
        "\t\t\tcase RUNNING: \n"
        "\t\t\t\tSDL_Delay(1); //Save CPU from going 100%\n"
        "\t\t\t\tbreak;\n"
        "\t\t\tcase SLOWED: case PAUSED:\n"
        "\t\t\t\tSDL_Delay(100); break; //More slowing down.\n"
        "\t\t}\n",
        "\t\t// Save on CPU\n"
        "\t\t{\n"
        "\t\tunsigned long dl_ = SDL_GetTicks();\n"
        "\t\tstatic unsigned long pa_ = 0, pp_ = 0, pe_ = 0, pn_ = 0;\n"
        "\t\tswitch (runningState)\n"
        "\t\t{\n"
        "\t\t\tcase RUNNING: \n"
        "\t\t\t\tSDL_Delay(1); //Save CPU from going 100%\n"
        "\t\t\t\tbreak;\n"
        "\t\t\tcase SLOWED: case PAUSED:\n"
        "\t\t\t\tSDL_Delay(100); break; //More slowing down.\n"
        "\t\t}\n"
        "\t\t{\n"
        "\t\t\tunsigned long now_ = SDL_GetTicks();\n"
        "\t\t\tunsigned long total_ = now_ - AmigaFrTop;\n"
        "\t\t\tdl_ = now_ - dl_;\n"
        "\t\t\tif (total_ >= 300)\n"
        "\t\t\t{\n"
        "\t\t\t\tchar fb_[256];\n"
        "\t\t\t\tsnprintf(fb_, sizeof fb_,\n"
        "\t\t\t\t\t\"frameprof: total %lu = clean %lu + ev %lu + think %lu + blit %lu + flip %lu + delay %lu; pump auto %lu idcmp %lu polls %lu evs %lu; state %s\",\n"
        "\t\t\t\t\ttotal_, AmigaFrClean, AmigaFrEv,\n"
        "\t\t\t\t\t(unsigned long)AmigaSlow_think, (unsigned long)AmigaSlow_blit, AmigaFrFlip, dl_,\n"
        "\t\t\t\t\tSDLmini_ProfAuto - pa_, SDLmini_ProfPump - pp_,\n"
        "\t\t\t\t\tSDLmini_ProfPolls - pn_, SDLmini_ProfEvents - pe_,\n"
        "\t\t\t\t\ttypeid(*_states.back()).name());\n"
        "\t\t\t\tSDLmini_Log(fb_);\n"
        "\t\t\t}\n"
        "\t\t\tpa_ = SDLmini_ProfAuto; pp_ = SDLmini_ProfPump;\n"
        "\t\t\tpe_ = SDLmini_ProfEvents; pn_ = SDLmini_ProfPolls;\n"
        "\t\t}\n"
        "\t\t}\n",
        "frame profile dump")))

    results.append(("Engine/Game.cpp (geo counters)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        '#include "Game.h"\n',
        '#include "Game.h"\n'
        '#ifdef __AMIGA__\n'
        'extern "C" { unsigned long AmigaGeo5Ms = 0, AmigaGeo5N = 0, AmigaGeo10Ms = 0, AmigaGeo10N = 0; }\n'
        'extern "C" { unsigned long AmigaEvMs = 0, AmigaEvT0 = 0, AmigaEvN = 0; }\n'
        'extern "C" { unsigned long AmigaFrTop = 0, AmigaFrClean = 0, AmigaFrEv = 0, AmigaFrFlip = 0; }\n'
        'extern "C" { unsigned long AmigaMapMs = 0, AmigaMapN = 0, AmigaTileN = 0, AmigaShadeN = 0; }\n'
        'extern "C" { unsigned long AmigaAnimMs = 0, AmigaAnimN = 0; }\n'
        'extern "C" void AmigaCacheReport(char *b, unsigned long n);\n'
        'extern "C" unsigned long AmigaCacheHitN(void);\n'
        'extern "C" unsigned long SDLmini_ProfAuto, SDLmini_ProfPump, SDLmini_ProfEvents, SDLmini_ProfPolls;\n'
        '#endif\n',
        "geo counters")))

    results.append(("Geoscape/GeoscapeState.cpp (geo clock extern)", edit(
        os.path.join(src, "Geoscape", "GeoscapeState.cpp"),
        '#include "GeoscapeState.h"\n',
        '#include "GeoscapeState.h"\n'
        '#ifdef __AMIGA__\n'
        'extern "C" unsigned long AmigaGeo5Ms, AmigaGeo5N, AmigaGeo10Ms, AmigaGeo10N;\n'
        'extern "C" unsigned int SDL_GetTicks(void);\n'
        '#endif\n',
        "geo clock extern")))

    results.append(("Geoscape/GeoscapeState.cpp (t5s probe)", edit(
        os.path.join(src, "Geoscape", "GeoscapeState.cpp"),
        "void GeoscapeState::time5Seconds()\n"
        "{\n",
        "void GeoscapeState::time5Seconds()\n"
        "{\n"
        "#ifdef __AMIGA__\n"
        "\tstruct AmGeo5_ { unsigned int t0; AmGeo5_() : t0(SDL_GetTicks()) {} \n"
        "\t\t~AmGeo5_() { AmigaGeo5Ms += SDL_GetTicks() - t0; ++AmigaGeo5N; } } amGeo5_;\n"
        "#endif\n",
        "t5s probe")))

    results.append(("Geoscape/GeoscapeState.cpp (t10m probe)", edit(
        os.path.join(src, "Geoscape", "GeoscapeState.cpp"),
        "void GeoscapeState::time10Minutes()\n"
        "{\n",
        "void GeoscapeState::time10Minutes()\n"
        "{\n"
        "#ifdef __AMIGA__\n"
        "\tstruct AmGeo10_ { unsigned int t0; AmGeo10_() : t0(SDL_GetTicks()) {} \n"
        "\t\t~AmGeo10_() { AmigaGeo10Ms += SDL_GetTicks() - t0; ++AmigaGeo10N; } } amGeo10_;\n"
        "#endif\n",
        "t10m probe")))

    results.append(("Engine/Game.cpp (include)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "#include \"Game.h\"",
        "#include \"Game.h\"\n"
        "#ifdef __AMIGA__\n"
        "#include \"amiga_startup.h\"\n"
        "#include <cstdio>\n"
        "#endif",
        "Game.cpp marker include")))

    # 5g. The logger reopens its file for every single line, and at verbose
    #     level echoes every line to stderr as well. On the Amiga stderr is an
    #     Intuition console window and the log lives on the host-side shared
    #     folder, so one startup meant several thousand open/append/close
    #     round trips plus several thousand lines of scrolling text - minutes
    #     of wall clock before the game did anything. The port keeps one file
    #     handle open and never writes to the console.
    results.append(("Engine/Logger.h (one open file, no console echo)", edit(
        os.path.join(src, "Engine", "Logger.h"),
        "\tFILE *file = fopen(logFile().c_str(), \"a\");\n"
        "\tif (file)\n"
        "\t{\n"
        "\t\tfprintf(file, \"%s\", ss.str().c_str());\n"
        "\t\tfflush(file);\n"
        "\t\tfclose(file);\n"
        "\t}\n"
        "\tif (!file || reportingLevel() == LOG_DEBUG || reportingLevel() == LOG_VERBOSE)\n"
        "\t{\n"
        "\t\tfprintf(stderr, \"%s\", os.str().c_str());\n"
        "\t\tfflush(stderr);\n"
        "\t}",
        "#ifdef __AMIGA__\n"
        "\tFILE *file = logHandle();\n"
        "\tif (file)\n"
        "\t{\n"
        "\t\tfprintf(file, \"%s\", ss.str().c_str());\n"
        "\t\tfflush(file);\n"
        "\t}\n"
        "#else\n"
        "\tFILE *file = fopen(logFile().c_str(), \"a\");\n"
        "\tif (file)\n"
        "\t{\n"
        "\t\tfprintf(file, \"%s\", ss.str().c_str());\n"
        "\t\tfflush(file);\n"
        "\t\tfclose(file);\n"
        "\t}\n"
        "\tif (!file || reportingLevel() == LOG_DEBUG || reportingLevel() == LOG_VERBOSE)\n"
        "\t{\n"
        "\t\tfprintf(stderr, \"%s\", os.str().c_str());\n"
        "\t\tfflush(stderr);\n"
        "\t}\n"
        "#endif",
        "logger keeps one file handle, no console echo")))

    results.append(("Engine/Logger.h (log handle)", edit(
        os.path.join(src, "Engine", "Logger.h"),
        "inline std::string& Logger::logFile()",
        "#ifdef __AMIGA__\n"
        "#include <string.h>\n"
        "/* AMIGA-PORT: one handle for the whole run instead of an open/append/\n"
        " * close per line. logFile() changes once, when Options::setFolders\n"
        " * moves the log into user/, so the name is remembered and the handle\n"
        " * reopened if it ever differs - that keeps upstream's behaviour and\n"
        " * costs one string compare per line. The handle is never closed on\n"
        " * purpose: the process exiting closes it, and every line is flushed,\n"
        " * so a crash loses nothing. */\n"
        "inline FILE* Logger::logHandle()\n"
        "{\n"
        "\t/* Plain arrays, not a std::string: a function-local static with a\n"
        "\t * constructor needs a guard variable and an atexit registration,\n"
        "\t * and this function is inline in a header that 300 translation\n"
        "\t * units include - exactly the shape the Hunk linker de-duplicates\n"
        "\t * wrongly (see the COMDAT note in CLAUDE.md). Both of these are\n"
        "\t * constant-initialised, so no guard is emitted at all. */\n"
        "\tstatic FILE* handle = 0;\n"
        "\tstatic char opened[256] = { 0 };\n"
        "\tif (handle == 0 || strncmp(opened, logFile().c_str(), sizeof(opened) - 1) != 0)\n"
        "\t{\n"
        "\t\tif (handle != 0) fclose(handle);\n"
        "\t\tstrncpy(opened, logFile().c_str(), sizeof(opened) - 1);\n"
        "\t\topened[sizeof(opened) - 1] = 0;\n"
        "\t\thandle = fopen(opened, \"w\");\n"
        "\t}\n"
        "\treturn handle;\n"
        "}\n"
        "#endif\n"
        "\n"
        "inline std::string& Logger::logFile()",
        "logger file handle accessor")))

    results.append(("Engine/Logger.h (declaration)", edit(
        os.path.join(src, "Engine", "Logger.h"),
        "\tstatic std::string& logFile();",
        "\tstatic std::string& logFile();\n"
        "#ifdef __AMIGA__\n"
        "\tstatic FILE* logHandle();   /* see the definition below */\n"
        "#endif",
        "logger file handle declaration")))

    # 5h. Logger::toString holds a function-local static array of string
    #     literals inside an inline function in a header that 300 translation
    #     units include. The Hunk linker has no COMDAT: it reports
    #     "duplicate section ...Logger8toString...buffer has DIFFERENT
    #     CONTENTS" 84 times and keeps one arbitrary copy, so the pointers in
    #     that array may belong to an object file whose rodata was dropped.
    #     Every single log line dereferences one of them. A switch over string
    #     literals needs no static object at all.
    results.append(("Engine/Logger.h (toString has no static array)", edit(
        os.path.join(src, "Engine", "Logger.h"),
        "\tstatic const char* const buffer[] = {\"FATAL\", \"ERROR\", \"WARN\", \"INFO\", \"DEBUG\", \"VERB\"};\n"
        "\treturn buffer[level];",
        "\tswitch (level)\n"
        "\t{\n"
        "\tcase LOG_FATAL:   return \"FATAL\";\n"
        "\tcase LOG_ERROR:   return \"ERROR\";\n"
        "\tcase LOG_WARNING: return \"WARN\";\n"
        "\tcase LOG_INFO:    return \"INFO\";\n"
        "\tcase LOG_DEBUG:   return \"DEBUG\";\n"
        "\tcase LOG_VERBOSE: return \"VERB\";\n"
        "\tdefault:          return \"?\";\n"
        "\t}",
        "toString without a duplicated static array")))

    results.append(("Engine/Options.cpp (include)", edit(
        os.path.join(src, "Engine", "Options.cpp"),
        "#include \"CrossPlatform.h\"",
        "#include \"CrossPlatform.h\"\n"
        "#ifdef __AMIGA__\n"
        "#include \"amiga_startup.h\"\n"
        "#endif",
        "Options::init markers include")))

    # 5z. New-game markers: the difficulty dialog's OK ends in a jump into
    #     garbage (TRAP 4); these say which of the five steps got there.
    results.append(("Menu/NewGameState.cpp (marker include)", edit(
        os.path.join(src, "Menu", "NewGameState.cpp"),
        "#include \"NewGameState.h\"",
        "#include \"NewGameState.h\"\n"
        "#ifdef __AMIGA__\n"
        "#include \"amiga_startup.h\"\n"
        "#endif",
        "NewGameState.cpp marker include")))
    results.append(("Menu/NewGameState.cpp (markers)", edit(
        os.path.join(src, "Menu", "NewGameState.cpp"),
        "\tSavedGame *save = _game->getMod()->newSave();\n"
        "\tsave->setDifficulty(diff);\n"
        "\tsave->setIronman(_btnIronman->getPressed());\n"
        "\t_game->setSavedGame(save);\n"
        "\n"
        "\tGeoscapeState *gs = new GeoscapeState;\n"
        "\t_game->setState(gs);\n"
        "\tgs->init();\n"
        "\t_game->pushState(new BuildNewBaseState(_game->getSavedGame()->getBases()->back(), gs->getGlobe(), true));\n",
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"newgame: OK clicked, creating save\");\n"
        "#endif\n"
        "\tSavedGame *save = _game->getMod()->newSave();\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"newgame: save created\");\n"
        "#endif\n"
        "\tsave->setDifficulty(diff);\n"
        "\tsave->setIronman(_btnIronman->getPressed());\n"
        "\t_game->setSavedGame(save);\n"
        "\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"newgame: constructing GeoscapeState\");\n"
        "#endif\n"
        "\tGeoscapeState *gs = new GeoscapeState;\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"newgame: GeoscapeState constructed\");\n"
        "#endif\n"
        "\t_game->setState(gs);\n"
        "\tgs->init();\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"newgame: GeoscapeState init done, pushing BuildNewBaseState\");\n"
        "#endif\n"
        "\t_game->pushState(new BuildNewBaseState(_game->getSavedGame()->getBases()->back(), gs->getGlobe(), true));\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"newgame: BuildNewBaseState pushed\");\n"
        "#endif\n",
        "NewGameState markers")))

    # 5y. Missing music/sound must not be a null vtable call. With __NO_MUSIC
    #     no Music rules are ever loaded, so Mod::getMusic("GMGEO1") returns 0
    #     and GeoscapeState::init()'s music->play() jumps through address 0
    #     (TRAP 4 at PC 0xnnnn0000 - the first new-game crash). Upstream never
    #     builds without music, so it never sees this. Sound gets the same
    #     guard: a CAT with fewer entries than a ruleset expects would end the
    #     same way. Both fall back to the mute objects the Mod already owns.
    results.append(("Mod/Mod.cpp (null-safe getMusic)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t\treturn getRule(name, \"Music\", _musics);\n",
        "\t\tMusic *m = getRule(name, \"Music\", _musics);\n"
        "\t\treturn m ? m : _muteMusic; /* AMIGA-PORT: no music loaded -> silence, not a jump through 0 */\n",
        "null-safe getMusic")))
    results.append(("Mod/Mod.cpp (null-safe getSound)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t\t\tSound *s = ss->getSound(sound);\n"
        "\t\t\tif (s == 0)\n"
        "\t\t\t{\n"
        "\t\t\t\tLog(LOG_ERROR) << \"Sound \" << sound << \" in \" << set << \" not found\";\n"
        "\t\t\t}\n"
        "\t\t\treturn s;\n"
        "\t\t}\n"
        "\t\telse\n"
        "\t\t{\n"
        "\t\t\treturn 0;\n"
        "\t\t}\n",
        "\t\t\tSound *s = ss->getSound(sound);\n"
        "\t\t\tif (s == 0)\n"
        "\t\t\t{\n"
        "\t\t\t\tLog(LOG_ERROR) << \"Sound \" << sound << \" in \" << set << \" not found\";\n"
        "\t\t\t\ts = _muteSound; /* AMIGA-PORT: callers do getSound(..)->play() unguarded */\n"
        "\t\t\t}\n"
        "\t\t\treturn s;\n"
        "\t\t}\n"
        "\t\telse\n"
        "\t\t{\n"
        "\t\t\treturn _muteSound; /* AMIGA-PORT: same */\n"
        "\t\t}\n",
        "null-safe getSound")))

    # Screen title bar: sdlmini reads SDLmini_show_bar when it opens the
    # display, so it has to be set before Screen is constructed.
    results.append(("Game.cpp (amiga app bar)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t// Create display\n"
        "\t_screen = new Screen();\n",
        "\t// Create display\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_show_bar = Options::amigaAppBar ? 1 : 0;\n"
        "#endif\n"
        "\t_screen = new Screen();\n",
        "amiga app bar option")))
    results.append(("Game.cpp (amiga app bar extern)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "#include \"Game.h\"\n",
        "#include \"Game.h\"\n"
        "#ifdef __AMIGA__\n"
        "extern \"C\" int SDLmini_show_bar; /* AMIGA-PORT: sdlmini_video.c */\n"
        "#endif\n",
        "amiga app bar extern")))

    # 5w2. TEMP step probe: the battlescape freezes 4-5 s after every unit
    #      step (slow-frame probe: think 4-5 s in BattlescapeState). The three
    #      suspects run right after each step - time each one separately.
    results.append(("UnitWalkBState.cpp (probe include)", edit(
        os.path.join(src, "Battlescape", "UnitWalkBState.cpp"),
        '#include "UnitWalkBState.h"\n',
        '#include "UnitWalkBState.h"\n'
        '#ifdef __AMIGA__\n'
        'extern "C" void SDLmini_Log(const char *msg);\n'
        '#include <cstdio>\n'
        '#define AMIGA_STEP_T(name, call) do { Uint32 t_ = SDL_GetTicks(); call; t_ = SDL_GetTicks() - t_; \\\n'
        '\tif (t_ >= 100) { char b_[96]; snprintf(b_, sizeof b_, "step: %s %lu ms", name, (unsigned long)t_); SDLmini_Log(b_); } } while (0)\n'
        '#else\n'
        '#define AMIGA_STEP_T(name, call) do { call; } while (0)\n'
        '#endif\n',
        "step probe include")))
    results.append(("UnitWalkBState.cpp (probe lighting+fov)", edit(
        os.path.join(src, "Battlescape", "UnitWalkBState.cpp"),
        '\t\t\t// move our personal lighting with us\n'
        '\t\t\t_terrain->calculateUnitLighting();\n',
        '\t\t\t// move our personal lighting with us\n'
        '\t\t\tAMIGA_STEP_T("unitLighting", _terrain->calculateUnitLighting());\n',
        "step probe lighting")))
    results.append(("UnitWalkBState.cpp (probe fov)", edit(
        os.path.join(src, "Battlescape", "UnitWalkBState.cpp"),
        '\t\t\t_terrain->calculateFOV(_unit->getPosition());\n',
        '\t\t\tAMIGA_STEP_T("fovAll", _terrain->calculateFOV(_unit->getPosition()));\n',
        "step probe fov")))
    results.append(("UnitWalkBState.cpp (probe reaction)", edit(
        os.path.join(src, "Battlescape", "UnitWalkBState.cpp"),
        '\t\t\t\tif (_terrain->checkReactionFire(_unit))\n',
        '\t\t\t\tUint32 tReact_ = SDL_GetTicks();\n'
        '\t\t\t\tbool reacted_ = _terrain->checkReactionFire(_unit);\n'
        '#ifdef __AMIGA__\n'
        '\t\t\t\ttReact_ = SDL_GetTicks() - tReact_;\n'
        '\t\t\t\tif (tReact_ >= 100) { char rb_[96]; snprintf(rb_, sizeof rb_, "step: reaction %lu ms", (unsigned long)tReact_); SDLmini_Log(rb_); }\n'
        '#endif\n'
        '\t\t\t\tif (reacted_)\n',
        "step probe reaction")))

    # 5w3. FOV split (measured 2026-08-17: every unit step ran a FULL FOV -
    #      including the map-discovery voxel raycast to every tile in the view
    #      cone - for EVERY unit within 20 tiles: 3.2-3.5 s per step on the
    #      -70% machine). For units that did not move, the map they can see
    #      cannot have changed; only WHO they see can. So: full FOV only for
    #      the unit standing at the changed position, spotting-only for the
    #      rest. `tiles` defaults to true, so every other call site is intact.
    results.append(("TileEngine.h (fov tiles param)", edit(
        os.path.join(src, "Battlescape", "TileEngine.h"),
        "\tbool calculateFOV(BattleUnit *unit);\n",
        "\tbool calculateFOV(BattleUnit *unit, bool tiles = true); /* AMIGA-PORT: tiles=false -> spotting only */\n",
        "fov tiles param decl")))
    results.append(("TileEngine.cpp (fov tiles param)", edit(
        os.path.join(src, "Battlescape", "TileEngine.cpp"),
        "bool TileEngine::calculateFOV(BattleUnit *unit)\n",
        "bool TileEngine::calculateFOV(BattleUnit *unit, bool tiles)\n",
        "fov tiles param def")))
    results.append(("TileEngine.cpp (fov clear guard)", edit(
        os.path.join(src, "Battlescape", "TileEngine.cpp"),
        "\tunit->clearVisibleUnits();\n"
        "\tunit->clearVisibleTiles();\n",
        "\tunit->clearVisibleUnits();\n"
        "\tif (tiles)\n"
        "\t\tunit->clearVisibleTiles();\n",
        "fov clear guard")))
    results.append(("TileEngine.cpp (fov setVisible guard)", edit(
        os.path.join(src, "Battlescape", "TileEngine.cpp"),
        "\t\t\t\t\t\t\tif (unit->getFaction() == FACTION_PLAYER)\n"
        "\t\t\t\t\t\t\t{\n"
        "\t\t\t\t\t\t\t\tvisibleUnit->getTile()->setVisible(+1);\n"
        "\t\t\t\t\t\t\t\tvisibleUnit->setVisible(true);\n"
        "\t\t\t\t\t\t\t}\n",
        "\t\t\t\t\t\t\tif (unit->getFaction() == FACTION_PLAYER)\n"
        "\t\t\t\t\t\t\t{\n"
        "\t\t\t\t\t\t\t\tif (tiles)\n"
        "\t\t\t\t\t\t\t\t\tvisibleUnit->getTile()->setVisible(+1);\n"
        "\t\t\t\t\t\t\t\tvisibleUnit->setVisible(true);\n"
        "\t\t\t\t\t\t\t}\n",
        "fov setVisible guard")))
    results.append(("TileEngine.cpp (fov visibleTiles guard)", edit(
        os.path.join(src, "Battlescape", "TileEngine.cpp"),
        "\t\t\t\t\t\t\t\tunit->addToVisibleUnits(visibleUnit);\n"
        "\t\t\t\t\t\t\t\tunit->addToVisibleTiles(visibleUnit->getTile());\n",
        "\t\t\t\t\t\t\t\tunit->addToVisibleUnits(visibleUnit);\n"
        "\t\t\t\t\t\t\t\tif (tiles)\n"
        "\t\t\t\t\t\t\t\t\tunit->addToVisibleTiles(visibleUnit->getTile());\n",
        "fov visibleTiles guard")))
    results.append(("TileEngine.cpp (fov discovery guard)", edit(
        os.path.join(src, "Battlescape", "TileEngine.cpp"),
        "\t\t\t\t\t\tif (unit->getFaction() == FACTION_PLAYER)\n"
        "\t\t\t\t\t\t{\n"
        "\t\t\t\t\t\t\t// this sets tiles to discovered if they are in LOS - tile visibility is not calculated in voxelspace but in tilespace\n",
        "\t\t\t\t\t\t/* AMIGA-PORT: discovery rays to the cone EDGE (plus the\n"
        "\t\t\t\t\t\t * first 3 tiles); their trajectories sweep the interior.\n"
        "\t\t\t\t\t\t * needRay_ (incremental, Fast mode only) skips targets\n"
        "\t\t\t\t\t\t * already discovered in the previous cone. */\n"
        "\t\t\t\t\t\tif (tiles && needRay_ && unit->getFaction() == FACTION_PLAYER\n"
        "\t\t\t\t\t\t\t&& (x <= 2 || x == MAX_VIEW_DISTANCE || y == y1 || y == y2\n"
        "\t\t\t\t\t\t\t\t|| (x+1)*(x+1) + y*y > MAX_VIEW_DISTANCE_SQR\n"
        "\t\t\t\t\t\t\t\t|| (Options::amigaAccurateFov == 2 && distanceSqr >= 81 && distanceSqr <= 110)))\n"
        "\t\t\t\t\t\t{\n"
        "\t\t\t\t\t\t\t// this sets tiles to discovered if they are in LOS - tile visibility is not calculated in voxelspace but in tilespace\n",
        "fov discovery guard")))
    results.append(("TileEngine.cpp (fovAll spot-only)", edit(
        os.path.join(src, "Battlescape", "TileEngine.cpp"),
        "\t\tif (distanceSq(position, (*i)->getPosition()) <= MAX_VIEW_DISTANCE_SQR)\n"
        "\t\t{\n"
        "\t\t\tcalculateFOV(*i);\n"
        "\t\t}\n",
        "\t\tif (distanceSq(position, (*i)->getPosition()) <= MAX_VIEW_DISTANCE_SQR)\n"
        "\t\t{\n"
        "\t\t\t/* AMIGA-PORT: after a step only the pairs involving the unit at\n"
        "\t\t\t * `position` (the mover) can have changed. The mover gets a full\n"
        "\t\t\t * FOV; everyone else just re-checks the mover: cheap cone test,\n"
        "\t\t\t * one visibility ray at most. If no unit stands at `position`\n"
        "\t\t\t * (terrain changed: door, explosion) fall back to full FOVs. */\n"
        "\t\t\tBattleUnit *mover_ = _save->getTile(position) ? _save->getTile(position)->getUnit() : 0;\n"
        "\t\t\tif (mover_ == 0)\n"
        "\t\t\t{\n"
        "\t\t\t\tcalculateFOV(*i);\n"
        "\t\t\t}\n"
        "\t\t\telse if (*i == mover_)\n"
        "\t\t\t{\n"
        "\t\t\t\tcalculateFOV(*i, true);\n"
        "\t\t\t}\n"
        "\t\t\telse if (!(*i)->isOut())\n"
        "\t\t\t{\n"
        "\t\t\t\tBattleUnit *w_ = *i;\n"
        "\t\t\t\tstd::vector<BattleUnit*> *vu_ = w_->getVisibleUnits();\n"
        "\t\t\t\tvu_->erase(std::remove(vu_->begin(), vu_->end(), mover_), vu_->end());\n"
        "\t\t\t\tint dir_;\n"
        "\t\t\t\tif (Options::strafe && (w_->getTurretType() > -1))\n"
        "\t\t\t\t\tdir_ = w_->getTurretDirection();\n"
        "\t\t\t\telse\n"
        "\t\t\t\t\tdir_ = w_->getDirection();\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\tstatic const int sX_[8] = { +1, +1, +1, +1, -1, -1, -1, -1 };\n"
        "\t\t\t\t\tstatic const int sY_[8] = { -1, -1, -1, +1, +1, +1, -1, -1 };\n"
        "\t\t\t\t\tconst bool sw_ = (dir_ == 0 || dir_ == 4);\n"
        "\t\t\t\t\tconst Position d_ = mover_->getPosition() - w_->getPosition();\n"
        "\t\t\t\t\tconst int xi_ = sw_ ? sY_[dir_]*d_.y : sX_[dir_]*d_.x;\n"
        "\t\t\t\t\tconst int yi_ = sw_ ? sX_[dir_]*d_.x : sY_[dir_]*d_.y;\n"
        "\t\t\t\t\tif (xi_ < 0 || xi_ > MAX_VIEW_DISTANCE) continue;\n"
        "\t\t\t\t\tif (dir_%2) { if (yi_ < 0 || yi_ > MAX_VIEW_DISTANCE) continue; }\n"
        "\t\t\t\t\telse        { if (yi_ < -xi_ || yi_ > xi_) continue; }\n"
        "\t\t\t\t\tif (xi_*xi_ + yi_*yi_ > MAX_VIEW_DISTANCE_SQR) continue;\n"
        "\t\t\t\t}\n"
        "\t\t\t\tif (visible(w_, mover_->getTile()))\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\tif (w_->getFaction() == FACTION_PLAYER)\n"
        "\t\t\t\t\t\tmover_->setVisible(true);\n"
        "\t\t\t\t\tif ((mover_->getFaction() == FACTION_HOSTILE && w_->getFaction() == FACTION_PLAYER)\n"
        "\t\t\t\t\t\t|| (mover_->getFaction() != FACTION_HOSTILE && w_->getFaction() == FACTION_HOSTILE))\n"
        "\t\t\t\t\t{\n"
        "\t\t\t\t\t\tw_->addToVisibleUnits(mover_);\n"
        "\t\t\t\t\t\tif (w_->getFaction() == FACTION_HOSTILE && mover_->getFaction() != FACTION_HOSTILE)\n"
        "\t\t\t\t\t\t\tmover_->setTurnsSinceSpotted(0);\n"
        "\t\t\t\t\t}\n"
        "\t\t\t\t}\n"
        "\t\t\t}\n"
        "\t\t}\n",
        "fovAll spot-only")))

    # 5w4. While TURNING mid-walk the engine ran a FULL FOV (with map
    #      discovery) after every 45 degrees. Spotting-only there; the full
    #      FOV at the end of the step / end of the path still discovers.
    results.append(("UnitWalkBState.cpp (turn fov spot-only)", edit(
        os.path.join(src, "Battlescape", "UnitWalkBState.cpp"),
        '\t\t// calculateFOV is unreliable for setting the unitSpotted bool, as it can be called from various other places\n'
        '\t\t// in the code, ie: doors opening, and this messes up the result.\n'
        '\t\t_terrain->calculateFOV(_unit);\n',
        '\t\t// calculateFOV is unreliable for setting the unitSpotted bool, as it can be called from various other places\n'
        '\t\t// in the code, ie: doors opening, and this messes up the result.\n'
        '\t\t_terrain->calculateFOV(_unit, false); /* AMIGA-PORT: spotting only while turning; step end discovers */\n',
        "turn fov spot-only")))
    results.append(("UnitWalkBState.cpp (path-end turn fov spot-only)", edit(
        os.path.join(src, "Battlescape", "UnitWalkBState.cpp"),
        '\t\t\twhile (_unit->getStatus() == STATUS_TURNING)\n'
        '\t\t\t{\n'
        '\t\t\t\t_unit->turn();\n'
        '\t\t\t\t_parent->getTileEngine()->calculateFOV(_unit);\n'
        '\t\t\t}\n',
        '\t\t\twhile (_unit->getStatus() == STATUS_TURNING)\n'
        '\t\t\t{\n'
        '\t\t\t\t_unit->turn();\n'
        '\t\t\t\t_parent->getTileEngine()->calculateFOV(_unit, false); /* AMIGA-PORT: spotting only; full FOV follows */\n'
        '\t\t\t}\n',
        "path-end turn fov spot-only")))

    # 5w5. addLight without floating point. Upstream computes
    #      Round(sqrt(float(x*x+y*y))) PER Z LEVEL and looks every tile up
    #      twice. Integer nearest-sqrt, hoisted out of the z loop, one lookup
    #      per corner. (Re-adds work an accidental cross-session cleanup
    #      removed on 2026-08-17.)
    results.append(("TileEngine.cpp (integer addLight)", edit(
        os.path.join(src, "Battlescape", "TileEngine.cpp"),
        '\t\t\tfor (int z = 0; z < _save->getMapSizeZ(); z++)\n'
        '\t\t\t{\n'
        '\t\t\t\tint distance = (int)Round(sqrt(float(x*x + y*y)));\n'
        '\n'
        '\t\t\t\tif (_save->getTile(Position(center.x + x,center.y + y, z)))\n'
        '\t\t\t\t\t_save->getTile(Position(center.x + x,center.y + y, z))->addLight(power - distance, layer);\n'
        '\n'
        '\t\t\t\tif (_save->getTile(Position(center.x - x,center.y - y, z)))\n'
        '\t\t\t\t\t_save->getTile(Position(center.x - x,center.y - y, z))->addLight(power - distance, layer);\n'
        '\n'
        '\t\t\t\tif (_save->getTile(Position(center.x - x,center.y + y, z)))\n'
        '\t\t\t\t\t_save->getTile(Position(center.x - x,center.y + y, z))->addLight(power - distance, layer);\n'
        '\n'
        '\t\t\t\tif (_save->getTile(Position(center.x + x,center.y - y, z)))\n'
        '\t\t\t\t\t_save->getTile(Position(center.x + x,center.y - y, z))->addLight(power - distance, layer);\n'
        '\t\t\t}\n',
        '\t\t\t/* AMIGA-PORT: integer nearest-sqrt (unique d with (2d-1)^2 <= 4n < (2d+1)^2),\n'
        '\t\t\t * hoisted out of the z loop; one tile lookup per corner. Upstream did a\n'
        '\t\t\t * float sqrt per z level - pure soft-float cost on this CPU. */\n'
        '\t\t\tconst int nsq_ = x*x + y*y;\n'
        '\t\t\tint distance = 0;\n'
        '\t\t\twhile ((2*distance + 1)*(2*distance + 1) <= 4*nsq_)\n'
        '\t\t\t\t++distance;\n'
        '\t\t\tconst int light_ = power - distance;\n'
        '\t\t\tconst int mapZ_ = _save->getMapSizeZ();\n'
        '\t\t\tfor (int z = 0; z < mapZ_; z++)\n'
        '\t\t\t{\n'
        '\t\t\t\tTile *t_;\n'
        '\t\t\t\tif ((t_ = _save->getTile(Position(center.x + x,center.y + y, z))))\n'
        '\t\t\t\t\tt_->addLight(light_, layer);\n'
        '\t\t\t\tif ((t_ = _save->getTile(Position(center.x - x,center.y - y, z))))\n'
        '\t\t\t\t\tt_->addLight(light_, layer);\n'
        '\t\t\t\tif ((t_ = _save->getTile(Position(center.x - x,center.y + y, z))))\n'
        '\t\t\t\t\tt_->addLight(light_, layer);\n'
        '\t\t\t\tif ((t_ = _save->getTile(Position(center.x + x,center.y - y, z))))\n'
        '\t\t\t\t\tt_->addLight(light_, layer);\n'
        '\t\t\t}\n',
        "integer addLight")))

    # 5w6. Spotting-only FOV walks the UNIT LIST, not the cone. The tile
    #      enumeration alone (21x21 columns x map height, a getTile per cell)
    #      costs ~100 ms per unit on the target CPU, and it ran for every
    #      unit in range after every step. ~30 units x 3 compares instead.
    results.append(("TileEngine.cpp (spot-only unit walk)", edit(
        os.path.join(src, "Battlescape", "TileEngine.cpp"),
        "\tfor (int x = 0; x <= MAX_VIEW_DISTANCE; ++x)\n"
        "\t{\n"
        "\t\tif (direction%2)\n",
        "#ifdef __AMIGA__\n"
        "\tif (!tiles)\n"
        "\t{\n"
        "\t\t/* AMIGA-PORT: spotting only - check each unit directly against the\n"
        "\t\t * view cone instead of enumerating every tile of the cone. The\n"
        "\t\t * cone test inverts the mapping the tile loop below uses. */\n"
        "\t\tfor (std::vector<BattleUnit*>::iterator ui_ = _save->getUnits()->begin(); ui_ != _save->getUnits()->end(); ++ui_)\n"
        "\t\t{\n"
        "\t\t\tBattleUnit *visibleUnit = *ui_;\n"
        "\t\t\tif (visibleUnit == unit || visibleUnit->isOut()) continue;\n"
        "\t\t\t{\n"
        "\t\t\t\tconst Position d_ = visibleUnit->getPosition() - center;\n"
        "\t\t\t\tconst int xi_ = swap ? signY[direction]*d_.y : signX[direction]*d_.x;\n"
        "\t\t\t\tconst int yi_ = swap ? signX[direction]*d_.x : signY[direction]*d_.y;\n"
        "\t\t\t\tif (xi_ < 0 || xi_ > MAX_VIEW_DISTANCE) continue;\n"
        "\t\t\t\tif (direction%2) { if (yi_ < 0 || yi_ > MAX_VIEW_DISTANCE) continue; }\n"
        "\t\t\t\telse             { if (yi_ < -xi_ || yi_ > xi_) continue; }\n"
        "\t\t\t\tif (xi_*xi_ + yi_*yi_ > MAX_VIEW_DISTANCE_SQR) continue;\n"
        "\t\t\t}\n"
        "\t\t\tif (visible(unit, visibleUnit->getTile()))\n"
        "\t\t\t{\n"
        "\t\t\t\tif (unit->getFaction() == FACTION_PLAYER)\n"
        "\t\t\t\t\tvisibleUnit->setVisible(true);\n"
        "\t\t\t\tif ((visibleUnit->getFaction() == FACTION_HOSTILE && unit->getFaction() == FACTION_PLAYER)\n"
        "\t\t\t\t\t|| (visibleUnit->getFaction() != FACTION_HOSTILE && unit->getFaction() == FACTION_HOSTILE))\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\tunit->addToVisibleUnits(visibleUnit);\n"
        "\t\t\t\t\tif (unit->getFaction() == FACTION_HOSTILE && visibleUnit->getFaction() != FACTION_HOSTILE)\n"
        "\t\t\t\t\t{\n"
        "\t\t\t\t\t\tvisibleUnit->setTurnsSinceSpotted(0);\n"
        "\t\t\t\t\t}\n"
        "\t\t\t\t}\n"
        "\t\t\t}\n"
        "\t\t}\n"
        "\t\tif (unit->getUnitsSpottedThisTurn().size() > oldNumVisibleUnits && !unit->getVisibleUnits()->empty())\n"
        "\t\t\treturn true;\n"
        "\t\treturn false;\n"
        "\t}\n"
        "#endif\n"
        "\tfor (int x = 0; x <= MAX_VIEW_DISTANCE; ++x)\n"
        "\t{\n"
        "\t\tif (direction%2)\n",
        "spot-only unit walk")))

    # 5w7. Incremental discovery (the original 1994 engine's trick): when the
    #      unit moved one tile with the same facing, tiles that were already in
    #      the previous cone AND are already discovered need no new ray. Blocked
    #      pockets (corner peeking) stay undiscovered, so they still get rays.
    results.append(("TileEngine.cpp (incr include)", edit(
        os.path.join(src, "Battlescape", "TileEngine.cpp"),
        '#include "TileEngine.h"\n',
        '#include "TileEngine.h"\n'
        '#include <map>\n'
        '#include <algorithm>\n',
        "incr include")))
    results.append(("TileEngine.cpp (incr bookkeeping)", edit(
        os.path.join(src, "Battlescape", "TileEngine.cpp"),
        "#endif\n"
        "\tfor (int x = 0; x <= MAX_VIEW_DISTANCE; ++x)\n"
        "\t{\n"
        "\t\tif (direction%2)\n",
        "\t/* AMIGA-PORT: incremental discovery - remember where this unit last ran\n"
        "\t * a full discovery. One step with unchanged facing -> most of the cone\n"
        "\t * was already swept. Keyed by unit id; a stale entry after a new\n"
        "\t * battle merely costs one extra full sweep. */\n"
        "\tAmigaFovRays_ = AmigaFovSteps_ = AmigaFovCols_ = 0;\n"
        "\tUint32 fovT0_ = SDL_GetTicks();\n"
        "\tbool incr_ = false;\n"
        "\tPosition oldC_ = center;\n"
        "\t{\n"
        "\t\tstatic std::map<int, std::pair<Position, int> > lastDisco_;\n"
        "\t\tif (tiles && Options::amigaAccurateFov != 1)\n"
        "\t\t{\n"
        "\t\t\tstd::map<int, std::pair<Position, int> >::iterator li_ = lastDisco_.find(unit->getId());\n"
        "\t\t\tif (li_ != lastDisco_.end() && li_->second.second == direction)\n"
        "\t\t\t{\n"
        "\t\t\t\tPosition dd_ = center - li_->second.first;\n"
        "\t\t\t\t/* same position included: a repeat full FOV skips every ray */\n"
        "\t\t\t\tif (dd_.z == 0 && dd_.x >= -1 && dd_.x <= 1 && dd_.y >= -1 && dd_.y <= 1)\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\tincr_ = true;\n"
        "\t\t\t\t\toldC_ = li_->second.first;\n"
        "\t\t\t\t}\n"
        "\t\t\t}\n"
        "\t\t\tlastDisco_[unit->getId()] = std::make_pair(center, direction);\n"
        "\t\t}\n"
        "\t}\n"
        "#endif\n"
        "\tfor (int x = 0; x <= MAX_VIEW_DISTANCE; ++x)\n"
        "\t{\n"
        "\t\tif (direction%2)\n",
        "incr bookkeeping")))
    results.append(("TileEngine.cpp (incr skip)", edit(
        os.path.join(src, "Battlescape", "TileEngine.cpp"),
        "\t\t\t\t\t\t/* AMIGA-PORT: discovery rays to the cone EDGE (plus the\n",
        "\t\t\t\t\t\tbool needRay_ = true;\n"
        "\t\t\t\t\t\tif (incr_)\n"
        "\t\t\t\t\t\t{\n"
        "\t\t\t\t\t\t\tconst int dxo_ = test.x - oldC_.x;\n"
        "\t\t\t\t\t\t\tconst int dyo_ = test.y - oldC_.y;\n"
        "\t\t\t\t\t\t\tconst int xio_ = swap ? signY[direction]*dyo_ : signX[direction]*dxo_;\n"
        "\t\t\t\t\t\t\tconst int yio_ = swap ? signX[direction]*dxo_ : signY[direction]*dyo_;\n"
        "\t\t\t\t\t\t\tif (xio_ >= 0 && xio_ <= MAX_VIEW_DISTANCE\n"
        "\t\t\t\t\t\t\t\t&& (direction%2 ? (yio_ >= 0 && yio_ <= MAX_VIEW_DISTANCE) : (yio_ >= -xio_ && yio_ <= xio_))\n"
        "\t\t\t\t\t\t\t\t&& xio_*xio_ + yio_*yio_ <= MAX_VIEW_DISTANCE_SQR\n"
        "\t\t\t\t\t\t\t\t&& _save->getTile(test)->isDiscovered(2))\n"
        "\t\t\t\t\t\t\t\tneedRay_ = false;\n"
        "\t\t\t\t\t\t}\n"
        "\t\t\t\t\t\t/* AMIGA-PORT: discovery rays to the cone EDGE (plus the\n",
        "incr skip calc")))
    # 5w8. TEMP ray counter: how many discovery rays / trajectory tiles one
    #      full calculateFOV really costs. One log line per full run.
    results.append(("TileEngine.cpp (ray counter decl)", edit(
        os.path.join(src, "Battlescape", "TileEngine.cpp"),
        '#include <map>\n',
        '#include <map>\n'
        '#ifdef __AMIGA__\n'
        'extern "C" void SDLmini_Log(const char *msg);\n'
        'static unsigned long AmigaFovRays_, AmigaFovSteps_, AmigaFovCols_;\n'
        '#endif\n',
        "ray counter decl")))
    results.append(("TileEngine.cpp (ray counter count)", edit(
        os.path.join(src, "Battlescape", "TileEngine.cpp"),
        "\t\t\t\t\t\t\t\t\tint tst = calculateLine(poso, test, true, &_trajectory, unit, false);\n"
        "\t\t\t\t\t\t\t\t\tsize_t tsize = _trajectory.size();\n",
        "\t\t\t\t\t\t\t\t\tint tst = calculateLine(poso, test, true, &_trajectory, unit, false);\n"
        "\t\t\t\t\t\t\t\t\tsize_t tsize = _trajectory.size();\n"
        "\t\t\t\t\t\t\t\t\tAmigaFovRays_++; AmigaFovSteps_ += (unsigned long)tsize;\n",
        "ray counter count")))
    results.append(("TileEngine.cpp (ray counter report)", edit(
        os.path.join(src, "Battlescape", "TileEngine.cpp"),
        "\t// we only react when there are at least the same amount of visible units as before AND the checksum is different\n",
        "#ifdef __AMIGA__\n"
        "\tif (tiles)\n"
        "\t{\n"
        "\t\tchar fb_[128];\n"
        "\t\tsnprintf(fb_, sizeof fb_, \"fov: %lu ms, rays %lu, traj tiles %lu, incr %d\",\n"
        "\t\t\t(unsigned long)(SDL_GetTicks() - fovT0_), AmigaFovRays_, AmigaFovSteps_, incr_ ? 1 : 0);\n"
        "\t\tSDLmini_Log(fb_);\n"
        "\t}\n"
        "#endif\n"
        "\t// we only react when there are at least the same amount of visible units as before AND the checksum is different\n",
        "ray counter report")))

    # 5w9. TEMP: how long ONE full battlescape map render takes and how often
    #      it runs. The animation timer requests one every 100 ms even when
    #      nothing moves - this shows what each one costs.
    results.append(("Map.cpp (probe extern)", edit(
        os.path.join(src, "Battlescape", "Map.cpp"),
        '#include "Map.h"\n',
        '#include "Map.h"\n'
        '#ifdef __AMIGA__\n'
        'extern "C" void SDLmini_Log(const char *msg);\n'
        'extern "C" unsigned long AmigaMapMs, AmigaMapN, AmigaTileN, AmigaShadeN;\n'
        'extern "C" unsigned long AmigaAnimMs, AmigaAnimN;\n'
        'extern "C" unsigned long AmigaTileRevealN, AmigaTileShadeN;\n'
        'extern "C" unsigned long AmigaShadeThruN;\n'
        'extern int AmigaClipX0, AmigaClipY0, AmigaClipX1, AmigaClipY1;\n'
        'const Uint8 *AmigaDirtyGrid = 0; int AmigaDirtyGridW = 0, AmigaDirtyGridH = 0;   /* dirty tile grid, set during a partial compose */\n'
        'static int AmigaDirtyFullColumn = 0;   /* tight repair: force the full column while dirtying the OLD cursor tiles */\n'
        'static unsigned long AmCp_full = 0, AmCp_fullMs = 0, AmCp_part = 0, AmCp_partMs = 0, AmCp_hit = 0, AmCp_partPx = 0, AmCp_partTiles = 0, AmCp_partBlits = 0, AmCp_partRects = 0, AmCp_fullBlits = 0;\n'
        'static unsigned long AmCp_whySig = 0, AmCp_whyMiss = 0, AmCp_whyUnits = 0, AmCp_whyCur = 0, AmCp_whyProj = 0, AmCp_whyExpl = 0, AmCp_whyScroll = 0;\n'
        'static unsigned long AmCp_lastSig = 0;\n'
        'static unsigned long AmSg_[16], AmSgN_ = 0;   /* sig probe: per-component last values */\n'
        '#endif\n',
        "map probe extern")))
    results.append(("Map.cpp (render probe)", edit(
        os.path.join(src, "Battlescape", "Map.cpp"),
        "\t{\n"
        "\t\tdrawTerrain(this);\n"
        "\t}\n"
        "\telse\n"
        "\t{\n"
        "\t\t_message->blit(this);\n",
        "\t{\n"
        "#ifdef __AMIGA__\n"
        "\t\tstatic Uint32 sum_ = 0; static int n_ = 0;\n"
        "\t\tUint32 t0_ = SDL_GetTicks();\n"
        "\t\tunsigned long tb_ = AmigaTileN, fb_ = AmigaShadeThruN;\n"
        "\t\tdrawTerrain(this);\n"
        "\t\t{ Uint32 d_ = SDL_GetTicks() - t0_; sum_ += d_; AmigaMapMs += d_; ++AmigaMapN;\n"
        "\t\t  if (AmigaClipX1 - AmigaClipX0 < getWidth()) { /* partial: counted by the caller */ } else { ++AmCp_full; AmCp_fullMs += d_; AmCp_fullBlits += AmigaShadeThruN - fb_; } }\n"
        "\t\tamigaCacheStore();   /* dirty-rect cache: copy composed area back, clear clip */\n"
        "\t\tif (++n_ == 20)\n"
        "\t\t{\n"
        "\t\t\tchar b_[96];\n"
        "\t\t\tsnprintf(b_, sizeof b_, \"map: 20 renders, %lu ms avg\", (unsigned long)(sum_ / 20));\n"
        "\t\t\tSDLmini_Log(b_);\n"
        "\t\t\tsum_ = 0; n_ = 0;\n"
        "\t\t}\n"
        "#else\n"
        "\t\tdrawTerrain(this);\n"
        "#endif\n"
        "\t}\n"
        "\telse\n"
        "\t{\n"
        "\t\t_message->blit(this);\n",
        "map render probe")))

    # 6a. blitNShade in plain C (LISTA-ROBOT pkt: bitwa). The ShaderDraw
    #     template pipeline costs ~15-25 instructions per PIXEL at -O1 on this
    #     gcc, and a battlescape render pushes ~250k pixels through it - ~100 ms
    #     per render, requested every animation tick. Straight pointer loops
    #     with a 4-pixel transparent skip and a shade==0 copy path. Semantics
    #     identical to StandardShade / ColorReplace (low nibble + off,
    #     saturate to 15, keep/replace the high nibble).
    results.append(("Surface.cpp (blitNShade include)", edit(
        os.path.join(src, "Engine", "Surface.cpp"),
        '#include "Surface.h"\n',
        '#include "Surface.h"\n'
        '#include <cstring>\n',
        "blitNShade include")))
    results.append(("Surface.cpp (fast blitNShade)", edit(
        os.path.join(src, "Engine", "Surface.cpp"),
        "\tShaderMove<Uint8> src(this, x, y);\n"
        "\tif (half)\n"
        "\t{\n"
        "\t\tGraphSubset g = src.getDomain();\n"
        "\t\tg.beg_x = g.end_x/2;\n"
        "\t\tsrc.setDomain(g);\n"
        "\t}\n"
        "\tif (newBaseColor)\n"
        "\t{\n"
        "\t\t--newBaseColor;\n"
        "\t\tnewBaseColor <<= 4;\n"
        "\t\tShaderDraw<ColorReplace>(ShaderSurface(surface), src, ShaderScalar(off), ShaderScalar(newBaseColor));\n"
        "\t}\n"
        "\telse\n"
        "\t\tShaderDraw<StandardShade>(ShaderSurface(surface), src, ShaderScalar(off));\n"
        "\n"
        "}\n",
        "\t/* AMIGA-PORT: plain C fast path - see the patch script for why. */\n"
        "\tSDL_Surface *ss_ = _surface;\n"
        "\tSDL_Surface *ds_ = surface->getSurface();\n"
        "\tint sx0 = half ? ss_->w / 2 : 0, sy0 = 0;\n"
        "\tint dx0 = x + sx0, dy0 = y;\n"
        "\tint cw = ss_->w - sx0, ch = ss_->h;\n"
        "\tint yy;\n"
        "\tif (dx0 < 0) { sx0 -= dx0; cw += dx0; dx0 = 0; }\n"
        "\tif (dy0 < 0) { sy0 -= dy0; ch += dy0; dy0 = 0; }\n"
        "\tif (dx0 + cw > ds_->w) cw = ds_->w - dx0;\n"
        "#ifdef __AMIGA__\n"
        "\tif (dx0 < AmigaClipX0) { int d_ = AmigaClipX0 - dx0; sx0 += d_; cw -= d_; dx0 = AmigaClipX0; }\n"
        "\tif (dx0 + cw > AmigaClipX1) cw = AmigaClipX1 - dx0;\n"
        "#endif\n"
        "\tif (dy0 + ch > ds_->h) ch = ds_->h - dy0;\n"
        "#ifdef __AMIGA__\n"
        "\tif (dy0 < AmigaClipY0) { int d_ = AmigaClipY0 - dy0; sy0 += d_; ch -= d_; dy0 = AmigaClipY0; }\n"
        "\tif (dy0 + ch > AmigaClipY1) ch = AmigaClipY1 - dy0;\n"
        "#endif\n"
        "\tif (cw <= 0 || ch <= 0) return;\n"
        "#ifdef __AMIGA__\n"
        "\t++AmigaShadeThruN;\n"
        "#endif\n"
        "\t{\n"
        "\tconst Uint8 *sp = (const Uint8 *)ss_->pixels + (size_t)sy0 * ss_->pitch + sx0;\n"
        "\tUint8 *dp = (Uint8 *)ds_->pixels + (size_t)dy0 * ds_->pitch + dx0;\n"
        "\tif (newBaseColor)\n"
        "\t{\n"
        "\t\tconst int base_ = (newBaseColor - 1) << 4;\n"
        "\t\tfor (yy = 0; yy < ch; ++yy)\n"
        "\t\t{\n"
        "\t\t\tconst Uint8 *s2 = sp; Uint8 *d2 = dp; int n = cw;\n"
        "\t\t\twhile (n-- > 0)\n"
        "\t\t\t{\n"
        "\t\t\t\tUint8 c = *s2++;\n"
        "\t\t\t\tif (c) { int ns = (c & 15) + off; *d2 = (ns > 15) ? 15 : (Uint8)(base_ | ns); }\n"
        "\t\t\t\t++d2;\n"
        "\t\t\t}\n"
        "\t\t\tsp += ss_->pitch; dp += ds_->pitch;\n"
        "\t\t}\n"
        "\t}\n"
        "\telse if (off == 0)\n"
        "\t{\n"
        "\t\t/* shade 0: pure colorkey copy, 4 px at a time */\n"
        "\t\tfor (yy = 0; yy < ch; ++yy)\n"
        "\t\t{\n"
        "\t\t\tconst Uint8 *s2 = sp; Uint8 *d2 = dp; int n = cw;\n"
        "\t\t\twhile (n >= 4)\n"
        "\t\t\t{\n"
        "\t\t\t\tUint32 v;\n"
        "\t\t\t\tmemcpy(&v, s2, 4);\n"
        "\t\t\t\tif (v != 0)\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\tif ((((v - 0x01010101UL) & ~v) & 0x80808080UL) == 0)\n"
        "\t\t\t\t\t\tmemcpy(d2, &v, 4);\n"
        "\t\t\t\t\telse\n"
        "\t\t\t\t\t{\n"
        "\t\t\t\t\t\tif (s2[0]) d2[0] = s2[0];\n"
        "\t\t\t\t\t\tif (s2[1]) d2[1] = s2[1];\n"
        "\t\t\t\t\t\tif (s2[2]) d2[2] = s2[2];\n"
        "\t\t\t\t\t\tif (s2[3]) d2[3] = s2[3];\n"
        "\t\t\t\t\t}\n"
        "\t\t\t\t}\n"
        "\t\t\t\ts2 += 4; d2 += 4; n -= 4;\n"
        "\t\t\t}\n"
        "\t\t\twhile (n-- > 0) { Uint8 c = *s2++; if (c) *d2 = c; ++d2; }\n"
        "\t\t\tsp += ss_->pitch; dp += ds_->pitch;\n"
        "\t\t}\n"
        "\t}\n"
        "\telse\n"
        "\t{\n"
        "\t\t/* AMIGA-PORT: shade LUT. The shaded blit is 69% of a battlescape\n"
        "\t\t * frame, and the per-pixel work was and/add/compare/or. The result\n"
        "\t\t * depends only on the source byte and the shade, so it is a 256-byte\n"
        "\t\t * table per shade level, built once on first use. Same 4-bytes-at-a\n"
        "\t\t * -time trick as the shade-0 path above. */\n"
        "\t\tstatic Uint8 lut_[32][256];\n"
        "\t\tstatic Uint8 lutOk_[32];\n"
        "\t\tif (off < 0 || off > 31)\n"
        "\t\t{\n"
        "\t\t\tfor (yy = 0; yy < ch; ++yy)\n"
        "\t\t\t{\n"
        "\t\t\t\tconst Uint8 *s2 = sp; Uint8 *d2 = dp; int n = cw;\n"
        "\t\t\t\twhile (n-- > 0)\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\tUint8 c = *s2++;\n"
        "\t\t\t\t\tif (c) { int ns = (c & 15) + off; *d2 = (ns > 15) ? 15 : (Uint8)((c & 0xF0) | ns); }\n"
        "\t\t\t\t\t++d2;\n"
        "\t\t\t\t}\n"
        "\t\t\t\tsp += ss_->pitch; dp += ds_->pitch;\n"
        "\t\t\t}\n"
        "\t\t}\n"
        "\t\telse\n"
        "\t\t{\n"
        "\t\tconst Uint8 *L_;\n"
        "\t\tif (!lutOk_[off])\n"
        "\t\t{\n"
        "\t\t\tint ci_;\n"
        "\t\t\tfor (ci_ = 0; ci_ < 256; ++ci_)\n"
        "\t\t\t{\n"
        "\t\t\t\tint ns_ = (ci_ & 15) + off;\n"
        "\t\t\t\tlut_[off][ci_] = (ns_ > 15) ? 15 : (Uint8)((ci_ & 0xF0) | ns_);\n"
        "\t\t\t}\n"
        "\t\t\tlutOk_[off] = 1;\n"
        "\t\t}\n"
        "\t\tL_ = lut_[off];\n"
        "\t\tfor (yy = 0; yy < ch; ++yy)\n"
        "\t\t{\n"
        "\t\t\tconst Uint8 *s2 = sp; Uint8 *d2 = dp; int n = cw;\n"
        "\t\t\twhile (n >= 4)\n"
        "\t\t\t{\n"
        "\t\t\t\tUint32 v;\n"
        "\t\t\t\tmemcpy(&v, s2, 4);\n"
        "\t\t\t\tif (v != 0)\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\tif ((((v - 0x01010101UL) & ~v) & 0x80808080UL) == 0)\n"
        "\t\t\t\t\t{\n"
        "\t\t\t\t\t\td2[0] = L_[s2[0]]; d2[1] = L_[s2[1]];\n"
        "\t\t\t\t\t\td2[2] = L_[s2[2]]; d2[3] = L_[s2[3]];\n"
        "\t\t\t\t\t}\n"
        "\t\t\t\t\telse\n"
        "\t\t\t\t\t{\n"
        "\t\t\t\t\t\tif (s2[0]) d2[0] = L_[s2[0]];\n"
        "\t\t\t\t\t\tif (s2[1]) d2[1] = L_[s2[1]];\n"
        "\t\t\t\t\t\tif (s2[2]) d2[2] = L_[s2[2]];\n"
        "\t\t\t\t\t\tif (s2[3]) d2[3] = L_[s2[3]];\n"
        "\t\t\t\t\t}\n"
        "\t\t\t\t}\n"
        "\t\t\t\ts2 += 4; d2 += 4; n -= 4;\n"
        "\t\t\t}\n"
        "\t\t\twhile (n-- > 0) { Uint8 c = *s2++; if (c) *d2 = L_[c]; ++d2; }\n"
        "\t\t\tsp += ss_->pitch; dp += ds_->pitch;\n"
        "\t\t}\n"
        "\t\t}\n"
        "\t}\n"
        "\t}\n"
        "}\n",
        "fast blitNShade")))

    # 6w. amigaAutoBattle: boot straight into a generated battle. Reaching the
    #     battlescape by hand costs ~35 s in the New Battle menu plus ~35 s in
    #     the generator, which makes measuring the battlescape painful and
    #     drives every test run through two screens that are not under test.
    #     Set amigaAutoBattle: 1 in Work:user/options.cfg (no rebuild needed).
    results.append(("Game.h (auto battle states accessor)", edit(
        os.path.join(src, "Engine", "Game.h"),
        "\tvoid popState();\n",
        "\tvoid popState();\n"
        "#ifdef __AMIGA__\n"
        "\t/* amigaAutoBattle needs the state it just pushed, to click through\n"
        "\t * the briefing without a human. */\n"
        "\tstd::list<State*> *getStates() { return &_states; }\n"
        "#endif\n",
        "auto battle states accessor")))

    results.append(("MainMenuState.cpp (auto battle)", edit(
        os.path.join(src, "Menu", "MainMenuState.cpp"),
        "\t_game->setState(new MainMenuState);\n"
        "}\n",
        "\t_game->setState(new MainMenuState);\n"
        "#ifdef __AMIGA__\n"
        "\tif (Options::amigaAutoBattle)\n"
        "\t{\n"
        "\t\tSDLmini_Log(\"autobattle: generating\");\n"
        "\t\tNewBattleState *nb_ = new NewBattleState;\n"
        "\t\t_game->pushState(nb_);\n"
        "\t\tnb_->init();\n"
        "\t\tnb_->btnOkClick(0);   /* pops NewBattle + MainMenu, pushes Briefing */\n"
        "\t\tBriefingState *br_ = dynamic_cast<BriefingState*>(_game->getStates()->back());\n"
        "\t\tif (br_ != 0) br_->btnOkClick(0);\n"
        "\t\tSDLmini_Log(\"autobattle: in the battlescape\");\n"
        "\t}\n"
        "#endif\n"
        "}\n",
        "auto battle")))
    results.append(("MainMenuState.cpp (auto battle includes)", edit(
        os.path.join(src, "Menu", "MainMenuState.cpp"),
        '#include "NewBattleState.h"\n',
        '#include "NewBattleState.h"\n'
        '#ifdef __AMIGA__\n'
        '#include "../Battlescape/BriefingState.h"\n'
        'extern "C" void SDLmini_Log(const char *msg);\n'
        '#endif\n',
        "auto battle includes")))
    results.append(("BriefingState.cpp (auto battle skips inventory)", edit(
        os.path.join(src, "Battlescape", "BriefingState.cpp"),
        "\t\t_game->pushState(new InventoryState(false, bs));\n",
        "#ifdef __AMIGA__\n"
        "\t\tif (!Options::amigaAutoBattle)   /* straight into the battle */\n"
        "#endif\n"
        "\t\t_game->pushState(new InventoryState(false, bs));\n",
        "auto battle skips inventory")))

    # 6x. Battle frame profile. The battlescape runs at 3-4 fps on the
    #     reference machine and nobody knows where the time goes, so count
    #     the two things that scale with the map: tiles walked in the
    #     drawTerrain triple loop, and shaded sprite blits.
    results.append(("Map.cpp (tile counter)", edit(
        os.path.join(src, "Battlescape", "Map.cpp"),
        "\t\t\t\t\ttile = _save->getTile(mapPosition);\n",
        "#ifdef __AMIGA__\n"
        "\t\t\t\t\t/* partial compose: draw every tile whose screen column can reach the clip\n"
        "\t\t\t\t\t * box. NOT only the dirty-grid tiles: a tall object 2-3 tiles behind on a\n"
        "\t\t\t\t\t * higher level hangs down into the box, and skipping it left holes that\n"
        "\t\t\t\t\t * flickered every frame (2026-08-18). The clip bounds the blits. */\n"
        "\t\t\t\t\tif (AmigaDirtyGrid != 0 && (screenPosition.x >= AmigaClipX1 || screenPosition.x + _spriteWidth <= AmigaClipX0 || screenPosition.y + _spriteHeight <= AmigaClipY0 || screenPosition.y - _spriteHeight * 3 >= AmigaClipY1)) continue;\n"
        "\t\t\t\t\t++AmigaTileN;\n"
        "#endif\n"
        "\t\t\t\t\ttile = _save->getTile(mapPosition);\n",
        "tile counter")))
    results.append(("Surface.cpp (shade blit counter extern)", edit(
        os.path.join(src, "Engine", "Surface.cpp"),
        '#include "Surface.h"\n',
        '#include "Surface.h"\n'
        '#ifdef __AMIGA__\n'
        'extern "C" unsigned long AmigaShadeN;\n'
        'extern "C" { unsigned long AmigaShadeThruN = 0; }   /* blit-through counter */\n'
        'int AmigaClipX0 = 0, AmigaClipY0 = 0, AmigaClipX1 = 1 << 14, AmigaClipY1 = 1 << 14;\n'
        '#endif\n',
        "shade blit counter extern")))
    results.append(("Surface.cpp (shade blit counter)", edit(
        os.path.join(src, "Engine", "Surface.cpp"),
        "void Surface::blitNShade(Surface *surface, int x, int y, int off, bool half, int newBaseColor)\n"
        "{\n",
        "void Surface::blitNShade(Surface *surface, int x, int y, int off, bool half, int newBaseColor)\n"
        "{\n"
        "#ifdef __AMIGA__\n"
        "\t++AmigaShadeN;\n"
        "\t/* AMIGA-PORT: partial redraw. A sprite entirely outside the dirty\n"
        "\t * rectangle costs one comparison instead of a full clipped blit. */\n"
        "\tif (x >= AmigaClipX1 || y >= AmigaClipY1 ||\n"
        "\t    x + _surface->w <= AmigaClipX0 || y + _surface->h <= AmigaClipY0) return;\n"
        "#endif\n",
        "shade blit counter")))

    # 6y. Map::animate walks every tile of the map (14k on a 60x60x4) and every
    #     unit on each animation tick. Time it, so the "think" slice of the
    #     battle profile stops being one opaque number.
    results.append(("Map.cpp (animate probe)", edit(
        os.path.join(src, "Battlescape", "Map.cpp"),
        "void Map::animate(bool redraw)\n"
        "{\n",
        "void Map::animate(bool redraw)\n"
        "{\n"
        "#ifdef __AMIGA__\n"
        "\tUint32 anT_ = SDL_GetTicks();\n"
        "\tstruct AmAn_ { Uint32 t0; AmAn_(Uint32 t) : t0(t) {}\n"
        "\t\t~AmAn_() { AmigaAnimMs += SDL_GetTicks() - t0; ++AmigaAnimN; } } amAn_(anT_);\n"
        "#endif\n",
        "animate probe")))

    # 6z. Battlescape 8-phase frame cache. Composing the map is ~46% of a
    #     battle frame even after the shade LUT, and standing still it composes
    #     the SAME picture over and over: animated tiles cycle through exactly
    #     8 frames, so at a standstill the map only ever has 8 distinct images.
    #     Terrain and units cannot be split into layers (they are interleaved in
    #     depth order), so the whole composed image is cached per animation
    #     phase, keyed by a signature of everything that is NOT the animation
    #     frame. Any change to camera, units, projectile, explosions, cursor or
    #     selector changes the signature and drops all eight.
    # 6z-pre-1. anim list: Map::animate() walked EVERY tile of the map (14k on
    #     a 60x60x4) on every 100 ms tick to bump _currentFrame - a no-op on
    #     the static majority. Only three kinds of tile change when animated:
    #     an animated TYPE (8 distinct sprite frames), a UFO door mid-swing,
    #     a tile holding vapor particles. SavedBattleGame keeps a list of
    #     exactly those; a tile joins when it becomes one (door opened,
    #     particle added, animated type placed) and never leaves (cheap, and
    #     the list stays small).
    results.append(("Tile.h (anim list flag)", edit(
        os.path.join(src, "Savegame", "Tile.h"),
        "\tstd::list<Particle*> _particles;\n",
        "\tstd::list<Particle*> _particles;\n"
        "#ifdef __AMIGA__\n"
        "public:\n"
        "\tbool _amigaAnimListed;   /* already on SavedBattleGame's animated-tile list */\n"
        "private:\n"
        "#endif\n",
        "anim list flag")))
    results.append(("Tile.cpp (anim list flag init)", edit(
        os.path.join(src, "Savegame", "Tile.cpp"),
        "Tile::Tile(const Position& pos): _smoke(0), _fire(0), _explosive(0), _explosiveType(0), _pos(pos), _unit(0), _animationOffset(0), _markerColor(0), _visible(false), _preview(-1), _TUMarker(-1), _overlaps(0), _danger(false)\n"
        "{\n",
        "Tile::Tile(const Position& pos): _smoke(0), _fire(0), _explosive(0), _explosiveType(0), _pos(pos), _unit(0), _animationOffset(0), _markerColor(0), _visible(false), _preview(-1), _TUMarker(-1), _overlaps(0), _danger(false)\n"
        "{\n"
        "#ifdef __AMIGA__\n"
        "\t_amigaAnimListed = false;\n"
        "#endif\n",
        "anim list flag init")))
    results.append(("SavedBattleGame.h (anim list)", edit(
        os.path.join(src, "Savegame", "SavedBattleGame.h"),
        "\tstd::vector<Node*> _nodes;\n",
        "\tstd::vector<Node*> _nodes;\n"
        "#ifdef __AMIGA__\n"
        "public:\n"
        "\tstd::vector<Tile*> _amigaAnimTiles;   /* anim list - see the patch script */\n"
        "\tvoid amigaAnimListAdd(Tile *t);   /* body in the .cpp - Tile is incomplete here */\n"
        "private:\n"
        "#endif\n",
        "anim list")))
    # placing map data: an animated TYPE joins the list
    results.append(("Tile.cpp (anim list on setMapData)", edit(
        os.path.join(src, "Savegame", "Tile.cpp"),
        "void Tile::setMapData(MapData *dat, int mapDataID, int mapDataSetID, int part)\n"
        "{\n"
        "\t_objects[part] = dat;\n"
        "\t_mapDataID[part] = mapDataID;\n"
        "\t_mapDataSetID[part] = mapDataSetID;\n"
        "}\n",
        "void Tile::setMapData(MapData *dat, int mapDataID, int mapDataSetID, int part)\n"
        "{\n"
        "\t_objects[part] = dat;\n"
        "\t_mapDataID[part] = mapDataID;\n"
        "\t_mapDataSetID[part] = mapDataSetID;\n"
        "#ifdef __AMIGA__\n"
        "\tif (dat && !_amigaAnimListed && (dat->amigaIsAnimated() || dat->isUFODoor())) AmigaAnimListPending(this);\n"
        "#endif\n"
        "}\n",
        "anim list on setMapData")))
    # Tile has no back-pointer to the save; a tiny global hook (set by
    # SavedBattleGame) collects tiles. Same file-scope trick as the probes.
    results.append(("Tile.cpp (anim list hook)", edit(
        os.path.join(src, "Savegame", "Tile.cpp"),
        '#include "Tile.h"\n',
        '#include "Tile.h"\n'
        '#ifdef __AMIGA__\n'
        '#include "../Mod/MapData.h"\n'
        'extern "C" { void (*AmigaAnimListHook)(OpenXcom::Tile *) = 0; }\n'
        'static void AmigaAnimListPending(OpenXcom::Tile *t) { if (AmigaAnimListHook) AmigaAnimListHook(t); }\n'
        '#endif\n',
        "anim list hook")))
    results.append(("Tile.cpp (anim list on particle)", edit(
        os.path.join(src, "Savegame", "Tile.cpp"),
        "void Tile::addParticle(Particle *particle)\n"
        "{\n",
        "void Tile::addParticle(Particle *particle)\n"
        "{\n"
        "#ifdef __AMIGA__\n"
        "\tif (!_amigaAnimListed) AmigaAnimListPending(this);\n"
        "#endif\n",
        "anim list on particle")))
    results.append(("SavedBattleGame.cpp (anim list hook install)", edit(
        os.path.join(src, "Savegame", "SavedBattleGame.cpp"),
        '#include "SavedBattleGame.h"\n',
        '#include "SavedBattleGame.h"\n'
        '#ifdef __AMIGA__\n'
        'extern "C" { extern void (*AmigaAnimListHook)(OpenXcom::Tile *); }\n'
        'static OpenXcom::SavedBattleGame *s_amigaAnimSave = 0;\n'
        'static void amigaAnimListCollect(OpenXcom::Tile *t) { if (s_amigaAnimSave) s_amigaAnimSave->amigaAnimListAdd(t); }\n'
        '#include "Tile.h"\n'
        'void OpenXcom::SavedBattleGame::amigaAnimListAdd(Tile *t) { if (t && !t->_amigaAnimListed) { t->_amigaAnimListed = true; _amigaAnimTiles.push_back(t); } }\n'
        '#endif\n',
        "anim list hook install")))
    results.append(("SavedBattleGame.cpp (anim list reset on initMap)", edit(
        os.path.join(src, "Savegame", "SavedBattleGame.cpp"),
        "\t_tiles = new Tile*[_mapsize_z * _mapsize_y * _mapsize_x];\n",
        "#ifdef __AMIGA__\n"
        "\t_amigaAnimTiles.clear();\n"
        "\ts_amigaAnimSave = this; AmigaAnimListHook = amigaAnimListCollect;\n"
        "#endif\n"
        "\t_tiles = new Tile*[_mapsize_z * _mapsize_y * _mapsize_x];\n",
        "anim list reset on initMap")))
    # Map::animate: walk the list, not the map
    results.append(("Map.cpp (anim list in animate)", edit(
        os.path.join(src, "Battlescape", "Map.cpp"),
        "\t// animate tiles\n"
        "\tfor (int i = 0; i < _save->getMapSizeXYZ(); ++i)\n"
        "\t{\n"
        "\t\t_save->getTiles()[i]->animate();\n"
        "\t}\n",
        "\t// animate tiles\n"
        "#ifdef __AMIGA__\n"
        "\t/* anim list: only tiles that actually change (animated type, UFO door,\n"
        "\t * vapor particles) - not the whole map. */\n"
        "\tfor (std::vector<Tile*>::iterator at_ = _save->_amigaAnimTiles.begin(); at_ != _save->_amigaAnimTiles.end(); ++at_)\n"
        "\t\t(*at_)->animate();\n"
        "#else\n"
        "\tfor (int i = 0; i < _save->getMapSizeXYZ(); ++i)\n"
        "\t{\n"
        "\t\t_save->getTiles()[i]->animate();\n"
        "\t}\n"
        "#endif\n",
        "anim list in animate")))

    # 6z-pre0. Projectile::amigaTrajIndex(): the frame cache dirties only the
    #     ENDS of the bullet trail (particles that entered/left the 35-window
    #     since last frame), not the whole trail. Needs the trajectory index.
    results.append(("Projectile.h (trail ends accessor)", edit(
        os.path.join(src, "Battlescape", "Projectile.h"),
        "\tPosition getPosition(int offset = 0) const;\n",
        "\tPosition getPosition(int offset = 0) const;\n"
        "#ifdef __AMIGA__\n"
        "\tint amigaTrajIndex() const { return (int)_position; }\n"
        "#endif\n",
        "trail ends accessor")))

    # 6z-pre1. bullet shade cache: castedShade()/isVoxelVisible() of the 35
    #     trail particles are computed per TILE of the trail's bounding box on
    #     every compose (dozens of voxel walks each). They depend only on the
    #     particle, so compute once per compose and look up.
    results.append(("Map.cpp (bullet shade cache decl)", edit(
        os.path.join(src, "Battlescape", "Map.cpp"),
        "void Map::drawTerrain(Surface *surface)\n"
        "{\n",
        "void Map::drawTerrain(Surface *surface)\n"
        "{\n"
        "#ifdef __AMIGA__\n"
        "\t/* bullet shade cache - see the patch script */\n"
        "\tint bsZ_[BULLET_SPRITES]; signed char bsVis_[BULLET_SPRITES]; signed char bsOk_[BULLET_SPRITES];\n"
        "\tfor (int bi_ = 0; bi_ < BULLET_SPRITES; ++bi_) bsOk_[bi_] = 0;\n"
        "#endif\n",
        "bullet shade cache decl")))
    results.append(("Map.cpp (bullet shade cache use)", edit(
        os.path.join(src, "Battlescape", "Map.cpp"),
        "\t\t\t\t\t\t\t\t\t\tPosition voxelPos = _projectile->getPosition(1-i);\n"
        "\t\t\t\t\t\t\t\t\t\t// draw shadow on the floor\n"
        "\t\t\t\t\t\t\t\t\t\tvoxelPos.z = _save->getTileEngine()->castedShade(voxelPos);\n"
        "\t\t\t\t\t\t\t\t\t\tif (voxelPos.x / 16 == itX &&\n"
        "\t\t\t\t\t\t\t\t\t\t\tvoxelPos.y / 16 == itY &&\n"
        "\t\t\t\t\t\t\t\t\t\t\tvoxelPos.z / 24 == itZ &&\n"
        "\t\t\t\t\t\t\t\t\t\t\t_save->getTileEngine()->isVoxelVisible(voxelPos))\n",
        "\t\t\t\t\t\t\t\t\t\tPosition voxelPos = _projectile->getPosition(1-i);\n"
        "\t\t\t\t\t\t\t\t\t\t// draw shadow on the floor\n"
        "#ifdef __AMIGA__\n"
        "\t\t\t\t\t\t\t\t\t\t/* cheap reject first: the particle's tile column */\n"
        "\t\t\t\t\t\t\t\t\t\tif (voxelPos.x / 16 != itX || voxelPos.y / 16 != itY) continue;\n"
        "\t\t\t\t\t\t\t\t\t\tif (!bsOk_[i]) { bsZ_[i] = _save->getTileEngine()->castedShade(voxelPos); Position sv_ = voxelPos; sv_.z = bsZ_[i]; bsVis_[i] = _save->getTileEngine()->isVoxelVisible(sv_) ? 1 : 0; bsOk_[i] = 1; }\n"
        "\t\t\t\t\t\t\t\t\t\tvoxelPos.z = bsZ_[i];\n"
        "\t\t\t\t\t\t\t\t\t\tif (voxelPos.z / 24 == itZ && bsVis_[i])\n"
        "#else\n"
        "\t\t\t\t\t\t\t\t\t\tvoxelPos.z = _save->getTileEngine()->castedShade(voxelPos);\n"
        "\t\t\t\t\t\t\t\t\t\tif (voxelPos.x / 16 == itX &&\n"
        "\t\t\t\t\t\t\t\t\t\t\tvoxelPos.y / 16 == itY &&\n"
        "\t\t\t\t\t\t\t\t\t\t\tvoxelPos.z / 24 == itZ &&\n"
        "\t\t\t\t\t\t\t\t\t\t\t_save->getTileEngine()->isVoxelVisible(voxelPos))\n"
        "#endif\n",
        "bullet shade cache use")))

    # 6z-pre2. MapData::amigaIsAnimated(): a tile TYPE is animated iff its 8
    #     sprite frames are not all the same. Computed once per MapData, used
    #     by the frame cache to seed the other 7 phases with a small dirty
    #     rect after a full recompose (instead of 7 more full recomposes).
    results.append(("MapData.h (anim-seed flag)", edit(
        os.path.join(src, "Mod", "MapData.h"),
        "\tint _sprite[8];\n",
        "\tint _sprite[8];\n"
        "#ifdef __AMIGA__\n"
        "\tmutable signed char _amigaAnim;   /* -1 unknown, 0 static, 1 animated */\n"
        "public:\n"
        "\tbool amigaIsAnimated() const\n"
        "\t{\n"
        "\t\tif (_amigaAnim < 0)\n"
        "\t\t{\n"
        "\t\t\t_amigaAnim = 0;\n"
        "\t\t\tfor (int i_ = 1; i_ < 8; ++i_) if (_sprite[i_] != _sprite[0]) { _amigaAnim = 1; break; }\n"
        "\t\t}\n"
        "\t\treturn _amigaAnim == 1;\n"
        "\t}\n"
        "private:\n"
        "#endif\n",
        "anim-seed flag")))
    results.append(("MapData.cpp (anim-seed init)", edit(
        os.path.join(src, "Mod", "MapData.cpp"),
        "MapData::MapData(MapDataSet *dataset) : _dataset(dataset)",
        "MapData::MapData(MapDataSet *dataset) :\n"
        "#ifdef __AMIGA__\n"
        "\t_amigaAnim(-1),\n"
        "#endif\n"
        "\t_dataset(dataset)",
        "anim-seed init")))

    # 6z-pre. step-dirty counters in Tile: the frame cache does a FULL
    #     recompose only when terrain was actually revealed or a tile's shade
    #     actually changed - not on every step. See amigaFullSig().
    results.append(("Tile.cpp (step-dirty counters)", edit(
        os.path.join(src, "Savegame", "Tile.cpp"),
        '#include "Tile.h"\n',
        '#include "Tile.h"\n'
        '#ifdef __AMIGA__\n'
        'extern "C" { unsigned long AmigaTileRevealN = 0, AmigaTileShadeN = 0; }\n'
        '#endif\n',
        "step-dirty counters")))
    results.append(("Tile.cpp (step-dirty reveal)", edit(
        os.path.join(src, "Savegame", "Tile.cpp"),
        "\tif (_discovered[part] != flag)\n"
        "\t{\n"
        "\t\t_discovered[part] = flag;\n",
        "\tif (_discovered[part] != flag)\n"
        "\t{\n"
        "#ifdef __AMIGA__\n"
        "\t\t++AmigaTileRevealN;\n"
        "#endif\n"
        "\t\t_discovered[part] = flag;\n",
        "step-dirty reveal")))
    results.append(("Tile.cpp (step-dirty shade)", edit(
        os.path.join(src, "Savegame", "Tile.cpp"),
        "void Tile::addLight(int light, int layer)\n"
        "{\n"
        "\tif (_light[layer] < light)\n"
        "\t\t_light[layer] = light;\n"
        "}\n",
        "void Tile::addLight(int light, int layer)\n"
        "{\n"
        "#ifdef __AMIGA__\n"
        "\t/* step-dirty: does this light change the tile's SHADE (= max over\n"
        "\t * layers)? Only then does the picture change. In daylight the ambient\n"
        "\t * layer is already 15 and a moving lamp changes nothing on screen. */\n"
        "\tif (_light[layer] < light)\n"
        "\t{\n"
        "\t\tint other_ = 0;\n"
        "\t\tfor (int l_ = 0; l_ < LIGHTLAYERS; ++l_) if (l_ != layer && _light[l_] > other_) other_ = _light[l_];\n"
        "\t\tif (light > other_ && light > _light[layer] && light != _lastLight[layer]) ++AmigaTileShadeN;\n"
        "\t\t_light[layer] = light;\n"
        "\t}\n"
        "#else\n"
        "\tif (_light[layer] < light)\n"
        "\t\t_light[layer] = light;\n"
        "#endif\n"
        "}\n",
        "step-dirty shade")))
    # resetLight zeroes the dynamic layer before every recalculation; a tile
    # that WAS lit by a lamp and is not any more also changes shade. Count that
    # too, but only if the layer was the shade-determining one.
    results.append(("Tile.cpp (step-dirty reset)", edit(
        os.path.join(src, "Savegame", "Tile.cpp"),
        "void Tile::resetLight(int layer)\n"
        "{\n"
        "\t_light[layer] = 0;\n"
        "\t_lastLight[layer] = _light[layer];\n"
        "}\n",
        "void Tile::resetLight(int layer)\n"
        "{\n"
        "#ifdef __AMIGA__\n"
        "\t/* remember what this layer contributed, so addLight() can tell a\n"
        "\t * re-lit tile (no change) from a newly lit or a darkened one. */\n"
        "\t_lastLight[layer] = _light[layer];\n"
        "\t_light[layer] = 0;\n"
        "#else\n"
        "\t_light[layer] = 0;\n"
        "\t_lastLight[layer] = _light[layer];\n"
        "#endif\n"
        "}\n",
        "step-dirty reset")))

    # 6z. Battlescape frame cache, dirty-rect design (2026-08-18 evening).
    #     Composing the map is the whole battle frame; standing still, only
    #     8 distinct pictures ever exist (tiles animate in 8 frames). Keep the
    #     8 pictures, and for every change keep - per picture - the union
    #     rectangle of what changed since it was composed. A picture reaches
    #     the screen only after its dirty rectangle has been recomposed, so a
    #     stale cursor or unit can never be shown. The dirty area is composed
    #     with the sprite blits clipped (AmigaClip*) AND the tile loop of
    #     drawTerrain narrowed to the rectangle, so a cursor move costs a
    #     handful of tiles, not the whole map.
    results.append(("Map.h (dirty-rect cache members)", edit(
        os.path.join(src, "Battlescape", "Map.h"),
        "\tvoid drawTerrain(Surface *surface);\n",
        "\tvoid drawTerrain(Surface *surface);\n"
        "#ifdef __AMIGA__\n"
        "\t/* dirty-rect cache: 8 animation phases, one picture + one dirty rect each */\n"
        "\tUint8 *_fcPix[8];\n"
        "\tint _fcValid[8];\n"
        "\t/* dirty tile grid per phase - see the patch script (6z). */\n"
        "\tUint8 *_fcGrid[8];          /* [mapY*mapX + mapX] 1 = dirty (all levels) */\n"
        "\tint _fcGridW, _fcGridH;\n"
        "\tint _fcDirtyN[8];            /* dirty tile count per phase */\n"
        "\tint _fcBx0[8], _fcBy0[8], _fcBx1[8], _fcBy1[8];   /* screen box of the dirty tiles */\n"
        "\tvoid amigaDirtyTile(int x, int y);       /* mark tile + 8 neighbours in all 8 phases */\n"
        "\tvoid amigaDirtyTileOne(int ph, int x, int y);\n"
        "\tvoid amigaMarkTileNoBox(int ph, int x, int y);   /* strip box: mark only, caller owns the box */\n"
        "\tvoid amigaGrowBox(int ph, int x0, int y0, int x1, int y1);\n"
        "\tvoid amigaBulletTiles(int i0, int i1);   /* trail particles i0..i1 -> tiles */\n"
        "\tvoid amigaSeedOtherPhases(int except);\n"
        "\tvoid amigaComposeVisible();\n"
        "\tint _fcProjIdx;\n"
        "\tint _fcCamX, _fcCamY;   /* scroll shift: camera offset the cached pictures were composed at */\n"
        "\tbool _fcScrollStrip;   /* scroll propagate: copy the repaired strip to the other phases */\n"
        "\tint _fcStripX0, _fcStripY0, _fcStripX1, _fcStripY1;   /* union of the exposed strips */\n"
        "\tint _fcProjLx0, _fcProjLy0, _fcProjLx1, _fcProjLy1;   /* last bullet envelope (unused now) */\n"
        "\tunsigned long _fcSig;\n"
        "\tint _fcW, _fcH;\n"
        "\tstd::vector<Position> _fcUnitPos;\n"
        "\tstd::vector<int> _fcUnitState;\n"
        "\tint _fcSelX, _fcSelY, _fcCurType, _fcCurSize;\n"
        "\tint _fcProjX, _fcProjY, _fcProjOn;\n"
        "\tint _fcExplN;\n"
        "\tint _fcClipX0, _fcClipY0, _fcClipX1, _fcClipY1;   /* rect being composed now */\n"
        "\tunsigned long amigaFullSig();\n"

        "\tvoid amigaDirtyMapPos(const Position &p, int &x0, int &y0, int &x1, int &y1);\n"
        "\tvoid amigaCacheStore();\n"
        "#endif\n",
        "dirty-rect cache members")))

    results.append(("Map.cpp (dirty-rect cache init)", edit(
        os.path.join(src, "Battlescape", "Map.cpp"),
        "\t_scrollMouseTimer = new Timer(SCROLL_INTERVAL);\n",
        "#ifdef __AMIGA__\n"
        "\tfor (int fc_ = 0; fc_ < 8; ++fc_) { _fcPix[fc_] = 0; _fcValid[fc_] = 0; _fcGrid[fc_] = 0; _fcDirtyN[fc_] = 0; _fcBx0[fc_] = _fcBy0[fc_] = 0; _fcBx1[fc_] = _fcBy1[fc_] = 0; }\n"
        "\t_fcGridW = _fcGridH = 0;\n"
        "\t_fcCamX = _fcCamY = -100000;\n"
        "\t_fcScrollStrip = false; _fcStripX0 = _fcStripY0 = 0; _fcStripX1 = _fcStripY1 = 0;\n"
        "\t_fcProjLx0 = _fcProjLy0 = 0; _fcProjLx1 = _fcProjLy1 = -1;\n"
        "\t_fcProjIdx = -1;\n"
        "\t_fcSig = 0; _fcW = _fcH = 0;\n"
        "\t_fcSelX = _fcSelY = -9999; _fcCurType = _fcCurSize = -1;\n"
        "\t_fcProjX = _fcProjY = 0; _fcProjOn = 0; _fcExplN = 0;\n"
        "\t_fcClipX0 = _fcClipY0 = 0; _fcClipX1 = _fcClipY1 = 1 << 14;\n"
        "#endif\n"
        "\t_scrollMouseTimer = new Timer(SCROLL_INTERVAL);\n",
        "dirty-rect cache init")))

    results.append(("Map.cpp (cache probe report)", edit(
        os.path.join(src, "Battlescape", "Map.cpp"),
        "/**\n"
        " * Draws the whole map, part by part.\n"
        " */\n"
        "void Map::draw()\n"
        "{\n",
        "#ifdef __AMIGA__\n"
        "extern \"C\" unsigned long AmigaCacheHitN(void) { return AmCp_hit; }\n"
        "extern \"C\" void AmigaCacheReport(char *b, unsigned long n)\n"
        "{\n"
        "\t/* TEMP cache probe: per 100 frames, how Map::draw resolved and what it cost */\n"
        "\tsnprintf(b, n, \"cache: hit %lu | partial %lu/%lu rects (%lu ms, %lu px, %lu tiles, %lu blits) | full %lu (%lu ms, %lu blits) | why: sig %lu miss %lu units %lu cur %lu proj %lu expl %lu scroll %lu\",\n"
        "\t\tAmCp_hit, AmCp_part, AmCp_partRects, AmCp_partMs, AmCp_partPx, AmCp_partTiles, AmCp_partBlits, AmCp_full, AmCp_fullMs, AmCp_fullBlits,\n"
        "\t\tAmCp_whySig, AmCp_whyMiss, AmCp_whyUnits, AmCp_whyCur, AmCp_whyProj, AmCp_whyExpl, AmCp_whyScroll);\n"
        "\tAmCp_hit = AmCp_part = AmCp_partMs = AmCp_partPx = AmCp_partTiles = AmCp_full = AmCp_fullMs = AmCp_partBlits = AmCp_partRects = AmCp_fullBlits = 0;\n"
        "\tAmCp_whySig = AmCp_whyMiss = AmCp_whyUnits = AmCp_whyCur = AmCp_whyProj = AmCp_whyExpl = AmCp_whyScroll = 0;\n"
        "}\n"
        "#endif\n"
        "\n"
        "/**\n"
        " * Draws the whole map, part by part.\n"
        " */\n"
        "void Map::draw()\n"
        "{\n",
        "cache probe report")))

    results.append(("Map.cpp (dirty-rect cache helpers)", edit(
        os.path.join(src, "Battlescape", "Map.cpp"),
        "/**\n"
        " * Draws the whole map, part by part.\n"
        " */\n"
        "void Map::draw()\n"
        "{\n",
        "#ifdef __AMIGA__\n"
        "/* Everything that changes the WHOLE picture. Anything covered here drops\n"
        " * all 8 cached phases; everything else is a dirty rectangle. */\n"
        "unsigned long Map::amigaFullSig()\n"
        "{\n"
        "\tPosition o_ = _camera->getMapOffset();\n"
        "\tunsigned long s_ = 2166136261UL;\n"
        "\tunsigned long c_[16]; int ci_ = 0;\n"
        "\tc_[ci_++] = 0;   /* scroll shift: camera x/y is a dirty producer now, not a full-sig component */\n"
        "\tc_[ci_++] = (unsigned long)(_camera->getViewLevel() + 64) * 2UL + (_camera->getShowAllLayers() ? 1 : 0);\n"
        "\tc_[ci_++] = (unsigned long)_waypoints.size();\n"
        "\tc_[ci_++] = (unsigned long)_previewSetting * 2UL + (_save->getPathfinding()->isPathPreviewed() ? 1 : 0);\n"
        "\tc_[ci_++] = (unsigned long)((_flashScreen ? 1 : 0) + (_unitDying ? 2 : 0) + (_save->getDebugMode() ? 4 : 0));\n"
        "\tc_[ci_++] = (unsigned long)_save->getSelectedUnit();\n"
        "\tc_[ci_++] = (unsigned long)_save->getUnits()->size();\n"
        "\ts_ = s_ * 16777619UL ^ (unsigned long)(_camera->getViewLevel() + 64);\n"
        "\ts_ = s_ * 16777619UL ^ (unsigned long)(_camera->getShowAllLayers() ? 1 : 0);\n"
        "\ts_ = s_ * 16777619UL ^ (unsigned long)_waypoints.size();\n"
        "\ts_ = s_ * 16777619UL ^ (unsigned long)_previewSetting;\n"
        "\ts_ = s_ * 16777619UL ^ (unsigned long)(_save->getPathfinding()->isPathPreviewed() ? 1 : 0);\n"
        "\ts_ = s_ * 16777619UL ^ (unsigned long)(_flashScreen ? 1 : 0);\n"
        "\ts_ = s_ * 16777619UL ^ (unsigned long)(_unitDying ? 1 : 0);\n"
        "\ts_ = s_ * 16777619UL ^ (unsigned long)(_save->getDebugMode() ? 1 : 0);\n"
        "\ts_ = s_ * 16777619UL ^ (unsigned long)_save->getSelectedUnit();\n"
        "\ts_ = s_ * 16777619UL ^ (unsigned long)_save->getUnits()->size();\n"
        "\t/* tile contents: any unit standing on a different TILE than last time\n"
        "\t * means FOV may have revealed terrain anywhere - full recompose. Also\n"
        "\t * doors opening etc. happen on tile change. Explosion count changing\n"
        "\t * likewise (debris, smoke, fire). */\n"
        "\t/* step-dirty: NOT the unit positions (a step is a dirty rect) but\n"
        "\t * whether terrain was revealed / a tile shade changed since last time */\n"
        "\tunsigned long up_ = AmigaTileRevealN * 65536UL + AmigaTileShadeN;\n"
        "\ts_ = s_ * 16777619UL ^ up_;\n"
        "\tc_[ci_++] = up_;\n"
        "\tc_[ci_++] = (unsigned long)_explosions.size();\n"
        "\ts_ = s_ * 16777619UL ^ (unsigned long)_explosions.size();\n"
        "\t/* sig probe: which component moved? (logged at most every 50th change) */\n"
        "\tif (AmSgN_ > 0)\n"
        "\t{\n"
        "\t\tint diff_ = 0; unsigned long mask_ = 0;\n"
        "\t\tfor (int k_ = 0; k_ < ci_; ++k_) if (c_[k_] != AmSg_[k_]) { diff_ = 1; mask_ |= (1UL << k_); }\n"
        "\t\tif (diff_)\n"
        "\t\t{\n"
        "\t\t\tstatic unsigned long sgLog_ = 0;\n"
        "\t\t\tif ((sgLog_++ % 50) == 0)\n"
        "\t\t\t{\n"
        "\t\t\t\tchar sb_[160];\n"
        "\t\t\t\tsnprintf(sb_, sizeof sb_, \"sig: changed mask 0x%lx (bit0 cam,1 level,2 wp,3 preview,4 flags,5 selUnit,6 nUnits,7 reveal/shade,8 nExpl) cam %lu->%lu\", mask_, AmSg_[0], c_[0]);\n"
        "\t\t\t\tSDLmini_Log(sb_);\n"
        "\t\t\t}\n"
        "\t\t}\n"
        "\t}\n"
        "\tfor (int k_ = 0; k_ < ci_; ++k_) AmSg_[k_] = c_[k_];\n"
        "\tAmSgN_ = 1;\n"
        "\treturn s_;\n"
        "}\n"
        "\n"
        "/* dirty tile grid: mark ONE tile in ONE phase and grow that phase's screen box */\n"
        "void Map::amigaDirtyTileOne(int ph, int x, int y)\n"
        "{\n"
        "\tif (x < 0 || y < 0 || x >= _fcGridW || y >= _fcGridH) return;\n"
        "\tUint8 *g_ = _fcGrid[ph];\n"
        "\tif (g_ == 0) return;\n"
        "\tUint8 &c_ = g_[y * _fcGridW + x];\n"
        "\tif (c_) return;\n"
        "\tc_ = 1; ++_fcDirtyN[ph];\n"
        "\t/* screen box: this tile's column from the floor up to the highest level\n"
        "\t * that has content here (object part or unit) - an empty level above\n"
        "\t * draws nothing, so the box need not cover it. */\n"
        "\tint vl_ = _camera->getShowAllLayers() ? _save->getMapSizeZ() - 1 : _camera->getViewLevel();\n"
        "\tint top_ = 0;\n"
        "\tfor (int z_ = vl_; z_ >= 0; --z_)\n"
        "\t{\n"
        "\t\tTile *tz_ = _save->getTile(Position(x, y, z_));\n"
        "\t\tif (tz_ && (tz_->getUnit() || tz_->getMapData(O_FLOOR) || tz_->getMapData(O_WESTWALL) || tz_->getMapData(O_NORTHWALL) || tz_->getMapData(O_OBJECT))) { top_ = z_; break; }\n"
        "\t}\n"
        "\t/* the cursor is drawn on every level up to the view level whatever is there */\n"
        "\tif (top_ < vl_ && ((x == _selectorX && y == _selectorY) || AmigaDirtyFullColumn)) top_ = vl_;\n"
        "\tPosition s0_, s1_;\n"
        "\t_camera->convertMapToScreen(Position(x, y, 0), &s0_); s0_ += _camera->getMapOffset();\n"
        "\t_camera->convertMapToScreen(Position(x, y, top_), &s1_); s1_ += _camera->getMapOffset();\n"
        "\tint bx0 = s0_.x, by0 = s1_.y - _spriteHeight, bx1 = s0_.x + _spriteWidth, by1 = s0_.y + _spriteHeight;\n"
        "\tamigaGrowBox(ph, bx0, by0, bx1, by1);\n"
        "}\n"
        "\n"
        "void Map::amigaGrowBox(int ph, int x0, int y0, int x1, int y1)\n"
        "{\n"
        "\tif (_fcBx1[ph] <= _fcBx0[ph] || _fcBy1[ph] <= _fcBy0[ph]) { _fcBx0[ph] = x0; _fcBy0[ph] = y0; _fcBx1[ph] = x1; _fcBy1[ph] = y1; return; }\n"
        "\tif (x0 < _fcBx0[ph]) _fcBx0[ph] = x0;\n"
        "\tif (y0 < _fcBy0[ph]) _fcBy0[ph] = y0;\n"
        "\tif (x1 > _fcBx1[ph]) _fcBx1[ph] = x1;\n"
        "\tif (y1 > _fcBy1[ph]) _fcBy1[ph] = y1;\n"
        "}\n"
        "\n"
        "void Map::amigaMarkTileNoBox(int ph, int x, int y)\n"
        "{\n"
        "\tif (x < 0 || y < 0 || x >= _fcGridW || y >= _fcGridH) return;\n"
        "\tUint8 *g_ = _fcGrid[ph];\n"
        "\tif (g_ == 0) return;\n"
        "\tUint8 &c_ = g_[y * _fcGridW + x];\n"
        "\tif (c_) return;\n"
        "\tc_ = 1; ++_fcDirtyN[ph];\n"
        "}\n"
        "\n"
        "/* mark a tile AND its 8 neighbours (overlap on screen) in all 8 phases -\n"
        " * or, in a scroll frame (scroll-frame producers), in the current phase only:\n"
        " * the repaired area is propagated to the other 7 after the repair. */\n"
        "void Map::amigaDirtyTile(int x, int y)\n"
        "{\n"
        "\tif (_fcScrollStrip)\n"
        "\t{\n"
        "\t\tint cph_ = _animFrame & 7;\n"
        "\t\tfor (int dy_ = -1; dy_ <= 1; ++dy_)\n"
        "\t\t\tfor (int dx_ = -1; dx_ <= 1; ++dx_)\n"
        "\t\t\t\tamigaDirtyTileOne(cph_, x + dx_, y + dy_);\n"
        "\t\treturn;\n"
        "\t}\n"
        "\tfor (int ph_ = 0; ph_ < 8; ++ph_)\n"
        "\t\tfor (int dy_ = -1; dy_ <= 1; ++dy_)\n"
        "\t\t\tfor (int dx_ = -1; dx_ <= 1; ++dx_)\n"
        "\t\t\t\tamigaDirtyTileOne(ph_, x + dx_, y + dy_);\n"
        "}\n"
        "\n"
        "/* bullet trail particles i0..i1 (0 = head) -> the tiles under them and\n"
        " * under their floor shadows */\n"
        "void Map::amigaBulletTiles(int i0, int i1)\n"
        "{\n"
        "\tif (!_projectile) return;\n"
        "\tint part_ = _projectile->getItem() ? 0 : BULLET_SPRITES - 1;\n"
        "\tif (i1 > part_) i1 = part_;\n"
        "\tif (i0 < 0) i0 = 0;\n"
        "\tint lx_ = -1, ly_ = -1;\n"
        "\tfor (int i_ = i0; i_ <= i1; ++i_)\n"
        "\t{\n"
        "\t\tPosition v_ = _projectile->getPosition(1 - i_);\n"
        "\t\tint tx_ = v_.x / 16, ty_ = v_.y / 16;\n"
        "\t\tif (tx_ != lx_ || ty_ != ly_) { amigaDirtyTile(tx_, ty_); lx_ = tx_; ly_ = ty_; }\n"
        "\t}\n"
        "}\n"
        "\n"
        "/* kept for the unit producer: screen box of a map position (unused by the grid) */\n"
        "void Map::amigaSeedOtherPhases(int except)\n"
        "{\n"
        "\tconst int w_ = getWidth(), h_ = getHeight();\n"
        "\tint beginX, endX, beginY, endY, dummy;\n"
        "\t_camera->convertScreenToMap(0, 0, &beginX, &dummy);\n"
        "\t_camera->convertScreenToMap(w_, 0, &dummy, &beginY);\n"
        "\t_camera->convertScreenToMap(w_ + _spriteWidth, h_ + _spriteHeight, &endX, &dummy);\n"
        "\t_camera->convertScreenToMap(0, h_ + _spriteHeight, &dummy, &endY);\n"
        "\tbeginY -= (_camera->getViewLevel() * 2); beginX -= (_camera->getViewLevel() * 2);\n"
        "\tif (beginX < 0) beginX = 0; if (beginY < 0) beginY = 0;\n"
        "\tint endZ = _camera->getShowAllLayers() ? _save->getMapSizeZ() - 1 : _camera->getViewLevel();\n"
        "\tSDL_Surface *ss_ = getSurface();\n"
        "\tfor (int i_ = 0; i_ < 8; ++i_)\n"
        "\t{\n"
        "\t\tif (i_ == except) continue;\n"
        "\t\tif (_fcPix[i_] == 0) _fcPix[i_] = new Uint8[(size_t)w_ * h_];\n"
        "\t\tif (_fcPix[i_] == 0) continue;\n"
        "\t\tconst Uint8 *sp_ = (const Uint8 *)ss_->pixels; Uint8 *dp_ = _fcPix[i_];\n"
        "\t\tfor (int y_ = 0; y_ < h_; ++y_) { memcpy(dp_, sp_, w_); dp_ += w_; sp_ += ss_->pitch; }\n"
        "\t\t_fcValid[i_] = 1;\n"
        "\t\tif (_fcGrid[i_]) memset(_fcGrid[i_], 0, (size_t)_fcGridW * _fcGridH);\n"
        "\t\t_fcDirtyN[i_] = 0; _fcBx0[i_] = _fcBy0[i_] = 0; _fcBx1[i_] = _fcBy1[i_] = 0;\n"
        "\t}\n"
        "\tint nAnim_ = 0;\n"
        "\tfor (int itZ = 0; itZ <= endZ; ++itZ)\n"
        "\t\tfor (int itX = beginX; itX <= endX; ++itX)\n"
        "\t\t\tfor (int itY = beginY; itY <= endY; ++itY)\n"
        "\t\t\t{\n"
        "\t\t\t\tTile *tl_ = _save->getTile(Position(itX, itY, itZ));\n"
        "\t\t\t\tif (!tl_ || !tl_->isDiscovered(2)) continue;\n"
        "\t\t\t\tbool an_ = false;\n"
        "\t\t\t\tfor (int pt_ = 0; pt_ < 4 && !an_; ++pt_) { MapData *md_ = tl_->getMapData(pt_); if (md_ && md_->amigaIsAnimated()) an_ = true; }\n"
        "\t\t\t\tif (!an_ && tl_->getFire() == 0 && tl_->getSmoke() == 0) continue;\n"
        "\t\t\t\t++nAnim_;\n"
        "\t\t\t\tfor (int i_ = 0; i_ < 8; ++i_) if (i_ != except)\n"
        "\t\t\t\t\tfor (int dy_ = -1; dy_ <= 1; ++dy_) for (int dx_ = -1; dx_ <= 1; ++dx_) amigaDirtyTileOne(i_, itX + dx_, itY + dy_);\n"
        "\t\t\t}\n"
        "\t{\n"
        "\t\tstatic unsigned long sp_n_ = 0;\n"
        "\t\tif ((sp_n_++ % 10) == 0) { char sb_[96]; snprintf(sb_, sizeof sb_, \"seed: %d animated tiles in view\", nAnim_); SDLmini_Log(sb_); }\n"
        "\t}\n"
        "}\n"
        "\n"
        "/* screen rect covering a map position: the tile sprite plus room for a\n"
        " * standing unit / tall object above it. Grows the given rect. */\n"
        "void Map::amigaDirtyMapPos(const Position &p, int &x0, int &y0, int &x1, int &y1)\n"
        "{\n"
        "\tPosition s_;\n"
        "\t_camera->convertMapToScreen(p, &s_);\n"
        "\ts_ += _camera->getMapOffset();\n"
        "\tint ax0 = s_.x - _spriteWidth / 2, ay0 = s_.y - _spriteHeight;\n"
        "\tint ax1 = s_.x + _spriteWidth + _spriteWidth / 2, ay1 = s_.y + _spriteHeight + _spriteHeight / 2;\n"
        "\tif (ax0 < x0) x0 = ax0;\n"
        "\tif (ay0 < y0) y0 = ay0;\n"
        "\tif (ax1 > x1) x1 = ax1;\n"
        "\tif (ay1 > y1) y1 = ay1;\n"
        "}\n"
        "\n"
        "/* tight cursor rect: the cursor is drawn on tiles (selX-size+1..selX,\n"
        " * selY-size+1..selY) on EVERY level 0..viewLevel, one 32x40 sprite each\n"
        " * (Map::drawTerrain, the CURSOR.PCK blits). That, and only that. */\n"
        "static void amigaCursorRect_(Camera *cam, int selX, int selY, int size, int vl, int sw, int sh, int &x0, int &y0, int &x1, int &y1)\n"
        "{\n"
        "\tPosition mo_ = cam->getMapOffset();\n"
        "\tfor (int z_ = 0; z_ <= vl; ++z_)\n"
        "\t\tfor (int dx_ = 0; dx_ < size; ++dx_)\n"
        "\t\t\tfor (int dy_ = 0; dy_ < size; ++dy_)\n"
        "\t\t\t{\n"
        "\t\t\t\tPosition s_;\n"
        "\t\t\t\tcam->convertMapToScreen(Position(selX - dx_, selY - dy_, z_), &s_);\n"
        "\t\t\t\ts_ += mo_;\n"
        "\t\t\t\tif (s_.x < x0) x0 = s_.x;\n"
        "\t\t\t\tif (s_.y < y0) y0 = s_.y;\n"
        "\t\t\t\tif (s_.x + sw > x1) x1 = s_.x + sw;\n"
        "\t\t\t\tif (s_.y + sh > y1) y1 = s_.y + sh;\n"
        "\t\t\t}\n"
        "}\n"
        "\n"
        "/* After drawTerrain: copy the composed area (whole picture or the clip\n"
        " * rect) into the current phase's cache and mark that phase clean. */\n"
        "void Map::amigaCacheStore()\n"
        "{\n"
        "\tconst int w_ = getWidth(), h_ = getHeight();\n"
        "\tconst int ph_ = _animFrame & 7;\n"
        "\t\tbool wasFull_ = (AmigaClipX0 <= 0 && AmigaClipY0 <= 0 && AmigaClipX1 >= w_ && AmigaClipY1 >= h_);\n"
        "\tif (_fcPix[ph_] == 0) _fcPix[ph_] = new Uint8[(size_t)w_ * h_];\n"
        "\tif (_fcPix[ph_] != 0)\n"
        "\t{\n"
        "\t\tint x0 = AmigaClipX0, y0 = AmigaClipY0, x1 = AmigaClipX1, y1 = AmigaClipY1;\n"
        "\t\tif (x0 < 0) x0 = 0;\n"
        "\t\tif (y0 < 0) y0 = 0;\n"
        "\t\tif (x1 > w_) x1 = w_;\n"
        "\t\tif (y1 > h_) y1 = h_;\n"
        "\t\tif (x1 > x0 && y1 > y0)\n"
        "\t\t{\n"
        "\t\t\tSDL_Surface *s_ = getSurface();\n"
        "\t\t\tconst Uint8 *sp_ = (const Uint8 *)s_->pixels + (size_t)y0 * s_->pitch + x0;\n"
        "\t\t\tUint8 *dp_ = _fcPix[ph_] + (size_t)y0 * w_ + x0;\n"
        "\t\t\tfor (int y_ = y0; y_ < y1; ++y_) { memcpy(dp_, sp_, x1 - x0); dp_ += w_; sp_ += s_->pitch; }\n"
        "\t\t}\n"
        "\t\t_fcValid[ph_] = 1;\n"
        "\t\tif (wasFull_) { if (_fcGrid[ph_]) memset(_fcGrid[ph_], 0, (size_t)_fcGridW * _fcGridH); _fcDirtyN[ph_] = 0; _fcBx0[ph_] = _fcBy0[ph_] = 0; _fcBx1[ph_] = _fcBy1[ph_] = 0; }\n"
        "\t\tif (wasFull_) { amigaSeedOtherPhases(ph_); _fcScrollStrip = false; }\n"
        "\t}\n"
        "\t_fcClipX0 = _fcClipY0 = 0; _fcClipX1 = _fcClipY1 = 1 << 14;\n"
        "\tif (wasFull_) { AmigaClipX0 = 0; AmigaClipY0 = 0; AmigaClipX1 = 1 << 14; AmigaClipY1 = 1 << 14; }\n"
        "}\n"
        "#endif\n"
        "\n"
        "/**\n"
        " * Draws the whole map, part by part.\n"
        " */\n"
        "void Map::draw()\n"
        "{\n",
        "dirty-rect cache helpers")))

    results.append(("Map.cpp (dirty-rect cache draw)", edit(
        os.path.join(src, "Battlescape", "Map.cpp"),
        "\t_redraw = false;\n"
        "\tclear(Palette::blockOffset(0)+15);\n",
        "#ifdef __AMIGA__\n"
        "\t/* AMIGA-PORT dirty-rect cache - see the comment at amigaFullSig(). */\n"
        "\tbool amPartial_ = false;\n"
        "\t{\n"
        "\t\tconst int w_ = getWidth(), h_ = getHeight();\n"
        "\t\tconst int ph_ = _animFrame & 7;\n"
        "\t\tconst unsigned long sig_ = amigaFullSig();\n"
        "\t\tstd::vector<BattleUnit*> *us_ = _save->getUnits();\n"
        "\t\tconst size_t un_ = us_->size();\n"
        "\t\t/* grid sized to the map, allocated once per battle size */\n"
        "\t\tif (_fcGridW != _save->getMapSizeX() || _fcGridH != _save->getMapSizeY())\n"
        "\t\t{\n"
        "\t\t\t_fcGridW = _save->getMapSizeX(); _fcGridH = _save->getMapSizeY();\n"
        "\t\t\tfor (int i_ = 0; i_ < 8; ++i_) { delete[] _fcGrid[i_]; _fcGrid[i_] = new Uint8[(size_t)_fcGridW * _fcGridH]; memset(_fcGrid[i_], 0, (size_t)_fcGridW * _fcGridH); _fcDirtyN[i_] = 0; _fcValid[i_] = 0; }\n"
        "\t\t}\n"
        "\t\tif (w_ != _fcW || h_ != _fcH || sig_ != _fcSig || _fcUnitPos.size() != un_)\n"
        "\t\t{\n"
        "\t\t\t++AmCp_whySig;\n"
        "\t\t\tfor (int i_ = 0; i_ < 8; ++i_) { _fcValid[i_] = 0; if (_fcGrid[i_]) memset(_fcGrid[i_], 0, (size_t)_fcGridW * _fcGridH); _fcDirtyN[i_] = 0; _fcBx0[i_] = _fcBy0[i_] = 0; _fcBx1[i_] = _fcBy1[i_] = 0; }\n"
        "\t\t\t_fcSig = sig_; _fcW = w_; _fcH = h_;\n"
        "\t\t\t_fcUnitPos.resize(un_); _fcUnitState.resize(un_);\n"
        "\t\t\tfor (size_t i_ = 0; i_ < un_; ++i_)\n"
        "\t\t\t{\n"
        "\t\t\t\tBattleUnit *bu_ = (*us_)[i_];\n"
        "\t\t\t\t_fcUnitPos[i_] = bu_->getPosition();\n"
        "\t\t\t\t_fcUnitState[i_] = bu_->getDirection() * 64 + (int)bu_->getStatus() * 8\n"
        "\t\t\t\t\t+ bu_->getWalkingPhase() + (bu_->getVisible() ? 4096 : 0);\n"
        "\t\t\t}\n"
        "\t\t\t_fcSelX = _selectorX; _fcSelY = _selectorY;\n"
        "\t\t\t_fcCurType = (int)_cursorType; _fcCurSize = _cursorSize;\n"
        "\t\t\t_fcProjOn = (_projectile != 0);\n"
        "\t\t\t_fcProjIdx = _projectile ? _projectile->amigaTrajIndex() : -1;\n"
        "\t\t\t_fcExplN = (int)_explosions.size();\n"
        "\t\t\t{ Position mo_ = _camera->getMapOffset(); _fcCamX = mo_.x; _fcCamY = mo_.y; }\n"
        "\t\t}\n"
        "\t\telse\n"
        "\t\t{\n"
        "\t\t\t/* scroll shift: camera moved by (dx,dy) with everything else equal.\n"
        "\t\t\t * The picture is the SAME picture translated - shift all 8 cached\n"
        "\t\t\t * buffers by (dx,dy) and dirty only the exposed strip (as tiles). A\n"
        "\t\t\t * jump larger than a third of the screen is a re-centre: full drop. */\n"
        "\t\t\t{\n"
        "\t\t\t\tPosition mo_ = _camera->getMapOffset();\n"
        "\t\t\t\tint dx_ = mo_.x - _fcCamX, dy_ = mo_.y - _fcCamY;\n"
        "\t\t\t\tif (dx_ != 0 || dy_ != 0)\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\tint adx_ = dx_ < 0 ? -dx_ : dx_, ady_ = dy_ < 0 ? -dy_ : dy_;\n"
        "\t\t\t\t\tif (adx_ >= w_ / 3 || ady_ >= h_ / 3)\n"
        "\t\t\t\t\t{\n"
        "\t\t\t\t\t\t++AmCp_whySig;\n"
        "\t\t\t\t\t\tfor (int i_ = 0; i_ < 8; ++i_) { _fcValid[i_] = 0; if (_fcGrid[i_]) memset(_fcGrid[i_], 0, (size_t)_fcGridW * _fcGridH); _fcDirtyN[i_] = 0; }\n"
        "\t\t\t\t\t}\n"
        "\t\t\t\t\telse\n"
        "\t\t\t\t\t{\n"
        "\t\t\t\t\t\t++AmCp_whyScroll;\n"
        "\t\t\t\t\t\t/* shift every valid buffer; the dirty grids are in MAP tiles and\n"
        "\t\t\t\t\t\t * stay valid as they are (their screen boxes are recomputed below) */\n"
        "\t\t\t\t\t\tfor (int i_ = 0; i_ < 8; ++i_)\n"
        "\t\t\t\t\t\t{\n"
        "\t\t\t\t\t\t\tif (!_fcValid[i_] || _fcPix[i_] == 0) continue;\n"
        "\t\t\t\t\t\t\tUint8 *b_ = _fcPix[i_];\n"
        "\t\t\t\t\t\t\tif (dy_ > 0)      { for (int y_ = h_ - 1; y_ >= dy_; --y_) memmove(b_ + (size_t)y_ * w_, b_ + (size_t)(y_ - dy_) * w_, w_); }\n"
        "\t\t\t\t\t\t\telse if (dy_ < 0) { for (int y_ = 0; y_ < h_ + dy_; ++y_) memmove(b_ + (size_t)y_ * w_, b_ + (size_t)(y_ - dy_) * w_, w_); }\n"
        "\t\t\t\t\t\t\tif (dx_ > 0)      { for (int y_ = 0; y_ < h_; ++y_) memmove(b_ + (size_t)y_ * w_ + dx_, b_ + (size_t)y_ * w_, w_ - dx_); }\n"
        "\t\t\t\t\t\t\telse if (dx_ < 0) { for (int y_ = 0; y_ < h_; ++y_) memmove(b_ + (size_t)y_ * w_, b_ + (size_t)y_ * w_ - dx_, w_ + dx_); }\n"
        "\t\t\t\t\t\t\t/* the exposed strips hold stale pixels: clear them to the map background\n"
        "\t\t\t\t\t\t\t * (beyond the map edge no tile will repaint them) */\n"
        "\t\t\t\t\t\t\tif (dy_ > 0)      memset(b_, Palette::blockOffset(0)+15, (size_t)dy_ * w_);\n"
        "\t\t\t\t\t\t\telse if (dy_ < 0) memset(b_ + (size_t)(h_ + dy_) * w_, Palette::blockOffset(0)+15, (size_t)(-dy_) * w_);\n"
        "\t\t\t\t\t\t\tif (dx_ > 0)      { for (int y_ = 0; y_ < h_; ++y_) memset(b_ + (size_t)y_ * w_, Palette::blockOffset(0)+15, dx_); }\n"
        "\t\t\t\t\t\t\telse if (dx_ < 0) { for (int y_ = 0; y_ < h_; ++y_) memset(b_ + (size_t)y_ * w_ + w_ + dx_, Palette::blockOffset(0)+15, -dx_); }\n"
        "\t\t\t\t\t\t}\n"
        "\t\t\t\t\t\t/* the exposed strip(s): every tile in view whose screen column touches\n"
        "\t\t\t\t\t\t * them - the grid halo takes care of overlap. Screen boxes of already\n"
        "\t\t\t\t\t\t * dirty tiles are rebuilt from scratch below (they moved on screen). */\n"
        "\t\t\t\t\t\tint sx0_ = 0, sx1_ = 0, sy0_ = 0, sy1_ = 0;   /* exposed strips in screen px */\n"
        "\t\t\t\t\t\tif (dx_ > 0) { sx0_ = 0; sx1_ = dx_; } else if (dx_ < 0) { sx0_ = w_ + dx_; sx1_ = w_; }\n"
        "\t\t\t\t\t\tif (dy_ > 0) { sy0_ = 0; sy1_ = dy_; } else if (dy_ < 0) { sy0_ = h_ + dy_; sy1_ = h_; }\n"
        "\t\t\t\t\t\t_fcScrollStrip = true;   /* scroll frame: every producer marks the current phase only */\n"
        "\t\t\t\t\t\t/* the strip union (an L when scrolling diagonally) as one box */\n"
        "\t\t\t\t\t\t_fcStripX0 = 0; _fcStripY0 = 0; _fcStripX1 = w_; _fcStripY1 = h_;\n"
        "\t\t\t\t\t\tif (sx1_ > sx0_ && !(sy1_ > sy0_)) { _fcStripX0 = sx0_; _fcStripX1 = sx1_; }\n"
        "\t\t\t\t\t\telse if (sy1_ > sy0_ && !(sx1_ > sx0_)) { _fcStripY0 = sy0_; _fcStripY1 = sy1_; }\n"
        "\t\t\t\t\t\t/* diagonal: keep the full box (copy is cheap; correctness first) */\n"
        "\t\t\t\t\t\tint bX, eX, bY, eY, dm_;\n"
        "\t\t\t\t\t\t_camera->convertScreenToMap(0, 0, &bX, &dm_);\n"
        "\t\t\t\t\t\t_camera->convertScreenToMap(w_, 0, &dm_, &bY);\n"
        "\t\t\t\t\t\t_camera->convertScreenToMap(w_ + _spriteWidth, h_ + _spriteHeight, &eX, &dm_);\n"
        "\t\t\t\t\t\t_camera->convertScreenToMap(0, h_ + _spriteHeight, &dm_, &eY);\n"
        "\t\t\t\t\t\tbY -= (_camera->getViewLevel() * 2); bX -= (_camera->getViewLevel() * 2);\n"
        "\t\t\t\t\t\tif (bX < 0) bX = 0; if (bY < 0) bY = 0;\n"
        "\t\t\t\t\t\tint vl_ = _camera->getViewLevel();\n"
        "\t\t\t\t\t\tfor (int tx_ = bX; tx_ <= eX; ++tx_)\n"
        "\t\t\t\t\t\t\tfor (int ty_ = bY; ty_ <= eY; ++ty_)\n"
        "\t\t\t\t\t\t\t{\n"
        "\t\t\t\t\t\t\t\tPosition s0_, s1_;\n"
        "\t\t\t\t\t\t\t\t_camera->convertMapToScreen(Position(tx_, ty_, 0), &s0_); s0_ += mo_;\n"
        "\t\t\t\t\t\t\t\t_camera->convertMapToScreen(Position(tx_, ty_, vl_), &s1_); s1_ += mo_;\n"
        "\t\t\t\t\t\t\t\tint cx0 = s0_.x, cx1 = s0_.x + _spriteWidth, cy0 = s1_.y - _spriteHeight, cy1 = s0_.y + _spriteHeight;\n"
        "\t\t\t\t\t\t\t\tbool hit_ = false;\n"
        "\t\t\t\t\t\t\t\tif (sx1_ > sx0_ && cx1 > sx0_ && cx0 < sx1_) hit_ = true;\n"
        "\t\t\t\t\t\t\t\tif (sy1_ > sy0_ && cy1 > sy0_ && cy0 < sy1_) hit_ = true;\n"
        "\t\t\t\t\t\t\t\tif (hit_)\n"
        "\t\t\t\t\t\t\t\t{\n"
        "\t\t\t\t\t\t\t\t\t/* scroll propagate: strip tiles go to the CURRENT phase only; the\n"
        "\t\t\t\t\t\t\t\t\t * repaired strip is copied to the other 7 after the repair, and only\n"
        "\t\t\t\t\t\t\t\t\t * their ANIMATED tiles in the strip stay dirty. Marking all 8 made\n"
        "\t\t\t\t\t\t\t\t\t * the idle phases pile up 7 scroll steps of dirt each (2026-08-19). */\n"
        "\t\t\t\t\t\t\t\t\tamigaMarkTileNoBox(ph_, tx_, ty_);\n"
        "\t\t\t\t\t\t\t\t\tTile *st_ = _save->getTile(Position(tx_, ty_, vl_));\n"
        "\t\t\t\t\t\t\t\t\tbool an_ = false;\n"
        "\t\t\t\t\t\t\t\t\tfor (int z2_ = 0; z2_ <= vl_ && !an_; ++z2_) { Tile *tz_ = _save->getTile(Position(tx_, ty_, z2_)); if (!tz_) continue; for (int pt_ = 0; pt_ < 4 && !an_; ++pt_) { MapData *md_ = tz_->getMapData(pt_); if (md_ && md_->amigaIsAnimated()) an_ = true; } if (tz_->getFire() || tz_->getSmoke()) an_ = true; }\n"
        "\t\t\t\t\t\t\t\t\t(void)st_;\n"
        "\t\t\t\t\t\t\t\t\tif (an_) for (int ph2_ = 0; ph2_ < 8; ++ph2_) if (ph2_ != ph_) amigaMarkTileNoBox(ph2_, tx_, ty_);\n"
        "\t\t\t\t\t\t\t\t\t_fcScrollStrip = true;\n"
        "\t\t\t\t\t\t\t\t}\n"
        "\t\t\t\t\t\t\t}\n"
        "\t\t\t\t\t\t/* strip box: existing boxes just moved with the pixels - shift them; the\n"
        "\t\t\t\t\t\t * strip is its own box (drawing the strip tiles clipped to it is all the\n"
        "\t\t\t\t\t\t * exposed pixels need - below the strip their sprites repaint identical\n"
        "\t\t\t\t\t\t * pixels). No tile columns for the strip: that was 85% of the screen. */\n"
        "\t\t\t\t\t\tfor (int i_ = 0; i_ < 8; ++i_)\n"
        "\t\t\t\t\t\t{\n"
        "\t\t\t\t\t\t\tif (_fcBx1[i_] > _fcBx0[i_] && _fcBy1[i_] > _fcBy0[i_])\n"
        "\t\t\t\t\t\t\t{\n"
        "\t\t\t\t\t\t\t\t_fcBx0[i_] += dx_; _fcBx1[i_] += dx_; _fcBy0[i_] += dy_; _fcBy1[i_] += dy_;\n"
        "\t\t\t\t\t\t\t\tif (_fcBx0[i_] < 0) _fcBx0[i_] = 0; if (_fcBy0[i_] < 0) _fcBy0[i_] = 0;\n"
        "\t\t\t\t\t\t\t\tif (_fcBx1[i_] > w_) _fcBx1[i_] = w_; if (_fcBy1[i_] > h_) _fcBy1[i_] = h_;\n"
        "\t\t\t\t\t\t\t}\n"
        "\t\t\t\t\t\t\tif (_fcDirtyN[i_] > 0 && _fcScrollStrip)\n"
        "\t\t\t\t\t\t\t{\n"
        "\t\t\t\t\t\t\t\tif (sx1_ > sx0_) amigaGrowBox(i_, sx0_, 0, sx1_, h_);\n"
        "\t\t\t\t\t\t\t\tif (sy1_ > sy0_) amigaGrowBox(i_, 0, sy0_, w_, sy1_);\n"
        "\t\t\t\t\t\t\t}\n"
        "\t\t\t\t\t\t}\n"
        "\t\t\t\t\t}\n"
        "\t\t\t\t\t_fcCamX = mo_.x; _fcCamY = mo_.y;\n"
        "\t\t\t\t}\n"
        "\t\t\t}\n"
        "\t\t\t/* incremental producers mark TILES */\n"
        "\t\t\tfor (size_t i_ = 0; i_ < un_; ++i_)\n"
        "\t\t\t{\n"
        "\t\t\t\tBattleUnit *bu_ = (*us_)[i_];\n"
        "\t\t\t\tint st_ = bu_->getDirection() * 64 + (int)bu_->getStatus() * 8\n"
        "\t\t\t\t\t+ bu_->getWalkingPhase() + (bu_->getVisible() ? 4096 : 0);\n"
        "\t\t\t\tif (st_ == _fcUnitState[i_] && bu_->getPosition() == _fcUnitPos[i_]) continue;\n"
        "\t\t\t\t++AmCp_whyUnits;\n"
        "\t\t\t\tint sz_ = bu_->getArmor()->getSize();\n"
        "\t\t\t\tfor (int a_ = 0; a_ < sz_; ++a_) for (int b_ = 0; b_ < sz_; ++b_) { amigaDirtyTile(_fcUnitPos[i_].x + a_, _fcUnitPos[i_].y + b_); amigaDirtyTile(bu_->getPosition().x + a_, bu_->getPosition().y + b_); }\n"
        "\t\t\t\t_fcUnitPos[i_] = bu_->getPosition(); _fcUnitState[i_] = st_;\n"
        "\t\t\t}\n"
        "\t\t\tif (_selectorX != _fcSelX || _selectorY != _fcSelY\n"
        "\t\t\t\t|| (int)_cursorType != _fcCurType || _cursorSize != _fcCurSize)\n"
        "\t\t\t{\n"
        "\t\t\t\t++AmCp_whyCur;\n"
        "\t\t\t\tint cs_ = _cursorSize > 0 ? _cursorSize : 1;\n"
        "\t\t\t\tint ocs_ = _fcCurSize > 0 ? _fcCurSize : 1;\n"
        "\t\t\t\tAmigaDirtyFullColumn = 1;\n"
        "\t\t\t\tif (_fcSelX > -9000) for (int a_ = 0; a_ < ocs_; ++a_) for (int b_ = 0; b_ < ocs_; ++b_) amigaDirtyTile(_fcSelX - a_, _fcSelY - b_);\n"
        "\t\t\t\tAmigaDirtyFullColumn = 0;\n"
        "\t\t\t\tfor (int a_ = 0; a_ < cs_; ++a_) for (int b_ = 0; b_ < cs_; ++b_) amigaDirtyTile(_selectorX - a_, _selectorY - b_);\n"
        "\t\t\t\t_fcSelX = _selectorX; _fcSelY = _selectorY;\n"
        "\t\t\t\t_fcCurType = (int)_cursorType; _fcCurSize = _cursorSize;\n"
        "\t\t\t}\n"
        "\t\t\tif (_projectile)\n"
        "\t\t\t{\n"
        "\t\t\t\tint idx_ = _projectile->amigaTrajIndex();\n"
        "\t\t\t\tif (_fcProjIdx < 0 || !_fcProjOn) { ++AmCp_whyProj; amigaBulletTiles(0, BULLET_SPRITES - 1); }\n"
        "\t\t\t\telse if (idx_ != _fcProjIdx)\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\t++AmCp_whyProj;\n"
        "\t\t\t\t\tint d_ = idx_ - _fcProjIdx; if (d_ < 0) d_ = -d_;\n"
        "\t\t\t\t\tif (d_ >= BULLET_SPRITES) d_ = BULLET_SPRITES - 1;\n"
        "\t\t\t\t\tamigaBulletTiles(0, d_);                                    /* head: new positions */\n"
        "\t\t\t\t\tamigaBulletTiles(BULLET_SPRITES - 1 - d_, BULLET_SPRITES - 1); /* tail: current tail */\n"
        "\t\t\t\t\tfor (int k_ = 1; k_ <= d_; ++k_)                             /* fell out of the window */\n"
        "\t\t\t\t\t{ Position v_ = _projectile->getPosition(1 - (BULLET_SPRITES - 1) - k_); amigaDirtyTile(v_.x / 16, v_.y / 16); }\n"
        "\t\t\t\t}\n"
        "\t\t\t\t_fcProjIdx = idx_; _fcProjOn = 1;\n"
        "\t\t\t}\n"
        "\t\t\telse if (_fcProjOn)\n"
        "\t\t\t{\n"
        "\t\t\t\t/* bullet gone: it was drawn LAST frame along its whole trail; those\n"
        "\t\t\t\t * tiles are already dirty from the head/tail marking over its flight\n"
        "\t\t\t\t * only if the animation phase repaired them... be safe: full drop. */\n"
        "\t\t\t\t++AmCp_whyProj;\n"
        "\t\t\t\tfor (int i_ = 0; i_ < 8; ++i_) _fcValid[i_] = 0;\n"
        "\t\t\t\t_fcProjOn = 0; _fcProjIdx = -1;\n"
        "\t\t\t}\n"
        "\t\t\tif (!_explosions.empty())\n"
        "\t\t\t{\n"
        "\t\t\t\t++AmCp_whyExpl;\n"
        "\t\t\t\tfor (std::list<Explosion*>::const_iterator e_ = _explosions.begin(); e_ != _explosions.end(); ++e_)\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\tPosition ep_ = (*e_)->getPosition();\n"
        "\t\t\t\t\tint tx_ = ep_.x / 16, ty_ = ep_.y / 16;\n"
        "\t\t\t\t\tif ((*e_)->isBig()) { for (int a_ = -2; a_ <= 2; ++a_) for (int b_ = -2; b_ <= 2; ++b_) amigaDirtyTile(tx_ + a_, ty_ + b_); }\n"
        "\t\t\t\t\telse amigaDirtyTile(tx_, ty_);\n"
        "\t\t\t\t}\n"
        "\t\t\t}\n"
        "\t\t}\n"
        "\t\t/* current phase usable? */\n"
        "\t\tif (_fcValid[ph_] && _fcPix[ph_] != 0)\n"
        "\t\t{\n"
        "\t\t\tSDL_Surface *d_ = getSurface();\n"
        "\t\t\tconst Uint8 *sp_ = _fcPix[ph_];\n"
        "\t\t\tUint8 *dp_ = (Uint8 *)d_->pixels;\n"
        "\t\t\tfor (int y_ = 0; y_ < h_; ++y_) { memcpy(dp_, sp_, w_); sp_ += w_; dp_ += d_->pitch; }\n"
        "\t\t\tif (_fcDirtyN[ph_] == 0)\n"
        "\t\t\t{\n"
        "\t\t\t\t++AmCp_hit;\n"
        "\t\t\t\t_fcScrollStrip = false;   /* nothing to propagate this frame */\n"
        "\t\t\t\t_redraw = false;\n"
        "\t\t\t\treturn;\n"
        "\t\t\t}\n"
        "\t\t\t/* dirty hit: ONE compose over the view, skipping clean tiles */\n"
        "\t\t\tamPartial_ = true; ++AmCp_part; ++AmCp_partRects;\n"
        "\t\t\tint x0 = _fcBx0[ph_] < 0 ? 0 : _fcBx0[ph_], y0 = _fcBy0[ph_] < 0 ? 0 : _fcBy0[ph_];\n"
        "\t\t\tint x1 = _fcBx1[ph_] > w_ ? w_ : _fcBx1[ph_], y1 = _fcBy1[ph_] > h_ ? h_ : _fcBy1[ph_];\n"
        "\t\t\tif (x1 > x0 && y1 > y0)\n"
        "\t\t\t{\n"
        "\t\t\t\tAmCp_partPx += (unsigned long)(x1 - x0) * (unsigned long)(y1 - y0);\n"
        "\t\t\t\tAmigaClipX0 = x0; AmigaClipY0 = y0; AmigaClipX1 = x1; AmigaClipY1 = y1;\n"
        "\t\t\t\tAmigaDirtyGrid = _fcGrid[ph_]; AmigaDirtyGridW = _fcGridW; AmigaDirtyGridH = _fcGridH;\n"
        "\t\t\t\t/* clear the dirty tiles' pixels: not the box (it holds clean tiles too)\n"
        "\t\t\t\t * but per dirty tile column - drawTerrain paints floors first, so a\n"
        "\t\t\t\t * dirty tile fully repaints itself; only the box beyond the map edge\n"
        "\t\t\t\t * needs the background. Simplest correct: clear the box. Clean tiles\n"
        "\t\t\t\t * inside it are neighbours of dirty ones and were marked too. */\n"
        "\t\t\t\tUint8 *cp_ = (Uint8 *)d_->pixels + (size_t)y0 * d_->pitch + x0;\n"
        "\t\t\t\tfor (int y_ = y0; y_ < y1; ++y_) { memset(cp_, Palette::blockOffset(0)+15, x1 - x0); cp_ += d_->pitch; }\n"
        "\t\t\t\tUint32 t0_ = SDL_GetTicks(); unsigned long tb_ = AmigaTileN, bb_ = AmigaShadeThruN;\n"
        "\t\t\t\tamigaComposeVisible();\n"
        "\t\t\t\t{ Uint32 dd_ = SDL_GetTicks() - t0_; AmCp_partMs += dd_; AmCp_partTiles += AmigaTileN - tb_; AmCp_partBlits += AmigaShadeThruN - bb_; }\n"
        "\t\t\t\tAmigaDirtyGrid = 0;\n"
        "\t\t\t\tif (_fcScrollStrip)\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\t/* scroll propagate: the repaired area of THIS phase is, bar the animated\n"
        "\t\t\t\t\t * tiles (left dirty there), the same in every other phase - copy it. */\n"
        "\t\t\t\t\tfor (int i_ = 0; i_ < 8; ++i_)\n"
        "\t\t\t\t\t{\n"
        "\t\t\t\t\t\tif (i_ == ph_ || !_fcValid[i_] || _fcPix[i_] == 0) continue;\n"
        "\t\t\t\t\t\tconst Uint8 *rs_ = (const Uint8 *)d_->pixels + (size_t)y0 * d_->pitch + x0;\n"
        "\t\t\t\t\t\tUint8 *rd_ = _fcPix[i_] + (size_t)y0 * w_ + x0;\n"
        "\t\t\t\t\t\tfor (int y_ = y0; y_ < y1; ++y_) { memcpy(rd_, rs_, x1 - x0); rd_ += w_; rs_ += d_->pitch; }\n"
        "\t\t\t\t\t}\n"
        "\t\t\t\t\t/* animated tiles anywhere in the copied box now show phase ph_ in the\n"
        "\t\t\t\t\t * other phases - mark them dirty there so they repaint on their turn */\n"
        "\t\t\t\t\t{\n"
        "\t\t\t\t\t\tint bX, eX, bY, eY, dm_;\n"
        "\t\t\t\t\t\t_camera->convertScreenToMap(0, 0, &bX, &dm_);\n"
        "\t\t\t\t\t\t_camera->convertScreenToMap(w_, 0, &dm_, &bY);\n"
        "\t\t\t\t\t\t_camera->convertScreenToMap(w_ + _spriteWidth, h_ + _spriteHeight, &eX, &dm_);\n"
        "\t\t\t\t\t\t_camera->convertScreenToMap(0, h_ + _spriteHeight, &dm_, &eY);\n"
        "\t\t\t\t\t\tint vl2_ = _camera->getViewLevel();\n"
        "\t\t\t\t\t\tbY -= vl2_ * 2; bX -= vl2_ * 2; if (bX < 0) bX = 0; if (bY < 0) bY = 0;\n"
        "\t\t\t\t\t\tPosition mo2_ = _camera->getMapOffset();\n"
        "\t\t\t\t\t\tfor (int tx_ = bX; tx_ <= eX; ++tx_) for (int ty_ = bY; ty_ <= eY; ++ty_)\n"
        "\t\t\t\t\t\t{\n"
        "\t\t\t\t\t\t\tPosition s0_, s1_;\n"
        "\t\t\t\t\t\t\t_camera->convertMapToScreen(Position(tx_, ty_, 0), &s0_); s0_ += mo2_;\n"
        "\t\t\t\t\t\t\t_camera->convertMapToScreen(Position(tx_, ty_, vl2_), &s1_); s1_ += mo2_;\n"
        "\t\t\t\t\t\t\tif (s0_.x + _spriteWidth <= x0 || s0_.x >= x1 || s0_.y + _spriteHeight <= y0 || s1_.y - _spriteHeight >= y1) continue;\n"
        "\t\t\t\t\t\t\tbool an_ = false;\n"
        "\t\t\t\t\t\t\tfor (int z2_ = 0; z2_ <= vl2_ && !an_; ++z2_) { Tile *tz_ = _save->getTile(Position(tx_, ty_, z2_)); if (!tz_) continue; for (int pt_ = 0; pt_ < 4 && !an_; ++pt_) { MapData *md_ = tz_->getMapData(pt_); if (md_ && md_->amigaIsAnimated()) an_ = true; } if (tz_->getFire() || tz_->getSmoke()) an_ = true; }\n"
        "\t\t\t\t\t\t\tif (an_) for (int i_ = 0; i_ < 8; ++i_) if (i_ != ph_) { amigaMarkTileNoBox(i_, tx_, ty_); amigaGrowBox(i_, s0_.x, s1_.y - _spriteHeight, s0_.x + _spriteWidth, s0_.y + _spriteHeight); }\n"
        "\t\t\t\t\t\t}\n"
        "\t\t\t\t\t}\n"
        "\t\t\t\t\t_fcScrollStrip = false;\n"
        "\t\t\t\t}\n"
        "\t\t\t}\n"
        "\t\t\tif (_fcGrid[ph_]) memset(_fcGrid[ph_], 0, (size_t)_fcGridW * _fcGridH);\n"
        "\t\t\t_fcDirtyN[ph_] = 0; _fcBx0[ph_] = _fcBy0[ph_] = 0; _fcBx1[ph_] = _fcBy1[ph_] = 0;\n"
        "\t\t\tAmigaClipX0 = 0; AmigaClipY0 = 0; AmigaClipX1 = 1 << 14; AmigaClipY1 = 1 << 14;\n"
        "\t\t\t_fcClipX0 = _fcClipY0 = 0; _fcClipX1 = _fcClipY1 = 1 << 14;\n"
        "\t\t\t_redraw = false;\n"
        "\t\t\treturn;\n"
        "\t\t}\n"
        "\t\telse\n"
        "\t\t{\n"
        "\t\t\t++AmCp_whyMiss;\n"
        "\t\t\t_fcClipX0 = 0; _fcClipY0 = 0; _fcClipX1 = w_; _fcClipY1 = h_;\n"
        "\t\t}\n"
        "\t}\n"
        "\tAmigaClipX0 = _fcClipX0; AmigaClipY0 = _fcClipY0;\n"
        "\tAmigaClipX1 = _fcClipX1; AmigaClipY1 = _fcClipY1;\n"
        "\t_redraw = false;\n"
        "\tclear(Palette::blockOffset(0)+15);\n"
        "#else\n"
        "\t_redraw = false;\n"
        "\tclear(Palette::blockOffset(0)+15);\n"
        "#endif\n"
        "#ifdef __AMIGA__\n"
        "\tamigaComposeVisible();   /* compose split */\n"
        "}\n"
        "\n"
        "/* The part of draw() that actually composes: FOV visibility flags for the\n"
        " * bullet/explosions, then drawTerrain (or the hidden-movement screen).\n"
        " * Called for a full compose and, with AmigaClip* set, for each dirty rect. */\n"
        "void Map::amigaComposeVisible()\n"
        "{\n"
        "#endif\n",
        "dirty-rect cache draw")))

    # The hidden-movement message path must not leave a stale clip and must
    # not be cached: drop the phases so the next real frame recomposes.
    results.append(("Map.cpp (dirty-rect cache message path)", edit(
        os.path.join(src, "Battlescape", "Map.cpp"),
        "\telse\n"
        "\t{\n"
        "\t\t_message->blit(this);\n"
        "\t}\n"
        "}\n",
        "\telse\n"
        "\t{\n"
        "#ifdef __AMIGA__\n"
        "\t\tAmigaClipX0 = 0; AmigaClipY0 = 0; AmigaClipX1 = 1 << 14; AmigaClipY1 = 1 << 14;\n"
        "\t\t_fcClipX0 = _fcClipY0 = 0; _fcClipX1 = _fcClipY1 = 1 << 14;\n"
        "\t\tif (AmigaClipX1 - AmigaClipX0 < getWidth()) clear(Palette::blockOffset(0)+15);\n"
        "\t\t/* the hidden-movement screen is NOT cached, but it must not throw\n"
        "\t\t * the cached map away either: an alien turn flips between this\n"
        "\t\t * screen and the map on every shot, and each flip used to be a full\n"
        "\t\t * recompose. The map underneath is still valid. */\n"
        "#endif\n"
        "\t\t_message->blit(this);\n"
        "\t}\n"
        "}\n",
        "dirty-rect cache message path")))

    # drawTerrain: narrow the tile loop to the clip rect. The corners of the
    # SURFACE become the corners of the rect being composed. Outside the port
    # (or with a full clip) this is exactly upstream's computation.
    results.append(("Map.cpp (dirty-rect narrow tile loop)", edit(
        os.path.join(src, "Battlescape", "Map.cpp"),
        "\t_camera->convertScreenToMap(0, 0, &beginX, &dummy);\n"
        "\t_camera->convertScreenToMap(surface->getWidth(), 0, &dummy, &beginY);\n"
        "\t_camera->convertScreenToMap(surface->getWidth() + _spriteWidth, surface->getHeight() + _spriteHeight, &endX, &dummy);\n"
        "\t_camera->convertScreenToMap(0, surface->getHeight() + _spriteHeight, &dummy, &endY);\n",
        "#ifdef __AMIGA__\n"
        "\t{\n"
        "\t\tint cx0_ = (AmigaDirtyGrid != 0 || AmigaClipX0 < 0) ? 0 : AmigaClipX0;\n"
        "\t\tint cy0_ = (AmigaDirtyGrid != 0 || AmigaClipY0 < 0) ? 0 : AmigaClipY0;\n"
        "\t\tint cx1_ = (AmigaDirtyGrid != 0 || AmigaClipX1 > surface->getWidth()) ? surface->getWidth() : AmigaClipX1;\n"
        "\t\tint cy1_ = (AmigaDirtyGrid != 0 || AmigaClipY1 > surface->getHeight()) ? surface->getHeight() : AmigaClipY1;\n"
        "\t\t/* tall objects on tiles ABOVE the rect can hang down into it: give the\n"
        "\t\t * top edge extra room (up to a whole level of walls). */\n"
        "\t\tint top_ = cy0_ - _spriteHeight * 2; if (top_ < 0) top_ = 0;\n"
        "\t\t_camera->convertScreenToMap(cx0_, top_, &beginX, &dummy);\n"
        "\t\t_camera->convertScreenToMap(cx1_, top_, &dummy, &beginY);\n"
        "\t\t_camera->convertScreenToMap(cx1_ + _spriteWidth, cy1_ + _spriteHeight, &endX, &dummy);\n"
        "\t\t_camera->convertScreenToMap(cx0_, cy1_ + _spriteHeight, &dummy, &endY);\n"
        "\t}\n"
        "#else\n"
        "\t_camera->convertScreenToMap(0, 0, &beginX, &dummy);\n"
        "\t_camera->convertScreenToMap(surface->getWidth(), 0, &dummy, &beginY);\n"
        "\t_camera->convertScreenToMap(surface->getWidth() + _spriteWidth, surface->getHeight() + _spriteHeight, &endX, &dummy);\n"
        "\t_camera->convertScreenToMap(0, surface->getHeight() + _spriteHeight, &dummy, &endY);\n"
        "#endif\n",
        "dirty-rect narrow tile loop")))

    results.append(("Map.cpp (dirty-rect cache free)", edit(
        os.path.join(src, "Battlescape", "Map.cpp"),
        "\tdelete _scrollMouseTimer;\n",
        "#ifdef __AMIGA__\n"
        "\tfor (int fc_ = 0; fc_ < 8; ++fc_) { delete[] _fcPix[fc_]; delete[] _fcGrid[fc_]; }\n"
        "#endif\n"
        "\tdelete _scrollMouseTimer;\n",
        "dirty-rect cache free")))

    # 6c. Config migration. Players carry options.cfg across releases, so a
    #     better default never reaches them. amigaCfgVersion in the file says
    #     which port defaults it has seen; anything older gets the new values
    #     forced once (they can change them again afterwards - the number is
    #     bumped, so it will not be forced a second time). Add a new
    #     `if (amigaCfgVersion < N)` block and bump AMIGA_CFG_VERSION for the
    #     next batch.
    results.append(("Options.cpp (config migration)", edit(
        os.path.join(src, "Engine", "Options.cpp"),
        "\t\tfor (std::vector<OptionInfo>::iterator i = _info.begin(); i != _info.end(); ++i)\n"
        "\t\t{\n"
        "\t\t\ti->load(doc[\"options\"]);\n"
        "\t\t}\n"
        "\n"
        "\t\tmods.clear();\n",
        "\t\tfor (std::vector<OptionInfo>::iterator i = _info.begin(); i != _info.end(); ++i)\n"
        "\t\t{\n"
        "\t\t\ti->load(doc[\"options\"]);\n"
        "\t\t}\n"
        "#ifdef __AMIGA__\n"
        "\t\t{\n"
        "\t\t\tconst int AMIGA_CFG_VERSION = 1;\n"
        "\t\t\tif (amigaCfgVersion < 1)\n"
        "\t\t\t{\n"
        "\t\t\t\t/* 0.6.0: on this machine a bullet step and a scroll step each cost\n"
        "\t\t\t\t * one composed frame, so bigger steps make both feel twice as fast */\n"
        "\t\t\t\tif (battleFireSpeed < 12) battleFireSpeed = 12;\n"
        "\t\t\t\tif (battleScrollSpeed < 16) battleScrollSpeed = 16;\n"
        "\t\t\t\tamigaAnimMs = 100;\n"
        "\t\t\t}\n"
        "\t\t\tif (amigaCfgVersion < AMIGA_CFG_VERSION)\n"
        "\t\t\t{\n"
        "\t\t\t\tamigaCfgVersion = AMIGA_CFG_VERSION;\n"
        "\t\t\t\tLog(LOG_INFO) << \"Amiga: options migrated to cfg version \" << AMIGA_CFG_VERSION;\n"
        "\t\t\t}\n"
        "\t\t}\n"
        "#endif\n"
        "\n"
        "\t\tmods.clear();\n",
        "config migration")))

    # 6b. Battle animation tick from an option (default 200 ms on this port -
    #     since 0.6.0 back to 100 ms: with the frame cache a redraw is cheap.
    results.append(("Options (amigaAnimMs)", edit(
        os.path.join(src, "Engine", "Options.inc.h"),
        "OPT int amigaAccurateFov; /* 0 fast, 1 accurate, 2 test */\n",
        "OPT int amigaAccurateFov; /* 0 fast, 1 accurate, 2 test */\n"
        "OPT int amigaAnimMs;     /* battle animation tick, ms */\n"
        "OPT int amigaFlatGlobe;  /* 1 = flat sun-shaded land polygons */\n"
        "OPT int amigaAutoBattle; /* 1 = boot straight into a New Battle */\n"
        "OPT int amigaCfgVersion; /* config migration: bumped by the port when it forces new defaults */\n",
        "amigaAnimMs var")))
    results.append(("Options.cpp (amigaAnimMs)", edit(
        os.path.join(src, "Engine", "Options.cpp"),
        "\t_info.push_back(OptionInfo(\"amigaAccurateFov\", &amigaAccurateFov, 1)); /* default: Accurate - same speed since the pair-update */\n",
        "\t_info.push_back(OptionInfo(\"amigaAccurateFov\", &amigaAccurateFov, 1)); /* default: Accurate - same speed since the pair-update */\n"
        "\t_info.push_back(OptionInfo(\"amigaAnimMs\", &amigaAnimMs, 100));\n"
        "\t_info.push_back(OptionInfo(\"amigaFlatGlobe\", &amigaFlatGlobe, 1)); /* test: default on; 0 = textured land */\n"
        "\t_info.push_back(OptionInfo(\"amigaAutoBattle\", &amigaAutoBattle, 0)); /* 1 = skip the menus, generate a battle at boot */\n"
        "\t_info.push_back(OptionInfo(\"amigaCfgVersion\", &amigaCfgVersion, 0));\n",
        "amigaAnimMs info")))
    results.append(("BattlescapeState.cpp (anim timer option)", edit(
        os.path.join(src, "Battlescape", "BattlescapeState.cpp"),
        "\t_animTimer = new Timer(DEFAULT_ANIM_SPEED, true);\n",
        "\t_animTimer = new Timer(Options::amigaAnimMs > 0 ? Options::amigaAnimMs : DEFAULT_ANIM_SPEED, true); /* AMIGA-PORT */\n",
        "anim timer option")))
    results.append(("en-US.yml (anim strings)", edit(
        os.path.join(src, "..", "bin", "common", "Language", "en-US.yml"),
        "  STR_AMIGA_FOV_TEST: \"Test\"\n",
        "  STR_AMIGA_FOV_TEST: \"Test\"\n"
        "  STR_AMIGA_ANIM: \"Battle animation speed\"\n"
        "  STR_AMIGA_ANIM_DESC: \"How often fire, water and the cursor animate in battle. Half rate frees a lot of CPU on real hardware.\"\n"
        "  STR_AMIGA_ANIM_NORMAL: \"Normal\"\n"
        "  STR_AMIGA_ANIM_HALF: \"Half (faster)\"\n",
        "anim strings")))

    # 6d. Screen::clear must not wipe the PHYSICAL screen (dirty rects).
    #     Upstream zeroes _screen every frame "for the black bands"; this port
    #     has no bands (_screen and _surface are both exactly the game area)
    #     and the full back-buffer blit in Screen::flip covers every pixel
    #     anyway. The zero-fill marked the whole screen dirty every frame and
    #     made the diff-blit re-copy everything - it defeated dirty rectangles
    #     entirely (0 skipped, full 320x200 c2p per frame, measured 2026-08-17).
    results.append(("Screen.cpp (no screen wipe per frame)", edit(
        os.path.join(src, "Engine", "Screen.cpp"),
        "\t_surface->clear();\n"
        "\tif (_screen->flags & SDL_SWSURFACE) memset(_screen->pixels, 0, _screen->h*_screen->pitch);\n"
        "\telse SDL_FillRect(_screen, &_clear, 0);\n",
        "\t_surface->clear();\n"
        "\t/* AMIGA-PORT: no wipe of the real screen - flip() blits the full\n"
        "\t * back buffer over it, and the wipe forced a full c2p per frame. */\n",
        "screen clear wipe")))

    # 6e. TEMP probes: where does a save spend its minute (build the node
    #     tree / emit / write). Logged once per save as "save:" / "optsave:".
    results.append(("SavedGame.cpp (save probe extern)", edit(
        os.path.join(src, "Savegame", "SavedGame.cpp"),
        '#include "SavedGame.h"\n',
        '#include "SavedGame.h"\n'
        '#ifdef __AMIGA__\n'
        '#include <cstdio>\n'
        '#include "amiga_yamlout.h"\n'
        'extern "C" void SDLmini_Log(const char *msg);\n'
        'extern "C" unsigned int SDL_GetTicks(void);\n'
        '#endif\n',
        "save probe extern")))
    results.append(("SavedGame.cpp (save probe t0)", edit(
        os.path.join(src, "Savegame", "SavedGame.cpp"),
        "\tstd::string s = Options::getMasterUserFolder() + filename;\n"
        "\tstd::ofstream sav(s.c_str());\n",
        "\tstd::string s = Options::getMasterUserFolder() + filename;\n"
        "\tunsigned int svT0_ = SDL_GetTicks(); /* TEMP save probe */\n"
        "\tstd::ofstream sav(s.c_str());\n",
        "save probe t0")))
    results.append(("SavedGame.cpp (fast writer brief)", edit(
        os.path.join(src, "Savegame", "SavedGame.cpp"),
        "\tout << brief;\n",
        "\tstd::string ydump_; ydump_.reserve(300 * 1024); /* AMIGA-PORT fast yaml writer */\n"
        "\tAmigaYamlWrite(ydump_, brief);\n",
        "fast writer brief")))
    results.append(("SavedGame.cpp (fast writer begindoc)", edit(
        os.path.join(src, "Savegame", "SavedGame.cpp"),
        "\tout << YAML::BeginDoc;\n",
        "\tydump_ += \"---\\n\"; /* AMIGA-PORT */\n",
        "fast writer begindoc")))
    # TEMP. New Battle takes ~30 s on the 040/40 reference machine. These
    #       probes split BattlescapeGenerator::run() into its phases so the
    #       report rests on numbers, not on a plausible story. Remove with the
    #       rest of the TEMP probes (LEFTOFF.md point 3).
    results.append(("BattlescapeGenerator.cpp (newbattle probe head)", edit(
        os.path.join(src, "Battlescape", "BattlescapeGenerator.cpp"),
        '#include "BattlescapeGenerator.h"\n',
        '#include "BattlescapeGenerator.h"\n'
        '#ifdef __AMIGA__\n'
        '#include <cstdio>\n'
        'extern "C" void SDLmini_Log(const char *msg);\n'
        'extern "C" unsigned int SDL_GetTicks(void);\n'
        'static unsigned int g_bgMap_ = 0, g_bgRmp_ = 0, g_bgInit_ = 0;\n'
        'static unsigned int g_bgMapN_ = 0, g_bgRmpN_ = 0;\n'
        '#define BGP1_(f, a) do { char bgb_[128]; snprintf(bgb_, sizeof bgb_, f, (unsigned)(a)); SDLmini_Log(bgb_); } while (0)\n'
        '#endif\n',
        "newbattle probe head")))

    results.append(("BattlescapeGenerator.cpp (newbattle probe run)", edit(
        os.path.join(src, "Battlescape", "BattlescapeGenerator.cpp"),
        "\tgenerateMap(script);\n"
        "\n"
        "\tsetupObjectives(ruleDeploy);\n"
        "\n"
        "\tdeployXCOM();\n"
        "\n"
        "\tsize_t unitCount = _save->getUnits()->size();\n"
        "\n"
        "\tdeployAliens(ruleDeploy);\n",
        "#ifdef __AMIGA__\n"
        "\tunsigned int bgT0_ = SDL_GetTicks();\n"
        "#endif\n"
        "\tgenerateMap(script);\n"
        "#ifdef __AMIGA__\n"
        "\tBGP1_(\"bgen: generateMap %u ms\", SDL_GetTicks() - bgT0_); bgT0_ = SDL_GetTicks();\n"
        "#endif\n"
        "\n"
        "\tsetupObjectives(ruleDeploy);\n"
        "#ifdef __AMIGA__\n"
        "\tBGP1_(\"bgen: objectives %u ms\", SDL_GetTicks() - bgT0_); bgT0_ = SDL_GetTicks();\n"
        "#endif\n"
        "\n"
        "\tdeployXCOM();\n"
        "#ifdef __AMIGA__\n"
        "\tBGP1_(\"bgen: deployXCOM %u ms\", SDL_GetTicks() - bgT0_); bgT0_ = SDL_GetTicks();\n"
        "#endif\n"
        "\n"
        "\tsize_t unitCount = _save->getUnits()->size();\n"
        "\n"
        "\tdeployAliens(ruleDeploy);\n"
        "#ifdef __AMIGA__\n"
        "\tBGP1_(\"bgen: deployAliens %u ms\", SDL_GetTicks() - bgT0_); bgT0_ = SDL_GetTicks();\n"
        "#endif\n",
        "newbattle probe run")))

    results.append(("BattlescapeGenerator.cpp (newbattle probe light)", edit(
        os.path.join(src, "Battlescape", "BattlescapeGenerator.cpp"),
        "\t// set shade (alien bases are a little darker, sites depend on worldshade)\n"
        "\t_save->setGlobalShade(_worldShade);\n"
        "\n"
        "\t_save->getTileEngine()->calculateSunShading();\n"
        "\t_save->getTileEngine()->calculateTerrainLighting();\n"
        "\t_save->getTileEngine()->calculateUnitLighting();\n"
        "\t_save->getTileEngine()->recalculateFOV();\n"
        "}\n",
        "\t// set shade (alien bases are a little darker, sites depend on worldshade)\n"
        "\t_save->setGlobalShade(_worldShade);\n"
        "\n"
        "#ifdef __AMIGA__\n"
        "\tBGP1_(\"bgen: rest %u ms\", SDL_GetTicks() - bgT0_); bgT0_ = SDL_GetTicks();\n"
        "#endif\n"
        "\t_save->getTileEngine()->calculateSunShading();\n"
        "#ifdef __AMIGA__\n"
        "\tBGP1_(\"bgen: sunShading %u ms\", SDL_GetTicks() - bgT0_); bgT0_ = SDL_GetTicks();\n"
        "#endif\n"
        "\t_save->getTileEngine()->calculateTerrainLighting();\n"
        "#ifdef __AMIGA__\n"
        "\tBGP1_(\"bgen: terrainLight %u ms\", SDL_GetTicks() - bgT0_); bgT0_ = SDL_GetTicks();\n"
        "#endif\n"
        "\t_save->getTileEngine()->calculateUnitLighting();\n"
        "#ifdef __AMIGA__\n"
        "\tBGP1_(\"bgen: unitLight %u ms\", SDL_GetTicks() - bgT0_); bgT0_ = SDL_GetTicks();\n"
        "#endif\n"
        "\t_save->getTileEngine()->recalculateFOV();\n"
        "#ifdef __AMIGA__\n"
        "\tBGP1_(\"bgen: recalcFOV %u ms\", SDL_GetTicks() - bgT0_);\n"
        "#endif\n"
        "}\n",
        "newbattle probe light")))

    results.append(("BattlescapeGenerator.cpp (newbattle probe genstart)", edit(
        os.path.join(src, "Battlescape", "BattlescapeGenerator.cpp"),
        '\t_dummy = new MapBlock("dummy");\n'
        "\n"
        "\tinit();\n",
        "#ifdef __AMIGA__\n"
        "\tg_bgMap_ = g_bgRmp_ = g_bgInit_ = g_bgMapN_ = g_bgRmpN_ = 0;\n"
        "\tunsigned int gmT_ = SDL_GetTicks();\n"
        "#endif\n"
        '\t_dummy = new MapBlock("dummy");\n'
        "\n"
        "\tinit();\n",
        "newbattle probe genstart")))

    results.append(("BattlescapeGenerator.cpp (newbattle probe datasets)", edit(
        os.path.join(src, "Battlescape", "BattlescapeGenerator.cpp"),
        "\tRuleTerrain* ufoTerrain = 0;\n",
        "#ifdef __AMIGA__\n"
        "\tBGP1_(\"gmap: datasets+init %u ms\", SDL_GetTicks() - gmT_); gmT_ = SDL_GetTicks();\n"
        "#endif\n"
        "\tRuleTerrain* ufoTerrain = 0;\n",
        "newbattle probe datasets")))

    results.append(("BattlescapeGenerator.cpp (newbattle probe script)", edit(
        os.path.join(src, "Battlescape", "BattlescapeGenerator.cpp"),
        "\tif (_blocksToDo)\n"
        "\t{\n"
        '\t\tthrow Exception("Map failed to fully generate.");\n'
        "\t}\n"
        "\n"
        "\tloadNodes();\n",
        "#ifdef __AMIGA__\n"
        "\tBGP1_(\"gmap: script %u ms\", SDL_GetTicks() - gmT_); gmT_ = SDL_GetTicks();\n"
        "#endif\n"
        "\tif (_blocksToDo)\n"
        "\t{\n"
        '\t\tthrow Exception("Map failed to fully generate.");\n'
        "\t}\n"
        "\n"
        "\tloadNodes();\n"
        "#ifdef __AMIGA__\n"
        "\tBGP1_(\"gmap: loadNodes %u ms\", SDL_GetTicks() - gmT_); gmT_ = SDL_GetTicks();\n"
        "#endif\n",
        "newbattle probe script")))

    results.append(("BattlescapeGenerator.cpp (newbattle probe tail)", edit(
        os.path.join(src, "Battlescape", "BattlescapeGenerator.cpp"),
        "\tattachNodeLinks();\n"
        "}\n",
        "#ifdef __AMIGA__\n"
        "\tBGP1_(\"gmap: ufo+craft+floors %u ms\", SDL_GetTicks() - gmT_); gmT_ = SDL_GetTicks();\n"
        "#endif\n"
        "\tattachNodeLinks();\n"
        "#ifdef __AMIGA__\n"
        "\tBGP1_(\"gmap: attachNodeLinks %u ms\", SDL_GetTicks() - gmT_);\n"
        "\tBGP1_(\"gmap: initMap+utils %u ms\", g_bgInit_);\n"
        "\t{ char bgb2_[128]; snprintf(bgb2_, sizeof bgb2_, \"gmap: loadMAP %u ms in %u files, loadRMP %u ms in %u files\",\n"
        "\t\tg_bgMap_, g_bgMapN_, g_bgRmp_, g_bgRmpN_); SDLmini_Log(bgb2_); }\n"
        "#endif\n"
        "}\n",
        "newbattle probe tail")))

    results.append(("BattlescapeGenerator.cpp (newbattle probe init)", edit(
        os.path.join(src, "Battlescape", "BattlescapeGenerator.cpp"),
        "\t_save->initMap(_mapsize_x, _mapsize_y, _mapsize_z);\n"
        "\t_save->initUtilities(_mod);\n"
        "}\n",
        "#ifdef __AMIGA__\n"
        "\tunsigned int inT_ = SDL_GetTicks();\n"
        "#endif\n"
        "\t_save->initMap(_mapsize_x, _mapsize_y, _mapsize_z);\n"
        "\t_save->initUtilities(_mod);\n"
        "#ifdef __AMIGA__\n"
        "\tg_bgInit_ += SDL_GetTicks() - inT_;\n"
        "#endif\n"
        "}\n",
        "newbattle probe init")))

    results.append(("BattlescapeGenerator.cpp (newbattle probe loadMAP)", edit(
        os.path.join(src, "Battlescape", "BattlescapeGenerator.cpp"),
        "\tint sizex, sizey, sizez;\n"
        "\tint x = xoff, y = yoff, z = 0;\n",
        "#ifdef __AMIGA__\n"
        "\tunsigned int lmT_ = SDL_GetTicks();\n"
        "#endif\n"
        "\tint sizex, sizey, sizez;\n"
        "\tint x = xoff, y = yoff, z = 0;\n",
        "newbattle probe loadMAP")))

    results.append(("BattlescapeGenerator.cpp (newbattle probe loadMAP end)", edit(
        os.path.join(src, "Battlescape", "BattlescapeGenerator.cpp"),
        "\treturn sizez;\n"
        "}\n",
        "#ifdef __AMIGA__\n"
        "\tg_bgMap_ += SDL_GetTicks() - lmT_; ++g_bgMapN_;\n"
        "#endif\n"
        "\treturn sizez;\n"
        "}\n",
        "newbattle probe loadMAP end")))

    results.append(("BattlescapeGenerator.cpp (newbattle probe loadRMP)", edit(
        os.path.join(src, "Battlescape", "BattlescapeGenerator.cpp"),
        "\tunsigned char value[24];\n",
        "#ifdef __AMIGA__\n"
        "\tunsigned int lrT_ = SDL_GetTicks();\n"
        "#endif\n"
        "\tunsigned char value[24];\n",
        "newbattle probe loadRMP")))

    results.append(("BattlescapeGenerator.cpp (newbattle probe loadRMP end)", edit(
        os.path.join(src, "Battlescape", "BattlescapeGenerator.cpp"),
        "\tmapFile.close();\n"
        "}\n",
        "\tmapFile.close();\n"
        "#ifdef __AMIGA__\n"
        "\tg_bgRmp_ += SDL_GetTicks() - lrT_; ++g_bgRmpN_;\n"
        "#endif\n"
        "}\n",
        "newbattle probe loadRMP end")))

    results.append(("NewBattleState.cpp (newbattle probe total)", edit(
        os.path.join(src, "Menu", "NewBattleState.cpp"),
        "\tbgen.run();\n"
        "\n"
        "\t_game->popState();\n",
        "#ifdef __AMIGA__\n"
        "\tunsigned int nbT_ = SDL_GetTicks();\n"
        "#endif\n"
        "\tbgen.run();\n"
        "#ifdef __AMIGA__\n"
        "\t{ char nbb_[96]; snprintf(nbb_, sizeof nbb_, \"newbattle: bgen.run %u ms\", SDL_GetTicks() - nbT_); SDLmini_Log(nbb_); }\n"
        "#endif\n"
        "\n"
        "\t_game->popState();\n",
        "newbattle probe total")))

    results.append(("NewBattleState.cpp (newbattle probe extern)", edit(
        os.path.join(src, "Menu", "NewBattleState.cpp"),
        '#include "NewBattleState.h"\n',
        '#include "NewBattleState.h"\n'
        '#ifdef __AMIGA__\n'
        '#include <cstdio>\n'
        'extern "C" void SDLmini_Log(const char *msg);\n'
        'extern "C" unsigned int SDL_GetTicks(void);\n'
        '#endif\n',
        "newbattle probe extern")))

    results.append(("SavedGame.cpp (save probe log)", edit(
        os.path.join(src, "Savegame", "SavedGame.cpp"),
        "\tout << node;\n"
        "\tsav << out.c_str();\n"
        "\tsav.close();\n"
        "}\n",
        "\tunsigned int svT1_ = SDL_GetTicks();\n"
        "\tAmigaYamlWrite(ydump_, node); /* AMIGA-PORT: no YAML::Emitter */\n"
        "\tif (_battleGame != 0) { ydump_ += \"battleGame:\\n\"; _battleGame->saveFastAmiga(ydump_); }\n"
        "\tunsigned int svT2_ = SDL_GetTicks();\n"
        "\tsav << ydump_;\n"
        "\tsav.close();\n"
        "\t{\n"
        "\t\tchar sb_[128];\n"
        "\t\tunsigned int svT3_ = SDL_GetTicks();\n"
        "\t\tsnprintf(sb_, sizeof sb_, \"save: build %u ms, emit %u ms, write %u ms, %lu bytes\",\n"
        "\t\t\tsvT1_ - svT0_, svT2_ - svT1_, svT3_ - svT2_, (unsigned long)ydump_.size());\n"
        "\t\tSDLmini_Log(sb_);\n"
        "\t}\n"
        "}\n",
        "save probe log")))
    results.append(("Options.cpp (optsave probe extern)", edit(
        os.path.join(src, "Engine", "Options.cpp"),
        '#include "Options.h"\n',
        '#include "Options.h"\n'
        '#ifdef __AMIGA__\n'
        '#include <cstdio>\n'
        '#include "amiga_yamlout.h"\n'
        'extern "C" void SDLmini_Log(const char *msg);\n'
        'extern "C" unsigned int SDL_GetTicks(void);\n'
        '#endif\n',
        "optsave probe extern")))
    results.append(("Options.cpp (optsave probe)", edit(
        os.path.join(src, "Engine", "Options.cpp"),
        "\t\tout << doc;\n"
        "\n"
        "\t\tsav << out.c_str();\n",
        "\t\tunsigned int ovT1_ = SDL_GetTicks(); /* TEMP optsave probe */\n"
        "\t\tstd::string ydump_; ydump_.reserve(32 * 1024);\n"
        "\t\tAmigaYamlWrite(ydump_, doc); /* AMIGA-PORT: no YAML::Emitter */\n"
        "\t\tunsigned int ovT2_ = SDL_GetTicks();\n"
        "\t\tsav << ydump_;\n"
        "\t\t{\n"
        "\t\t\tchar ob_[128];\n"
        "\t\t\tsnprintf(ob_, sizeof ob_, \"optsave: emit %u ms, write %u ms, %lu bytes\",\n"
        "\t\t\t\tovT2_ - ovT1_, SDL_GetTicks() - ovT2_, (unsigned long)ydump_.size());\n"
        "\t\t\tSDLmini_Log(ob_);\n"
        "\t\t}\n",
        "optsave probe")))

    # 6f. Direct battlescape save (LISTA pkt 3). Building the YAML::Node tree
    #     for battleGame was 85% of the 15 s save: every scalar costs several
    #     node allocations, pool merges and set inserts. These hand-written
    #     saveFastAmiga() methods append "key: value" text straight to the
    #     output string via amiga_yamlout.h - same YAML, same loader, no tree.
    #     Each mirrors its class's save() field by field.
    for hdr, why in (("Savegame/BattleUnit.h", "bu decl"), ("Savegame/BattleItem.h", "bi decl"),
                     ("Savegame/Node.h", "nd decl"), ("Savegame/SavedBattleGame.h", "sbg decl"),
                     ("Battlescape/AIModule.h", "ai decl")):
        extra = "\tvoid saveFastAmiga(std::string &out) const; /* AMIGA-PORT */\n" if "SavedBattleGame" in hdr else "\tvoid saveFastAmiga(std::string &out, int ind) const; /* AMIGA-PORT */\n"
        results.append((hdr + " (saveFastAmiga decl)", edit(
            os.path.join(src, *hdr.split("/")),
            "\tYAML::Node save() const;\n",
            "\tYAML::Node save() const;\n" + extra,
            why)))
    for cpp, hdrname in (("Savegame/BattleUnit.cpp", "BattleUnit.h"),
                         ("Savegame/BattleItem.cpp", "BattleItem.h"),
                         ("Savegame/Node.cpp", "Node.h"),
                         ("Savegame/SavedBattleGame.cpp", "SavedBattleGame.h"),
                         ("Battlescape/AIModule.cpp", "AIModule.h")):
        results.append((cpp + " (yamlout include)", edit(
            os.path.join(src, *cpp.split("/")),
            '#include "%s"\n' % hdrname,
            '#include "%s"\n#include "amiga_yamlout.h"\n' % hdrname,
            "yamlout include")))
    results.append(("BattleUnitStatistics.h (yamlout include)", edit(
        os.path.join(src, "Savegame", "BattleUnitStatistics.h"),
        '#include "../Engine/Language.h"\n',
        '#include "../Engine/Language.h"\n#include "amiga_yamlout.h"\n',
        "stats include")))

    results.append(("BattleUnitStatistics.h (kills saveFast)", edit(
        os.path.join(src, "Savegame", "BattleUnitStatistics.h"),
        '\t\tnode["id"] = id;\n\t\treturn node;\n\t}\n',
        '\t\tnode["id"] = id;\n\t\treturn node;\n\t}\n' + KILLS_FAST,
        "kills saveFast")))
    results.append(("BattleUnitStatistics.h (stats saveFast)", edit(
        os.path.join(src, "Savegame", "BattleUnitStatistics.h"),
        '\t\tif (slaveKills) node["slaveKills"] = slaveKills;\n\t\treturn node;\n\t}\n',
        '\t\tif (slaveKills) node["slaveKills"] = slaveKills;\n\t\treturn node;\n\t}\n' + STATS_FAST,
        "stats saveFast")))
    results.append(("AIModule.cpp (saveFast)", edit(
        os.path.join(src, "Battlescape", "AIModule.cpp"),
        '\tnode["wasHitBy"] = _wasHitBy;\n\treturn node;\n}\n',
        '\tnode["wasHitBy"] = _wasHitBy;\n\treturn node;\n}\n' + AI_FAST,
        "ai saveFast")))
    results.append(("Node.cpp (saveFast)", edit(
        os.path.join(src, "Savegame", "Node.cpp"),
        '\tnode["dummy"] = _dummy;\n\treturn node;\n}\n',
        '\tnode["dummy"] = _dummy;\n\treturn node;\n}\n' + NODE_FAST,
        "node saveFast")))
    results.append(("BattleItem.cpp (saveFast)", edit(
        os.path.join(src, "Savegame", "BattleItem.cpp"),
        '\t\tnode["droppedOnAlienTurn"] = _droppedOnAlienTurn;\n\n\treturn node;\n}\n',
        '\t\tnode["droppedOnAlienTurn"] = _droppedOnAlienTurn;\n\n\treturn node;\n}\n' + ITEM_FAST,
        "item saveFast")))
    results.append(("BattleUnit.cpp (saveFast)", edit(
        os.path.join(src, "Savegame", "BattleUnit.cpp"),
        '\tnode["mindControllerID"] = _mindControllerID;\n\n\treturn node;\n}\n',
        '\tnode["mindControllerID"] = _mindControllerID;\n\n\treturn node;\n}\n' + UNIT_FAST,
        "unit saveFast")))
    results.append(("SavedBattleGame.cpp (saveFast)", edit(
        os.path.join(src, "Savegame", "SavedBattleGame.cpp"),
        '\tnode["cheatTurn"] = _cheatTurn;\n\n\treturn node;\n}\n',
        '\tnode["cheatTurn"] = _cheatTurn;\n\n\treturn node;\n}\n' + SBG_FAST,
        "sbg saveFast")))
    results.append(("SavedGame.cpp (battleGame out of node)", edit(
        os.path.join(src, "Savegame", "SavedGame.cpp"),
        '\tif (_battleGame != 0)\n\t{\n\t\tnode["battleGame"] = _battleGame->save();\n\t}\n',
        '\t/* AMIGA-PORT: battleGame is appended after the node dump (saveFastAmiga) */\n',
        "battleGame out of node")))

    # 6g. TEMP load probes: where does loading a save hang/spend time.
    results.append(("SavedGame.cpp (load probe parse)", edit(
        os.path.join(src, "Savegame", "SavedGame.cpp"),
        "\tstd::vector<YAML::Node> file = YAML::LoadAllFromFile(s);\n",
        "\tunsigned int ldT0_ = SDL_GetTicks();\n"
        "\tstd::vector<YAML::Node> file = YAML::LoadAllFromFile(s);\n"
        "\t{ char lb_[96]; snprintf(lb_, sizeof lb_, \"load: parse %u ms\", SDL_GetTicks() - ldT0_); SDLmini_Log(lb_); }\n",
        "load probe parse")))
    results.append(("SavedBattleGame.cpp (load probes)", edit(
        os.path.join(src, "Savegame", "SavedBattleGame.cpp"),
        '#include "SavedBattleGame.h"\n#include "amiga_yamlout.h"\n',
        '#include "SavedBattleGame.h"\n#include "amiga_yamlout.h"\n'
        '#ifdef __AMIGA__\n'
        '#include <cstdio>\n'
        'extern "C" void SDLmini_Log(const char *msg);\n'
        'extern "C" unsigned int SDL_GetTicks(void);\n'
        '#define AMIGA_LP(tag) do { char lp_[64]; snprintf(lp_, sizeof lp_, "load: %s at %u ms", tag, SDL_GetTicks()); SDLmini_Log(lp_); } while (0)\n'
        '#else\n'
        '#define AMIGA_LP(tag)\n'
        '#endif\n',
        "sbg load probe macro")))
    results.append(("SavedBattleGame.cpp (probe battle start)", edit(
        os.path.join(src, "Savegame", "SavedBattleGame.cpp"),
        "\tint selectedUnit = node[\"selectedUnit\"].as<int>();\n",
        "\tAMIGA_LP(\"battle begin\");\n"
        "\tint selectedUnit = node[\"selectedUnit\"].as<int>();\n",
        "probe battle start")))
    results.append(("SavedBattleGame.cpp (probe tiles)", edit(
        os.path.join(src, "Savegame", "SavedBattleGame.cpp"),
        "\t\tYAML::Binary binTiles = node[\"binTiles\"].as<YAML::Binary>();\n",
        "\t\tAMIGA_LP(\"binTiles decode\");\n"
        "\t\tYAML::Binary binTiles = node[\"binTiles\"].as<YAML::Binary>();\n"
        "\t\tAMIGA_LP(\"binTiles decoded\");\n",
        "probe tiles")))
    results.append(("SavedBattleGame.cpp (probe nodes)", edit(
        os.path.join(src, "Savegame", "SavedBattleGame.cpp"),
        "\tfor (YAML::const_iterator i = node[\"nodes\"].begin(); i != node[\"nodes\"].end(); ++i)\n",
        "\tAMIGA_LP(\"nodes\");\n"
        "\tfor (YAML::const_iterator i = node[\"nodes\"].begin(); i != node[\"nodes\"].end(); ++i)\n",
        "probe nodes")))
    results.append(("SavedBattleGame.cpp (probe units)", edit(
        os.path.join(src, "Savegame", "SavedBattleGame.cpp"),
        "\tfor (YAML::const_iterator i = node[\"units\"].begin(); i != node[\"units\"].end(); ++i)\n",
        "\tAMIGA_LP(\"units\");\n"
        "\tfor (YAML::const_iterator i = node[\"units\"].begin(); i != node[\"units\"].end(); ++i)\n",
        "probe units")))
    results.append(("SavedBattleGame.cpp (probe items)", edit(
        os.path.join(src, "Savegame", "SavedBattleGame.cpp"),
        "\tstd::string fromContainer[3] = { \"items\", \"recoverConditional\", \"recoverGuaranteed\" };\n",
        "\tAMIGA_LP(\"items\");\n"
        "\tstd::string fromContainer[3] = { \"items\", \"recoverConditional\", \"recoverGuaranteed\" };\n",
        "probe items")))
    results.append(("SavedBattleGame.cpp (probe ammo)", edit(
        os.path.join(src, "Savegame", "SavedBattleGame.cpp"),
        "\tstd::vector<BattleItem*>::iterator weaponi = _items.begin();\n",
        "\tAMIGA_LP(\"ammo tie\");\n"
        "\tstd::vector<BattleItem*>::iterator weaponi = _items.begin();\n",
        "probe ammo")))

    # 6h. TEMP probes: the 44 s tail after battle load (loadMapResources etc).
    results.append(("SavedBattleGame.cpp (probe mapres)", edit(
        os.path.join(src, "Savegame", "SavedBattleGame.cpp"),
        "void SavedBattleGame::loadMapResources(Mod *mod)\n{\n",
        "void SavedBattleGame::loadMapResources(Mod *mod)\n{\n"
        "\tAMIGA_LP(\"mapres begin\");\n",
        "probe mapres")))
    results.append(("SavedBattleGame.cpp (probe mapres mid)", edit(
        os.path.join(src, "Savegame", "SavedBattleGame.cpp"),
        "\tint mdsID, mdID;\n",
        "\tAMIGA_LP(\"mapres mcd loaded\");\n"
        "\tint mdsID, mdID;\n",
        "probe mapres mid")))
    results.append(("LoadGameState.cpp (probe around mapres)", edit(
        os.path.join(src, "Menu", "LoadGameState.cpp"),
        "\t\t\t\t\t_game->getSavedGame()->getSavedBattle()->loadMapResources(_game->getMod());\n",
        "\t\t\t\t\t_game->getSavedGame()->getSavedBattle()->loadMapResources(_game->getMod());\n"
        "#ifdef __AMIGA__\n"
        "\t\t\t\t\t{ char pb_[64]; snprintf(pb_, sizeof pb_, \"load: mapres done at %u ms\", SDL_GetTicks()); SDLmini_Log(pb_); }\n"
        "#endif\n",
        "probe load mapres done")))
    results.append(("LoadGameState.cpp (probe extern)", edit(
        os.path.join(src, "Menu", "LoadGameState.cpp"),
        '#include "LoadGameState.h"\n',
        '#include "LoadGameState.h"\n'
        '#ifdef __AMIGA__\n'
        '#include <cstdio>\n'
        'extern "C" void SDLmini_Log(const char *msg);\n'
        'extern "C" unsigned int SDL_GetTicks(void);\n'
        '#endif\n',
        "probe lgs extern")))

    # 6i. TEMP probes: what inside "new GeoscapeState" costs 33 s on 040/40.
    results.append(("GeoscapeState.cpp (probe extern)", edit(
        os.path.join(src, "Geoscape", "GeoscapeState.cpp"),
        '#include "GeoscapeState.h"\n',
        '#include "GeoscapeState.h"\n'
        '#ifdef __AMIGA__\n'
        '#include <cstdio>\n'
        'extern "C" void SDLmini_Log(const char *msg);\n'
        'extern "C" unsigned int SDL_GetTicks(void);\n'
        '#define AMIGA_GP(tag) do { char gp_[64]; snprintf(gp_, sizeof gp_, "geo: %s at %u ms", tag, SDL_GetTicks()); SDLmini_Log(gp_); } while (0)\n'
        '#endif\n',
        "geo probe extern")))
    results.append(("GeoscapeState.cpp (ctor probes)", edit(
        os.path.join(src, "Geoscape", "GeoscapeState.cpp"),
        "\tint screenWidth = Options::baseXGeoscape;\n",
        "\tAMIGA_GP(\"ctor begin\");\n"
        "\tint screenWidth = Options::baseXGeoscape;\n",
        "geo ctor probe")))
    results.append(("GeoscapeState.cpp (globe made probe)", edit(
        os.path.join(src, "Geoscape", "GeoscapeState.cpp"),
        "\t_globe = new Globe(_game, (screenWidth-64)/2, screenHeight/2, screenWidth-64, screenHeight, 0, 0);\n",
        "\tAMIGA_GP(\"globe ctor begin\");\n"
        "\t_globe = new Globe(_game, (screenWidth-64)/2, screenHeight/2, screenWidth-64, screenHeight, 0, 0);\n"
        "\tAMIGA_GP(\"globe ctor end\");\n",
        "globe ctor probe")))
    results.append(("GeoscapeState.cpp (ctor end probe)", edit(
        os.path.join(src, "Geoscape", "GeoscapeState.cpp"),
        "\ttimeDisplay();\n}\n",
        "\ttimeDisplay();\n"
        "\tAMIGA_GP(\"ctor end\");\n"
        "}\n",
        "geo ctor end probe")))

    # 6j. Dogfight zoom in ONE step (user: reaching a fight took 30-60 s).
    #     The smooth effect changes the radius ~10 times and every change
    #     recomputes the whole globe geometry (cachePolygons, ~3 s on the
    #     -70% 040/40). One jump = one recompute.
    results.append(("Globe.cpp (dogfight zoom in jump)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        "bool Globe::zoomDogfightIn()\n{\n",
        "bool Globe::zoomDogfightIn()\n{\n"
        "#ifdef __AMIGA__\n"
        "\t/* AMIGA-PORT: jump straight to dogfight zoom - see patch script. */\n"
        "\tif (_zoom < DOGFIGHT_ZOOM) setZoom(DOGFIGHT_ZOOM);\n"
        "\treturn true;\n"
        "#endif\n",
        "dogfight zoom jump")))
    results.append(("Globe.cpp (dogfight zoom out jump)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        "bool Globe::zoomDogfightOut()\n{\n",
        "bool Globe::zoomDogfightOut()\n{\n"
        "#ifdef __AMIGA__\n"
        "\t/* AMIGA-PORT: jump straight back - see zoomDogfightIn. */\n"
        "\tif (_zoom > _zoomOld) setZoom(_zoomOld);\n"
        "\treturn true;\n"
        "#endif\n",
        "dogfight zoom out jump")))

    # 6k. cachePolygons without per-vertex trig (user: rotation/zoom ~3 s,
    #     dogfight approach 30-60 s). Vertex sin/cos precomputed once; each
    #     recache does 4 trig calls total plus multiplies. See body comment.
    results.append(("Globe.cpp (vertex trig table)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        GLOBE_CACHE_OLD,
        GLOBE_CACHE_NEW,
        "vertex trig table")))

    # 6l. Hover radar circles: one circle per DISTINCT range, not one per
    #     facility TYPE (~15 identical circles of 48 trig-heavy segments each
    #     made base placement cost ~700 ms per globe redraw).
    results.append(("Globe.cpp (hover ranges dedup)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        "\t\tconst std::vector<std::string> &facilities = _game->getMod()->getBaseFacilitiesList();\n"
        "\t\tfor (std::vector<std::string>::const_iterator i = facilities.begin(); i != facilities.end(); ++i)\n"
        "\t\t{\n"
        "\t\t\trange=_game->getMod()->getBaseFacility(*i)->getRadarRange();\n"
        "\t\t\trange = range * (1 / 60.0) * (M_PI / 180);\n"
        "\t\t\tdrawGlobeCircle(_hoverLat,_hoverLon,range,48);\n"
        "\t\t\tif (Options::globeAllRadarsOnBaseBuild) ranges.push_back(range);\n"
        "\t\t}\n",
        "\t\t/* AMIGA-PORT: draw each DISTINCT radar range once - facility types\n"
        "\t\t * share ranges, and every circle is 48 trig-heavy segments. */\n"
        "\t\tconst std::vector<std::string> &facilities = _game->getMod()->getBaseFacilitiesList();\n"
        "\t\tstd::vector<double> seen_;\n"
        "\t\tfor (std::vector<std::string>::const_iterator i = facilities.begin(); i != facilities.end(); ++i)\n"
        "\t\t{\n"
        "\t\t\trange=_game->getMod()->getBaseFacility(*i)->getRadarRange();\n"
        "\t\t\trange = range * (1 / 60.0) * (M_PI / 180);\n"
        "\t\t\tbool dup_ = false;\n"
        "\t\t\tfor (size_t k_ = 0; k_ < seen_.size(); ++k_) if (seen_[k_] == range) { dup_ = true; break; }\n"
        "\t\t\tif (dup_) continue;\n"
        "\t\t\tseen_.push_back(range);\n"
        "\t\t\tdrawGlobeCircle(_hoverLat,_hoverLon,range,48);\n"
        "\t\t\tif (Options::globeAllRadarsOnBaseBuild) ranges.push_back(range);\n"
        "\t\t}\n",
        "hover ranges dedup")))

    results.append(("Globe.cpp (cstdio include)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        '#include "Globe.h"\n',
        '#include "Globe.h"\n#include <cstdio>\n',
        "globe cstdio")))

    # 6m. Flat sun-shaded land polygons (LISTA 2d; option amigaFlatGlobe,
    #     default ON for evaluation - set 0 in options.cfg to get the old
    #     textured land back, no rebuild needed). Colour = dominant colour of
    #     the polygon's texture tile; shade = polygon normal (dot) sun in
    #     Q1.14, so facing-the-sun land is lighter and grazing land darker;
    #     the per-pixel night terminator still comes from drawShadow.
    results.append(("Globe.cpp (cstring include)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        '#include "Globe.h"\n#include <cstdio>\n',
        '#include "Globe.h"\n#include <cstdio>\n#include <cstring>\n',
        "globe cstring")))
    results.append(("Globe.cpp (flat land)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        GLOBE_LAND_OLD,
        GLOBE_LAND_NEW,
        "flat land")))

    # 6n. Radar circles and country lines without per-step doubles (pkt 3).
    #     drawGlobeCircle ran asin/atan2/sin/cos per SEGMENT (~250 trig per
    #     circle); the vector form needs 12 per circle. XuLine stepped in
    #     doubles; it walks in 16.16 fixed point now.
    results.append(("Globe.cpp (vector circles)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        GLOBE_CIRCLE_OLD,
        GLOBE_CIRCLE_NEW,
        "vector circles")))
    results.append(("Globe.cpp (fixed-point XuLine)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        GLOBE_XULINE_OLD,
        GLOBE_XULINE_NEW,
        "fixed-point XuLine")))

    # 6o. Port credit, small font, bottom-left of the title screen.
    results.append(("MainMenuState.cpp (port credit)", edit(
        os.path.join(src, "Menu", "MainMenuState.cpp"),
        "\tadd(_txtTitle, \"text\", \"mainMenu\");\n",
        "\tadd(_txtTitle, \"text\", \"mainMenu\");\n"
        "\t{\n"
        "\t\tText *txtPort_ = new Text(200, 9, 2, 191); /* AMIGA-PORT credit */\n"
        "\t\tadd(txtPort_, \"text\", \"mainMenu\");\n"
        "\t\ttxtPort_->setSmall();\n"
        "\t\ttxtPort_->setText(Language::utf8ToWstr(\"PORT MADE BY GRZEGORZ KORYCKI\"));\n"
        "\t}\n",
        "port credit")))

    # 6p. Loading-splash progress (native/amiga_splash.c). The splash shows
    #     itself when the screen opens (sdlmini); the game only feeds the bar:
    #     one tick per ruleset file (3..85%), milestone marks for the later
    #     phases, and the finish call (fade to black, hand back the display).
    results.append(("Mod.cpp (splash decls)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        '#include "Mod.h"\n',
        '#include "Mod.h"\n'
        '#ifdef __AMIGA__\n'
        'extern "C" void AmigaSplash_Progress(int percent);\n'
        'static long AmigaSplashDone_ = 0, AmigaSplashTotal_ = 0;\n'
        '#endif\n',
        "splash decls")))
    results.append(("Mod.cpp (splash total)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\tfor (size_t i = 0; mods.size() > i; ++i)\n"
        "\t{\n"
        "\t\ttry\n"
        "\t\t{\n"
        "\t\t\tloadMod(mods[i].second, i);\n",
        "#ifdef __AMIGA__\n"
        "\tAmigaSplashDone_ = 0;\n"
        "\tAmigaSplashTotal_ = 0;\n"
        "\tfor (size_t i = 0; mods.size() > i; ++i)\n"
        "\t\tAmigaSplashTotal_ += (long)mods[i].second.size();\n"
        "\tif (AmigaSplashTotal_ < 1) AmigaSplashTotal_ = 1;\n"
        "#endif\n"
        "\tfor (size_t i = 0; mods.size() > i; ++i)\n"
        "\t{\n"
        "\t\ttry\n"
        "\t\t{\n"
        "\t\t\tloadMod(mods[i].second, i);\n",
        "splash total")))
    results.append(("Mod.cpp (splash tick)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t\tcatch (YAML::Exception &e)\n"
        "\t\t{\n"
        "\t\t\tthrow Exception((*i) + \": \" + std::string(e.what()));\n"
        "\t\t}\n"
        "\t}\n",
        "\t\tcatch (YAML::Exception &e)\n"
        "\t\t{\n"
        "\t\t\tthrow Exception((*i) + \": \" + std::string(e.what()));\n"
        "\t\t}\n"
        "#ifdef __AMIGA__\n"
        "\t\t++AmigaSplashDone_;\n"
        "\t\tAmigaSplash_Progress(5 + (int)((32L * AmigaSplashDone_) / AmigaSplashTotal_));\n"
        "#endif\n"
        "\t}\n",
        "splash tick")))
    results.append(("Mod.cpp (splash fonts mark)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        '\tLog(LOG_INFO) << "Loading fonts... " << _fontName;\n',
        '\tLog(LOG_INFO) << "Loading fonts... " << _fontName;\n'
        '#ifdef __AMIGA__\n'
        '\tAmigaSplash_Progress(80);\n'
        '#endif\n',
        "splash fonts mark")))
    results.append(("StartState.cpp (splash decls)", edit(
        os.path.join(src, "Menu", "StartState.cpp"),
        '#include "StartState.h"\n',
        '#include "StartState.h"\n'
        '#ifdef __AMIGA__\n'
        'extern "C" void AmigaSplash_Progress(int percent);\n'
        'extern "C" void SDLmini_SplashFinish(void);\n'
        'extern "C" void (*YamlTickHook)(unsigned long);\n'
        'extern "C" unsigned long YamlTickCount;\n'
        'static unsigned long amigaLangBase_ = 0;\n'
        'static void amigaLangTick_(unsigned long n)\n'
        '{\n'
        '\tint p = 89 + (int)((n - amigaLangBase_) / 40000UL);\n'
        '\tif (p > 98) p = 98;\n'
        '\tAmigaSplash_Progress(p);\n'
        '}\n'
        '#endif\n',
        "start splash decls")))
    results.append(("StartState.cpp (splash lang mark)", edit(
        os.path.join(src, "Menu", "StartState.cpp"),
        '\t\tLog(LOG_INFO) << "Loading language...";\n',
        '#ifdef __AMIGA__\n'
        '\t\tAmigaSplash_Progress(89);\n'
        '#endif\n'
        '\t\tLog(LOG_INFO) << "Loading language...";\n',
        "splash lang mark")))
    results.append(("StartState.cpp (splash finish)", edit(
        os.path.join(src, "Menu", "StartState.cpp"),
        '\t\tLog(LOG_INFO) << "OpenXcom started successfully!";\n'
        "\t\t_game->setState(new GoToMainMenuState);\n",
        '\t\tLog(LOG_INFO) << "OpenXcom started successfully!";\n'
        "#ifdef __AMIGA__\n"
        "\t\tSDLmini_SplashFinish();\n"
        "#endif\n"
        "\t\t_game->setState(new GoToMainMenuState);\n",
        "splash finish")))

    # 6q. Splash bar rebalance: measured phases on the 040/40 - rulesets
    #     ~120 s, fonts ~7 s, extra sprites/sounds ~13 s, language ~18 s.
    #     Rulesets 2..70, fonts 71, sprites 72..80 (per pack), sounds 80..86
    #     (per pack), data-loaded 87, language 88 -> 98, done 100.
    results.append(("Mod.cpp (splash sprites ticks)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\tfor (std::vector< std::pair<std::string, ExtraSprites *> >::const_iterator i = _extraSprites.begin(); i != _extraSprites.end(); ++i)\n"
        "\t{\n"
        "\t\tstd::string sheetName = i->first;\n",
        "#ifdef __AMIGA__\n"
        "\tAmigaSplashDone_ = 0;\n"
        "\tAmigaSplashTotal_ = (long)_extraSprites.size(); if (AmigaSplashTotal_ < 1) AmigaSplashTotal_ = 1;\n"
        "#endif\n"
        "\tfor (std::vector< std::pair<std::string, ExtraSprites *> >::const_iterator i = _extraSprites.begin(); i != _extraSprites.end(); ++i)\n"
        "\t{\n"
        "#ifdef __AMIGA__\n"
        "\t\t++AmigaSplashDone_;\n"
        "\t\tAmigaSplash_Progress(81 + (int)((4L * AmigaSplashDone_) / AmigaSplashTotal_));\n"
        "#endif\n"
        "\t\tstd::string sheetName = i->first;\n",
        "splash sprites ticks")))
    results.append(("Mod.cpp (splash sounds ticks)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\tfor (std::vector< std::pair<std::string, ExtraSounds *> >::const_iterator i = _extraSounds.begin(); i != _extraSounds.end(); ++i)\n"
        "\t{\n"
        "\t\tstd::string setName = i->first;\n",
        "#ifdef __AMIGA__\n"
        "\tAmigaSplashDone_ = 0;\n"
        "\tAmigaSplashTotal_ = (long)_extraSounds.size(); if (AmigaSplashTotal_ < 1) AmigaSplashTotal_ = 1;\n"
        "#endif\n"
        "\tfor (std::vector< std::pair<std::string, ExtraSounds *> >::const_iterator i = _extraSounds.begin(); i != _extraSounds.end(); ++i)\n"
        "\t{\n"
        "#ifdef __AMIGA__\n"
        "\t\t++AmigaSplashDone_;\n"
        "\t\tAmigaSplash_Progress(85 + (int)((3L * AmigaSplashDone_) / AmigaSplashTotal_));\n"
        "#endif\n"
        "\t\tstd::string setName = i->first;\n",
        "splash sounds ticks")))
    results.append(("StartState.cpp (splash data mark)", edit(
        os.path.join(src, "Menu", "StartState.cpp"),
        '\t\tLog(LOG_INFO) << "Data loaded successfully.";\n',
        '#ifdef __AMIGA__\n'
        '\t\tAmigaSplash_Progress(89);\n'
        '#endif\n'
        '\t\tLog(LOG_INFO) << "Data loaded successfully.";\n',
        "splash data mark")))
    results.append(("StartState.cpp (splash lang done)", edit(
        os.path.join(src, "Menu", "StartState.cpp"),
        "\t\tgame->defaultLanguage();\n",
        "#ifdef __AMIGA__\n"
        "\t\tamigaLangBase_ = YamlTickCount;\n"
        "\t\tYamlTickHook = amigaLangTick_;\n"
        "#endif\n"
        "\t\tgame->defaultLanguage();\n"
        "#ifdef __AMIGA__\n"
        "\t\tYamlTickHook = 0;\n"
        "\t\tAmigaSplash_Progress(99);\n"
        "#endif\n",
        "splash lang done")))

    # 6r. sortLists is the measured 80 s block (9 std::sorts comparing rules
    #     through string-map lookups). One tick before each sort spreads the
    #     37..79% span; validation gets its own mark at 38.
    results.append(("Mod.cpp (splash sort ticks)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "void Mod::sortLists()\n{\n"
        "\tstd::sort(_itemsIndex.begin(), _itemsIndex.end(), compareRule<RuleItem>(this, (compareRule<RuleItem>::RuleLookup)&Mod::getItem));\n"
        "\tstd::sort(_craftsIndex.begin(), _craftsIndex.end(), compareRule<RuleCraft>(this, (compareRule<RuleCraft>::RuleLookup)&Mod::getCraft));\n"
        "\tstd::sort(_facilitiesIndex.begin(), _facilitiesIndex.end(), compareRule<RuleBaseFacility>(this, (compareRule<RuleBaseFacility>::RuleLookup)&Mod::getBaseFacility));\n"
        "\tstd::sort(_researchIndex.begin(), _researchIndex.end(), compareRule<RuleResearch>(this, (compareRule<RuleResearch>::RuleLookup)&Mod::getResearch));\n"
        "\tstd::sort(_manufactureIndex.begin(), _manufactureIndex.end(), compareRule<RuleManufacture>(this, (compareRule<RuleManufacture>::RuleLookup)&Mod::getManufacture));\n"
        "\tstd::sort(_invsIndex.begin(), _invsIndex.end(), compareRule<RuleInventory>(this, (compareRule<RuleInventory>::RuleLookup)&Mod::getInventory));\n"
        "\t// special cases\n"
        "\tstd::sort(_craftWeaponsIndex.begin(), _craftWeaponsIndex.end(), compareRule<RuleCraftWeapon>(this));\n"
        "\tstd::sort(_armorsIndex.begin(), _armorsIndex.end(), compareRule<Armor>(this));\n"
        "\tstd::sort(_ufopaediaIndex.begin(), _ufopaediaIndex.end(), compareRule<ArticleDefinition>(this));\n"
        "}\n",
        "void Mod::sortLists()\n{\n"
        "#define AMIGA_SP(x) AmigaSplash_Progress(x);\n"
        "\tAMIGA_SP(77)\n"
        "\tstd::sort(_itemsIndex.begin(), _itemsIndex.end(), compareRule<RuleItem>(this, (compareRule<RuleItem>::RuleLookup)&Mod::getItem));\n"
        "\tAMIGA_SP(77)\n"
        "\tstd::sort(_craftsIndex.begin(), _craftsIndex.end(), compareRule<RuleCraft>(this, (compareRule<RuleCraft>::RuleLookup)&Mod::getCraft));\n"
        "\tAMIGA_SP(77)\n"
        "\tstd::sort(_facilitiesIndex.begin(), _facilitiesIndex.end(), compareRule<RuleBaseFacility>(this, (compareRule<RuleBaseFacility>::RuleLookup)&Mod::getBaseFacility));\n"
        "\tAMIGA_SP(77)\n"
        "\tstd::sort(_researchIndex.begin(), _researchIndex.end(), compareRule<RuleResearch>(this, (compareRule<RuleResearch>::RuleLookup)&Mod::getResearch));\n"
        "\tAMIGA_SP(77)\n"
        "\tstd::sort(_manufactureIndex.begin(), _manufactureIndex.end(), compareRule<RuleManufacture>(this, (compareRule<RuleManufacture>::RuleLookup)&Mod::getManufacture));\n"
        "\tAMIGA_SP(77)\n"
        "\tstd::sort(_invsIndex.begin(), _invsIndex.end(), compareRule<RuleInventory>(this, (compareRule<RuleInventory>::RuleLookup)&Mod::getInventory));\n"
        "\t// special cases\n"
        "\tAMIGA_SP(77)\n"
        "\tstd::sort(_craftWeaponsIndex.begin(), _craftWeaponsIndex.end(), compareRule<RuleCraftWeapon>(this));\n"
        "\tAMIGA_SP(78)\n"
        "\tstd::sort(_armorsIndex.begin(), _armorsIndex.end(), compareRule<Armor>(this));\n"
        "\tAMIGA_SP(79)\n"
        "\tstd::sort(_ufopaediaIndex.begin(), _ufopaediaIndex.end(), compareRule<ArticleDefinition>(this));\n"
        "#undef AMIGA_SP\n"
        "}\n",
        "splash sort ticks")))
    results.append(("Mod.cpp (splash validation mark)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t// these need to be validated, otherwise we\'re gonna get into some serious trouble down the line.\n",
        "#ifdef __AMIGA__\n"
        "\tAmigaSplash_Progress(38);\n"
        "#endif\n"
        "\t// these need to be validated, otherwise we\'re gonna get into some serious trouble down the line.\n",
        "splash validation mark")))

    # 6s. TEMP: narrow the 74 s between mark 38 and sortLists.
    results.append(("Mod.cpp (splash val fine 39)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t// instead of passing a pointer to the region load function",
        "#ifdef __AMIGA__\n"
        "\tAmigaSplash_Progress(39);\n"
        "#endif\n"
        "\t// instead of passing a pointer to the region load function",
        "splash val fine 39")))
    results.append(("Mod.cpp (splash val fine 41)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\tsortLists();\n"
        "\tloadExtraResources();\n",
        "#ifdef __AMIGA__\n"
        "\tAmigaSplash_Progress(41);\n"
        "#endif\n"
        "\tsortLists();\n"
        "\tloadExtraResources();\n",
        "splash val fine 41")))

    # 6t. The measured 72 s block is the REGION sanitation loop in loadMod
    #     (~5.5 s per region - why so slow is a separate question, noted in
    #     LISTA-ROBOT). One tick per region spreads 39..76.
    results.append(("Mod.cpp (splash region tick)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\tfor (std::map<std::string, RuleRegion*>::iterator i = _regions.begin(); i != _regions.end(); ++i)\n"
        "\t{\n"
        "\t\t// bleh, make copies, const correctness kinda screwed me here.\n",
        "#ifdef __AMIGA__\n"
        "\tAmigaSplashDone_ = 0;\n"
        "\tAmigaSplashTotal_ = (long)_regions.size(); if (AmigaSplashTotal_ < 1) AmigaSplashTotal_ = 1;\n"
        "#endif\n"
        "\tfor (std::map<std::string, RuleRegion*>::iterator i = _regions.begin(); i != _regions.end(); ++i)\n"
        "\t{\n"
        "#ifdef __AMIGA__\n"
        "\t\t++AmigaSplashDone_;\n"
        "\t\tAmigaSplash_Progress(39);\n"
        "#endif\n"
        "\t\t// bleh, make copies, const correctness kinda screwed me here.\n",
        "splash region tick")))

    # 6u. loadVanillaResources IS the measured 72 s (vanilla screens, PCK
    #     sets and the TFTD sound CATs). Per-file ticks across 40..76.
    results.append(("Mod.cpp (vanilla ticks scr)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        '\tstd::set<std::string> scrs = FileMap::filterFiles(geographFiles, "SCR");\n'
        "\tfor (std::set<std::string>::iterator i = scrs.begin(); i != scrs.end(); ++i)\n"
        "\t{\n",
        '\tstd::set<std::string> scrs = FileMap::filterFiles(geographFiles, "SCR");\n'
        "#ifdef __AMIGA__\n"
        "\tAmigaSplashDone_ = 0; AmigaSplashTotal_ = (long)scrs.size(); if (AmigaSplashTotal_ < 1) AmigaSplashTotal_ = 1;\n"
        "#endif\n"
        "\tfor (std::set<std::string>::iterator i = scrs.begin(); i != scrs.end(); ++i)\n"
        "\t{\n"
        "#ifdef __AMIGA__\n"
        "\t\t++AmigaSplashDone_; AmigaSplash_Progress(40 + (int)((6L * AmigaSplashDone_) / AmigaSplashTotal_));\n"
        "#endif\n",
        "vanilla ticks scr")))
    results.append(("Mod.cpp (vanilla ticks bdy)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        '\tstd::set<std::string> bdys = FileMap::filterFiles(geographFiles, "BDY");\n'
        "\tfor (std::set<std::string>::iterator i = bdys.begin(); i != bdys.end(); ++i)\n"
        "\t{\n",
        '\tstd::set<std::string> bdys = FileMap::filterFiles(geographFiles, "BDY");\n'
        "#ifdef __AMIGA__\n"
        "\tAmigaSplashDone_ = 0; AmigaSplashTotal_ = (long)bdys.size(); if (AmigaSplashTotal_ < 1) AmigaSplashTotal_ = 1;\n"
        "#endif\n"
        "\tfor (std::set<std::string>::iterator i = bdys.begin(); i != bdys.end(); ++i)\n"
        "\t{\n"
        "#ifdef __AMIGA__\n"
        "\t\t++AmigaSplashDone_; AmigaSplash_Progress(46 + (int)((4L * AmigaSplashDone_) / AmigaSplashTotal_));\n"
        "#endif\n",
        "vanilla ticks bdy")))
    results.append(("Mod.cpp (vanilla ticks spk)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        '\tstd::set<std::string> spks = FileMap::filterFiles(geographFiles, "SPK");\n'
        "\tfor (std::set<std::string>::iterator i = spks.begin(); i != spks.end(); ++i)\n"
        "\t{\n",
        '\tstd::set<std::string> spks = FileMap::filterFiles(geographFiles, "SPK");\n'
        "#ifdef __AMIGA__\n"
        "\tAmigaSplashDone_ = 0; AmigaSplashTotal_ = (long)spks.size(); if (AmigaSplashTotal_ < 1) AmigaSplashTotal_ = 1;\n"
        "#endif\n"
        "\tfor (std::set<std::string>::iterator i = spks.begin(); i != spks.end(); ++i)\n"
        "\t{\n"
        "#ifdef __AMIGA__\n"
        "\t\t++AmigaSplashDone_; AmigaSplash_Progress(50 + (int)((7L * AmigaSplashDone_) / AmigaSplashTotal_));\n"
        "#endif\n",
        "vanilla ticks spk")))
    results.append(("Mod.cpp (vanilla mark sets)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t// Load surface sets\n",
        "#ifdef __AMIGA__\n"
        "\tAmigaSplash_Progress(58);\n"
        "#endif\n"
        "\t// Load surface sets\n",
        "vanilla mark sets")))
    results.append(("Mod.cpp (vanilla ticks sounds)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t\t\tfor (std::map<std::string, SoundDefinition*>::const_iterator i = _soundDefs.begin(); i != _soundDefs.end(); ++i)\n"
        "\t\t\t{\n"
        "\t\t\t\tstd::string fname = i->second->getCATFile();\n",
        "#ifdef __AMIGA__\n"
        "\t\t\tAmigaSplashDone_ = 0; AmigaSplashTotal_ = (long)_soundDefs.size(); if (AmigaSplashTotal_ < 1) AmigaSplashTotal_ = 1;\n"
        "#endif\n"
        "\t\t\tfor (std::map<std::string, SoundDefinition*>::const_iterator i = _soundDefs.begin(); i != _soundDefs.end(); ++i)\n"
        "\t\t\t{\n"
        "#ifdef __AMIGA__\n"
        "\t\t\t\t++AmigaSplashDone_; AmigaSplash_Progress(59 + (int)((11L * AmigaSplashDone_) / AmigaSplashTotal_));\n"
        "#endif\n"
        "\t\t\t\tstd::string fname = i->second->getCATFile();\n",
        "vanilla ticks sounds")))

    # 6v. loadBattlescapeResources (UNITS/TERRAIN PCKs) is the remaining
    #     36 s block: mark at entry, per-file ticks over the units sets.
    results.append(("Mod.cpp (battlescape res ticks)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        '\t// Load Battlescape ICONS\n'
        '\t_sets["SPICONS.DAT"] = new SurfaceSet(32, 24);\n',
        '#ifdef __AMIGA__\n'
        '\tAmigaSplash_Progress(71);\n'
        '#endif\n'
        '\t// Load Battlescape ICONS\n'
        '\t_sets["SPICONS.DAT"] = new SurfaceSet(32, 24);\n',
        "battlescape res ticks")))
    results.append(("Mod.cpp (battlescape usets ticks)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        '\tstd::set<std::string> usets = FileMap::filterFiles(unitsContents, "PCK");\n'
        "\tfor (std::set<std::string>::iterator i = usets.begin(); i != usets.end(); ++i)\n"
        "\t{\n",
        '\tstd::set<std::string> usets = FileMap::filterFiles(unitsContents, "PCK");\n'
        "#ifdef __AMIGA__\n"
        "\tAmigaSplashDone_ = 0; AmigaSplashTotal_ = (long)usets.size(); if (AmigaSplashTotal_ < 1) AmigaSplashTotal_ = 1;\n"
        "#endif\n"
        "\tfor (std::set<std::string>::iterator i = usets.begin(); i != usets.end(); ++i)\n"
        "\t{\n"
        "#ifdef __AMIGA__\n"
        "\t\t++AmigaSplashDone_; AmigaSplash_Progress(71 + (int)((5L * AmigaSplashDone_) / AmigaSplashTotal_));\n"
        "#endif\n",
        "battlescape usets ticks")))
    results.append(("Mod.cpp (battlescape bdys ticks)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        '\tstd::set<std::string> bdys = FileMap::filterFiles(ufographContents, "BDY");\n'
        "\tfor (std::set<std::string>::iterator i = bdys.begin(); i != bdys.end(); ++i)\n"
        "\t{\n",
        '\tstd::set<std::string> bdys = FileMap::filterFiles(ufographContents, "BDY");\n'
        "#ifdef __AMIGA__\n"
        "\tAmigaSplashDone_ = 0; AmigaSplashTotal_ = (long)bdys.size(); if (AmigaSplashTotal_ < 1) AmigaSplashTotal_ = 1;\n"
        "#endif\n"
        "\tfor (std::set<std::string>::iterator i = bdys.begin(); i != bdys.end(); ++i)\n"
        "\t{\n"
        "#ifdef __AMIGA__\n"
        "\t\t++AmigaSplashDone_; AmigaSplash_Progress(76 + (int)((1L * AmigaSplashDone_) / AmigaSplashTotal_));\n"
        "#endif\n",
        "battlescape bdys ticks")))

    # 5x. Globe blit diagnostics (temporary): the globe draws (first
    #     filledCircle/texturedPolygon are logged by sdlmini) but the screen
    #     stays black where it should be. Count non-zero pixels in the globe
    #     surface and in the screen after the blit, once.
    results.append(("Geoscape/Globe.cpp (marker include)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        "#include \"Globe.h\"\n",
        "#include \"Globe.h\"\n"
        "#ifdef __AMIGA__\n"
        "#include \"amiga_startup.h\"\n"
        "#include <cstdio>\n"
        "extern \"C\" int SDLmini_diag_armed;\n"
        "extern \"C\" unsigned long SDLmini_flips;\n"
        "#include \"SDL_gfxPrimitives.h\"\n"
        "/* Shortest interval between two full globe redraws, milliseconds.\n"
        " * 1000 = the hard cap the port runs with; lower it once drawShadow is\n"
        " * fixed-point (PROGRESS.md) and the redraw is no longer ~330 ms. */\n"
        "#define AMIGA_GLOBE_MIN_MS 1000\n"
        "#define AMIGA_GLOBE_SUN_MINUTES 3\n"
        "#endif\n",
        "Globe.cpp marker include")))
    results.append(("Geoscape/Globe.cpp (blit markers)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        "void Globe::blit(Surface *surface)\n"
        "{\n"
        "\tSurface::blit(surface);\n",
        "void Globe::blit(Surface *surface)\n"
        "{\n"
        "\tSurface::blit(surface);\n"
        "#ifdef __AMIGA__\n"
        "\t{\n"
        "\t\tstatic int once_;\n"
        "\t\tif (once_ < 3 || (once_ % 100) == 0)\n"
        "\t\t{\n"
        "\t\t\tchar b[256];\n"
        "\t\t\tlong mine = 0, theirs = 0;\n"
        "\t\t\tSDL_Surface *s = getSurface(), *t = surface->getSurface();\n"
        "\t\t\tfor (int y = 0; y < s->h; ++y) { Uint8 *p = (Uint8 *)s->pixels + y * s->pitch; for (int x = 0; x < s->w; ++x) if (p[x]) ++mine; }\n"
        "\t\t\tfor (int y = 0; y < t->h; ++y) { Uint8 *p = (Uint8 *)t->pixels + y * t->pitch; for (int x = 0; x < s->w && x < t->w; ++x) if (p[x]) ++theirs; }\n"
        "\t\t\tsnprintf(b, sizeof b, \"globe: blit #%d visible=%d hidden=%d redraw=%d at %d,%d size %dx%d pitch %d: %ld non-zero px in globe, %ld in screen area; screen %dx%d pitch %d flags %lx\",\n"
        "\t\t\t\tonce_, (int)_visible, (int)_hidden, (int)_redraw, getX(), getY(), s->w, s->h, s->pitch, mine, theirs, t->w, t->h, t->pitch, (unsigned long)s->flags);\n"
        "\t\t\tSDLmini_Log(b);\n"
        "\t\t\t{\n"
        "\t\t\t\tlong hist[256]; int k;\n"
        "\t\t\t\tfor (k = 0; k < 256; ++k) hist[k] = 0;\n"
        "\t\t\t\tfor (int y = 0; y < t->h; ++y) { Uint8 *p = (Uint8 *)t->pixels + y * t->pitch; for (int x = 0; x < s->w && x < t->w; ++x) ++hist[p[x]]; }\n"
        "\t\t\t\tint n = 0;\n"
        "\t\t\t\tn += snprintf(b + n, sizeof b - n, \"globe: screen-area histogram (idx:count rgb):\");\n"
        "\t\t\t\tfor (int r = 0; r < 8; ++r) { int best = 0; for (k = 1; k < 256; ++k) if (hist[k] > hist[best]) best = k; if (hist[best] == 0) break;\n"
        "\t\t\t\t\tSDL_Color c = t->format->palette ? t->format->palette->colors[best] : SDL_Color();\n"
        "\t\t\t\t\tn += snprintf(b + n, sizeof b - n, \" %d:%ld(%d,%d,%d)\", best, hist[best], c.r, c.g, c.b); hist[best] = 0; }\n"
        "\t\t\t\tSDLmini_Log(b);\n"
        "\t\t\t}\n"
        "\t\t\tSDLmini_diag_armed = 3;\n"
        "\t\t\t++once_;\n"
        "\t\t}\n"
        "\t}\n"
        "#endif\n",
        "Globe blit markers")))

    # 5v. State for the two globe throttles below: what _cacheLand was last
    #     projected for. Real members rather than function statics, because a
    #     new game builds a new Globe and a stale "still valid" would leave the
    #     land unprojected.
    results.append(("Geoscape/Globe.h (cache key)", edit(
        os.path.join(src, "Geoscape", "Globe.h"),
        "\tstd::list<Polygon*> _cacheLand;\n",
        "\tstd::list<Polygon*> _cacheLand;\n"
        "#ifdef __AMIGA__\n"
        "\t/* AMIGA-PORT: what _cacheLand was projected for - see Globe::draw(). */\n"
        "\tdouble _cacheLon, _cacheLat, _cacheRadius;\n"
        "\tbool _cacheValid;\n"
        "\t/* AMIGA-PORT: what the ocean/land/shadow surface and the radar layer\n"
        "\t * currently show - see Globe::draw(). */\n"
        "\tbool _baseValid;\n"
        "\tlong _sunKey, _radarKey;\n"
        "#endif\n",
        "Globe cache key members")))

    results.append(("Geoscape/Globe.cpp (cache key init)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        "\t\t_randomNoiseData[i] = rand()%4;\n"
        "\n"
        "\tcachePolygons();\n"
        "}\n",
        "\t\t_randomNoiseData[i] = rand()%4;\n"
        "\n"
        "#ifdef __AMIGA__\n"
        "\t/* AMIGA-PORT: LAZY globe cache. cachePolygons() took 36 s of every\n"
        "\t * load-into-battle on an 040/40 (GeoscapeState is constructed under\n"
        "\t * the battlescape so there is something to return to). draw() runs\n"
        "\t * it on first use via the !_cacheValid branch instead. */\n"
        "\t_cacheValid = false;\n"
        "\t_baseValid = false;\n"
        "\t_sunKey = _radarKey = -1;\n"
        "#else\n"
        "\tcachePolygons();\n"
        "#endif\n"
        "}\n",
        "Globe cache key init")))

    # 5w. Where does a globe redraw go, and does it happen every frame?
    #     `SDLmini_flips` is one per rendered frame, so "10 draws over N frames"
    #     answers the second question outright; the per-phase millisecond sums
    #     answer the first. drawShadow is double-precision maths per pixel and
    #     goes through the ROM IEEE library, so it is the prime suspect.
    results.append(("Geoscape/Globe.cpp (draw timing)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        "void Globe::draw()\n"
        "{\n"
        "\tif (_redraw)\n"
        "\t{\n"
        "\t\tcachePolygons();\n"
        "\t}\n"
        "\tSurface::draw();\n"
        "\tdrawOcean();\n"
        "\tdrawLand();\n"
        "\tdrawRadars();\n"
        "\tdrawShadow();\n"
        "\tdrawMarkers();\n"
        "\tdrawDetail();\n"
        "\tdrawFlights();\n"
        "}\n",
        "void Globe::draw()\n"
        "{\n"
        "#ifdef __AMIGA__\n"
        "\t/* AMIGA-PORT: draw only what changed. Upstream repaints the whole globe\n"
        "\t * (ocean, land, day/night shadow, radars, countries, markers) on every\n"
        "\t * clock tick - 10 times a second at the slowest speed - because on a PC\n"
        "\t * that is free. Here a full repaint is ~150 ms on an 040/40, so the\n"
        "\t * geoscape ran at 3-4 fps with nobody touching anything.\n"
        "\t *   - ocean+land+shadow (this surface): only when the projection changed\n"
        "\t *     (rotate/zoom) or the sun moved far enough to shift the terminator\n"
        "\t *     by about a pixel (AMIGA_GLOBE_SUN_MINUTES of game time), and never\n"
        "\t *     more often than once per AMIGA_GLOBE_MIN_MS;\n"
        "\t *   - radars+flight paths (_radars): with the base, or when the hover\n"
        "\t *     circle / base count / craft count changed;\n"
        "\t *   - countries/cities (_countries): with the base (projection only);\n"
        "\t *   - markers (_markers): every call, they are cheap and things move.\n"
        "\t * Nothing else is touched, so a quiet globe costs the markers only. */\n"
        "\tstatic unsigned long calls_ = 0, lastFlips_ = 0, baseDraws_ = 0, radarDraws_ = 0;\n"
        "\tstatic Uint32 lastTicks_ = 0, lastBase_ = 0, sBase = 0, sCache = 0, sRadar = 0, sMark = 0, sDetail = 0;\n"
        "\tstatic Uint32 sOcean = 0, sLand = 0, sShadow = 0; /* TEMP globe3d split */\n"
        "\t++calls_;\n"
        "\t_redraw = false;\n"
        "\n"
        "\tconst GameTime *gt = _game->getSavedGame()->getTime();\n"
        "\tconst long sunKey = ((((long)gt->getMonth() * 32 + gt->getDay()) * 24 + gt->getHour()) * 60 + gt->getMinute()) / AMIGA_GLOBE_SUN_MINUTES;\n"
        "\tconst bool proj = (!_cacheValid || _cacheLon != _cenLon || _cacheLat != _cenLat || _cacheRadius != _radius);\n"
        "\tlong radarKey = (long)_game->getSavedGame()->getBases()->size() * 100000L;\n"
        "\tif (_hover)\n"
        "\t\tradarKey += 50000L + (long)(_hoverLon * 1000.0) * 7L + (long)(_hoverLat * 1000.0) * 13L;\n"
        "\tfor (std::vector<Base*>::iterator bi = _game->getSavedGame()->getBases()->begin(); bi != _game->getSavedGame()->getBases()->end(); ++bi)\n"
        "\t\tfor (std::vector<Craft*>::iterator ci = (*bi)->getCrafts()->begin(); ci != (*bi)->getCrafts()->end(); ++ci)\n"
        "\t\t{\n"
        "\t\t\tradarKey += 1;\n"
        "\t\t\tif ((*ci)->getStatus() == \"STR_OUT\")\n"
        "\t\t\t\tradarKey += 1000L + sunKey * 17L; /* flight paths and craft radars move: refresh with the sun key */\n"
        "\t\t}\n"
        "\n"
        "\tconst Uint32 now = SDL_GetTicks();\n"
        "\tbool wantBase = (!_baseValid || proj || sunKey != _sunKey);\n"
        "\tif (wantBase && _baseValid && lastBase_ != 0 && (Uint32)(now - lastBase_) < AMIGA_GLOBE_MIN_MS)\n"
        "\t{\n"
        "\t\t/* throttled: keep showing the previous image; the next call retries.\n"
        "\t\t * If the projection moved, the layers on top would not line up with\n"
        "\t\t * the old base, so leave them alone as well. */\n"
        "\t\tif (proj)\n"
        "\t\t\treturn;\n"
        "\t\twantBase = false;\n"
        "\t}\n"
        "\tif (wantBase)\n"
        "\t{\n"
        "\t\tUint32 t0 = SDL_GetTicks();\n"
        "\t\tif (proj)\n"
        "\t\t{\n"
        "\t\t\tcachePolygons();\n"
        "\t\t\t_cacheLon = _cenLon;\n"
        "\t\t\t_cacheLat = _cenLat;\n"
        "\t\t\t_cacheRadius = _radius;\n"
        "\t\t\t_cacheValid = true;\n"
        "\t\t}\n"
        "\t\tUint32 t1 = SDL_GetTicks();\n"
        "\t\tSurface::draw();\n"
        "\t\tdrawOcean();\n"
        "\t\tUint32 t1a = SDL_GetTicks(); sOcean += t1a - t1;\n"
        "\t\tdrawLand();\n"
        "\t\tUint32 t1b = SDL_GetTicks(); sLand += t1b - t1a;\n"
        "\t\tdrawShadow();\n"
        "\t\tUint32 t2 = SDL_GetTicks(); sShadow += t2 - t1b;\n"
        "\t\tdrawDetail();\n"
        "\t\tsCache += t1 - t0; sBase += t2 - t1; sDetail += SDL_GetTicks() - t2;\n"
        "\t\t++baseDraws_;\n"
        "\t\t_baseValid = true;\n"
        "\t\t_sunKey = sunKey;\n"
        "\t\tlastBase_ = now;\n"
        "\t}\n"
        "\tif (wantBase || radarKey != _radarKey)\n"
        "\t{\n"
        "\t\tUint32 t0 = SDL_GetTicks();\n"
        "\t\tdrawRadars();\n"
        "\t\tdrawFlights();\n"
        "\t\tsRadar += SDL_GetTicks() - t0;\n"
        "\t\t++radarDraws_;\n"
        "\t\t_radarKey = radarKey;\n"
        "\t}\n"
        "\t{\n"
        "\t\tUint32 t0 = SDL_GetTicks();\n"
        "\t\tdrawMarkers();\n"
        "\t\tsMark += SDL_GetTicks() - t0;\n"
        "\t}\n"
        "\tif ((calls_ % 10) == 0)\n"
        "\t{\n"
        "\t\tchar b[200];\n"
        "\t\tsnprintf(b, sizeof b, \"globe: 10 calls in %lu ms over %lu frames: base %lu (cache %lu + ocean %lu + land %lu + shadow %lu + detail %lu ms each), radar %lu (%lu ms each), markers %lu ms total\",\n"
        "\t\t\t(unsigned long)(now - lastTicks_), SDLmini_flips - lastFlips_,\n"
        "\t\t\tbaseDraws_, baseDraws_ ? (unsigned long)sCache / baseDraws_ : 0UL, baseDraws_ ? (unsigned long)sOcean / baseDraws_ : 0UL, baseDraws_ ? (unsigned long)sLand / baseDraws_ : 0UL, baseDraws_ ? (unsigned long)sShadow / baseDraws_ : 0UL, baseDraws_ ? (unsigned long)sDetail / baseDraws_ : 0UL,\n"
        "\t\t\tradarDraws_, radarDraws_ ? (unsigned long)sRadar / radarDraws_ : 0UL, (unsigned long)sMark);\n"
        "\t\tSDLmini_Log(b);\n"
        "\t\tlastTicks_ = now; lastFlips_ = SDLmini_flips;\n"
        "\t\tbaseDraws_ = radarDraws_ = 0; sBase = sCache = sRadar = sMark = sDetail = 0;\n"
        "\t\tsOcean = sLand = sShadow = 0;\n"
        "\t}\n"
        "#else\n"
        "\tif (_redraw)\n"
        "\t{\n"
        "\t\tcachePolygons();\n"
        "\t}\n"
        "\tSurface::draw();\n"
        "\tdrawOcean();\n"
        "\tdrawLand();\n"
        "\tdrawRadars();\n"
        "\tdrawShadow();\n"
        "\tdrawMarkers();\n"
        "\tdrawDetail();\n"
        "\tdrawFlights();\n"
        "#endif\n"
        "}\n",
        "Globe draw timing")))

    # 5u. drawShadow in fixed point. Measured without JIT (PROGRESS.md): a globe
    #     redraw was ~330 ms, ~280 of them in drawShadow, whose per-pixel loop
    #     made 26 calls into the ROM IEEE double library. The maths is a squared
    #     distance between two unit vectors, a scale, a clamp and a table
    #     lookup - all integer work in Q1.14:
    #       - `CordFix` (Globe.h): three Sint16 components, 6 bytes per pixel
    #         instead of Cord's 24. _earthFix replaces _earthData for the
    #         shader (256x200 x 6 zoom levels: 7.4 MB of doubles -> 1.8 MB).
    #       - `CreateShadowFix` (Globe.cpp): the same decision tree as
    #         CreateShadow with the double arithmetic replaced. Products of two
    #         Q14 differences are Q28 and up to 2^30 each, so each is dropped to
    #         Q24 before summing (max 3*2^26, fits); the "-2, *125" step is done
    #         in Q16 so *125 cannot overflow; the gradient index uses C division
    #         (truncation toward zero) exactly like the original (Sint16) cast.
    #       - z is stored as at least 1 inside the disc, so a rim pixel whose
    #         real z rounds to 0 is still shaded, not blacked out ("earth.z"
    #         doubles as the inside-the-disc test in func()).
    #     CreateShadow (double) stays for the one call per query in
    #     getPolygonTextureAndShade; getSunDirection stays double - once per
    #     redraw, not per pixel.
    results.append(("Geoscape/Globe.h (CordFix)", edit(
        os.path.join(src, "Geoscape", "Globe.h"),
        "class Globe : public InteractiveSurface\n",
        "#ifdef __AMIGA__\n"
        "/* AMIGA-PORT: a unit vector in Q1.14 - what the day/night shader reads per\n"
        " * pixel. See CreateShadowFix in Globe.cpp. */\n"
        "struct CordFix\n"
        "{\n"
        "\tSint16 x, y, z;\n"
        "};\n"
        "#endif\n"
        "\n"
        "class Globe : public InteractiveSurface\n",
        "CordFix type")))
    results.append(("Geoscape/Globe.h (earthFix member)", edit(
        os.path.join(src, "Geoscape", "Globe.h"),
        "\tstd::vector<std::vector<Cord> > _earthData;\n",
        "\tstd::vector<std::vector<Cord> > _earthData;\n"
        "#ifdef __AMIGA__\n"
        "\t/* AMIGA-PORT: the same normals in Q1.14; _earthData is left empty. */\n"
        "\tstd::vector<std::vector<CordFix> > _earthFix;\n"
        "#endif\n",
        "earthFix member")))
    results.append(("Geoscape/Globe.cpp (CreateShadowFix)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        "\tstatic inline void func(Uint8& dest, const Cord& earth, const Cord& sun, const Sint16& noise, const int&)\n"
        "\t{\n"
        "\t\tif (dest && earth.z)\n"
        "\t\t\tdest = getShadowValue(dest, earth, sun, noise);\n"
        "\t\telse\n"
        "\t\t\tdest = 0;\n"
        "\t}\n"
        "};\n",
        "\tstatic inline void func(Uint8& dest, const Cord& earth, const Cord& sun, const Sint16& noise, const int&)\n"
        "\t{\n"
        "\t\tif (dest && earth.z)\n"
        "\t\t\tdest = getShadowValue(dest, earth, sun, noise);\n"
        "\t\telse\n"
        "\t\t\tdest = 0;\n"
        "\t}\n"
        "};\n"
        "\n"
        "#ifdef __AMIGA__\n"
        "/* AMIGA-PORT: CreateShadow with the arithmetic in Q1.14 integers. Same\n"
        " * decisions, same table, same palette logic; only the double maths is\n"
        " * gone. On a 68020 without FPU every double operation in the original\n"
        " * was a call into the Kickstart IEEE library - 26 of them per pixel. */\n"
        "struct CreateShadowFix\n"
        "{\n"
        "\tstatic inline Uint8 getShadowValue(const Uint8& dest, const CordFix& earth, const CordFix& sun, const Sint16& noise)\n"
        "\t{\n"
        "\t\tconst Sint32 dx = (Sint32)earth.x - sun.x;   /* Q14, |d| <= 2 */\n"
        "\t\tconst Sint32 dy = (Sint32)earth.y - sun.y;\n"
        "\t\tconst Sint32 dz = (Sint32)earth.z - sun.z;\n"
        "\t\t/* squared distance: Q28 products dropped to Q24 before the sum */\n"
        "\t\tconst Sint32 n = ((dx * dx) >> 4) + ((dy * dy) >> 4) + ((dz * dz) >> 4);\n"
        "\t\t/* (n - 2) * 125, kept in Q16 */\n"
        "\t\tconst Sint32 x = ((n - (2L << 24)) >> 8) * 125;\n"
        "\t\tint v;\n"
        "\t\tif (x < -(110L << 16))\n"
        "\t\t\tv = -31;\n"
        "\t\telse if (x > (120L << 16))\n"
        "\t\t\tv = 50;\n"
        "\t\telse\n"
        "\t\t\tv = static_data.shade_gradient[(int)(x / 65536) + 120];\n"
        "\n"
        "\t\tv -= noise;\n"
        "\n"
        "\t\tif (v > 0)\n"
        "\t\t{\n"
        "\t\t\tconst int val = (v > 31) ? 31 : v;\n"
        "\t\t\tconst int d = dest & helper::ColorGroup;\n"
        "\t\t\tif (d == Globe::OCEAN_COLOR || d == Globe::OCEAN_COLOR + 16)\n"
        "\t\t\t{\n"
        "\t\t\t\treturn Globe::OCEAN_COLOR + val;\n"
        "\t\t\t}\n"
        "\t\t\telse\n"
        "\t\t\t{\n"
        "\t\t\t\tif (dest == 0) return val;\n"
        "\t\t\t\tconst int s = val / 3;\n"
        "\t\t\t\tconst int e = dest + s;\n"
        "\t\t\t\tif (e > d + helper::ColorShade)\n"
        "\t\t\t\t\treturn d + helper::ColorShade;\n"
        "\t\t\t\treturn e;\n"
        "\t\t\t}\n"
        "\t\t}\n"
        "\t\telse\n"
        "\t\t{\n"
        "\t\t\tconst int d = dest & helper::ColorGroup;\n"
        "\t\t\tif (d == Globe::OCEAN_COLOR || d == Globe::OCEAN_COLOR + 16)\n"
        "\t\t\t\treturn Globe::OCEAN_COLOR;\n"
        "\t\t\telse\n"
        "\t\t\t\treturn dest;\n"
        "\t\t}\n"
        "\t}\n"
        "\n"
        "\tstatic inline void func(Uint8& dest, const CordFix& earth, const CordFix& sun, const Sint16& noise, const int&)\n"
        "\t{\n"
        "\t\tif (dest && earth.z)\n"
        "\t\t\tdest = getShadowValue(dest, earth, sun, noise);\n"
        "\t\telse\n"
        "\t\t\tdest = 0;\n"
        "\t}\n"
        "};\n"
        "\n"
        "/* AMIGA-PORT: shadow at HALF resolution. The Q1.14 dot product runs\n"
        " * once per 2x2 block - the terminator is a soft noise-dithered\n"
        " * gradient, so sharing it is invisible - while the palette logic\n"
        " * still runs per pixel, keeping land/ocean boundaries and the disc\n"
        " * rim exact. Rim pixels whose block anchor lies outside the disc\n"
        " * compute their own dot product. Was ~110 ms per redraw, per-pixel. */\n"
        "static inline int shadowDotV(const CordFix &e, const CordFix &sun)\n"
        "{\n"
        "\tconst Sint32 dx = (Sint32)e.x - sun.x;\n"
        "\tconst Sint32 dy = (Sint32)e.y - sun.y;\n"
        "\tconst Sint32 dz = (Sint32)e.z - sun.z;\n"
        "\tconst Sint32 n = ((dx * dx) >> 4) + ((dy * dy) >> 4) + ((dz * dz) >> 4);\n"
        "\tconst Sint32 x = ((n - (2L << 24)) >> 8) * 125;\n"
        "\tif (x < -(110L << 16)) return -31;\n"
        "\tif (x > (120L << 16)) return 50;\n"
        "\treturn static_data.shade_gradient[(int)(x / 65536) + 120];\n"
        "}\n"
        "\n"
        "static inline Uint8 shadowApply(Uint8 dest, int v)\n"
        "{\n"
        "\tif (v > 0)\n"
        "\t{\n"
        "\t\tconst int val = (v > 31) ? 31 : v;\n"
        "\t\tconst int d = dest & helper::ColorGroup;\n"
        "\t\tif (d == Globe::OCEAN_COLOR || d == Globe::OCEAN_COLOR + 16)\n"
        "\t\t\treturn (Uint8)(Globe::OCEAN_COLOR + val);\n"
        "\t\tconst int s = val / 3;\n"
        "\t\tconst int e = dest + s;\n"
        "\t\tif (e > d + helper::ColorShade)\n"
        "\t\t\treturn (Uint8)(d + helper::ColorShade);\n"
        "\t\treturn (Uint8)e;\n"
        "\t}\n"
        "\tconst int d = dest & helper::ColorGroup;\n"
        "\tif (d == Globe::OCEAN_COLOR || d == Globe::OCEAN_COLOR + 16)\n"
        "\t\treturn (Uint8)Globe::OCEAN_COLOR;\n"
        "\treturn dest;\n"
        "}\n"
        "\n"
        "static void drawShadowHalfFix(SDL_Surface *ss, const CordFix *ef, int w2, int h2, const CordFix &sun, const Sint16 *noise, int nsz)\n"
        "{\n"
        "\tUint8 *px = (Uint8 *)ss->pixels;\n"
        "\tconst int pitch = ss->pitch;\n"
        "\tfor (int j = 0; j < h2; j += 2)\n"
        "\t{\n"
        "\t\tconst int rows = (j + 1 < h2) ? 2 : 1;\n"
        "\t\tconst Sint16 *nrow0 = noise + (j % nsz) * nsz;\n"
        "\t\tconst Sint16 *nrow1 = noise + ((j + 1) % nsz) * nsz;\n"
        "\t\tint n0 = 0;\n"
        "\t\tfor (int i = 0; i < w2; i += 2)\n"
        "\t\t{\n"
        "\t\t\tconst int cols = (i + 1 < w2) ? 2 : 1;\n"
        "\t\t\tint n1 = n0 + 1; if (n1 >= nsz) n1 = 0;\n"
        "\t\t\tconst CordFix *e0 = &ef[(size_t)j * w2 + i];\n"
        "\t\t\tconst int vb = (e0->z != 0) ? shadowDotV(*e0, sun) : 0x7FFF;\n"
        "\t\t\tfor (int bj = 0; bj < rows; ++bj)\n"
        "\t\t\t{\n"
        "\t\t\t\tUint8 *dp = px + (size_t)(j + bj) * pitch + i;\n"
        "\t\t\t\tconst CordFix *eb = &ef[(size_t)(j + bj) * w2 + i];\n"
        "\t\t\t\tconst Sint16 *nr = bj ? nrow1 : nrow0;\n"
        "\t\t\t\tconst int ni[2] = { n0, n1 };\n"
        "\t\t\t\tfor (int bi = 0; bi < cols; ++bi)\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\tconst Uint8 dest = dp[bi];\n"
        "\t\t\t\t\tif (!dest || eb[bi].z == 0) { dp[bi] = 0; continue; }\n"
        "\t\t\t\t\tint v = (vb != 0x7FFF) ? vb : shadowDotV(eb[bi], sun);\n"
        "\t\t\t\t\tv -= nr[ni[bi]];\n"
        "\t\t\t\t\tdp[bi] = shadowApply(dest, v);\n"
        "\t\t\t\t}\n"
        "\t\t\t}\n"
        "\t\t\tn0 += 2; if (n0 >= nsz) n0 -= nsz;\n"
        "\t\t}\n"
        "\t}\n"
        "}\n"
        "\n"
        "/* double unit vector -> Q1.14, rounded */\n"
        "static inline CordFix cordToFix(const Cord &c)\n"
        "{\n"
        "\tCordFix f;\n"
        "\tf.x = (Sint16)floor(c.x * 16384.0 + 0.5);\n"
        "\tf.y = (Sint16)floor(c.y * 16384.0 + 0.5);\n"
        "\tf.z = (Sint16)floor(c.z * 16384.0 + 0.5);\n"
        "\treturn f;\n"
        "}\n"
        "#endif\n",
        "CreateShadowFix shader")))
    results.append(("Geoscape/Globe.cpp (earthFix fill)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        "\tfor (size_t r = 0; r<_zoomRadius.size(); ++r)\n"
        "\t{\n"
        "\t\t_earthData[r].resize(width * height);\n"
        "\t\tfor (int j=0; j<height; ++j)\n"
        "\t\t\tfor (int i=0; i<width; ++i)\n"
        "\t\t\t{\n"
        "\t\t\t\t_earthData[r][width*j + i] = static_data.circle_norm(width/2, height/2, _zoomRadius[r], i+.5, j+.5);\n"
        "\t\t\t}\n"
        "\t}\n",
        "#ifdef __AMIGA__\n"
        "\t/* AMIGA-PORT: the normals go straight into Q1.14; the double table is\n"
        "\t * never allocated (it would be 7.4 MB). Inside the disc z is kept >= 1\n"
        "\t * so the shader's inside test never loses a rim pixel to rounding. */\n"
        "\t/* LAZY: filling all 6 zoom levels eagerly (307k soft-float sqrt) took\n"
        "\t * 30 s on an 040/40 in the Globe constructor - and loading straight\n"
        "\t * into a battle never shows the globe at all. drawShadow() fills the\n"
        "\t * level it actually uses on first touch. */\n"
        "\t_earthFix.resize(_zoomRadius.size());\n"
        "#else\n"
        "\tfor (size_t r = 0; r<_zoomRadius.size(); ++r)\n"
        "\t{\n"
        "\t\t_earthData[r].resize(width * height);\n"
        "\t\tfor (int j=0; j<height; ++j)\n"
        "\t\t\tfor (int i=0; i<width; ++i)\n"
        "\t\t\t{\n"
        "\t\t\t\t_earthData[r][width*j + i] = static_data.circle_norm(width/2, height/2, _zoomRadius[r], i+.5, j+.5);\n"
        "\t\t\t}\n"
        "\t}\n"
        "#endif\n",
        "earthFix fill")))
    results.append(("Geoscape/Globe.cpp (fixed-point drawShadow)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        "void Globe::drawShadow()\n"
        "{\n"
        "\tShaderMove<Cord> earth = ShaderMove<Cord>(_earthData[_zoom], getWidth(), getHeight());\n"
        "\tShaderRepeat<Sint16> noise = ShaderRepeat<Sint16>(_randomNoiseData, static_data.random_surf_size, static_data.random_surf_size);\n"
        "\n"
        "\tearth.setMove(_cenX-getWidth()/2, _cenY-getHeight()/2);\n"
        "\n"
        "\tlock();\n"
        "\tShaderDraw<CreateShadow>(ShaderSurface(this), earth, ShaderScalar(getSunDirection(_cenLon, _cenLat)), noise);\n"
        "\tunlock();\n",
        "void Globe::drawShadow()\n"
        "{\n"
        "#ifdef __AMIGA__\n"
        "\t/* AMIGA-PORT: fixed-point shader; see CreateShadowFix. */\n"
        "\tif (_earthFix[_zoom].empty())\n"
        "\t{\n"
        "\t\t/* lazy fill; first try data/common/earthfix.dat, precomputed at\n"
        "\t\t * build time (gen_earthfix.py) - computing this table live was\n"
        "\t\t * 307k soft-double sqrts = ~5 s per zoom level on an 040/40. */\n"
        "\t\tconst int w_ = getWidth(), h_ = getHeight();\n"
        "\t\t_earthFix[_zoom].resize(w_ * h_);\n"
        "\t\tbool got_ = false;\n"
        "\t\tif (sizeof(CordFix) == 6)\n"
        "\t\t{\n"
        "\t\t\tFILE *ef_ = fopen(\"PROGDIR:data/common/earthfix.dat\", \"rb\");\n"
        "\t\t\tif (ef_)\n"
        "\t\t\t{\n"
        "\t\t\t\tunsigned char hd_[10];\n"
        "\t\t\t\tif (fread(hd_, 1, 10, ef_) == 10 && hd_[0]==69 && hd_[1]==70 && hd_[2]==88 && hd_[3]==49)\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\tconst int fw_ = (hd_[4]<<8)|hd_[5], fh_ = (hd_[6]<<8)|hd_[7], fl_ = (hd_[8]<<8)|hd_[9];\n"
        "\t\t\t\t\tif (fw_ == w_ && fh_ == h_ && (int)_zoom < fl_)\n"
        "\t\t\t\t\t{\n"
        "\t\t\t\t\t\tunsigned char rr_[4];\n"
        "\t\t\t\t\t\tfseek(ef_, 10 + 4 * (long)_zoom, SEEK_SET);\n"
        "\t\t\t\t\t\tif (fread(rr_, 1, 4, ef_) == 4)\n"
        "\t\t\t\t\t\t{\n"
        "\t\t\t\t\t\t\tconst unsigned long fr_ = ((unsigned long)rr_[0]<<24)|((unsigned long)rr_[1]<<16)|((unsigned long)rr_[2]<<8)|rr_[3];\n"
        "\t\t\t\t\t\t\tif (fr_ == (unsigned long)(_zoomRadius[_zoom] * 256.0 + 0.5))\n"
        "\t\t\t\t\t\t\t{\n"
        "\t\t\t\t\t\t\t\tfseek(ef_, 10 + 4L * fl_ + 6L * w_ * h_ * (long)_zoom, SEEK_SET);\n"
        "\t\t\t\t\t\t\t\tgot_ = fread(&_earthFix[_zoom][0], 6, (size_t)(w_ * h_), ef_) == (size_t)(w_ * h_);\n"
        "\t\t\t\t\t\t\t}\n"
        "\t\t\t\t\t\t}\n"
        "\t\t\t\t\t}\n"
        "\t\t\t\t}\n"
        "\t\t\t\tfclose(ef_);\n"
        "\t\t\t}\n"
        "\t\t}\n"
        "\t\tif (!got_)\n"
        "\t\tfor (int j=0; j<h_; ++j)\n"
        "\t\t\tfor (int i=0; i<w_; ++i)\n"
        "\t\t\t{\n"
        "\t\t\t\tCord c = static_data.circle_norm(w_/2, h_/2, _zoomRadius[_zoom], i+.5, j+.5);\n"
        "\t\t\t\tCordFix f = cordToFix(c);\n"
        "\t\t\t\tif (c.z != 0. && f.z == 0) f.z = 1;\n"
        "\t\t\t\t_earthFix[_zoom][w_*j + i] = f;\n"
        "\t\t\t}\n"
        "\t}\n"
        "\tShaderMove<CordFix> earth = ShaderMove<CordFix>(_earthFix[_zoom], getWidth(), getHeight());\n"
        "\tShaderRepeat<Sint16> noise = ShaderRepeat<Sint16>(_randomNoiseData, static_data.random_surf_size, static_data.random_surf_size);\n"
        "\n"
        "\tearth.setMove(_cenX-getWidth()/2, _cenY-getHeight()/2);\n"
        "\n"
        "\tCordFix sun = cordToFix(getSunDirection(_cenLon, _cenLat));\n"
        "\tlock();\n"
        "\tif (_cenX == getWidth() / 2 && _cenY == getHeight() / 2)\n"
        "\t\tdrawShadowHalfFix(getSurface(), &_earthFix[_zoom][0], getWidth(), getHeight(), sun, &_randomNoiseData[0], static_data.random_surf_size);\n"
        "\telse\n"
        "\t\tShaderDraw<CreateShadowFix>(ShaderSurface(this), earth, ShaderScalar(sun), noise);\n"
        "\tunlock();\n"
        "#else\n"
        "\tShaderMove<Cord> earth = ShaderMove<Cord>(_earthData[_zoom], getWidth(), getHeight());\n"
        "\tShaderRepeat<Sint16> noise = ShaderRepeat<Sint16>(_randomNoiseData, static_data.random_surf_size, static_data.random_surf_size);\n"
        "\n"
        "\tearth.setMove(_cenX-getWidth()/2, _cenY-getHeight()/2);\n"
        "\n"
        "\tlock();\n"
        "\tShaderDraw<CreateShadow>(ShaderSurface(this), earth, ShaderScalar(getSunDirection(_cenLon, _cenLat)), noise);\n"
        "\tunlock();\n"
        "#endif\n",
        "fixed-point drawShadow")))

    # 6. File streams. bebbo's libstdc++ hangs forever in
    #    std::ifstream::close() on a file that exists (see native/amiga_fstream.h
    #    for the proof), and every destructor calls close(). Every use in the
    #    game is switched to the stdio-backed replacements, which behave the
    #    same way from the caller's point of view.
    swapped = []
    for root, _dirs, files in os.walk(src):
        for fn in files:
            if not fn.endswith((".cpp", ".h")):
                continue
            path = os.path.join(root, fn)
            with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
                text = f.read()
            if "std::ifstream" not in text and "std::ofstream" not in text:
                continue
            text = text.replace("std::ifstream", "OpenXcom::AmigaIFStream")
            text = text.replace("std::ofstream", "OpenXcom::AmigaOFStream")
            if '#include "amiga_fstream.h"' not in text:
                # after the first #include in the file, so it lands past the
                # licence header and any #pragma once
                idx = text.find("#include")
                end = text.find("\n", idx)
                text = text[:end + 1] + '#include "amiga_fstream.h"\n' + text[end + 1:]
            with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
                f.write(text)
            swapped.append(os.path.relpath(path, src))
    results.append(("file streams", "%d files" % len(swapped) if swapped else "already"))

    for name, state in results:
        print("  %-24s %s" % (name, state))


if __name__ == "__main__":
    main()
