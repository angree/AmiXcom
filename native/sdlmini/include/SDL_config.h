/*
 * SDL_config.h for SDLmini - the AmigaOS 68k SDL 1.2 API shim used by the
 * Amiga OpenXcom port.
 *
 * SDLmini is NOT SDL. It reuses SDL 1.2.15's public headers verbatim, so that
 * every struct layout and enum value OpenXcom compiles against is exactly the
 * one it expects, and then implements the small subset of the API OpenXcom
 * actually calls on top of amiga_gfx.c / amiga_audio.c (the native AmigaOS
 * display and Paula audio layer taken from the openttd_amiga_68k port).
 *
 * The real SDL 1.2 for 68k was tried first and abandoned - see
 * PORT_RESEARCH.md; its CyberGraphX path hangs in LockBitMapTags on this
 * toolchain, and it brings a display stack we would have to fight rather than
 * use.
 *
 * bebbo's m68k-amigaos GCC 6.5 ships a complete libnix C library, so the libc
 * side of the config is simply "yes to everything we use".
 */
#ifndef _SDL_config_h
#define _SDL_config_h

#include "SDL_platform.h"

/* Fixed-size types: bebbo provides <stdint.h>, so let SDL use it. */
#define HAVE_STDINT_H   1
#define HAVE_STDIO_H    1
#define HAVE_STDLIB_H   1
#define HAVE_STDARG_H   1
#define HAVE_STRING_H   1
#define HAVE_CTYPE_H    1
#define HAVE_MATH_H     1
#define HAVE_INTTYPES_H 1
#define HAVE_LIMITS_H   1
#define HAVE_SIGNAL_H   1

#define SIZEOF_VOIDP 4
#define SDL_HAS_64BIT_TYPE 1

/* Use the C library rather than SDL's private reimplementations. */
#define HAVE_LIBC 1
#define HAVE_MALLOC 1
#define HAVE_CALLOC 1
#define HAVE_REALLOC 1
#define HAVE_FREE 1
#define HAVE_ALLOCA 1
#define HAVE_GETENV 1
#define HAVE_PUTENV 1
#define HAVE_QSORT 1
#define HAVE_ABS 1
#define HAVE_BCOPY 1
#define HAVE_MEMSET 1
#define HAVE_MEMCPY 1
#define HAVE_MEMMOVE 1
#define HAVE_MEMCMP 1
#define HAVE_STRLEN 1
#define HAVE_STRCPY 1
#define HAVE_STRNCPY 1
#define HAVE_STRCAT 1
#define HAVE_STRNCAT 1
#define HAVE_STRDUP 1
#define HAVE_STRCHR 1
#define HAVE_STRRCHR 1
#define HAVE_STRSTR 1
#define HAVE_STRTOL 1
#define HAVE_STRTOUL 1
#define HAVE_STRTOD 1
#define HAVE_ATOI 1
#define HAVE_ATOF 1
#define HAVE_STRCMP 1
#define HAVE_STRNCMP 1
#define HAVE_SSCANF 1
#define HAVE_SNPRINTF 1
#define HAVE_VSNPRINTF 1

/* Subsystems. Everything we do not implement is compiled out of the headers'
 * point of view as well, so a stray call is a link error rather than a
 * silently missing feature at runtime. */
#define SDL_AUDIO_DRIVER_DISK   0
#define SDL_AUDIO_DRIVER_DUMMY  0
#define SDL_CDROM_DISABLED      1
#define SDL_JOYSTICK_DISABLED   1
#define SDL_LOADSO_DISABLED     1
#define SDL_THREADS_DISABLED    1
#define SDL_TIMERS_DISABLED     0
#define SDL_VIDEO_DRIVER_DUMMY  0

/* No OpenGL on a 68020, by design. */
#define SDL_VIDEO_OPENGL 0

#endif /* _SDL_config_h */
