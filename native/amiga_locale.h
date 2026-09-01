/*
 * AMIGA-PORT: the Workbench's preferred language, as an OpenXcom language code.
 */
#ifndef AMIGA_LOCALE_H
#define AMIGA_LOCALE_H

#ifdef __cplusplus
extern "C" {
#endif

/* Returns "pl", "de", "fr"... for the first preferred language this port
 * ships a translation for, or NULL when locale.library is absent or says
 * nothing we recognise - in which case the player's own setting stands.
 * If rawname is given it receives the raw locale name ("polski"), which is
 * worth logging: it is the only way to find out why a machine was not
 * recognised. */
const char *AmigaLocale_Language(char *rawname, int rawlen);

#ifdef __cplusplus
}
#endif

#endif
