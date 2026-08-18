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


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit(__doc__)
    src = sys.argv[1]
    if len(sys.argv) == 3:
        print("  %-24s %s" % ("yaml-cpp LoadFile", patch_yamlcpp(sys.argv[2])))
        print("  %-24s %s" % ("yaml-cpp fast convert", patch_yamlcpp_convert(sys.argv[2])))
        print("  %-24s %s" % ("yaml-cpp pool merge", patch_yamlcpp_memory(sys.argv[2])))
        print("  %-24s %s" % ("yaml-cpp ICE dodge", patch_yamlcpp_ice(sys.argv[2])))
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
        '#define OPENXCOM_VERSION_SHORT "0.5.6"\n'
        '#define OPENXCOM_VERSION_LONG "0.5.6.0"\n'
        '#define OPENXCOM_VERSION_NUMBER 0,5,6,0\n'
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
        "\t\tdrawTerrain(this);\n"
        "\t\tsum_ += SDL_GetTicks() - t0_;\n"
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
        "\tif (dy0 + ch > ds_->h) ch = ds_->h - dy0;\n"
        "\tif (cw <= 0 || ch <= 0) return;\n"
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
        "\t\tfor (yy = 0; yy < ch; ++yy)\n"
        "\t\t{\n"
        "\t\t\tconst Uint8 *s2 = sp; Uint8 *d2 = dp; int n = cw;\n"
        "\t\t\twhile (n-- > 0)\n"
        "\t\t\t{\n"
        "\t\t\t\tUint8 c = *s2++;\n"
        "\t\t\t\tif (c) { int ns = (c & 15) + off; *d2 = (ns > 15) ? 15 : (Uint8)((c & 0xF0) | ns); }\n"
        "\t\t\t\t++d2;\n"
        "\t\t\t}\n"
        "\t\t\tsp += ss_->pitch; dp += ds_->pitch;\n"
        "\t\t}\n"
        "\t}\n"
        "\t}\n"
        "}\n",
        "fast blitNShade")))

    # 6b. Battle animation tick from an option (default 200 ms on this port -
    #     upstream's 100 ms demanded a full map render 10x per second).
    results.append(("Options (amigaAnimMs)", edit(
        os.path.join(src, "Engine", "Options.inc.h"),
        "OPT int amigaAccurateFov; /* 0 fast, 1 accurate, 2 test */\n",
        "OPT int amigaAccurateFov; /* 0 fast, 1 accurate, 2 test */\n"
        "OPT int amigaAnimMs;     /* battle animation tick, ms */\n"
        "OPT int amigaFlatGlobe;  /* 1 = flat sun-shaded land polygons */\n",
        "amigaAnimMs var")))
    results.append(("Options.cpp (amigaAnimMs)", edit(
        os.path.join(src, "Engine", "Options.cpp"),
        "\t_info.push_back(OptionInfo(\"amigaAccurateFov\", &amigaAccurateFov, 1)); /* default: Accurate - same speed since the pair-update */\n",
        "\t_info.push_back(OptionInfo(\"amigaAccurateFov\", &amigaAccurateFov, 1)); /* default: Accurate - same speed since the pair-update */\n"
        "\t_info.push_back(OptionInfo(\"amigaAnimMs\", &amigaAnimMs, 200));\n"
        "\t_info.push_back(OptionInfo(\"amigaFlatGlobe\", &amigaFlatGlobe, 1)); /* test: default on; 0 = textured land */\n",
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
        "\t\tAmigaSplash_Progress(2 + (int)((68L * AmigaSplashDone_) / AmigaSplashTotal_));\n"
        "#endif\n"
        "\t}\n",
        "splash tick")))
    results.append(("Mod.cpp (splash fonts mark)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        '\tLog(LOG_INFO) << "Loading fonts... " << _fontName;\n',
        '\tLog(LOG_INFO) << "Loading fonts... " << _fontName;\n'
        '#ifdef __AMIGA__\n'
        '\tAmigaSplash_Progress(71);\n'
        '#endif\n',
        "splash fonts mark")))
    results.append(("StartState.cpp (splash decls)", edit(
        os.path.join(src, "Menu", "StartState.cpp"),
        '#include "StartState.h"\n',
        '#include "StartState.h"\n'
        '#ifdef __AMIGA__\n'
        'extern "C" void AmigaSplash_Progress(int percent);\n'
        'extern "C" void SDLmini_SplashFinish(void);\n'
        '#endif\n',
        "start splash decls")))
    results.append(("StartState.cpp (splash lang mark)", edit(
        os.path.join(src, "Menu", "StartState.cpp"),
        '\t\tLog(LOG_INFO) << "Loading language...";\n',
        '#ifdef __AMIGA__\n'
        '\t\tAmigaSplash_Progress(88);\n'
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
        "\t\tAmigaSplash_Progress(72 + (int)((8L * AmigaSplashDone_) / AmigaSplashTotal_));\n"
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
        "\t\tAmigaSplash_Progress(80 + (int)((6L * AmigaSplashDone_) / AmigaSplashTotal_));\n"
        "#endif\n"
        "\t\tstd::string setName = i->first;\n",
        "splash sounds ticks")))
    results.append(("StartState.cpp (splash data mark)", edit(
        os.path.join(src, "Menu", "StartState.cpp"),
        '\t\tLog(LOG_INFO) << "Data loaded successfully.";\n',
        '#ifdef __AMIGA__\n'
        '\t\tAmigaSplash_Progress(87);\n'
        '#endif\n'
        '\t\tLog(LOG_INFO) << "Data loaded successfully.";\n',
        "splash data mark")))
    results.append(("StartState.cpp (splash lang done)", edit(
        os.path.join(src, "Menu", "StartState.cpp"),
        "\t\tgame->defaultLanguage();\n",
        "\t\tgame->defaultLanguage();\n"
        "#ifdef __AMIGA__\n"
        "\t\tAmigaSplash_Progress(98);\n"
        "#endif\n",
        "splash lang done")))

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
