/*
 * AMIGA-PORT: fast YAML writer for the save path.
 *
 * WHY: YAML::Emitter costs ~2.5 ms per scalar on the 68020 (regex-ish string
 * analysis, EmitterState push/pop, stringstream machinery) - 25 s of the 45 s
 * battle save. The Node tree is already built; all the emitter really has to
 * do is walk it and print. This does exactly that: block style, 2-space
 * indent, insertion order preserved, quoting rules conservative enough that
 * yaml-cpp's parser reads back the identical scalars.
 *
 * Not handled (never appears in OpenXcom saves): anchors/aliases, cyclic
 * graphs, non-scalar map keys, multi-document beyond what the callers
 * concatenate themselves.
 */
#ifndef AMIGA_YAMLOUT_H
#define AMIGA_YAMLOUT_H

#include <string>
#include <yaml-cpp/yaml.h>

namespace OpenXcom {

/* A scalar may be written unquoted if it is short, non-empty and contains
 * only characters that can never change meaning in block context. "-" alone
 * could open a sequence entry, so a lone "-" is quoted. */
inline bool AmigaYamlPlain(const std::string &s)
{
	if (s.empty() || s.size() > 80) return false;
	if (s.size() == 1 && (s[0] == '-' || s[0] == '~' || s[0] == '?')) return false;
	for (std::string::size_type i = 0; i < s.size(); ++i) {
		const char c = s[i];
		if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
		      (c >= '0' && c <= '9') ||
		      c == '_' || c == '.' || c == '-' || c == '+'))
			return false;
	}
	return true;
}

inline void AmigaYamlScalar(std::string &out, const std::string &s)
{
	if (AmigaYamlPlain(s)) { out += s; return; }
	bool ctrl = false;
	for (std::string::size_type i = 0; i < s.size(); ++i)
		if ((unsigned char)s[i] < 0x20) { ctrl = true; break; }
	if (!ctrl) {
		/* single quotes: only ' needs doubling; UTF-8 bytes pass through */
		out += '\'';
		for (std::string::size_type i = 0; i < s.size(); ++i) {
			if (s[i] == '\'') out += "''";
			else out += s[i];
		}
		out += '\'';
	} else {
		/* control characters: double quotes with escapes */
		static const char hex[] = "0123456789abcdef";
		out += '"';
		for (std::string::size_type i = 0; i < s.size(); ++i) {
			const unsigned char c = (unsigned char)s[i];
			if (c == '"')  { out += "\\\""; }
			else if (c == '\\') { out += "\\\\"; }
			else if (c == '\n') { out += "\\n"; }
			else if (c == '\t') { out += "\\t"; }
			else if (c < 0x20) { out += "\\x"; out += hex[c >> 4]; out += hex[c & 15]; }
			else out += (char)c;
		}
		out += '"';
	}
}

/* Writes the VALUE of a key or sequence entry. The cursor stands right after
 * "key:" or "-"; nested block lines are indented by `ind` spaces. */
inline void AmigaYamlValue(std::string &out, const YAML::Node &n, int ind)
{
	switch (n.Type()) {
	case YAML::NodeType::Scalar:
		out += ' ';
		AmigaYamlScalar(out, n.Scalar());
		out += '\n';
		return;
	case YAML::NodeType::Sequence: {
		if (n.size() == 0) { out += " []\n"; return; }
		out += '\n';
		for (YAML::const_iterator it = n.begin(); it != n.end(); ++it) {
			out.append((std::string::size_type)ind, ' ');
			out += '-';
			AmigaYamlValue(out, *it, ind + 2);
		}
		return;
	}
	case YAML::NodeType::Map: {
		if (n.size() == 0) { out += " {}\n"; return; }
		out += '\n';
		for (YAML::const_iterator it = n.begin(); it != n.end(); ++it) {
			if (!it->first.IsScalar()) continue;   /* never happens in saves */
			out.append((std::string::size_type)ind, ' ');
			AmigaYamlScalar(out, it->first.Scalar());
			out += ':';
			AmigaYamlValue(out, it->second, ind + 2);
		}
		return;
	}
	case YAML::NodeType::Null:
	case YAML::NodeType::Undefined:
	default:
		out += " ~\n";
		return;
	}
}

