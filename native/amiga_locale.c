/*
 * AMIGA-PORT: which language does this Workbench prefer?
 *
 * locale.library knows: Prefs/Locale sets a list of preferred languages and a
 * country, and every well-behaved Amiga program reads it. This port had a
 * painful introduction to that setting from the other side - a comma-decimal
 * country broke every ruleset it loaded (see PROGRESS, 0.9.1/0.9.3) - so it is
 * a small pleasure to use it for something good.
 *
 * The names locale.library hands back are the catalog names: "english",
 * "deutsch", "français", "polski". They are matched on an ASCII prefix, which
 * sidesteps both the accents and the encoding they arrive in. When nothing
 * matches, the answer is NULL and the port leaves the player's own setting
 * alone.
 */
#include <exec/types.h>
#include <libraries/locale.h>
#include <proto/exec.h>
#include <proto/locale.h>
#include <string.h>

#include "amiga_locale.h"

/* Prefix -> OpenXcom language file. Only languages this port actually ships
 * are listed (build/fetch_translations.py decides that set); anything else
 * would name a file that is not there. Prefixes are lower case and matched
 * case-insensitively against the start of the locale name. */
static const struct { const char *prefix; const char *code; } s_map[] = {
	{ "engl", "en-US" },
	{ "deut", "de"    }, { "germ", "de"    },
	{ "fran", "fr"    }, { "fren", "fr"    },
	{ "ital", "it"    },
	{ "espa", "es-ES" }, { "span", "es-ES" },
	{ "cata", "ca-ES" },
	{ "port", "pt-PT" }, { "bras", "pt-BR" }, { "braz", "pt-BR" },
	{ "nede", "nl"    }, { "dutc", "nl"    },
	{ "pols", "pl"    }, { "poli", "pl"    },
	{ "russ", "ru"    },
	{ "ukra", "uk"    },
	{ "cesk", "cs"    }, { "czec", "cs"    },
	{ "slovak",  "sk" }, { "slovensky", "sk" },
	{ "magy", "hu"    }, { "hung", "hu"    },
	{ "roma", "ro"    }, { "ruma", "ro"    }, { "rum", "ro" },
	{ "bulg", "bg"    },
	{ "gree", "el"    }, { "ellh", "el"    },
	{ "turk", "tr"    },
	{ "sven", "sv"    }, { "swed", "sv"    },
	{ "nors", "no"    }, { "norw", "no"    },
	{ "dans", "da"    }, { "dani", "da"    },
	{ "suom", "fi"    }, { "finn", "fi"    },
	{ "eest", "et"    }, { "esto", "et"    },
	{ "isle", "is"    }, { "icel", "is"    },
	{ "letz", "lb"    }, { "luxe", "lb"    },
};

static int prefix_match(const char *name, const char *prefix)
{
	int i;
	for (i = 0; prefix[i] != '\0'; i++) {
		unsigned char a = (unsigned char)name[i];
		unsigned char b = (unsigned char)prefix[i];
		if (a >= 'A' && a <= 'Z') a = (unsigned char)(a - 'A' + 'a');
		if (a != b) return 0;
	}
	return 1;
}

/* Second guess: the country, when the language list said nothing we know.
 * loc_CountryCode is the ISO-3166 three-letter code packed into a ULONG. */
static const struct { const char *cc; const char *code; } s_country[] = {
	{ "POL", "pl"    }, { "DEU", "de"    }, { "AUT", "de"    },
	{ "FRA", "fr"    }, { "BEL", "fr"    }, { "ITA", "it"    },
	{ "ESP", "es-ES" }, { "MEX", "es-419"}, { "ARG", "es-419"},
	{ "PRT", "pt-PT" }, { "BRA", "pt-BR" }, { "NLD", "nl"    },
	{ "RUS", "ru"    }, { "UKR", "uk"    }, { "CZE", "cs"    },
	{ "SVK", "sk"    }, { "HUN", "hu"    }, { "ROU", "ro"    },
	{ "BGR", "bg"    }, { "GRC", "el"    }, { "TUR", "tr"    },
	{ "SWE", "sv"    }, { "NOR", "no"    }, { "DNK", "da"    },
	{ "FIN", "fi"    }, { "EST", "et"    }, { "ISL", "is"    },
	{ "LUX", "lb"    },
};

static const char *country_lang(const char *cc)
{
	unsigned int i;
	if (cc == NULL || cc[0] == '\0') return NULL;
	for (i = 0; i < sizeof(s_country) / sizeof(s_country[0]); i++) {
		if (strncmp(cc, s_country[i].cc, 3) == 0) return s_country[i].code;
	}
	return NULL;
}

static const char *lookup(const char *name)
{
	unsigned int i;
	if (name == NULL || name[0] == '\0') return NULL;
	for (i = 0; i < sizeof(s_map) / sizeof(s_map[0]); i++) {
		if (prefix_match(name, s_map[i].prefix)) return s_map[i].code;
	}
	return NULL;
}

const char *AmigaLocale_Language(char *rawname, int rawlen)
{
	struct Library *base;
	struct Locale *loc;
	const char *code = NULL;

	if (rawname != NULL && rawlen > 0) rawname[0] = '\0';

	/* v38 is 2.1; older Workbenches simply have no locale.library and the
	 * player's own setting stands. */
	base = OpenLibrary("locale.library", 38);
	if (base == NULL) return NULL;

	{
		struct Library *LocaleBase = base;
		loc = OpenLocale(NULL);
		if (loc != NULL) {
			int i;
			/* The preferred-languages list is in order; take the first one
			 * this port can actually show. */
			for (i = 0; i < 10 && code == NULL; i++) {
				const char *n = (const char *)loc->loc_PrefLanguages[i];
				if (n == NULL || n[0] == '\0') break;
				code = lookup(n);
				if (rawname != NULL && rawlen > 0 && i == 0) {
					strncpy(rawname, n, (size_t)(rawlen - 1));
					rawname[rawlen - 1] = '\0';
				}
			}
			/* Nothing recognised? The country is a decent second guess.
			 * loc_CountryCode is four packed characters ('POL\0'), not a
			 * string, so unpack it first. */
			if (code == NULL) {
				char cc[5];
				ULONG v = loc->loc_CountryCode;
				cc[0] = (char)((v >> 24) & 0xFF);
				cc[1] = (char)((v >> 16) & 0xFF);
				cc[2] = (char)((v >> 8) & 0xFF);
				cc[3] = (char)(v & 0xFF);
				cc[4] = '\0';
				code = country_lang(cc);
			}
			CloseLocale(loc);
		}
	}

	CloseLibrary(base);
	return code;
}