/* Top-level document: a map's keys start at column 0. */
inline void AmigaYamlWrite(std::string &out, const YAML::Node &doc)
{
	if (doc.IsMap() && doc.size() > 0) {
		for (YAML::const_iterator it = doc.begin(); it != doc.end(); ++it) {
			if (!it->first.IsScalar()) continue;
			AmigaYamlScalar(out, it->first.Scalar());
			out += ':';
			AmigaYamlValue(out, it->second, 2);
		}
	} else {
		AmigaYamlValue(out, doc, 0);
		/* AmigaYamlValue starts with ' ' or '\n'; a lone leading blank is
		 * harmless to the parser, so keep it simple. */
	}
}

/* ---- helpers for hand-written fast save paths (battlescape) -------------
 * These skip YAML::Node entirely: the caller appends "key: value" lines to a
 * std::string. Number conversion reuses YAML::conversion::amiga_to_string
 * (defined by the port's convert.h patch). Output stays plain YAML that the
 * unchanged loader reads. */

inline void ay_key(std::string &o, int ind, const char *k)
{
	o.append((std::string::size_type)ind, ' ');
	o += k;
	o += ':';
}
inline void ay_i(std::string &o, int ind, const char *k, long long v)
{
	ay_key(o, ind, k);
	o += ' ';
	o += YAML::conversion::amiga_to_string(v);
	o += '\n';
}
inline void ay_u(std::string &o, int ind, const char *k, unsigned long long v)
{
	ay_key(o, ind, k);
	o += ' ';
	o += YAML::conversion::amiga_to_string(v);
	o += '\n';
}
inline void ay_d(std::string &o, int ind, const char *k, double v)
{
	ay_key(o, ind, k);
	o += ' ';
	o += YAML::conversion::amiga_to_string(v);
	o += '\n';
}
inline void ay_b(std::string &o, int ind, const char *k, bool v)
{
	ay_key(o, ind, k);
	o += v ? " true\n" : " false\n";
}
inline void ay_s(std::string &o, int ind, const char *k, const std::string &v)
{
	ay_key(o, ind, k);
	o += ' ';
	AmigaYamlScalar(o, v);
	o += '\n';
}
/* value appended verbatim - caller guarantees it is yaml-safe (base64 etc.) */
inline void ay_raw(std::string &o, int ind, const char *k, const std::string &v)
{
	ay_key(o, ind, k);
	o += ' ';
	o += v;
	o += '\n';
}
inline void ay_xyz(std::string &o, int ind, const char *k, int x, int y, int z)
{
	ay_key(o, ind, k);
	o += " [";
	o += YAML::conversion::amiga_to_string((long long)x);
	o += ", ";
	o += YAML::conversion::amiga_to_string((long long)y);
	o += ", ";
	o += YAML::conversion::amiga_to_string((long long)z);
	o += "]\n";
}
/* flow list of ints: "k: [a, b, c]" (or "k: []") */
inline void ay_iv(std::string &o, int ind, const char *k, const int *v, size_t n)
{
	ay_key(o, ind, k);
	o += " [";
	for (size_t i = 0; i < n; ++i) {
		if (i) o += ", ";
		o += YAML::conversion::amiga_to_string((long long)v[i]);
	}
	o += "]\n";
}
/* sequence-of-maps entry opener: writes "  - " and returns; the caller emits
 * the FIRST key with ind 0 semantics by passing ind = -1 markers is clumsy,
 * so instead: open the entry and write the first key/value inline. */
inline void ay_entry_i(std::string &o, int ind, const char *k, long long v)
{
	o.append((std::string::size_type)ind, ' ');
	o += "- ";
	o += k;
	o += ": ";
	o += YAML::conversion::amiga_to_string(v);
	o += '\n';
}

}  // namespace OpenXcom

#endif
